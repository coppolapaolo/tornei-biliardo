"""Che cosa allena un esercizio, quanto è difficile, in quante varianti (ADR-065).

Fino a qui `Challenge` diceva **come si valuta** una prova (a punteggio o
superato/non superato, con o senza tetto) e niente su **che cosa allena**. Questo
file fissa il profilo dell'esercizio:

* due vocabolari **fissi di piattaforma**, abilità e gesto, con zero, una o più
  voci per esercizio — e al più tre abilità, perché un esercizio che allena
  tutto non dice niente a chi filtra;
* un livello dichiarato da 1 a 5, facoltativo;
* famiglia e passo, liberi dell'autore;
* la bianca che si rimette o resta dove si ferma;
* le **varianti**: etichette dello stesso esercizio, registrate separate. Mai un
  secondo esercizio.

«Non lo so» e un default inventato sono cose diverse: un esercizio nato prima di
oggi resta senza profilo finché l'autore non glielo dà.
"""

from __future__ import annotations

import uuid

import pytest

from models.challenge.models import (
    Challenge,
    ChallengeAttempt,
    ChallengeCategory,
    ChallengeVariant,
)
from models.challenge.profile_service import ChallengeProfileService
from models.challenge.services import ChallengeService
from models.challenge.vocabulary import (
    MAX_ABILITA,
    Abilita,
    CategoryAxis,
    Gesto,
)
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.user.models import User
from models.user.role_enum import UserRole


def _utente(db_session, prefisso="gio"):
    u = User(
        username=f"{prefisso}_{uuid.uuid4().hex[:8]}",
        email=f"{prefisso}_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _esercizio(db_session, **campi):
    c = Challenge(
        title=f"Spot Shot {uuid.uuid4().hex[:6]}",
        description="Dieci tiri dalla stessa posizione",
        image_path="test.jpg",
        pass_fail_only=False,
        is_active=True,
        **campi,
    )
    db_session.add(c)
    db_session.flush()
    return c


# ────────────────────────────────────────────────────────────────────────
# I vocabolari
# ────────────────────────────────────────────────────────────────────────
class TestVocabolari:
    def test_le_sette_abilita_decise_dall_utente(self):
        assert [a.value for a in Abilita] == [
            "fondamentali",
            "tiro",
            "battente",
            "posizione",
            "sponde",
            "difesa",
            "spaccata",
        ]

    def test_i_dieci_gesti_decisi_dall_utente(self):
        assert [g.value for g in Gesto] == [
            "stop",
            "stun",
            "follow",
            "draw",
            "spin",
            "forza",
            "bank",
            "kick",
            "jump",
            "masse",
        ]

    def test_ogni_voce_ha_un_nome_da_mostrare(self, app):
        with app.test_request_context():
            for voce in [*Abilita, *Gesto]:
                assert voce.display_name
            assert Gesto.MASSE.display_name == "massé"

    def test_normalize_torna_none_sull_ignoto(self):
        assert Abilita.normalize("tiro") is Abilita.TIRO
        assert Abilita.normalize("Tiro ") is Abilita.TIRO
        assert Abilita.normalize("esordienti") is None
        assert Gesto.normalize(None) is None


# ────────────────────────────────────────────────────────────────────────
# Il profilo
# ────────────────────────────────────────────────────────────────────────
class TestProfilo:
    def test_un_esercizio_nato_prima_resta_senza_profilo(self, db_session):
        c = _esercizio(db_session)
        assert c.abilita == []
        assert c.gesti == []
        assert c.declared_level is None
        assert c.family is None
        assert c.family_step is None
        assert c.cue_ball_reset is None
        assert c.variants == []

    def test_si_scrivono_abilita_gesti_e_livello(self, db_session):
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(
            c.id,
            abilita=["posizione", "tiro"],
            gesti=["draw", "forza"],
            declared_level=2,
            family="stop shot",
            family_step=3,
            cue_ball_reset=True,
        )
        c = db_session.get(Challenge, c.id)
        # L'ordine è quello del vocabolario, non quello d'arrivo: due esercizi
        # con le stesse voci mostrano le stesse etichette nello stesso ordine.
        assert c.abilita == [Abilita.TIRO, Abilita.POSIZIONE]
        assert c.gesti == [Gesto.DRAW, Gesto.FORZA]
        assert c.declared_level == 2
        assert c.family == "stop shot"
        assert c.family_step == 3
        assert c.cue_ball_reset is True

    def test_il_profilo_si_sostituisce_non_si_somma(self, db_session):
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(c.id, abilita=["tiro"], gesti=["stop"])
        ChallengeProfileService.set_profile(c.id, abilita=["difesa"], gesti=[])
        c = db_session.get(Challenge, c.id)
        assert c.abilita == [Abilita.DIFESA]
        assert c.gesti == []
        assert (
            db_session.query(ChallengeCategory).filter_by(challenge_id=c.id).count()
            == 1
        )

    def test_una_voce_ripetuta_vale_una(self, db_session):
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(c.id, abilita=["tiro", "tiro"])
        assert db_session.get(Challenge, c.id).abilita == [Abilita.TIRO]

    def test_al_piu_tre_abilita(self, db_session):
        c = _esercizio(db_session)
        assert MAX_ABILITA == 3
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(
                c.id, abilita=["tiro", "posizione", "sponde", "difesa"]
            )

    def test_i_gesti_non_hanno_tetto(self, db_session):
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(c.id, gesti=[g.value for g in Gesto])
        assert len(db_session.get(Challenge, c.id).gesti) == len(Gesto)

    def test_una_voce_fuori_vocabolario_si_rifiuta(self, db_session):
        """«Esordienti» non è un'abilità: è uno dei livelli."""
        c = _esercizio(db_session)
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(c.id, abilita=["esordienti"])

    def test_i_due_vocabolari_non_si_mescolano(self, db_session):
        c = _esercizio(db_session)
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(c.id, gesti=["tiro"])

    @pytest.mark.parametrize("livello", [0, 6, -1])
    def test_il_livello_va_da_uno_a_cinque(self, db_session, livello):
        c = _esercizio(db_session)
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(c.id, declared_level=livello)

    def test_il_passo_senza_famiglia_non_ha_senso(self, db_session):
        c = _esercizio(db_session)
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(c.id, family="", family_step=2)

    def test_la_famiglia_di_soli_spazi_e_nessuna_famiglia(self, db_session):
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(c.id, family="   ")
        assert db_session.get(Challenge, c.id).family is None

    def test_esercizio_inesistente(self, db_session):
        with pytest.raises(NotFoundError):
            ChallengeProfileService.set_profile(999_999, abilita=["tiro"])

    def test_la_categoria_sta_su_disco_come_valore(self, db_session):
        """Presidio dell'incidente del 17/08: si salva il valore, non il nome."""
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(c.id, gesti=["masse"])
        riga = db_session.query(ChallengeCategory).filter_by(challenge_id=c.id).one()
        assert riga.axis == CategoryAxis.GESTO.value == "gesto"
        assert riga.value == "masse"


# ────────────────────────────────────────────────────────────────────────
# Le varianti
# ────────────────────────────────────────────────────────────────────────
class TestVarianti:
    def test_nascono_nell_ordine_dato(self, db_session):
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(
            c.id, variants=[{"label": "destra"}, {"label": "sinistra"}]
        )
        c = db_session.get(Challenge, c.id)
        assert [v.label for v in c.variants] == ["destra", "sinistra"]
        assert [v.position for v in c.variants] == [1, 2]

    def test_rinominare_tiene_le_prove(self, db_session):
        c = _esercizio(db_session)
        u = _utente(db_session)
        ChallengeProfileService.set_profile(
            c.id, variants=[{"label": "dx"}, {"label": "sx"}]
        )
        dx = db_session.get(Challenge, c.id).variants[0]
        ChallengeService.record_attempt(u.id, c.id, score=7, variant_id=dx.id)

        ChallengeProfileService.set_profile(
            c.id,
            variants=[{"id": dx.id, "label": "destra"}, {"label": "sinistra"}],
        )
        c = db_session.get(Challenge, c.id)
        assert [v.label for v in c.variants] == ["destra", "sinistra"]
        prova = db_session.query(ChallengeAttempt).filter_by(challenge_id=c.id).one()
        assert prova.variant_id == dx.id

    def test_una_variante_con_prove_non_si_toglie(self, db_session):
        c = _esercizio(db_session)
        u = _utente(db_session)
        ChallengeProfileService.set_profile(c.id, variants=[{"label": "A"}])
        a = db_session.get(Challenge, c.id).variants[0]
        ChallengeService.record_attempt(u.id, c.id, score=3, variant_id=a.id)
        with pytest.raises(ConflictError):
            ChallengeProfileService.set_profile(c.id, variants=[])

    def test_una_variante_senza_prove_si_toglie(self, db_session):
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(
            c.id, variants=[{"label": "A"}, {"label": "B"}]
        )
        ChallengeProfileService.set_profile(c.id, variants=[{"label": "B"}])
        c = db_session.get(Challenge, c.id)
        assert [v.label for v in c.variants] == ["B"]
        assert db_session.query(ChallengeVariant).filter_by(challenge_id=c.id).count()

    def test_due_varianti_con_lo_stesso_nome(self, db_session):
        c = _esercizio(db_session)
        with pytest.raises(ValidationError):
            ChallengeProfileService.set_profile(
                c.id, variants=[{"label": "dx"}, {"label": " DX "}]
            )

    def test_una_variante_sola_non_e_una_variante(self, db_session):
        """Le varianti distinguono: con un'etichetta sola non c'è niente da
        distinguere, ma il modello la accetta — è l'autore a metà del lavoro."""
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(c.id, variants=[{"label": "dx"}])
        assert len(db_session.get(Challenge, c.id).variants) == 1

    def test_variants_none_non_tocca_le_varianti(self, db_session):
        c = _esercizio(db_session)
        ChallengeProfileService.set_profile(c.id, variants=[{"label": "dx"}])
        ChallengeProfileService.set_profile(c.id, abilita=["tiro"])
        assert len(db_session.get(Challenge, c.id).variants) == 1

    def test_la_prova_rifiuta_la_variante_di_un_altro_esercizio(self, db_session):
        c1 = _esercizio(db_session)
        c2 = _esercizio(db_session)
        u = _utente(db_session)
        ChallengeProfileService.set_profile(c1.id, variants=[{"label": "dx"}])
        dx = db_session.get(Challenge, c1.id).variants[0]
        with pytest.raises(ValidationError):
            ChallengeService.record_attempt(u.id, c2.id, score=3, variant_id=dx.id)

    def test_senza_variante_la_prova_resta_generica(self, db_session):
        c = _esercizio(db_session)
        u = _utente(db_session)
        prova = ChallengeService.record_attempt(u.id, c.id, score=3)
        assert prova.variant_id is None


# ────────────────────────────────────────────────────────────────────────
# Quanti l'hanno provato, e che voto gli danno
# ────────────────────────────────────────────────────────────────────────
class TestPopolarita:
    def test_un_esercizio_nuovo_ha_tutto_a_zero(self, db_session):
        from models.challenge.popularity import popularity_for

        c = _esercizio(db_session)
        numeri = popularity_for([c.id])[c.id]
        assert numeri.players == 0
        assert numeri.rating_count == 0
        assert numeri.rating_average is None
        assert not numeri.has_rating

    def test_si_contano_i_giocatori_non_le_prove(self, db_session):
        from models.challenge.popularity import has_tried, popularity_for

        c = _esercizio(db_session)
        a, b, mai = (_utente(db_session) for _ in range(3))
        for _ in range(3):
            ChallengeService.record_attempt(a.id, c.id, score=5)
        ChallengeService.record_attempt(b.id, c.id, score=2)

        assert popularity_for([c.id])[c.id].players == 2
        assert has_tried(a.id, c.id)
        assert not has_tried(mai.id, c.id)

    def test_una_prova_lasciata_a_meta_non_conta(self, db_session):
        from models.challenge.popularity import popularity_for

        c = _esercizio(db_session)
        u = _utente(db_session)
        ChallengeService.start_challenge_attempt(u.id, c.id)
        assert popularity_for([c.id])[c.id].players == 0

    def test_la_media_dei_voti(self, db_session):
        from models.challenge.models import ChallengeRating
        from models.challenge.popularity import popularity_for

        c = _esercizio(db_session)
        for voto in (5, 4, 3):
            db_session.add(
                ChallengeRating(
                    challenge_id=c.id, user_id=_utente(db_session).id, rating=voto
                )
            )
        db_session.flush()
        numeri = popularity_for([c.id])[c.id]
        assert numeri.rating_count == 3
        assert numeri.rating_average == pytest.approx(4.0)

    def test_piu_esercizi_in_un_colpo_ognuno_coi_suoi(self, db_session):
        from models.challenge.popularity import popularity_for

        c1, c2 = _esercizio(db_session), _esercizio(db_session)
        u = _utente(db_session)
        ChallengeService.record_attempt(u.id, c1.id, score=5)
        numeri = popularity_for([c1.id, c2.id])
        assert numeri[c1.id].players == 1
        assert numeri[c2.id].players == 0


class TestCopia:
    def test_la_copia_porta_il_profilo_e_non_la_storia(self, db_session):
        from models.challenge.models import ChallengeRating
        from models.challenge.popularity import popularity_for
        from models.challenge.profile_service import copy_profile

        originale = _esercizio(db_session)
        u = _utente(db_session)
        ChallengeProfileService.set_profile(
            originale.id,
            abilita=["tiro"],
            gesti=["stop"],
            declared_level=3,
            family="stop shot",
            family_step=2,
            cue_ball_reset=False,
            variants=[{"label": "dx"}, {"label": "sx"}],
        )
        ChallengeService.record_attempt(u.id, originale.id, score=4)
        db_session.add(
            ChallengeRating(challenge_id=originale.id, user_id=u.id, rating=5)
        )
        originale = db_session.get(Challenge, originale.id)

        copia = _esercizio(db_session)
        copy_profile(originale, copia)
        db_session.flush()

        assert copia.abilita == [Abilita.TIRO]
        assert copia.gesti == [Gesto.STOP]
        assert copia.declared_level == 3
        assert (copia.family, copia.family_step) == ("stop shot", 2)
        assert copia.cue_ball_reset is False
        assert [v.label for v in copia.variants] == ["dx", "sx"]
        # Le varianti della copia sono righe sue, non quelle dell'originale.
        assert {v.id for v in copia.variants}.isdisjoint(
            {v.id for v in originale.variants}
        )
        numeri = popularity_for([copia.id])[copia.id]
        assert (numeri.players, numeri.rating_count) == (0, 0)
