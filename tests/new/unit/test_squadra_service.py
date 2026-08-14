"""Unit test di ``SquadraService`` (US-2, US-3, US-8, US-9, US-11).

Le regole verificate qui vivono nel servizio e non nella schermata, perché
una schermata non è un vincolo: la finestra di modifica che si chiude al
sorteggio, chi può scrivere cosa, e il fatto che l'elenco appartenga al
campionato quando la gara ne fa parte.
"""

from datetime import date, timedelta

import pytest

from models import Campionato, Gara, Inscription, Squadra, User
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.squadra.service import SquadraService
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _user(db_session, suffix, role=UserRole.PLAYER.value, squadra=None):
    user = User(
        username=f"u_{suffix}",
        email=f"u_{suffix}@example.com",
        role=role,
        squadra=squadra,
    )
    user.set_password("pw")
    db_session.add(user)
    db_session.flush()
    return user


def _gara(db_session, suffix, *, campionato=None, director=None, **kwargs):
    gara = Gara(
        campionato_id=campionato.id if campionato else None,
        director_id=None if campionato else (director.id if director else None),
        number=1,
        name=f"Gara {suffix}",
        date=date.today() + timedelta(days=7),
        discipline="palla_8",
        distance=5,
        rounds_count=3,
        matchmaking_strategy="direct_elimination",
        **{"separate_teammates": True, **kwargs},
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _inscription(db_session, gara, user):
    inscription = Inscription(gara_id=gara.id, user_id=user.id)
    db_session.add(inscription)
    db_session.flush()
    return inscription


class FakeActor:
    """Un attore con permessi dichiarati, per non tirarsi dietro l'ABAC."""

    is_authenticated = True

    def __init__(self, user_id, manages=True):
        self.id = user_id
        self._manages = manages

    def can_manage_competition(self, gara_id):
        return self._manages


class TestProprietarioDellElenco:
    def test_gara_in_campionato_usa_l_elenco_del_campionato(self, db_session):
        camp = Campionato(name="Camp elenco")
        db_session.add(camp)
        db_session.flush()
        prima = _gara(db_session, "una", campionato=camp)
        seconda = _gara(db_session, "due", campionato=camp)

        SquadraService.create(prima, "Circolo Nord")

        # US-2: alla seconda gara l'elenco è già popolato.
        assert [s.name for s in SquadraService.list_for_gara(seconda)] == [
            "Circolo Nord"
        ]

    def test_gara_standalone_ha_un_elenco_suo(self, db_session):
        director = _user(db_session, "dir_sa", UserRole.DIRECTOR.value)
        una = _gara(db_session, "sa1", director=director)
        altra = _gara(db_session, "sa2", director=director)

        SquadraService.create(una, "Circolo Sud")

        assert SquadraService.list_for_gara(una)
        assert SquadraService.list_for_gara(altra) == []


class TestElenco:
    def test_doppione_rifiutato_a_meno_di_maiuscole(self, db_session):
        gara = _gara(db_session, "dup")
        SquadraService.create(gara, "Circolo X")
        with pytest.raises(ConflictError):
            SquadraService.create(gara, "  circolo   x ")

    def test_nome_vuoto_rifiutato(self, db_session):
        gara = _gara(db_session, "vuoto")
        with pytest.raises(ValidationError):
            SquadraService.create(gara, "   ")

    def test_nomi_simili_prima_di_creare(self, db_session):
        """US-2: il doppione si fa notare prima di nascere, non dopo."""
        gara = _gara(db_session, "simili")
        SquadraService.create(gara, "Circolo Nord")
        SquadraService.create(gara, "Biliardo Sud")

        simili = SquadraService.similar_names(gara, "circolo")
        assert [s.name for s in simili] == ["Circolo Nord"]

    def test_rinomina(self, db_session):
        gara = _gara(db_session, "ren")
        squadra = SquadraService.create(gara, "Vechio Nome")
        SquadraService.rename(gara, squadra.id, "Vecchio Nome", FakeActor(1))
        assert squadra.name == "Vecchio Nome"
        assert squadra.normalized_name == "vecchio nome"

    def test_rinomina_su_un_nome_gia_in_elenco_rifiutata(self, db_session):
        gara = _gara(db_session, "ren2")
        SquadraService.create(gara, "Alfa")
        beta = SquadraService.create(gara, "Beta")
        with pytest.raises(ConflictError):
            SquadraService.rename(gara, beta.id, "alfa", FakeActor(1))

    def test_unione_riassegna_le_iscrizioni(self, db_session):
        """US-3: unire due doppioni non deve perdere per strada chi li usava."""
        gara = _gara(db_session, "merge")
        alfa = SquadraService.create(gara, "Circolo Alfa")
        alfa_bis = SquadraService.create(gara, "C. Alfa")
        giocatore = _user(db_session, "merge_p")
        iscrizione = _inscription(db_session, gara, giocatore)
        iscrizione.squadra_id = alfa_bis.id
        db_session.flush()

        SquadraService.merge(gara, alfa_bis.id, alfa.id, FakeActor(1))

        assert iscrizione.squadra_id == alfa.id
        assert db_session.get(Squadra, alfa_bis.id) is None

    def test_unione_con_se_stessa_rifiutata(self, db_session):
        gara = _gara(db_session, "merge_self")
        alfa = SquadraService.create(gara, "Alfa")
        with pytest.raises(ValidationError):
            SquadraService.merge(gara, alfa.id, alfa.id, FakeActor(1))

    def test_disattivata_sparisce_dalle_scelte_ma_non_dall_elenco(self, db_session):
        gara = _gara(db_session, "off")
        squadra = SquadraService.create(gara, "Spenta")
        SquadraService.set_active(gara, squadra.id, False, FakeActor(1))

        assert SquadraService.list_for_gara(gara) == []
        assert SquadraService.list_for_gara(gara, include_inactive=True) == [squadra]

    def test_squadra_di_un_altra_competizione_non_si_tocca(self, db_session):
        """Il controllo di appartenenza non è formale: senza, un id altrui
        basterebbe a rinominare le squadre di un'altra competizione."""
        mia = _gara(db_session, "mia")
        altrui = _gara(db_session, "altrui")
        loro = SquadraService.create(altrui, "Loro")

        with pytest.raises(NotFoundError):
            SquadraService.rename(mia, loro.id, "Mia", FakeActor(1))

    def test_chi_non_dirige_non_governa_l_elenco(self, db_session):
        gara = _gara(db_session, "perm")
        squadra = SquadraService.create(gara, "Alfa")
        with pytest.raises(PermissionDeniedError):
            SquadraService.rename(gara, squadra.id, "Beta", FakeActor(2, manages=False))


class TestSquadraDellIscritto:
    def test_assegnazione_e_rimozione(self, db_session):
        """None non è "non scelto": è "gioco senza squadra qui" (US-8)."""
        gara = _gara(db_session, "assign")
        squadra = SquadraService.create(gara, "Alfa")
        giocatore = _user(db_session, "assign_p")
        iscrizione = _inscription(db_session, gara, giocatore)

        SquadraService.set_inscription_squadra(
            gara, iscrizione, squadra.id, FakeActor(giocatore.id, manages=False)
        )
        assert iscrizione.squadra_id == squadra.id

        SquadraService.set_inscription_squadra(
            gara, iscrizione, None, FakeActor(giocatore.id, manages=False)
        )
        assert iscrizione.squadra_id is None

    def test_il_director_puo_correggere_l_iscritto(self, db_session):
        """US-9: chi rappresenta chi quella sera lo sa il direttore di gara."""
        gara = _gara(db_session, "dir_fix")
        squadra = SquadraService.create(gara, "Alfa")
        giocatore = _user(db_session, "dir_fix_p")
        iscrizione = _inscription(db_session, gara, giocatore)

        SquadraService.set_inscription_squadra(
            gara, iscrizione, squadra.id, FakeActor(999, manages=True)
        )
        assert iscrizione.squadra_id == squadra.id

    def test_un_altro_giocatore_non_puo(self, db_session):
        gara = _gara(db_session, "altrui_ins")
        squadra = SquadraService.create(gara, "Alfa")
        giocatore = _user(db_session, "altrui_p")
        iscrizione = _inscription(db_session, gara, giocatore)

        with pytest.raises(PermissionDeniedError):
            SquadraService.set_inscription_squadra(
                gara, iscrizione, squadra.id, FakeActor(999, manages=False)
            )

    def test_dopo_l_avvio_del_primo_turno_e_rifiutata(self, db_session):
        """US-11: il tabellone è già estratto, quindi si rifiuta e non si
        accetta-e-ignora."""
        gara = _gara(db_session, "frozen")
        squadra = SquadraService.create(gara, "Alfa")
        giocatore = _user(db_session, "frozen_p")
        iscrizione = _inscription(db_session, gara, giocatore)
        gara.status = GaraStatus.PLAYING.value
        gara.current_round = 1
        # Commit e non flush: il rifiuto fa rollback della transazione del
        # servizio, e un cambio di stato solo "flushato" tornerebbe indietro
        # con lui — il secondo tentativo troverebbe la gara ancora in setup.
        db_session.commit()

        assert SquadraService.is_editable(gara) is False
        for attore in (FakeActor(giocatore.id, manages=False), FakeActor(9)):
            with pytest.raises(ConflictError):
                SquadraService.set_inscription_squadra(
                    gara, iscrizione, squadra.id, attore
                )

    def test_senza_separazione_attiva_non_si_assegna(self, db_session):
        gara = _gara(db_session, "nosep", separate_teammates=False)
        giocatore = _user(db_session, "nosep_p")
        iscrizione = _inscription(db_session, gara, giocatore)
        squadra = SquadraService.create(gara, "Alfa")

        with pytest.raises(ValidationError):
            SquadraService.set_inscription_squadra(
                gara, iscrizione, squadra.id, FakeActor(giocatore.id, manages=False)
            )


class TestPrecompilazioneDalProfilo:
    def test_il_testo_del_profilo_trova_la_voce_in_elenco(self, db_session):
        gara = _gara(db_session, "pre")
        squadra = SquadraService.create(gara, "Circolo Nord")
        giocatore = _user(db_session, "pre_p", squadra="circolo  nord")

        assert SquadraService.suggest_for_user(gara, giocatore) is squadra

    def test_nessuna_corrispondenza_nessun_suggerimento(self, db_session):
        gara = _gara(db_session, "pre_no")
        SquadraService.create(gara, "Circolo Nord")
        giocatore = _user(db_session, "pre_no_p", squadra="Biliardo Sud")

        assert SquadraService.suggest_for_user(gara, giocatore) is None

    def test_profilo_vuoto(self, db_session):
        gara = _gara(db_session, "pre_vuoto")
        giocatore = _user(db_session, "pre_vuoto_p")
        assert SquadraService.suggest_for_user(gara, giocatore) is None

    def test_voce_disattivata_non_viene_proposta(self, db_session):
        gara = _gara(db_session, "pre_off")
        squadra = SquadraService.create(gara, "Circolo Nord")
        SquadraService.set_active(gara, squadra.id, False, FakeActor(1))
        giocatore = _user(db_session, "pre_off_p", squadra="Circolo Nord")

        assert SquadraService.suggest_for_user(gara, giocatore) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
