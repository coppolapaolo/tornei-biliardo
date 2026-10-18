"""La partita di altri due, tenuta da un istruttore o da un direttore (ADR-084).

Il percorso intero, dal servizio alle pagine: chi può creare, il referto
tenuto dallo scorer senza firme d'ufficio, la chiusura che dichiara la
partita e avvisa i due, la conferma per giocatore, i livelli per persona e
l'ELO per coppia, l'annullamento di chi segna. E la regola del 2026-10-18: un
rifiuto basta, la partita sparisce ai due giocatori e chi l'ha segnata la
corregge o la cancella.

UC12 di ``docs/usecases/sfide-e-certificazione.md``.
"""

from __future__ import annotations

import uuid

import pytest
from flask import g

from models import User, db
from models.certificazione import Livello, Vista, sfide_della_vista
from models.exceptions import ConflictError, PermissionDeniedError, ValidationError
from models.individual_match.match_lifecycle_service import MatchLifecycleService
from models.individual_match.models import IndividualMatch
from models.individual_match.pending_confirmation import PendingConfirmationService
from models.individual_match.scored_match_service import ScoredMatchService
from models.individual_match.services import IndividualMatchService
from models.notification.models import (
    Notification,
    NotificationStatus,
    NotificationType,
)
from models.player.history_service import HistoryFilters, PlayerHistoryService
from models.rating.models import MatchRatingHistory, RatingSystem
from models.status_enum import Discipline, MatchStatus
from models.tpa.services import TpaRefertoService
from models.tpa.stats_service import TpaStatsService
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

DESCRIZIONE = "Finale 1ª giornata, serie C FVG"


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"pt_{uid}",
        email=f"pt_{uid}@test.com",
        role=role,
        gamification_override=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _istruttore() -> User:
    admin = _user(UserRole.ADMIN.value)
    marco = _user()
    RoleGrantService.grant(marco.id, GrantableRole.INSTRUCTOR, admin)
    db.session.commit()
    return marco


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
    return client


def _get(client, url, **kw):
    g.pop("_login_user", None)
    return client.get(url, **kw)


def _post(client, url, **kw):
    g.pop("_login_user", None)
    return client.post(url, **kw)


def _crea(scorer: User, a: User, b: User, **config) -> IndividualMatch:
    config.setdefault("discipline", Discipline.NINE_BALL.value)
    config.setdefault("distance", 3)
    config.setdefault("description", DESCRIZIONE)
    return ScoredMatchService.start(scorer, a.id, b.id, config)


def _vinci(match: IndividualMatch, scorer: User, posto: int, quanti: int = 1) -> None:
    referto = TpaRefertoService.get_for_match(match.id)
    assert referto is not None
    for _ in range(quanti):
        TpaRefertoService.press(referto.id, scorer.id, f"seat:{posto}")
        TpaRefertoService.press(referto.id, scorer.id, "1")
        TpaRefertoService.press(referto.id, scorer.id, "9")
        TpaRefertoService.press(referto.id, scorer.id, "end")


def _dichiarata(scorer=None, a=None, b=None):
    """Marco segna A–B «al 3», finisce 3-0 e chiude il referto."""
    scorer = scorer or _istruttore()
    a, b = a or _user(), b or _user()
    match = _crea(scorer, a, b)
    _vinci(match, scorer, 1, 3)
    TpaRefertoService.close(TpaRefertoService.get_for_match(match.id).id, scorer.id)
    return scorer, a, b, db.session.get(IndividualMatch, match.id)


def _nella_vista(match_id, vista, user_id=None) -> bool:
    return (
        db.session.query(IndividualMatch.id)
        .filter(
            IndividualMatch.id == match_id, sfide_della_vista(vista, user_id=user_id)
        )
        .first()
        is not None
    )


def _righe_elo(match_id, sistema) -> int:
    return MatchRatingHistory.query.filter_by(
        individual_match_id=match_id, rating_system=sistema
    ).count()


def _notifiche(user, tipo):
    return Notification.query.filter_by(user_id=user.id, notification_type=tipo).all()


@pytest.mark.integration
class TestChiCrea:
    def test_un_giocatore_senza_ruolo_non_crea(self):
        gianni, a, b = _user(), _user(), _user()
        with pytest.raises(PermissionDeniedError):
            _crea(gianni, a, b)

    def test_il_direttore_crea(self):
        match = _crea(_user(UserRole.DIRECTOR.value), _user(), _user())
        assert match.scorer_id is not None

    def test_l_admin_non_crea_nemmeno_da_istruttore(self):
        """«admin non dovrebbe segnare partite» (2026-10-18)."""
        admin = _user(UserRole.ADMIN.value)
        with pytest.raises(PermissionDeniedError):
            _crea(admin, _user(), _user())
        RoleGrantService.grant(admin.id, GrantableRole.INSTRUCTOR, admin)
        db.session.commit()
        with pytest.raises(PermissionDeniedError):
            _crea(admin, _user(), _user())

    def test_l_istruttore_crea_col_referto_gia_aperto(self):
        marco, a, b = _istruttore(), _user(), _user()
        match = _crea(marco, a, b)

        assert match.status == MatchStatus.IN_PROGRESS
        assert match.scorer_id == marco.id
        assert match.description == DESCRIZIONE
        referto = TpaRefertoService.get_for_match(match.id)
        assert referto is not None and referto.compiler_id == marco.id
        for giocatore in (a, b):
            avvisi = _notifiche(giocatore, NotificationType.MATCH_ACCEPTED)
            assert len(avvisi) == 1
            assert DESCRIZIONE in avvisi[0].message

    def test_chi_segna_non_gioca(self):
        marco, b = _istruttore(), _user()
        with pytest.raises(ValidationError):
            _crea(marco, marco, b)
        with pytest.raises(ValidationError):
            _crea(marco, b, b)

    def test_disciplina_che_il_tpa_non_copre(self):
        with pytest.raises(ValidationError):
            _crea(
                _istruttore(),
                _user(),
                _user(),
                discipline=Discipline.STRAIGHT_POOL.value,
            )


@pytest.mark.integration
class TestReferto:
    def test_alla_distanza_nessuno_firma_d_ufficio(self):
        marco, a, b = _istruttore(), _user(), _user()
        match = _crea(marco, a, b)
        _vinci(match, marco, 1, 3)

        match = db.session.get(IndividualMatch, match.id)
        assert (match.player1_score, match.player2_score) == (3, 0)
        assert not match.player1_confirmed and not match.player2_confirmed
        assert not _notifiche(a, NotificationType.MATCH_RESULT_TO_CONFIRM)

    def test_i_giocatori_non_scrivono_il_referto(self):
        marco, a, b = _istruttore(), _user(), _user()
        match = _crea(marco, a, b)
        referto = TpaRefertoService.get_for_match(match.id)
        with pytest.raises(PermissionDeniedError):
            TpaRefertoService.press(referto.id, a.id, "seat:1")

    def test_a_meta_partita_il_referto_non_si_chiude(self):
        marco, a, b = _istruttore(), _user(), _user()
        match = _crea(marco, a, b)
        _vinci(match, marco, 1, 2)
        referto = TpaRefertoService.get_for_match(match.id)
        with pytest.raises(ConflictError):
            TpaRefertoService.close(referto.id, marco.id)

    def test_la_chiusura_avvisa_tutti_e_due_e_non_blocca_nessuno(self):
        _marco, a, b, match = _dichiarata()
        for giocatore in (a, b):
            avvisi = _notifiche(giocatore, NotificationType.MATCH_RESULT_TO_CONFIRM)
            assert len(avvisi) == 1
            assert DESCRIZIONE in avvisi[0].message
            PendingConfirmationService.ensure_none_pending(giocatore.id)
        assert match.awaits_decision_from(a.id) and match.awaits_decision_from(b.id)


@pytest.mark.integration
class TestDecisioni:
    def test_dichiarata_entra_nell_elo_di_tutte(self):
        _marco, _a, _b, match = _dichiarata()
        assert _righe_elo(match.id, RatingSystem.ELO_ALL) == 2
        assert _righe_elo(match.id, RatingSystem.ELO_GLOBAL) == 0

    def test_a_conferma_e_la_vede_confermata_b_in_attesa(self):
        _marco, a, b, match = _dichiarata()
        MatchLifecycleService.confirm_match_result(match.id, a.id)

        assert _nella_vista(match.id, Vista.CONFERMATE, a.id)
        assert not _nella_vista(match.id, Vista.CONFERMATE, b.id)
        assert _nella_vista(match.id, Vista.TUTTE, b.id)

        for giocatore, attesi in ((a, [Livello.CONFERMATA]), (b, [])):
            pagina, _stats = PlayerHistoryService.get_unified_match_history(
                giocatore.id, HistoryFilters(), vista=Vista.CONFERMATE
            )
            assert [v.livello for v in pagina.items if v.match_id == match.id] == (
                attesi
            )

    def test_entrambi_confermano_e_si_muove_l_elo_di_confermate(self):
        _marco, a, b, match = _dichiarata()
        MatchLifecycleService.confirm_match_result(match.id, a.id)
        MatchLifecycleService.confirm_match_result(match.id, b.id)

        match = db.session.get(IndividualMatch, match.id)
        assert match.status == MatchStatus.CONFIRMED_BY_BOTH
        assert match.winner_id == a.id
        assert _righe_elo(match.id, RatingSystem.ELO_GLOBAL) == 2

    def test_b_rifiuta_dopo_la_conferma_di_a_e_vale_il_rifiuto(self):
        """Regola del 2026-10-18: un rifiuto basta, per tutti e due."""
        _marco, a, b, match = _dichiarata()
        MatchLifecycleService.confirm_match_result(match.id, a.id)
        MatchLifecycleService.reject_match_result(match.id, b.id)

        match = db.session.get(IndividualMatch, match.id)
        assert match.status == MatchStatus.REJECTED
        assert (match.player1_score, match.player2_score) == (3, 0)
        for giocatore in (a, b):
            assert not _nella_vista(match.id, Vista.TUTTE, giocatore.id)
            assert not TpaStatsService.referti_for_user(giocatore.id, Vista.TUTTE)
            pagina, _stats = PlayerHistoryService.get_unified_match_history(
                giocatore.id, HistoryFilters(), vista=Vista.TUTTE
            )
            assert match.id not in [v.match_id for v in pagina.items]
            assert match.id not in [
                m.id for m in IndividualMatchService.get_user_matches(giocatore.id)
            ]
        assert not _nella_vista(match.id, Vista.TUTTE)
        assert _righe_elo(match.id, RatingSystem.ELO_ALL) == 0

    def test_il_rifiuto_avvisa_l_altro_e_chi_segna(self):
        marco, a, b, match = _dichiarata()
        MatchLifecycleService.reject_match_result(match.id, a.id)

        for chi in (b, marco):
            avvisi = _notifiche(chi, NotificationType.MATCH_CANCELLED)
            assert len(avvisi) == 1
            assert DESCRIZIONE in avvisi[0].message
            assert a.username in avvisi[0].message
        assert not _notifiche(a, NotificationType.MATCH_CANCELLED)

    def test_il_rifiuto_ritira_le_richieste_di_conferma_in_sospeso(self):
        _marco, a, b, match = _dichiarata()
        MatchLifecycleService.reject_match_result(match.id, a.id)
        for giocatore in (a, b):
            for avviso in _notifiche(
                giocatore, NotificationType.MATCH_RESULT_TO_CONFIRM
            ):
                assert avviso.status not in (
                    NotificationStatus.PENDING,
                    NotificationStatus.SENT,
                )

    def test_chi_segna_corregge_e_i_due_confermano_di_nuovo(self):
        marco, a, b, match = _dichiarata()
        MatchLifecycleService.confirm_match_result(match.id, a.id)
        MatchLifecycleService.reject_match_result(match.id, b.id)

        with pytest.raises(PermissionDeniedError):
            ScoredMatchService.reopen(match.id, a.id)
        ScoredMatchService.reopen(match.id, marco.id)
        match = db.session.get(IndividualMatch, match.id)
        assert match.status == MatchStatus.IN_PROGRESS
        assert not match.is_declared_by_scorer
        assert match.decision_of(a.id) is None and match.decision_of(b.id) is None

        # Marco toglie l'ultimo triangolo, lo riassegna a B e chiude: 2-1 e
        # poi 3-1, e i due ricevono di nuovo la richiesta.
        referto = TpaRefertoService.get_for_match(match.id)
        for _ in range(4):
            TpaRefertoService.undo(referto.id, marco.id)
        _vinci(match, marco, 2)
        _vinci(match, marco, 1)
        TpaRefertoService.close(referto.id, marco.id)
        match = db.session.get(IndividualMatch, match.id)
        assert (match.player1_score, match.player2_score) == (3, 1)
        for giocatore in (a, b):
            assert match.awaits_decision_from(giocatore.id)
            in_sospeso = [
                n
                for n in _notifiche(giocatore, NotificationType.MATCH_RESULT_TO_CONFIRM)
                if n.status in (NotificationStatus.PENDING, NotificationStatus.SENT)
            ]
            assert len(in_sospeso) == 1

        MatchLifecycleService.confirm_match_result(match.id, a.id)
        MatchLifecycleService.confirm_match_result(match.id, b.id)
        assert db.session.get(IndividualMatch, match.id).status == (
            MatchStatus.CONFIRMED_BY_BOTH
        )

    def test_chi_segna_cancella_la_rifiutata_anche_dopo_una_conferma(self):
        marco, a, b, match = _dichiarata()
        MatchLifecycleService.confirm_match_result(match.id, a.id)
        MatchLifecycleService.reject_match_result(match.id, b.id)
        with pytest.raises(PermissionDeniedError):
            MatchLifecycleService.cancel_match(match.id, a.id)
        MatchLifecycleService.cancel_match(match.id, marco.id)
        assert db.session.get(IndividualMatch, match.id).status == (
            MatchStatus.CANCELLED
        )

    def test_chi_segna_annulla_prima_delle_conferme_non_dopo(self):
        marco, a, b = _istruttore(), _user(), _user()
        match = _crea(marco, a, b)
        _vinci(match, marco, 2, 1)
        MatchLifecycleService.cancel_match(match.id, marco.id)
        assert db.session.get(IndividualMatch, match.id).status == (
            MatchStatus.CANCELLED
        )

        _m, a2, _b2, match2 = _dichiarata(scorer=marco)
        MatchLifecycleService.confirm_match_result(match2.id, a2.id)
        with pytest.raises(ConflictError):
            MatchLifecycleService.cancel_match(match2.id, marco.id)


@pytest.mark.integration
class TestPagine:
    def test_la_voce_in_match_la_vede_solo_chi_puo_segnare(self, app):
        voce = "Segna la partita di altri due"
        assert voce in _get(_client_for(app, _istruttore()), "/match/").get_data(
            as_text=True
        )
        assert voce not in _get(_client_for(app, _user()), "/match/").get_data(
            as_text=True
        )
        risposta = _get(_client_for(app, _user()), "/match/scored")
        assert risposta.status_code in (302, 403)

    def test_il_modulo_crea_e_porta_al_referto(self, app):
        marco, a, b = _istruttore(), _user(), _user()
        risposta = _post(
            _client_for(app, marco),
            "/match/scored",
            data={
                "player1_id": a.id,
                "player2_id": b.id,
                "description": DESCRIZIONE,
                "discipline": Discipline.NINE_BALL.value,
                "match_format": "single",
                "distance": 3,
                "is_race_to": "true",
            },
        )
        assert risposta.status_code == 302
        match = IndividualMatch.query.filter_by(scorer_id=marco.id).one()
        assert risposta.headers["Location"].endswith(f"/match/matches/{match.id}/tpa")

    def test_il_giocatore_non_vede_continua_ma_conferma_o_rifiuta(self, app):
        marco, a, b = _istruttore(), _user(), _user()
        match = _crea(marco, a, b)
        client = _client_for(app, a)

        pagina = _get(client, f"/match/matches/{match.id}").get_data(as_text=True)
        assert "c7-rackpad__btn" not in pagina
        assert marco.username in pagina

        dashboard = _get(client, "/match/").get_data(as_text=True)
        assert "Continua" not in dashboard

        _vinci(match, marco, 1, 3)
        TpaRefertoService.close(TpaRefertoService.get_for_match(match.id).id, marco.id)
        pagina = _get(client, f"/match/matches/{match.id}").get_data(as_text=True)
        assert f"/match/matches/{match.id}/confirm" in pagina
        assert f"/match/matches/{match.id}/reject" in pagina

        _post(client, f"/match/matches/{match.id}/reject")
        match = db.session.get(IndividualMatch, match.id)
        assert match.player1_rejected_at is not None
        assert match.status == MatchStatus.REJECTED
        assert match.player1_score == 3

    def test_la_rifiutata_sparisce_ai_giocatori_e_resta_a_chi_segna(self, app):
        marco, a, b, match = _dichiarata()
        MatchLifecycleService.confirm_match_result(match.id, a.id)
        MatchLifecycleService.reject_match_result(match.id, b.id)
        dettaglio = f"/match/matches/{match.id}"

        for giocatore in (a, b):
            client = _client_for(app, giocatore)
            for pagina in ("/match/", "/match/matches"):
                assert dettaglio not in _get(client, pagina).get_data(as_text=True)
            risposta = _get(client, dettaglio)
            assert risposta.status_code == 302
            assert _get(client, f"{dettaglio}/tpa").status_code == 302

        client = _client_for(app, marco)
        dashboard = _get(client, "/match/").get_data(as_text=True)
        assert dettaglio in dashboard and "Rifiutata" in dashboard
        pagina = _get(client, dettaglio).get_data(as_text=True)
        assert f"{dettaglio}/reopen" in pagina
        assert f"{dettaglio}/cancel" in pagina
        assert "Correggi la partita" in pagina and "Cancella la partita" in pagina

    def test_la_correzione_dalla_pagina_porta_al_referto(self, app):
        marco, a, b, match = _dichiarata()
        MatchLifecycleService.reject_match_result(match.id, b.id)
        risposta = _post(_client_for(app, a), f"/match/matches/{match.id}/reopen")
        assert db.session.get(IndividualMatch, match.id).status == (
            MatchStatus.REJECTED
        )
        assert risposta.status_code in (302, 403)

        risposta = _post(_client_for(app, marco), f"/match/matches/{match.id}/reopen")
        assert risposta.status_code == 302
        assert risposta.headers["Location"].endswith(f"/match/matches/{match.id}/tpa")
        assert db.session.get(IndividualMatch, match.id).status == (
            MatchStatus.IN_PROGRESS
        )

    def test_chi_segna_apre_pagina_e_referto(self, app):
        marco, a, b = _istruttore(), _user(), _user()
        match = _crea(marco, a, b)
        client = _client_for(app, marco)
        assert _get(client, f"/match/matches/{match.id}").status_code == 200
        assert _get(client, f"/match/matches/{match.id}/tpa").status_code == 200
        assert "Partite che segni" in _get(client, "/match/").get_data(as_text=True)

    def test_l_admin_non_vede_e_non_usa_il_modulo(self, app):
        """L'admin non segna partite (2026-10-18): niente modulo, e la
        creazione mandata a mano non crea niente."""
        admin = _user(UserRole.ADMIN.value)
        client = _client_for(app, admin)
        assert _get(client, "/match/scored").status_code in (302, 403)
        risposta = _post(
            client,
            "/match/scored",
            data={"player1_id": _user().id, "player2_id": _user().id},
        )
        assert risposta.status_code in (302, 403)
        assert IndividualMatch.query.filter_by(scorer_id=admin.id).count() == 0
        for pagina in ("/", "/dashboard", "/match/"):
            html = _get(client, pagina).get_data(as_text=True)
            assert "/match/scored" not in html

    def test_un_estraneo_non_legge_il_referto(self, app):
        marco, a, b = _istruttore(), _user(), _user()
        match = _crea(marco, a, b)
        risposta = _get(_client_for(app, _user()), f"/match/matches/{match.id}/tpa")
        assert risposta.status_code == 302
