"""Test E2E ADR-027: round-level configuration overrides.

Verifica end-to-end:
1. Override per turno persistito via API endpoint
2. Round creation popola correttamente i campi del Match (match_distance,
   is_race_to, discipline) sulla base di RoundConfiguration
3. Scoring/validation usa Distance VO del match (non della gara), quindi
   i match del turno con override accettano la distanza override e
   rifiutano quella della gara.

Sintomo originale (produzione, gara dell'utente paolo):
- Gara exact-5, override turno 2/4 a exact-4
- Frontend pretendeva 5 rack ma backend chiudeva i match a 4
- Cause: RoundConfiguration era dead code (UI salvava in localStorage),
  inoltre scoring usava `match.gara.distance` invece di `match.distance_config`
"""

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Match, User
from models.base import utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.round_configuration import RoundConfiguration
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.match.scoring_service import ScoringService
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole


@pytest.mark.integration
class TestRoundOverridesEndToEnd:
    """Override per turno: persistenza, propagazione e enforcement."""

    @pytest.fixture
    def director(self, db_session) -> User:
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"dir_{unique_id}",
            email=f"dir_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()
        return director

    @pytest.fixture
    def players_8(self, db_session) -> list[User]:
        batch = str(uuid.uuid4())[:8]
        out = []
        for i in range(8):
            p = User(
                username=f"p_{i}_{batch}",
                email=f"p_{i}_{batch}@test.com",
                role=UserRole.PLAYER.value,
            )
            p.set_password("pwd")
            out.append(p)
        db_session.add_all(out)
        db_session.commit()
        return out

    def _make_gara(self, director: User, *, distance: int, is_race_to: bool) -> Gara:
        return GaraService.create_gara(
            campionato_id=None,
            number=1,
            name=f"ADR027 {uuid.uuid4().hex[:6]}",
            date=date.today() + timedelta(days=2),
            location="Test",
            description="adr027",
            rounds_count=2,
            min_participants=4,
            max_participants=10,
            entry_fee=0.0,
            discipline="palla_9",
            distance=distance,
            is_race_to=is_race_to,
            director_id=director.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

    def test_round_creation_propagates_override_to_match(
        self, director, players_8, db_session
    ):
        """Match del round con override hanno match_distance e is_race_to giusti."""
        # Gara: exact-5
        gara = self._make_gara(director, distance=5, is_race_to=False)

        # Override turno 2: exact-4 (palla_8)
        RoundConfiguration.create_or_update(
            gara_id=gara.id,
            round_number=2,
            distance=4,
            is_race_to=False,
            discipline="palla_8",
        )
        db_session.commit()

        # Iscrizioni e avvio
        InscriptionService.open_inscriptions(
            gara.id,
            utc_now() - timedelta(hours=1),
            utc_now() + timedelta(hours=1),
        )
        for p in players_8:
            InscriptionService.inscribe_user(p.id, gara.id)
        RoundService.start_first_round(gara.id)

        # Round 1: nessun override → eredita da gara
        r1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert r1_matches, "round 1 deve avere match"
        for m in r1_matches:
            assert (
                m.match_distance == 5
            ), f"round 1 match {m.id}: match_distance={m.match_distance}, atteso 5"
            # is_race_to=None su Match significa "eredita dalla gara"
            assert (
                m.effective_is_race_to is False
            ), f"round 1 match {m.id}: effective_is_race_to atteso False (exact)"
            assert m.get_effective_discipline() == "palla_9"

    def test_scoring_respects_round_override(self, director, players_8, db_session):
        """Round con override exact-4: il match accetta totale 4 rack, non 5.

        Questo è il test di regressione per il bug osservato in produzione.
        Il match.distance_config deve risolvere alla distanza del turno (4),
        non della gara (5).
        """
        # Gara: exact-5
        gara = self._make_gara(director, distance=5, is_race_to=False)

        # Override turno 1: exact-4. Mettiamo l'override sul turno 1 perché è
        # quello che parte subito ed è facile da testare.
        RoundConfiguration.create_or_update(
            gara_id=gara.id,
            round_number=1,
            distance=4,
            is_race_to=False,
        )
        db_session.commit()

        InscriptionService.open_inscriptions(
            gara.id,
            utc_now() - timedelta(hours=1),
            utc_now() + timedelta(hours=1),
        )
        for p in players_8:
            InscriptionService.inscribe_user(p.id, gara.id)
        RoundService.start_first_round(gara.id)

        match = Match.query.filter_by(
            gara_id=gara.id, round_number=1, is_bye=False
        ).first()
        assert match is not None
        assert match.match_distance == 4
        assert match.effective_distance == 4
        assert match.effective_is_race_to is False

        distance = match.distance_config
        assert distance.racks == 4
        assert distance.is_race_to_racks is False

        # Set 2-2 (totale 4) deve essere ACCETTATO come completo (tie in exact).
        # Senza ADR-027, lo scoring chiedeva totale 5 (gara.distance) e
        # rifiutava il 2-2 come "incompleto".
        ScoringService.set_match_result_direct(match.id, 2, 2)

        db_session.refresh(match)
        assert match.player1_score == 2
        assert match.player2_score == 2

        # Set 3-2 (totale 5) deve essere RIFIUTATO perché eccede exact-4.
        with pytest.raises(ValueError):
            ScoringService.set_match_result_direct(match.id, 3, 2)


@pytest.mark.integration
class TestRoundConfigAPIEnforcement:
    """API round-config: persistenza e blocco fuori da setup."""

    @pytest.fixture
    def admin_client(self, app, db_session):
        username = f"adm_{uuid.uuid4().hex[:6]}"
        admin = User(
            username=username,
            email=f"{username}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("pwd")
        db_session.add(admin)
        db_session.commit()
        client = app.test_client()
        # Login via POST all'auth endpoint per sessione coerente con il
        # pattern dei test esistenti (vedi test_admin_inscribe_user.py).
        client.post(
            "/auth/login",
            data={"username": username, "password": "pwd"},
            follow_redirects=True,
        )
        return client, admin

    @pytest.fixture
    def gara_setup(self, db_session, admin_client) -> Gara:
        _, admin = admin_client
        return GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="API test",
            date=date.today() + timedelta(days=2),
            location="Test",
            description="api",
            rounds_count=3,
            min_participants=4,
            max_participants=8,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=False,
            director_id=admin.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )

    def test_post_creates_override(self, admin_client, gara_setup, db_session):
        client, _ = admin_client
        resp = client.post(
            f"/admin/gara/{gara_setup.id}/round-config/2",
            json={"distance": 4, "is_race_to": False, "discipline": "palla_8"},
        )
        assert resp.status_code == 200, resp.data
        data = resp.get_json()
        assert data["success"] is True
        assert data["config"]["distance"] == 4
        assert data["config"]["is_race_to"] is False

        # Verifica persistenza
        cfg = RoundConfiguration.get_for_gara_round(gara_setup.id, 2)
        assert cfg is not None
        assert cfg.distance == 4
        assert cfg.is_race_to is False

    def test_get_lists_overrides(self, admin_client, gara_setup, db_session):
        client, _ = admin_client
        # Crea due override
        RoundConfiguration.create_or_update(
            gara_id=gara_setup.id, round_number=1, distance=3
        )
        RoundConfiguration.create_or_update(
            gara_id=gara_setup.id, round_number=3, distance=4, is_race_to=True
        )
        db_session.commit()

        resp = client.get(f"/admin/gara/{gara_setup.id}/round-config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["rounds_count"] == 3
        assert data["defaults"]["distance"] == 5
        rounds = {o["round_number"]: o for o in data["overrides"]}
        assert 1 in rounds and rounds[1]["distance"] == 3
        assert 3 in rounds and rounds[3]["is_race_to"] is True

    def test_delete_removes_override(self, admin_client, gara_setup, db_session):
        client, _ = admin_client
        RoundConfiguration.create_or_update(
            gara_id=gara_setup.id, round_number=2, distance=4
        )
        db_session.commit()

        resp = client.delete(f"/admin/gara/{gara_setup.id}/round-config/2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["deleted"] is True

        assert RoundConfiguration.get_for_gara_round(gara_setup.id, 2) is None

    def test_post_blocked_outside_setup(self, admin_client, gara_setup, db_session):
        """Una volta aperte le iscrizioni, gli override sono congelati."""
        client, _ = admin_client
        gara_setup.status = GaraStatus.INSCRIPTION.value
        db_session.commit()

        resp = client.post(
            f"/admin/gara/{gara_setup.id}/round-config/1",
            json={"distance": 4},
        )
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["success"] is False
        assert RoundConfiguration.get_for_gara_round(gara_setup.id, 1) is None
