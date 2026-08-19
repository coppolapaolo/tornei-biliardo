"""Unit test di ``CategoriaService`` (ADR-049).

Le regole verificate qui vivono nel servizio e non nella schermata, perché una
schermata non è un vincolo: la finestra che si chiude all'avvio del turno, il
fatto che solo chi dirige possa scrivere una categoria, e il «crea assegnando»
che rende definire l'elenco e assegnare un gesto solo.
"""

from datetime import date, timedelta

import pytest

from models import Campionato, Gara, Inscription, User
from models.categoria.service import CategoriaService
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _user(db_session, suffix, role=UserRole.PLAYER.value):
    user = User(username=f"c_{suffix}", email=f"c_{suffix}@example.com", role=role)
    user.set_password("pw")
    db_session.add(user)
    db_session.flush()
    return user


def _gara(db_session, suffix, *, campionato=None, **kwargs):
    gara = Gara(
        campionato_id=campionato.id if campionato else None,
        number=1,
        name=f"Gara {suffix}",
        date=date.today() + timedelta(days=7),
        discipline="palla_8",
        distance=5,
        rounds_count=3,
        matchmaking_strategy="direct_elimination",
        has_handicap=True,
        **kwargs,
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
    def test_le_gare_di_un_campionato_condividono_l_elenco(self, db_session):
        """È la proprietà che giustifica l'ambito «competizione»."""
        camp = Campionato(name="Camp categorie")
        db_session.add(camp)
        db_session.flush()
        prima = _gara(db_session, "una", campionato=camp)
        seconda = _gara(db_session, "due", campionato=camp)

        CategoriaService.create(prima, "B")

        assert [c.name for c in CategoriaService.list_for_gara(seconda)] == ["B"]

    def test_la_gara_standalone_ha_il_proprio_elenco(self, db_session):
        una = _gara(db_session, "sola")
        altra = _gara(db_session, "altra")

        CategoriaService.create(una, "B")

        assert CategoriaService.list_for_gara(altra) == []

    def test_l_elenco_e_alfabetico(self, db_session):
        gara = _gara(db_session, "ordine")
        for nome in ("N", "C", "A", "B"):
            CategoriaService.create(gara, nome)

        assert [c.name for c in CategoriaService.list_for_gara(gara)] == [
            "A",
            "B",
            "C",
            "N",
        ]


class TestDoppioni:
    def test_maiuscole_e_spazi_non_creano_una_seconda_categoria(self, db_session):
        gara = _gara(db_session, "dup")
        CategoriaService.create(gara, "B")

        with pytest.raises(ConflictError):
            CategoriaService.create(gara, "  b  ")

    def test_il_nome_vuoto_e_rifiutato(self, db_session):
        gara = _gara(db_session, "vuoto")
        with pytest.raises(ValidationError):
            CategoriaService.create(gara, "   ")

    def test_il_nome_troppo_lungo_e_rifiutato(self, db_session):
        gara = _gara(db_session, "lungo")
        with pytest.raises(ValidationError):
            CategoriaService.create(gara, "x" * 51)


class TestCreaAssegnando:
    """Il gesto centrale: scrivere «B» sul primo iscritto crea la categoria."""

    def test_un_nome_nuovo_crea_la_categoria(self, db_session):
        gara = _gara(db_session, "crea")
        ins = _inscription(db_session, gara, _user(db_session, "p1"))

        categoria = CategoriaService.set_inscription_categoria_by_name(gara, ins, "B")

        assert categoria is not None
        assert categoria.name == "B"
        assert ins.categoria_id == categoria.id
        assert len(CategoriaService.list_for_gara(gara)) == 1

    def test_lo_stesso_nome_riusa_la_categoria(self, db_session):
        gara = _gara(db_session, "riusa")
        a = _inscription(db_session, gara, _user(db_session, "a"))
        b = _inscription(db_session, gara, _user(db_session, "b"))

        prima = CategoriaService.set_inscription_categoria_by_name(gara, a, "B")
        # Minuscolo e con spazi: è la stessa categoria, non una seconda.
        dopo = CategoriaService.set_inscription_categoria_by_name(gara, b, "  b ")

        assert prima is not None and dopo is not None
        assert prima.id == dopo.id
        assert len(CategoriaService.list_for_gara(gara)) == 1

    def test_il_nome_vuoto_toglie_l_assegnazione(self, db_session):
        gara = _gara(db_session, "toglie")
        ins = _inscription(db_session, gara, _user(db_session, "p"))
        CategoriaService.set_inscription_categoria_by_name(gara, ins, "B")

        assert CategoriaService.set_inscription_categoria_by_name(gara, ins, "") is None
        assert ins.categoria_id is None

    def test_riassegnare_una_disattivata_la_riattiva(self, db_session):
        """Accettare la scelta e ignorarla sarebbe peggio che riattivarla."""
        gara = _gara(db_session, "riattiva")
        categoria = CategoriaService.create(gara, "B")
        categoria.is_active = False
        db_session.flush()
        ins = _inscription(db_session, gara, _user(db_session, "p"))

        CategoriaService.set_inscription_categoria_by_name(gara, ins, "B")

        assert categoria.is_active is True

    def test_un_iscrizione_di_un_altra_gara_non_si_tocca(self, db_session):
        gara = _gara(db_session, "mia")
        altra = _gara(db_session, "altrui")
        ins = _inscription(db_session, altra, _user(db_session, "p"))

        with pytest.raises(NotFoundError):
            CategoriaService.set_inscription_categoria_by_name(gara, ins, "B")


class TestChiPuoScrivere:
    def test_il_giocatore_non_si_assegna_la_categoria(self, db_session):
        """A differenza della squadra: qui deciderebbe se il suo Elo si muove."""
        gara = _gara(db_session, "perm")
        player = _user(db_session, "self")
        ins = _inscription(db_session, gara, player)
        attore = FakeActor(player.id, manages=False)

        with pytest.raises(PermissionDeniedError):
            CategoriaService.set_inscription_categoria_by_name(
                gara, ins, "B", actor=attore
            )

    def test_can_edit_inscription_e_falso_per_il_giocatore(self, db_session):
        gara = _gara(db_session, "canedit")
        player = _user(db_session, "ce")
        assert (
            CategoriaService.can_edit_inscription(gara, FakeActor(player.id, False))
            is False
        )
        assert (
            CategoriaService.can_edit_inscription(gara, FakeActor(player.id, True))
            is True
        )

    def test_chi_non_dirige_non_tocca_l_elenco(self, db_session):
        gara = _gara(db_session, "elenco")
        categoria = CategoriaService.create(gara, "B")
        estraneo = FakeActor(_user(db_session, "x").id, manages=False)

        with pytest.raises(PermissionDeniedError):
            CategoriaService.rename(gara, categoria.id, "A", actor=estraneo)


class TestFinestraDiModifica:
    def test_dopo_l_avvio_si_rifiuta(self, db_session):
        gara = _gara(db_session, "chiusa", status=GaraStatus.PLAYING.value)
        gara.current_round = 1
        db_session.flush()
        ins = _inscription(db_session, gara, _user(db_session, "p"))

        assert CategoriaService.is_editable(gara) is False
        with pytest.raises(ConflictError):
            CategoriaService.set_inscription_categoria_by_name(gara, ins, "B")

    def test_force_scavalca_la_finestra(self, db_session):
        """È così che lo script recupera le gare già giocate."""
        gara = _gara(db_session, "force", status=GaraStatus.PLAYING.value)
        gara.current_round = 1
        db_session.flush()
        ins = _inscription(db_session, gara, _user(db_session, "p"))

        categoria = CategoriaService.set_inscription_categoria_by_name(
            gara, ins, "B", force=True
        )

        assert categoria is not None
        assert ins.categoria_id == categoria.id


class TestAntiIDOR:
    def test_una_categoria_di_un_altra_competizione_non_si_raggiunge(self, db_session):
        mia = _gara(db_session, "mia2")
        altrui = _gara(db_session, "altrui2")
        categoria_altrui = CategoriaService.create(altrui, "B")

        direttore = FakeActor(_user(db_session, "dir_idor").id)
        with pytest.raises(NotFoundError):
            CategoriaService.rename(mia, categoria_altrui.id, "A", actor=direttore)


class TestEliminazione:
    def test_una_categoria_in_uso_non_si_elimina(self, db_session):
        gara = _gara(db_session, "usata")
        ins = _inscription(db_session, gara, _user(db_session, "p"))
        categoria = CategoriaService.set_inscription_categoria_by_name(gara, ins, "B")
        assert categoria is not None

        direttore = FakeActor(_user(db_session, "dir_uso").id)
        with pytest.raises(ConflictError):
            CategoriaService.elimina(gara, categoria.id, actor=direttore)

    def test_il_refuso_appena_creato_si_elimina(self, db_session):
        gara = _gara(db_session, "refuso")
        categoria = CategoriaService.create(gara, "BB")
        direttore = FakeActor(_user(db_session, "dir_ref").id)

        CategoriaService.elimina(gara, categoria.id, actor=direttore)

        assert CategoriaService.list_for_gara(gara) == []


class TestConteggi:
    def test_i_conteggi_smascherano_il_refuso(self, db_session):
        gara = _gara(db_session, "conta")
        for i in range(3):
            ins = _inscription(db_session, gara, _user(db_session, f"ok{i}"))
            CategoriaService.set_inscription_categoria_by_name(gara, ins, "B")
        sbagliata = _inscription(db_session, gara, _user(db_session, "ko"))
        CategoriaService.set_inscription_categoria_by_name(gara, sbagliata, "BB")

        conteggi = CategoriaService.counts_by_categoria(gara.id)
        per_nome = {
            c.name: conteggi.get(c.id, 0) for c in CategoriaService.list_for_gara(gara)
        }
        assert per_nome == {"B": 3, "BB": 1}

    def test_conta_gli_iscritti_senza_categoria(self, db_session):
        gara = _gara(db_session, "senza")
        con = _inscription(db_session, gara, _user(db_session, "con"))
        CategoriaService.set_inscription_categoria_by_name(gara, con, "B")
        _inscription(db_session, gara, _user(db_session, "senza1"))
        _inscription(db_session, gara, _user(db_session, "senza2"))

        assert CategoriaService.count_senza_categoria(gara.id) == 2


class TestRiportoNelCampionato:
    def test_la_categoria_si_riporta_dalla_gara_precedente(self, db_session):
        camp = Campionato(name="Camp riporto")
        db_session.add(camp)
        db_session.flush()
        prima = _gara(db_session, "p1", campionato=camp)
        seconda = _gara(db_session, "p2", campionato=camp)
        player = _user(db_session, "rip")

        ins = _inscription(db_session, prima, player)
        CategoriaService.set_inscription_categoria_by_name(prima, ins, "B")

        suggerita = CategoriaService.suggest_for_user(seconda, player)
        assert suggerita is not None and suggerita.name == "B"

    def test_non_si_riporta_da_un_altra_competizione(self, db_session):
        altro_camp = Campionato(name="Camp altro")
        db_session.add(altro_camp)
        db_session.flush()
        altrove = _gara(db_session, "altrove", campionato=altro_camp)
        player = _user(db_session, "cross")
        ins = _inscription(db_session, altrove, player)
        CategoriaService.set_inscription_categoria_by_name(altrove, ins, "B")

        camp = Campionato(name="Camp mio")
        db_session.add(camp)
        db_session.flush()
        mia = _gara(db_session, "mia3", campionato=camp)

        assert CategoriaService.suggest_for_user(mia, player) is None

    def test_una_gara_standalone_non_ha_un_prima(self, db_session):
        gara = _gara(db_session, "standalone")
        assert CategoriaService.suggest_for_user(gara, _user(db_session, "s")) is None
