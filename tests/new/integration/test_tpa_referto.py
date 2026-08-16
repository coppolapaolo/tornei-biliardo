"""Il referto TPA su un match individuale: chi puo' aprirlo, chi puo' scriverci
e come il punteggio del match ne discende.

Il conto degli errori non si verifica qui — quello e' il motore, e ha i suoi
test. Qui si verifica il contorno: i permessi, le condizioni di apertura, e
soprattutto che **il punteggio del match e il referto non possano divergere**,
nemmeno annullando.
"""

from __future__ import annotations

import json
import uuid

import pytest

from models import db
from models.base import utc_now
from models.exceptions import ConflictError, PermissionDeniedError, ValidationError
from models.individual_match.models import IndividualMatch, IndividualRack
from models.status_enum import Discipline, MatchStatus
from models.tpa.services import FEATURE_CODE, TpaRefertoService
from models.user.models import User
from models.user.role_enum import UserRole
from datetime import timedelta


def _player(prefix: str) -> User:
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"{prefix}_{unique}",
        email=f"{prefix}_{unique}@test.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("test123")
    db.session.add(user)
    db.session.commit()
    return user


def _match(player1: User, player2: User, **overrides) -> IndividualMatch:
    data = dict(
        player1_id=player1.id,
        player2_id=player2.id,
        location="Sala di prova",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=MatchStatus.IN_PROGRESS,
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
        player1_score=0,
        player2_score=0,
    )
    data.update(overrides)
    match = IndividualMatch(**data)
    db.session.add(match)
    db.session.commit()
    return match


@pytest.fixture
def players(app):
    with app.app_context():
        yield _player("p1"), _player("p2")


class TestApertura:
    """Chi puo' prendere il referto, e su cosa."""

    def test_un_giocatore_apre_il_referto_e_ne_diventa_il_compilatore(
        self, app, players
    ):
        with app.app_context():
            one, two = players
            match = _match(one, two)

            referto = TpaRefertoService.open_referto(match.id, one.id)

            assert referto.compiler_id == one.id
            assert referto.game_type == 9
            assert referto.is_closed is False
            assert TpaRefertoService.get_for_match(match.id) is not None

    def test_chi_non_gioca_il_match_non_apre_niente(self, app, players):
        with app.app_context():
            one, two = players
            estraneo = _player("estraneo")
            match = _match(one, two)

            with pytest.raises(ValidationError):
                TpaRefertoService.open_referto(match.id, estraneo.id)

    def test_il_secondo_referto_non_si_apre(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)

            with pytest.raises(ConflictError):
                TpaRefertoService.open_referto(match.id, two.id)

    @pytest.mark.parametrize(
        "discipline",
        [
            Discipline.ONE_POCKET.value,
            Discipline.STRAIGHT_POOL.value,
            Discipline.BANK_POOL.value,
        ],
    )
    def test_le_discipline_senza_tpa_lo_dicono(self, app, players, discipline):
        """Il TPA e' definito per palla 8, 9 e 10. Altrove non vuol dire niente."""
        with app.app_context():
            one, two = players
            match = _match(one, two, discipline=discipline)

            assert TpaRefertoService.can_open(match, one.id) is False
            with pytest.raises(ValidationError):
                TpaRefertoService.open_referto(match.id, one.id)

    @pytest.mark.parametrize(
        "discipline,atteso",
        [
            (Discipline.EIGHT_BALL.value, 8),
            (Discipline.NINE_BALL.value, 9),
            (Discipline.TEN_BALL.value, 10),
            ("palla_9", 9),  # vocabolario storico, tradotto da Discipline.normalize
        ],
    )
    def test_le_discipline_col_tpa_fissano_le_bilie_del_rack(self, discipline, atteso):
        assert TpaRefertoService.game_type_for(discipline) == atteso

    def test_a_match_non_iniziato_non_si_apre(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two, status=MatchStatus.SCHEDULED)

            assert TpaRefertoService.can_open(match, one.id) is False

    def test_con_dei_rack_gia_segnati_non_si_apre(self, app, players):
        """Il referto parte da 0-0: aprirlo dopo vorrebbe dire cancellare rack veri."""
        with app.app_context():
            one, two = players
            match = _match(one, two, player1_score=2)

            assert TpaRefertoService.can_open(match, one.id) is False
            assert "rack" in (TpaRefertoService.blocking_reason(match, one.id) or "")

    def test_sui_match_a_set_non_si_apre(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two, is_multi_set=True, match_distance=3)

            assert TpaRefertoService.can_open(match, one.id) is False


class TestCompilazione:
    """Il registro dei comandi e le sue difese."""

    def test_solo_il_compilatore_scrive(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            with pytest.raises(PermissionDeniedError):
                TpaRefertoService.press(referto.id, two.id, "1")

    def test_un_comando_che_il_tastierino_non_proponeva_viene_rifiutato(
        self, app, players
    ):
        """La difesa e' contro un client fuori sincrono, non contro l'utente."""
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            # A inizio rack si annotano le bilie: `M` non e' ancora possibile.
            with pytest.raises(ValidationError):
                TpaRefertoService.press(referto.id, one.id, "M")

            # E un comando che non esiste proprio.
            with pytest.raises(ValidationError):
                TpaRefertoService.press(referto.id, one.id, "Z")

    def test_il_tavolo_non_passa_a_turno_incompleto(self, app, players):
        """Manca il perche' il turno e' finito: il referto non lo lascia in bianco."""
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            TpaRefertoService.press(referto.id, one.id, "1")  # bilie sulla spaccata
            TpaRefertoService.press(referto.id, one.id, "3")  # bilie in tutto

            with pytest.raises(ValidationError):
                TpaRefertoService.press(referto.id, one.id, "end")

            TpaRefertoService.press(referto.id, one.id, "M")
            state = TpaRefertoService.press(referto.id, one.id, "end")
            assert state.current_player == 2

    def test_chi_spacca_si_puo_cambiare_prima_di_annotare(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            state = TpaRefertoService.press(referto.id, one.id, "seat:2")
            assert state.current_player == 2
            assert state.turn().is_break() is True

            TpaRefertoService.press(referto.id, one.id, "0")
            with pytest.raises(ValidationError):
                TpaRefertoService.press(referto.id, one.id, "seat:1")

    def test_su_referto_chiuso_non_si_scrive_piu(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            TpaRefertoService.close(referto.id, one.id)

            with pytest.raises(ConflictError):
                TpaRefertoService.press(referto.id, one.id, "1")


class TestPunteggioDerivato:
    """Il punto della funzione: si segna una volta sola."""

    @staticmethod
    def _vinci_un_rack(referto_id: int, user_id: int, seat: int = 1) -> None:
        """Spacca imbucando tutto: nove bilie, rack chiuso.

        Il posto va dichiarato ogni volta: a rack finito il motore mette in
        spaccata l'avversario, come vuole la spaccata alternata.
        """
        TpaRefertoService.press(referto_id, user_id, f"seat:{seat}")
        TpaRefertoService.press(referto_id, user_id, "1")  # sulla spaccata
        TpaRefertoService.press(referto_id, user_id, "9")  # in tutto: chiude
        TpaRefertoService.press(referto_id, user_id, "end")

    def test_un_rack_vinto_nel_referto_diventa_un_rack_del_match(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            self._vinci_un_rack(referto.id, one.id)

            match = db.session.get(IndividualMatch, match.id)
            assert match.player1_score == 1
            assert match.player2_score == 0
            racks = IndividualRack.query.filter_by(
                match_id=match.id, is_deleted=False
            ).all()
            assert len(racks) == 1
            assert racks[0].winner_id == one.id

    def test_annullare_riporta_indietro_anche_il_punteggio(self, app, players):
        """E' la prova che le due cose sono una cosa sola."""
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            self._vinci_un_rack(referto.id, one.id)
            assert db.session.get(IndividualMatch, match.id).player1_score == 1

            TpaRefertoService.undo(referto.id, one.id)

            match = db.session.get(IndividualMatch, match.id)
            assert match.player1_score == 0
            assert (
                IndividualRack.query.filter_by(
                    match_id=match.id, is_deleted=False
                ).count()
                == 0
            )

    def test_annullare_toglie_un_comando_per_volta(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            TpaRefertoService.press(referto.id, one.id, "1")
            TpaRefertoService.press(referto.id, one.id, "3")

            state = TpaRefertoService.undo(referto.id, one.id)

            assert state.turn().annotation.break_potted == 1
            assert state.turn().annotation.total_potted is None

    def test_senza_niente_da_annullare_lo_dice(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            with pytest.raises(ConflictError):
                TpaRefertoService.undo(referto.id, one.id)

    def test_alla_distanza_il_match_e_pronto_per_la_conferma(self, app, players):
        """Cinque rack a zero al 5: il referto porta il match a fine corsa."""
        with app.app_context():
            one, two = players
            match = _match(one, two, distance=5)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            for _ in range(5):
                self._vinci_un_rack(referto.id, one.id)

            match = db.session.get(IndividualMatch, match.id)
            assert match.player1_score == 5
            assert match.is_ready_for_validation() is True
            # Chi e' avanti conferma da solo: manca la firma dell'avversario.
            assert match.player1_confirmed is True
            assert match.player2_confirmed is False


class TestRotte:
    """La superficie HTTP."""

    @staticmethod
    def _client(app, user: User):
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
        return client

    def test_la_pagina_si_apre_per_entrambi_i_giocatori(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)

            for user in (one, two):
                response = self._client(app, user).get(f"/match/matches/{match.id}/tpa")
                assert response.status_code == 200

    def test_chi_guarda_non_scrive(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)

            response = self._client(app, two).post(
                f"/match/matches/{match.id}/tpa/press",
                json={"command": "1"},
            )

            assert response.status_code == 403
            assert response.get_json()["success"] is False

    def test_il_compilatore_annota_e_riceve_lo_stato_intero(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)

            response = self._client(app, one).post(
                f"/match/matches/{match.id}/tpa/press",
                json={"command": "1"},
            )

            assert response.status_code == 200
            state = response.get_json()["state"]
            assert state["can_write"] is True
            assert state["current"]["annotation"]["break_potted"] == 1
            # Il tastierino arriva col resto: il client non lo ricalcola.
            assert state["buttons"]

    def test_un_estraneo_al_match_non_vede_il_referto(self, app, players):
        with app.app_context():
            one, two = players
            estraneo = _player("estraneo")
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)

            response = self._client(app, estraneo).get(
                f"/match/matches/{match.id}/tpa/state"
            )
            assert response.status_code == 404

    def test_lo_stato_serve_a_chi_guarda_da_lontano(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            TpaRefertoService.press(referto.id, one.id, "2")

            response = self._client(app, two).get(
                f"/match/matches/{match.id}/tpa/state"
            )

            assert response.status_code == 200
            state = response.get_json()["state"]
            assert state["can_write"] is False
            assert state["current"]["annotation"]["break_potted"] == 2


class TestSblocco:
    """Il gate della gamification."""

    def test_senza_i_requisiti_la_funzione_non_si_raggiunge(self, app, players):
        """Chi non l'ha sbloccata, indovinando l'URL, non entra.

        La pagina rimbalza sul cruscotto (e' il gestore 403 del blueprint), le
        chiamate JSON rispondono 403: in nessuno dei due casi si annota.
        """
        with app.app_context():
            from models.gamification.feature_models import FeatureConfig

            one, two = players
            match = _match(one, two)

            db.session.add(
                FeatureConfig(
                    code=FEATURE_CODE,
                    name="Referto TPA",
                    description="",
                    is_active=True,
                    rules=json.dumps(
                        [
                            {
                                "description": "Veterano",
                                "conditions": [
                                    {
                                        "type": "METRIC",
                                        "metric": "exams_certified",
                                        "operator": "gte",
                                        "value": 1,
                                    }
                                ],
                            }
                        ]
                    ),
                )
            )
            db.session.commit()

            client = TestRotte._client(app, one)

            page = client.get(f"/match/matches/{match.id}/tpa")
            assert page.status_code == 302
            assert "/match/" in page.headers["Location"]

            api = client.post(
                f"/match/matches/{match.id}/tpa/press", json={"command": "1"}
            )
            assert api.status_code == 403
