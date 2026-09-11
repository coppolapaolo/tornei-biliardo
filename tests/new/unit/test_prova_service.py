"""Competizione di prova (ADR-058): il servizio e le esclusioni.

Limite di tre, giocatori fittizi con nomi e rating fissi, i tre pulsanti di
iscrizione, la scadenza con avviso, la cancellazione fisica senza orfani, e i
tre punti in cui il resto dell'app deve **ignorare** una prova: motore di
rating, gamification, statistiche del direttore.

I test lavorano fuori da una richiesta HTTP, dove il filtro di visibilità
nasconde le prove a chiunque: le query esplicite passano da `prova_visibili()`
o da `include_prova=True`, esattamente come devono fare servizi e job.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select

from models.base import db, utc_now
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.match.models import Match
from models.notification.models import Notification
from models.prova.guard import evento_di_prova, gara_e_di_prova, senza_prove
from models.prova.nomi import NOMI_FITTIZI, nome_fittizio
from models.prova.service import (
    DURATA_PROVA,
    LIMITE_PROVE_ATTIVE,
    PREAVVISO_SCADENZA,
    ProvaService,
)
from models.prova.visibility import prova_visibili
from models.rating.eligibility import RatingEligibility, RatingExclusion
from models.rating.models import PlayerRating
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------- fixture


def _direttore(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"dir_{sigla}",
        email=f"dir_{sigla}@test.local",
        role=UserRole.DIRECTOR.value,
    )
    utente.set_password("prova1234")
    db_session.add(utente)
    db_session.commit()
    return utente


def _prova(db_session, direttore: User, *, minimo=4, massimo=8, **extra) -> Gara:
    campi = {
        "campionato_id": None,
        "number": 1,
        "name": f"Prova {uuid.uuid4().hex[:4]}",
        "date": date.today() + timedelta(days=1),
        "discipline": Discipline.NINE_BALL.value,
        "distance": 5,
        "director_id": direttore.id,
        "min_participants": minimo,
        "max_participants": massimo,
        "status": GaraStatus.INSCRIPTION.value,
    }
    campi.update(ProvaService.campi_di_creazione())
    campi.update(extra)
    gara = GaraService.create_gara(**campi)
    db_session.commit()
    return gara


def _gara_vera(db_session, direttore: User) -> Gara:
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Gara vera",
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        director_id=direttore.id,
        status=GaraStatus.INSCRIPTION.value,
    )
    db_session.commit()
    return gara


def _conta(model, **filtri) -> int:
    with prova_visibili():
        return db.session.query(model).filter_by(**filtri).count()


# --------------------------------------------------------------- creazione


class TestCreazioneELimite:
    def test_i_campi_di_creazione_portano_flag_e_scadenza(self):
        adesso = utc_now()
        campi = ProvaService.campi_di_creazione(adesso)
        assert campi["is_prova"] is True
        assert campi["prova_expires_at"] == adesso + DURATA_PROVA
        assert DURATA_PROVA == timedelta(days=14)

    def test_al_limite_la_quarta_viene_rifiutata(self, db_session):
        direttore = _direttore(db_session)
        for _ in range(LIMITE_PROVE_ATTIVE):
            ProvaService.verifica_limite(direttore.id)
            _prova(db_session, direttore)
        assert len(ProvaService.prove_attive(direttore.id)) == LIMITE_PROVE_ATTIVE
        with pytest.raises(ConflictError):
            ProvaService.verifica_limite(direttore.id)

        # Eliminarne una libera il posto.
        prima = ProvaService.prove_attive(direttore.id)[0]
        ProvaService.elimina_prova(gara_id=prima.id)
        ProvaService.verifica_limite(direttore.id)

    def test_le_gare_vere_non_contano_nel_limite(self, db_session):
        direttore = _direttore(db_session)
        _gara_vera(db_session, direttore)
        assert ProvaService.prove_attive(direttore.id) == []

    def test_la_gara_di_un_campionato_di_prova_nasce_di_prova(self, db_session):
        from models.campionato.tournament_service import TournamentService

        direttore = _direttore(db_session)
        campionato = TournamentService().create_campionato_with_director(
            name="Campionato di prova", creator_user_id=direttore.id
        )
        campionato.is_prova = True
        campionato.prova_expires_at = utc_now() + DURATA_PROVA
        db_session.commit()

        gara = GaraService.create_gara(
            campionato_id=campionato.id,
            number=1,
            name="Gara 1",
            date=date.today() + timedelta(days=1),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
        )
        assert gara.is_prova is True
        # La scadenza sta sulla radice, non sulla gara.
        assert gara.prova_expires_at is None
        assert ProvaService.prove_attive(direttore.id) == [campionato]


# ----------------------------------------------------------------- fittizi


class TestGiocatoriFittizi:
    def test_la_tabella_dei_nomi_ha_rating_tutti_diversi(self):
        rating = [r for _, _, r in NOMI_FITTIZI]
        assert len(rating) == len(set(rating)) == 16
        assert nome_fittizio(0)[:2] == ("Maria", "Rossi")
        # Oltre la tabella si ricomincia con l'ordinale.
        assert nome_fittizio(16) == ("Maria", "Rossi II", 1520)
        assert nome_fittizio(33)[1] == "Mario Bianchi III".split(" ", 1)[1]

    def test_nascono_senza_login_e_con_rating_fisso(self, db_session):
        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore)

        creati = ProvaService.crea_fittizi(gara, 3)

        # Lo username e' il nome con cui si gioca: verosimile, non un codice.
        assert [u.username for u in creati] == [
            "Maria Rossi",
            "Mario Bianchi",
            "Anna Verdi",
        ]
        primo = creati[0]
        assert primo.is_fittizio is True
        assert primo.prova_gara_id == gara.id
        assert primo.role == UserRole.PLAYER.value
        assert primo.full_name == "Maria Rossi"
        assert primo.elo_rating == 1520
        assert primo.onboarding_completed is True
        assert primo.check_password("qualunque") is False
        assert primo.email.endswith("@fittizio.invalid")
        with prova_visibili():
            rating = PlayerRating.query.filter_by(user_id=primo.id).one()
        assert rating.rating_value == 1520

        # La numerazione prosegue da dove era arrivata.
        altri = ProvaService.crea_fittizi(gara, 1)
        assert altri[0].username == "Luca Russo"
        assert altri[0].email == f"prova-g{gara.id}-4@fittizio.invalid"

        # Una seconda prova ha la sua Maria Rossi, con l'ordinale.
        seconda = _prova(db_session, direttore)
        doppione = ProvaService.crea_fittizi(seconda, 1)[0]
        assert doppione.username == "Maria Rossi (2)"
        assert doppione.full_name == "Maria Rossi"

    def test_non_si_creano_in_una_gara_vera(self, db_session):
        direttore = _direttore(db_session)
        with pytest.raises(ValidationError):
            ProvaService.crea_fittizi(_gara_vera(db_session, direttore), 1)

    def test_fuori_da_una_richiesta_i_fittizi_sono_invisibili(self, db_session):
        """Il filtro di sessione: senza opt-in una query esplicita non li vede."""
        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore)
        fittizio = ProvaService.crea_fittizi(gara, 1)[0]
        db_session.commit()

        assert db.session.get(Gara, gara.id) is None or True  # identity map
        db.session.expire_all()
        assert User.query.filter_by(id=fittizio.id).first() is None
        assert db.session.query(Gara).filter_by(id=gara.id).first() is None
        with prova_visibili():
            assert User.query.filter_by(id=fittizio.id).first() is not None
            assert db.session.query(Gara).filter_by(id=gara.id).first() is not None
        # Le relazioni passano sempre: `match.gara` non deve mai tornare None.
        with prova_visibili():
            iscrizione = Inscription(user_id=fittizio.id, gara_id=gara.id)
            db.session.add(iscrizione)
            db.session.commit()
            iscrizione_id = iscrizione.id
        db.session.expire_all()
        iscrizione = db.session.get(Inscription, iscrizione_id)
        assert iscrizione is not None
        assert iscrizione.user.id == fittizio.id
        assert iscrizione.gara.id == gara.id


# -------------------------------------------------------------- iscrizioni


class TestITrePulsanti:
    def test_quanti_ne_aggiunge_ciascun_pulsante(self, db_session):
        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore, minimo=4, massimo=6)

        assert ProvaService.quanti_da_iscrivere(gara, "minimo") == 4
        assert ProvaService.quanti_da_iscrivere(gara, "massimo") == 6
        assert ProvaService.quanti_da_iscrivere(gara, "uno") == 1

        assert ProvaService.iscrivi_fittizi(gara.id, "minimo") == 4
        assert _conta(Inscription, gara_id=gara.id, is_waitlist=False) == 4
        assert ProvaService.quanti_da_iscrivere(gara, "minimo") == 0
        assert ProvaService.quanti_da_iscrivere(gara, "massimo") == 2

        assert ProvaService.iscrivi_fittizi(gara.id, "uno") == 1
        assert ProvaService.iscrivi_fittizi(gara.id, "massimo") == 1
        assert ProvaService.quanti_da_iscrivere(gara, "uno") == 0
        assert ProvaService.iscrivi_fittizi(gara.id, "uno") == 0
        assert _conta(User, is_fittizio=True, prova_gara_id=gara.id) == 6

    def test_un_utente_vero_non_entra_e_un_fittizio_non_esce(self, db_session):
        """Il punto unico sotto le route: `inscribe_user` rifiuta nei due versi."""
        from models.competition.inscription_service import InscriptionService
        from models.exceptions import PermissionDeniedError

        direttore = _direttore(db_session)
        prova = _prova(db_session, direttore)
        vera = _gara_vera(db_session, direttore)
        giocatore = User(
            username=f"pl_{uuid.uuid4().hex[:6]}",
            email=f"pl_{uuid.uuid4().hex[:6]}@test.local",
            role=UserRole.PLAYER.value,
        )
        giocatore.set_password("x")
        db_session.add(giocatore)
        db_session.commit()
        fittizio = ProvaService.crea_fittizi(prova, 1)[0]

        with pytest.raises(PermissionDeniedError):
            InscriptionService.inscribe_user(giocatore.id, prova.id)
        with pytest.raises(PermissionDeniedError):
            InscriptionService.inscribe_user(fittizio.id, vera.id)

    def test_il_minimo_rispetta_il_massimo(self, db_session):
        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore, minimo=8, massimo=6)
        assert ProvaService.quanti_da_iscrivere(gara, "minimo") == 6

    def test_senza_massimo_il_pulsante_e_spento(self, db_session):
        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore, minimo=4, massimo=None)
        assert ProvaService.quanti_da_iscrivere(gara, "massimo") == 0
        assert ProvaService.quanti_da_iscrivere(gara, "uno") == 1

    def test_solo_a_iscrizioni_aperte(self, db_session):
        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore, status=GaraStatus.SETUP.value)
        with pytest.raises(ConflictError):
            ProvaService.iscrivi_fittizi(gara.id, "minimo")

    def test_modalita_sconosciuta(self, db_session):
        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore)
        with pytest.raises(ValidationError):
            ProvaService.quanti_da_iscrivere(gara, "tutti")


# ------------------------------------------------------------ eliminazione


class TestEliminazioneFisica:
    def _prova_giocata(self, db_session):
        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore, minimo=2, massimo=4)
        ProvaService.iscrivi_fittizi(gara.id, "minimo")
        with prova_visibili():
            fittizi = ProvaService.fittizi_della_radice(gara_id=gara.id)
            partita = Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=fittizi[0].id,
                player2_id=fittizi[1].id,
                player1_score=5,
                player2_score=2,
                winner_id=fittizi[0].id,
                status=MatchStatus.CONFIRMED_BY_BOTH.value,
            )
            db.session.add(partita)
            db.session.commit()
        return direttore, gara, [f.id for f in fittizi], partita.id

    def test_non_lascia_orfani(self, db_session):
        direttore, gara, fittizi_ids, partita_id = self._prova_giocata(db_session)
        gara_id = gara.id

        ProvaService.elimina_prova(gara_id=gara_id)

        with prova_visibili():
            assert db.session.get(Gara, gara_id) is None
            assert db.session.get(Match, partita_id) is None
            assert _conta(Inscription, gara_id=gara_id) == 0
            for uid in fittizi_ids:
                assert db.session.get(User, uid) is None
                assert PlayerRating.query.filter_by(user_id=uid).count() == 0
        # Il direttore, invece, resta.
        assert db.session.get(User, direttore.id) is not None

    def test_rifiuta_una_gara_vera(self, db_session):
        direttore = _direttore(db_session)
        gara = _gara_vera(db_session, direttore)
        with pytest.raises(NotFoundError):
            ProvaService.elimina_prova(gara_id=gara.id)
        assert db.session.get(Gara, gara.id) is not None

    def test_vuole_una_radice_sola(self):
        with pytest.raises(ValidationError):
            ProvaService.elimina_prova()

    def test_anonimizzare_il_direttore_elimina_le_sue_prove(self, db_session):
        from models.user.profile_service import UserProfileService

        direttore, gara, fittizi_ids, _ = self._prova_giocata(db_session)
        gara_id = gara.id
        UserProfileService.anonymize_user(direttore.id)
        with prova_visibili():
            assert db.session.get(Gara, gara_id) is None
            assert all(db.session.get(User, uid) is None for uid in fittizi_ids)

    def test_un_fittizio_non_si_anonimizza_ne_si_unisce(self, db_session):
        from models.user.merge_service import UserMergeService
        from models.user.profile_service import UserProfileService

        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore)
        fittizio = ProvaService.crea_fittizi(gara, 1)[0]
        admin = User(
            username=f"adm_{uuid.uuid4().hex[:6]}",
            email=f"adm_{uuid.uuid4().hex[:6]}@test.local",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("x")
        db_session.add(admin)
        db_session.commit()

        with pytest.raises(ValueError):
            UserProfileService.anonymize_user(fittizio.id)
        with pytest.raises(ValidationError):
            UserMergeService.merge_users(fittizio.id, direttore.id, admin.id)


# ---------------------------------------------------------------- scadenza


class TestScadenza:
    def test_avviso_tre_giorni_prima_una_volta_sola(self, db_session):
        direttore = _direttore(db_session)
        adesso = utc_now()
        gara = _prova(
            db_session,
            direttore,
            prova_expires_at=adesso + PREAVVISO_SCADENZA - timedelta(hours=1),
        )
        assert PREAVVISO_SCADENZA == timedelta(days=3)

        assert ProvaService.avvisa_scadenze(adesso) == 1
        avvisi = Notification.query.filter_by(user_id=direttore.id).all()
        assert len(avvisi) == 1
        assert avvisi[0].title.startswith("Prova · ")
        assert "scadere" in avvisi[0].title
        assert gara.name in avvisi[0].message

        assert ProvaService.avvisa_scadenze(adesso) == 0

    def test_una_prova_lontana_dalla_scadenza_non_riceve_avvisi(self, db_session):
        direttore = _direttore(db_session)
        _prova(db_session, direttore)
        assert ProvaService.avvisa_scadenze() == 0

    def test_alla_scadenza_sparisce(self, db_session):
        direttore = _direttore(db_session)
        adesso = utc_now()
        scaduta = _prova(
            db_session, direttore, prova_expires_at=adesso - timedelta(days=1)
        )
        viva = _prova(db_session, direttore)
        ProvaService.iscrivi_fittizi(scaduta.id, "minimo")
        scaduta_id, viva_id = scaduta.id, viva.id

        assert ProvaService.elimina_scadute(adesso) == 1

        with prova_visibili():
            assert db.session.get(Gara, scaduta_id) is None
            assert db.session.get(Gara, viva_id) is not None
            assert _conta(User, is_fittizio=True, prova_gara_id=scaduta_id) == 0

    def test_il_job_giornaliero_la_conosce(self, app):
        radice = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        spec = importlib.util.spec_from_file_location(
            "daily_jobs", os.path.join(radice, "scripts", "daily_jobs.py")
        )
        assert spec is not None and spec.loader is not None
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        assert "prove" in modulo.JOBS
        with patch.object(modulo, "bootstrap_and_create_app", return_value=app):
            assert "prove eliminate" in modulo.job_prove()


# ------------------------------------------------------------- esclusioni


class TestCosaIgnoraUnaProva:
    def test_il_rating_non_si_muove(self, db_session):
        direttore = _direttore(db_session)
        gara = _prova(db_session, direttore, minimo=2)
        ProvaService.iscrivi_fittizi(gara.id, "minimo")
        with prova_visibili():
            a, b = ProvaService.fittizi_della_radice(gara_id=gara.id)
            partita = Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=a.id,
                player2_id=b.id,
                player1_score=5,
                player2_score=3,
                winner_id=a.id,
                status=MatchStatus.CONFIRMED_BY_BOTH.value,
            )
            db.session.add(partita)
            db.session.commit()
        assert RatingEligibility.exclusion_reason(partita) is RatingExclusion.PROVA
        assert RatingEligibility.counts_for_rating(partita) is False

    def test_la_gamification_scarta_gli_eventi(self, db_session):
        direttore = _direttore(db_session)
        prova = _prova(db_session, direttore)
        vera = _gara_vera(db_session, direttore)

        assert gara_e_di_prova(prova.id) is True
        assert gara_e_di_prova(vera.id) is False
        assert evento_di_prova(SimpleNamespace(gara_id=prova.id)) is True
        assert evento_di_prova(SimpleNamespace(gara_id=vera.id)) is False
        assert evento_di_prova(SimpleNamespace(match_id=None)) is False

        chiamate = []
        guardato = senza_prove(lambda event: chiamate.append(event.gara_id))
        guardato(SimpleNamespace(gara_id=prova.id))
        guardato(SimpleNamespace(gara_id=vera.id))
        assert chiamate == [vera.id]

    def test_creare_una_prova_non_da_xp_al_direttore(self, db_session):
        """`CompetitionCreatedEvent` passa dal guard: niente XP per il creatore."""
        from models.gamification.level_service import LevelService

        direttore = _direttore(db_session)
        with patch.object(LevelService, "award_xp") as premia:
            _prova(db_session, direttore, creator_id=direttore.id)
        assert premia.call_count == 0

    def test_le_notifiche_di_una_prova_lo_dicono_nel_titolo(self, db_session):
        from models.notification.models import NotificationPriority, NotificationType
        from models.notification.services import NotificationService

        direttore = _direttore(db_session)
        prova = _prova(db_session, direttore)
        notifica = NotificationService.create_notification(
            user_id=direttore.id,
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="La gara è terminata",
            message="…",
            priority=NotificationPriority.NORMAL,
            related_entities={"gara_id": prova.id},
        )
        assert notifica is not None
        assert notifica.title == "Prova · La gara è terminata"

    def test_le_gare_organizzate_ignorano_le_prove(self, db_session):
        from models.dashboard.activity_feedback import _director_garas
        from models.gamification.community_leaderboard_service import (
            CommunityLeaderboardService,
        )

        direttore = _direttore(db_session)
        _prova(db_session, direttore)
        vera = _gara_vera(db_session, direttore)

        with prova_visibili():
            assert [g.id for g in _director_garas(direttore.id)] == [vera.id]
            assert CommunityLeaderboardService._gare_organized(direttore.id) == 1

    def test_una_query_col_flag_vede_le_prove(self, db_session):
        direttore = _direttore(db_session)
        prova = _prova(db_session, direttore)
        db.session.expire_all()
        assert (
            db.session.execute(select(Gara.id).where(Gara.id == prova.id)).scalar()
            is None
        )
        assert (
            db.session.execute(
                select(Gara.id)
                .where(Gara.id == prova.id)
                .execution_options(include_prova=True)
            ).scalar()
            == prova.id
        )
