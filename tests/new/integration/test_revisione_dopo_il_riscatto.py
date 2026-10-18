"""Dopo il riscatto, chi ha riscattato rivede le partite del non registrato.

Regola del 2026-10-18 sera, decisa dall'utente (emendamenti agli ADR-085 e
ADR-086):

    «Quando un match con giocatore aggiunto finisce non deve aspettare la
    conferma da parte del giocatore aggiunto. Eventualmente, se qualcuno
    riscatta l'utente, allora gli si può chiedere se vuole rivedere tutti i
    match passati ed eventualmente contestarne alcuni oppure riconoscerli
    tutti oppure contestarli tutti. I match contestati rimangono all'utente
    che li ha registrati come contestati e contribuiscono a ELO solo nel
    calcolo più generale.»

Il percorso dalle route: invito, pagina di revisione, i tre esiti, la
contestata che resta a chi l'ha registrata e sparisce per chi l'ha
contestata, la partita di altri due in cui il non registrato era un
giocatore, e la revisione che non blocca niente. UC14 di
``docs/usecases/sfide-e-certificazione.md``.
"""

from __future__ import annotations

import uuid

import pytest
from flask import g

from models import User, db
from models.certificazione import (
    Livello,
    Vista,
    livello_di_sfida,
    livello_di_sfida_per,
    sfide_della_vista,
)
from models.individual_match.individual_rack_service import IndividualRackService
from models.individual_match.models import IndividualMatch
from models.individual_match.quick_match_service import QuickMatchService
from models.individual_match.revisione import RevisioneService
from models.individual_match.scored_match_service import ScoredMatchService
from models.individual_match.statistics_service import (
    IndividualMatchStatisticsService,
)
from models.notification.models import Notification, NotificationType
from models.player.history_service import HistoryFilters, PlayerHistoryService
from models.rating.models import MatchRatingHistory, RatingSystem
from models.status_enum import Discipline, MatchStatus
from models.tpa.services import TpaRefertoService
from models.user.claim_service import ClaimService
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService
from models.user.services import UserService


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"rv_{uid}",
        email=f"rv_{uid}@test.com",
        role=role,
        gamification_override=True,
        onboarding_completed=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


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


def _placeholder(creatore: User) -> User:
    giocatore = UserService.create_placeholder(
        "Gino", f"Verdi{uuid.uuid4().hex[:5]}", creatore
    )
    db.session.commit()
    return giocatore


def _registrata(creatore: User, gino: User, vince_il_creatore=True) -> IndividualMatch:
    """Il creatore apre la sfida contro Gino e la porta alla distanza (al 3)."""
    match = QuickMatchService.start(
        creatore.id, gino.id, {"match_format": "single", "distance": 3}
    )
    db.session.commit()
    vincitore = creatore.id if vince_il_creatore else gino.id
    for _ in range(3):
        IndividualRackService.add_rack_for_player(match.id, creatore.id, vincitore)
    db.session.commit()
    match = db.session.get(IndividualMatch, match.id)
    assert match is not None and match.is_recorded_by_one
    return match


def _riscatta(gino: User, creatore: User) -> User:
    luca = _user()
    richiesta = ClaimService.richiedi(gino.id, luca)
    db.session.commit()
    ClaimService.approve(richiesta.id, creatore)
    db.session.commit()
    return luca


def _scenario(quante=2):
    """Marco registra ``quante`` sfide contro Gino; Luca riscatta Gino."""
    marco = _user(UserRole.DIRECTOR.value)
    gino = _placeholder(marco)
    partite = [_registrata(marco, gino) for _ in range(quante)]
    luca = _riscatta(gino, marco)
    return marco, luca, [p.id for p in partite]


def _nella_vista(match_id, vista, user_id=None) -> bool:
    return (
        db.session.query(IndividualMatch.id)
        .filter(
            IndividualMatch.id == match_id, sfide_della_vista(vista, user_id=user_id)
        )
        .first()
        is not None
    )


def _nel_pool(match_id, sistema) -> bool:
    return MatchRatingHistory.exists_for_individual_match(match_id, sistema)


def _rivedi(client, partite, azione, contesta=()):
    return _post(
        client,
        "/match/revisione",
        data={"partite": partite, "azione": azione, "contesta": list(contesta)},
    )


@pytest.mark.integration
class TestInvito:
    def test_il_riscatto_porta_l_invito_e_la_pagina(self, app):
        _marco, luca, partite = _scenario(2)

        inviti = Notification.query.filter_by(
            user_id=luca.id, action_url="/match/revisione"
        ).all()
        assert len(inviti) == 1
        assert inviti[0].notification_type == NotificationType.MATCH_RESULT_TO_CONFIRM

        client = _client_for(app, luca)
        pagina = _get(client, "/match/revisione").get_data(as_text=True)
        assert "Partite da rivedere" in pagina
        for match_id in partite:
            assert f'name="partite" value="{match_id}"' in pagina
        elenco = _get(client, "/match/matches").get_data(as_text=True)
        assert "/match/revisione" in elenco
        assert "Da rivedere" in elenco

    def test_senza_partite_niente_invito(self, app):
        marco = _user(UserRole.DIRECTOR.value)
        gino = _placeholder(marco)
        luca = _riscatta(gino, marco)
        assert (
            Notification.query.filter_by(
                user_id=luca.id, action_url="/match/revisione"
            ).count()
            == 0
        )


@pytest.mark.integration
class TestRiconosciTutte:
    def test_diventano_confermate_e_vanno_nell_elo_globale(self, app):
        _marco, luca, partite = _scenario(2)
        for match_id in partite:
            assert not _nel_pool(match_id, RatingSystem.ELO_GLOBAL)

        risposta = _rivedi(_client_for(app, luca), partite, "riconosci_tutte")

        assert risposta.status_code == 302
        for match_id in partite:
            match = db.session.get(IndividualMatch, match_id)
            assert match.status == MatchStatus.CONFIRMED_BY_BOTH
            assert livello_di_sfida(match) is Livello.CONFERMATA
            assert _nella_vista(match_id, Vista.CONFERMATE, user_id=luca.id)
            assert _nel_pool(match_id, RatingSystem.ELO_GLOBAL)
            assert _nel_pool(match_id, RatingSystem.ELO_ALL)
        assert RevisioneService.da_rivedere(luca.id) == []


@pytest.mark.integration
class TestContestazione:
    def _controlla_contestata(self, match_id, marco, luca):
        match = db.session.get(IndividualMatch, match_id)
        assert match.status == MatchStatus.CLOSED_UNILATERALLY
        assert match.is_contested
        # A chi l'ha registrata resta, contestata, solo fra «Tutte».
        assert livello_di_sfida_per(match, marco.id) is Livello.IN_ATTESA
        assert _nella_vista(match_id, Vista.TUTTE, user_id=marco.id)
        assert not _nella_vista(match_id, Vista.CONFERMATE, user_id=marco.id)
        # Nell'ELO conta solo nel calcolo più generale.
        assert _nel_pool(match_id, RatingSystem.ELO_ALL)
        assert not _nel_pool(match_id, RatingSystem.ELO_GLOBAL)
        # Per chi l'ha contestata sparisce: liste, viste, statistiche.
        assert livello_di_sfida_per(match, luca.id) is None
        assert not _nella_vista(match_id, Vista.TUTTE, user_id=luca.id)
        assert match_id not in {
            m.id for m in IndividualMatchStatisticsService.get_user_matches(luca.id)
        }
        storico, _stats = PlayerHistoryService.get_unified_match_history(
            luca.id, HistoryFilters(), vista=Vista.TUTTE
        )
        assert match_id not in {v.match_id for v in storico.items}
        storico_marco, _stats = PlayerHistoryService.get_unified_match_history(
            marco.id, HistoryFilters(), vista=Vista.TUTTE
        )
        voce = next(v for v in storico_marco.items if v.match_id == match_id)
        assert voce.firma == "contestata"

    def test_contesta_tutte(self, app):
        marco, luca, partite = _scenario(2)

        risposta = _rivedi(_client_for(app, luca), partite, "contesta_tutte")

        assert risposta.status_code == 302
        for match_id in partite:
            self._controlla_contestata(match_id, marco, luca)
            # Chi l'ha registrata riceve l'avviso.
            assert (
                Notification.query.filter_by(
                    user_id=marco.id, action_url=f"/match/matches/{match_id}"
                ).count()
                == 1
            )
        # Marco la vede, contestata; Luca no.
        marco_client = _client_for(app, marco)
        pagina = _get(marco_client, f"/match/matches/{partite[0]}").get_data(
            as_text=True
        )
        assert "Contestata" in pagina
        assert "Contestata" in _get(marco_client, "/match/matches").get_data(
            as_text=True
        )
        assert (
            _get(_client_for(app, luca), f"/match/matches/{partite[0]}").status_code
            == 302
        )
        assert RevisioneService.da_rivedere(luca.id) == []

    def test_contestazione_selettiva(self, app):
        marco, luca, partite = _scenario(3)
        contestata, *riconosciute = partite

        risposta = _rivedi(
            _client_for(app, luca), partite, "scegli", contesta=[contestata]
        )

        assert risposta.status_code == 302
        self._controlla_contestata(contestata, marco, luca)
        for match_id in riconosciute:
            match = db.session.get(IndividualMatch, match_id)
            assert match.status == MatchStatus.CONFIRMED_BY_BOTH
            assert _nel_pool(match_id, RatingSystem.ELO_GLOBAL)

    def test_dalla_pagina_della_sfida(self, app):
        marco, luca, (match_id,) = _scenario(1)
        client = _client_for(app, luca)
        pagina = _get(client, f"/match/matches/{match_id}").get_data(as_text=True)
        assert "La riconosco" in pagina and "La contesto" in pagina

        _rivedi(client, [match_id], "contesta_tutte")

        self._controlla_contestata(match_id, marco, luca)


@pytest.mark.integration
class TestPartitaDiAltriDue:
    """Il non registrato era uno dei due giocatori di una partita segnata da
    un istruttore (ADR-084): contestare è rifiutare, riconoscere è
    confermare, con le regole già in vigore."""

    def _di_un_terzo(self):
        admin = _user(UserRole.ADMIN.value)
        istruttore = _user()
        RoleGrantService.grant(istruttore.id, GrantableRole.INSTRUCTOR, admin)
        db.session.commit()
        anna = _user()
        gino = _placeholder(istruttore)
        match = ScoredMatchService.start(
            istruttore,
            anna.id,
            gino.id,
            {"discipline": Discipline.NINE_BALL.value, "distance": 3},
        )
        referto = TpaRefertoService.get_for_match(match.id)
        for _ in range(3):
            for comando in ("seat:1", "1", "9", "end"):
                TpaRefertoService.press(referto.id, istruttore.id, comando)
        TpaRefertoService.close(referto.id, istruttore.id)
        db.session.commit()
        luca = _riscatta(gino, istruttore)
        return istruttore, anna, luca, match.id

    def test_riconoscere_e_confermare(self, app):
        _istruttore, _anna, luca, match_id = self._di_un_terzo()
        assert match_id in {m.id for m in RevisioneService.da_rivedere(luca.id)}

        _rivedi(_client_for(app, luca), [match_id], "riconosci_tutte")

        match = db.session.get(IndividualMatch, match_id)
        assert match.decision_of(luca.id) == "confirmed"
        assert livello_di_sfida_per(match, luca.id) is Livello.CONFERMATA

    def test_contestare_e_rifiutare(self, app):
        _istruttore, anna, luca, match_id = self._di_un_terzo()

        _rivedi(_client_for(app, luca), [match_id], "contesta_tutte")

        match = db.session.get(IndividualMatch, match_id)
        assert match.status == MatchStatus.REJECTED
        assert match.is_hidden_from(luca.id) and match.is_hidden_from(anna.id)


@pytest.mark.integration
class TestNonBlocca:
    def test_le_partite_non_rivedute_restano_e_non_bloccano(self, app):
        marco, luca, partite = _scenario(2)

        # Senza revisione: restano registrate da uno, In attesa, anche per lui.
        for match_id in partite:
            match = db.session.get(IndividualMatch, match_id)
            assert match.is_recorded_by_one and not match.is_contested
            assert livello_di_sfida_per(match, luca.id) is Livello.IN_ATTESA
            assert _nella_vista(match_id, Vista.TUTTE, user_id=luca.id)
        # E lui apre sfide nuove, contro chiunque, anche contro Marco.
        client = _client_for(app, luca)
        risposta = _post(
            client,
            "/match/quick",
            json={"opponent_id": marco.id, "match_format": "single", "distance": 3},
        )
        assert risposta.status_code == 200, risposta.get_data(as_text=True)[:300]

    def test_chi_ha_registrato_la_ritira_anche_durante_la_revisione(self, app):
        marco, luca, (match_id,) = _scenario(1)

        _post(_client_for(app, marco), f"/match/matches/{match_id}/withdraw")

        assert db.session.get(IndividualMatch, match_id).status == MatchStatus.CANCELLED
        assert RevisioneService.da_rivedere(luca.id) == []
        # Lui, che la stava rivedendo, ne riceve l'avviso.
        assert (
            Notification.query.filter_by(
                user_id=luca.id, notification_type=NotificationType.MATCH_CANCELLED
            ).count()
            == 1
        )

    def test_chi_rivede_non_la_ritira(self, app):
        _marco, luca, (match_id,) = _scenario(1)
        _post(_client_for(app, luca), f"/match/matches/{match_id}/withdraw")
        assert db.session.get(IndividualMatch, match_id).is_recorded_by_one


@pytest.mark.integration
class TestSoloLePartiteRiscattate:
    """La revisione mostra solo le partite che erano del non registrato
    (emendamento del 2026-10-18 sera all'ADR-086).

    Fino a questa data compariva ogni partita di altri due che aspettava una
    decisione di chi aveva riscattato, anche quelle in cui era un giocatore
    dall'inizio: dopo l'unione non restava traccia di quali fossero di Gino.
    Ora `ClaimService.approve` lo annota prima dell'unione.
    """

    @staticmethod
    def _istruttore():
        admin = _user(UserRole.ADMIN.value)
        istruttore = _user()
        RoleGrantService.grant(istruttore.id, GrantableRole.INSTRUCTOR, admin)
        db.session.commit()
        return istruttore

    @staticmethod
    def _dichiarata(istruttore, player1_id, player2_id) -> int:
        match = ScoredMatchService.start(
            istruttore,
            player1_id,
            player2_id,
            {"discipline": Discipline.NINE_BALL.value, "distance": 3},
        )
        referto = TpaRefertoService.get_for_match(match.id)
        for _ in range(3):
            for comando in ("seat:1", "1", "9", "end"):
                TpaRefertoService.press(referto.id, istruttore.id, comando)
        TpaRefertoService.close(referto.id, istruttore.id)
        db.session.commit()
        return match.id

    def _scenario(self):
        """Luca, già registrato, ha una partita sua segnata da un istruttore
        e ancora da decidere; poi riscatta Gino, che ne aveva una sua e una
        sfida registrata da Marco."""
        istruttore = self._istruttore()
        marco = _user(UserRole.DIRECTOR.value)
        anna, luca = _user(), _user()
        gino = _placeholder(istruttore)
        sua = self._dichiarata(istruttore, luca.id, anna.id)
        di_gino = self._dichiarata(istruttore, anna.id, gino.id)
        registrata = _registrata(marco, gino).id

        richiesta = ClaimService.richiedi(gino.id, luca)
        db.session.commit()
        ClaimService.approve(richiesta.id, istruttore)
        db.session.commit()
        return luca, richiesta.id, sua, di_gino, registrata

    def test_la_partita_che_era_gia_sua_non_si_rivede(self, app):
        luca, _richiesta, sua, di_gino, registrata = self._scenario()

        da_rivedere = {m.id for m in RevisioneService.da_rivedere(luca.id)}
        assert da_rivedere == {di_gino, registrata}
        # Resta da decidere, dalla sua pagina, come sempre.
        assert db.session.get(IndividualMatch, sua).awaits_decision_from(luca.id)

        pagina = _get(_client_for(app, luca), "/match/revisione").get_data(as_text=True)
        assert f'name="partite" value="{di_gino}"' in pagina
        assert f'name="partite" value="{sua}"' not in pagina

    def test_la_traccia_si_scrive_prima_dell_unione(self):
        from models.user.claim_request import ClaimRequestMatch

        _luca, richiesta_id, sua, di_gino, registrata = self._scenario()

        annotate = {
            riga.individual_match_id
            for riga in ClaimRequestMatch.query.filter_by(request_id=richiesta_id)
        }
        assert annotate == {di_gino, registrata}
        assert sua not in annotate

    def test_l_invito_conta_solo_le_partite_del_riscatto(self):
        luca, _richiesta, _sua, _di_gino, _registrata = self._scenario()

        (invito,) = Notification.query.filter_by(
            user_id=luca.id, action_url="/match/revisione"
        ).all()
        assert "2 partite" in invito.message

    def test_riscatto_senza_traccia_valgono_le_registrate_da_uno(self):
        """I riscatti approvati prima della traccia: le partite di altri due
        non si sa più di chi fossero, quindi non compaiono; le registrate da
        uno vengono per forza da un non registrato, e restano."""
        from models.user.claim_request import ClaimRequestMatch

        luca, richiesta_id, _sua, di_gino, registrata = self._scenario()
        ClaimRequestMatch.query.filter_by(request_id=richiesta_id).delete()
        db.session.commit()

        assert {m.id for m in RevisioneService.da_rivedere(luca.id)} == {registrata}
        assert db.session.get(IndividualMatch, di_gino).awaits_decision_from(luca.id)
