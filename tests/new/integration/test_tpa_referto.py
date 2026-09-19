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
            assert "triangoli" in (
                TpaRefertoService.blocking_reason(match, one.id) or ""
            )

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
            # Chi ha tolto il rack resta scritto, come nel resto del dominio.
            rimosso = IndividualRack.query.filter_by(match_id=match.id).first()
            assert rimosso.removed_by_id == one.id

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


class TestCancellaIlTurno:
    """«Cancella»: via l'annotazione del turno in corso, e solo quella.

    Non e' l'annulla: l'annulla toglie **un** comando, qualunque sia, e puo'
    riportare il tavolo al giocatore di prima. «Cancella» si ferma al confine
    del turno — l'ultimo ``end`` o ``seat:`` — perche' serve a chi ha sbagliato
    a scrivere *questo* turno e vuole riscriverlo da capo.
    """

    def test_toglie_tutta_l_annotazione_del_turno_in_corso(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            for command in ("1", "3", "M", "end", "2", "S", "x"):
                TpaRefertoService.press(referto.id, one.id, command)

            state = TpaRefertoService.clear_turn(referto.id, one.id)

            referto = db.session.get(type(referto), referto.id)
            assert [c.command for c in referto.comandi] == ["1", "3", "M", "end"]
            # Il tavolo resta a chi c'era: si riscrive il turno, non si torna indietro.
            assert state.current_player == 2
            assert state.turn().annotation.total_potted is None

    def test_si_ferma_alla_scelta_di_chi_spacca(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            for command in ("seat:2", "1", "3"):
                TpaRefertoService.press(referto.id, one.id, command)

            state = TpaRefertoService.clear_turn(referto.id, one.id)

            referto = db.session.get(type(referto), referto.id)
            assert [c.command for c in referto.comandi] == ["seat:2"]
            assert state.current_player == 2

    def test_a_turno_bianco_non_c_e_niente_da_cancellare(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            assert (
                TpaRefertoService.describe(referto, viewer_id=one.id)["can_clear"]
                is False
            )
            with pytest.raises(ConflictError):
                TpaRefertoService.clear_turn(referto.id, one.id)

            for command in ("1", "3", "M", "end"):
                TpaRefertoService.press(referto.id, one.id, command)
            referto = db.session.get(type(referto), referto.id)
            assert (
                TpaRefertoService.describe(referto, viewer_id=one.id)["can_clear"]
                is False
            )
            with pytest.raises(ConflictError):
                TpaRefertoService.clear_turn(referto.id, one.id)

            TpaRefertoService.press(referto.id, one.id, "2")
            referto = db.session.get(type(referto), referto.id)
            assert (
                TpaRefertoService.describe(referto, viewer_id=one.id)["can_clear"]
                is True
            )

    def test_cancellare_il_turno_vincente_non_tocca_il_punteggio(self, app, players):
        """Il triangolo si assegna quando il tavolo passa, non quando si annota:
        un turno vincente ancora in corso si cancella senza muovere la partita."""
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            for command in ("3", "9"):
                TpaRefertoService.press(referto.id, one.id, command)
            assert TpaRefertoService.build_state(referto).turn().is_winning() is True
            assert db.session.get(IndividualMatch, match.id).player1_score == 0

            state = TpaRefertoService.clear_turn(referto.id, one.id)

            assert state.turn().is_winning() is False
            assert "3" in state.available_buttons()
            assert db.session.get(IndividualMatch, match.id).player1_score == 0

    def test_solo_il_compilatore_e_solo_a_referto_aperto(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            TpaRefertoService.press(referto.id, one.id, "1")

            with pytest.raises(PermissionDeniedError):
                TpaRefertoService.clear_turn(referto.id, two.id)

            TpaRefertoService.close(referto.id, one.id)
            with pytest.raises((ConflictError, PermissionDeniedError, ValidationError)):
                TpaRefertoService.clear_turn(referto.id, one.id)


class TestRipartireDaUnTurno:
    """«Riparti da questo turno…»: il registro si tronca all'inizio di un turno
    del passato, che si riapre vuoto.

    Scorrere il referto indietro e avanti e' una vista, nel browser, e non
    tocca niente (ADR-044, emendamento del 19/09/2026). Questo e' l'unico gesto
    che scrive, e lo fa dopo una conferma che nomina i turni che escono.
    """

    PARTITA = ("1", "3", "M", "end", "2", "S", "end", "3", "G", "end", "0", "N")
    #            rack 1 turno 1 ......  turno 2 ....  turno 3 ....  rack 2 turno 1

    def _referto(self, one, two):
        match = _match(one, two)
        referto = TpaRefertoService.open_referto(match.id, one.id)
        for command in self.PARTITA:
            TpaRefertoService.press(referto.id, one.id, command)
        return match, referto

    def _comandi(self, referto):
        return [c.command for c in db.session.get(type(referto), referto.id).comandi]

    def test_tronca_all_inizio_del_turno_e_lo_riapre_vuoto(self, app, players):
        with app.app_context():
            one, two = players
            match, referto = self._referto(one, two)

            state = TpaRefertoService.restart_from_turn(referto.id, one.id, 1, 2)

            assert self._comandi(referto) == ["1", "3", "M", "end"]
            assert (state.current_rack, state.current_turn) == (1, 2)
            assert state.current_player == 2
            assert state.turn().annotation.total_potted is None

    def test_il_triangolo_vinto_dopo_torna_indietro_anche_nel_match(self, app, players):
        """Il punteggio discende dal referto: se il turno che ha chiuso il
        triangolo esce dal referto, il triangolo esce dalla partita."""
        with app.app_context():
            one, two = players
            match, referto = self._referto(one, two)
            assert db.session.get(IndividualMatch, match.id).player1_score == 1

            TpaRefertoService.restart_from_turn(referto.id, one.id, 1, 3)

            assert self._comandi(referto) == ["1", "3", "M", "end", "2", "S", "end"]
            assert db.session.get(IndividualMatch, match.id).player1_score == 0

    def test_chi_spacca_resta_scelto(self, app, players):
        """Riaprire la spaccata non rimette in discussione chi spacca: quella e'
        un'altra scelta, e si rifa' toccando l'avversario."""
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            for command in ("seat:2", "1", "3", "M", "end", "2"):
                TpaRefertoService.press(referto.id, one.id, command)

            state = TpaRefertoService.restart_from_turn(referto.id, one.id, 1, 1)

            assert self._comandi(referto) == ["seat:2"]
            assert state.current_player == 2

    def test_il_turno_in_corso_non_e_il_passato(self, app, players):
        """Per il turno che si sta scrivendo c'e' «cancella»."""
        with app.app_context():
            one, two = players
            match, referto = self._referto(one, two)

            with pytest.raises(ConflictError):
                TpaRefertoService.restart_from_turn(referto.id, one.id, 2, 1)
            assert len(self._comandi(referto)) == len(self.PARTITA)

    def test_un_turno_che_non_esiste_viene_rifiutato(self, app, players):
        with app.app_context():
            one, two = players
            match, referto = self._referto(one, two)

            for rack, turn in ((1, 9), (5, 1), (0, 0)):
                with pytest.raises(ValidationError):
                    TpaRefertoService.restart_from_turn(referto.id, one.id, rack, turn)
            assert len(self._comandi(referto)) == len(self.PARTITA)

    def test_solo_il_compilatore_e_solo_a_referto_aperto(self, app, players):
        with app.app_context():
            one, two = players
            match, referto = self._referto(one, two)

            with pytest.raises(PermissionDeniedError):
                TpaRefertoService.restart_from_turn(referto.id, two.id, 1, 2)

            TpaRefertoService.close(referto.id, one.id)
            with pytest.raises(ConflictError):
                TpaRefertoService.restart_from_turn(referto.id, one.id, 1, 2)


class TestRotte:
    """La superficie HTTP."""

    @staticmethod
    def _client(app, user: User):
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = user.get_id()
            session["_fresh"] = True
        return client

    def test_la_pagina_si_apre_per_entrambi_i_giocatori(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)

            from flask import g

            for user, scrive in ((one, "true"), (two, "false")):
                # `g` qui non e' per-richiesta: senza ripulirlo il secondo giro
                # risponderebbe ancora per il primo giocatore.
                g.pop("_login_user", None)
                response = self._client(app, user).get(f"/match/matches/{match.id}/tpa")
                assert response.status_code == 200
                assert f'data-can-write="{scrive}"' in response.get_data(as_text=True)

    def test_la_pagina_consegna_al_modulo_indirizzi_e_stato(self, app, players):
        """Il JavaScript sta in ``static/js/tpa-referto.js`` e non sa niente
        della pagina: indirizzi e stato glieli consegna il template.

        Il modulo lo prova ``tests/frontend/test_tpa_referto.cjs`` con indirizzi
        finti; qui si prova l'altra meta' del contratto — che quelli veri
        arrivino, e che siano quelli delle route.
        """
        import json
        import re

        with app.app_context():
            one, two = players
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)
            base = f"/match/matches/{match.id}/tpa"

            html = self._client(app, one).get(base).get_data(as_text=True)

            assert f'data-press-url="{base}/press"' in html
            assert f'data-restart-url="{base}/restart"' in html
            assert f'data-clear-url="{base}/clear"' in html
            assert f'data-state-url="{base}/state"' in html
            assert f'data-poll-url="/sse/poll/individual_match/{match.id}"' in html
            assert 'data-can-write="true"' in html
            assert "js/tpa-referto.js" in html

            blocco = re.search(
                r'<script type="application/json" id="tpaStato">(.*?)</script>',
                html,
                re.S,
            )
            assert blocco is not None
            state = json.loads(blocco.group(1))
            assert state["can_write"] is True
            assert state["buttons"]

            # La chiusura si conferma in un foglio 7c, col suo token.
            assert "confirm(" not in html
            foglio = html[html.index('id="tpaChiudiModal"') :]
            assert f'action="{base}/close"' in foglio
            assert 'name="csrf_token"' in foglio[: foglio.index("</form>")]

            # «Chiudi il referto» c'e' due volte — in testata da lg, in fondo
            # sotto — e nessuna delle due porta un `id`: aprono lo stesso foglio.
            assert html.count('data-bs-target="#tpaChiudiModal"') == 2
            assert html.count('id="tpaChiudiModal"') == 1
            # La legenda spiega anche la notazione, non solo le lettere.
            legenda = html[html.index('id="tpaLegenda"') : html.index('id="tpaSheet"')]
            assert "c7-tpa-kick" in legenda and "<sup>1</sup>4" in legenda

            # Chi guarda non riceve ne' il tastierino ne' il foglio di chiusura.
            # In questa suite `g` non e' per-richiesta: senza ripulirlo
            # Flask-Login risponderebbe ancora per il primo giocatore.
            from flask import g

            g.pop("_login_user", None)
            html_due = self._client(app, two).get(base).get_data(as_text=True)
            assert 'data-can-write="false"' in html_due
            assert 'id="tpaChiudiModal"' not in html_due
            # ...e tiene la nav flottante, che a chi compila lascia il posto
            # al tastierino agganciato in basso.
            assert 'class="c7-mobilenav"' in html_due
            assert 'class="c7-mobilenav"' not in html

    def test_cancella_risponde_con_lo_stato_intero(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            TpaRefertoService.press(referto.id, one.id, "1")

            response = self._client(app, one).post(
                f"/match/matches/{match.id}/tpa/clear"
            )

            assert response.status_code == 200
            state = response.get_json()["state"]
            assert state["commands"] == 0
            assert state["can_clear"] is False

            # A turno bianco e' un conflitto, non un errore del server.
            again = self._client(app, one).post(f"/match/matches/{match.id}/tpa/clear")
            assert again.status_code == 409

    def test_ripartire_risponde_con_lo_stato_intero(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            for command in ("1", "3", "M", "end", "2", "S", "end", "1"):
                TpaRefertoService.press(referto.id, one.id, command)
            url = f"/match/matches/{match.id}/tpa/restart"

            response = self._client(app, one).post(url, json={"rack": 1, "turn": 2})

            assert response.status_code == 200
            state = response.get_json()["state"]
            assert state["commands"] == 4
            assert (state["current_rack"], state["current_turn"]) == (1, 2)

            # Dati che non sono numeri: una richiesta sbagliata, non un 500.
            storta = self._client(app, one).post(url, json={"rack": "x"})
            assert storta.status_code == 400

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

    @staticmethod
    def _gate_chiuso() -> None:
        """Configura `tpa_scoresheet` con una regola che nessuno soddisfa."""
        from models.gamification.feature_models import FeatureConfig

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

    def test_senza_i_requisiti_la_funzione_non_si_raggiunge(self, app, players):
        """Chi non l'ha sbloccata, indovinando l'URL, non entra.

        La pagina rimbalza sul cruscotto (e' il gestore 403 del blueprint), le
        chiamate JSON rispondono 403: in nessuno dei due casi si annota.
        """
        with app.app_context():
            one, two = players
            match = _match(one, two)
            self._gate_chiuso()

            client = TestRotte._client(app, one)

            # La pagina che propone il referto rimbalza sul cruscotto.
            page = client.get(f"/match/matches/{match.id}/tpa")
            assert page.status_code == 302
            assert "/match/" in page.headers["Location"]

            # E il referto non si prende: e' *quello* il gesto da sbloccare.
            client.post(f"/match/matches/{match.id}/tpa/open")
            assert TpaRefertoService.get_for_match(match.id) is None

    def test_chi_non_ha_sbloccato_puo_comunque_guardare_il_referto(self, app, players):
        """Il gate sta sull'apertura, non sulla lettura.

        Il referto di una tua partita ti riguarda anche se la funzione non l'hai
        sbloccata tu: e' la stessa regola del TPA nel profilo. Vietarne la
        lettura renderebbe falsa la promessa dell'interfaccia — «l'altro
        giocatore lo vede aggiornarsi».
        """
        with app.app_context():
            one, two = players
            match = _match(one, two)
            # Il referto lo apre `one` mentre la funzione e' ancora aperta...
            referto = TpaRefertoService.open_referto(match.id, one.id)
            TpaRefertoService.press(referto.id, one.id, "2")
            # ...e solo dopo il gate si chiude per tutti.
            self._gate_chiuso()

            client = TestRotte._client(app, two)

            assert client.get(f"/match/matches/{match.id}/tpa").status_code == 200
            stato = client.get(f"/match/matches/{match.id}/tpa/state")
            assert stato.status_code == 200
            assert stato.get_json()["state"]["can_write"] is False

    def test_guardare_non_vuol_dire_scrivere(self, app, players):
        """Chi guarda resta chi guarda, gate o non gate."""
        with app.app_context():
            one, two = players
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)
            self._gate_chiuso()

            risposta = TestRotte._client(app, two).post(
                f"/match/matches/{match.id}/tpa/press", json={"command": "1"}
            )
            assert risposta.status_code == 403

    def test_il_compilatore_continua_a_scrivere_anche_se_le_regole_cambiano(
        self, app, players
    ):
        """Un referto a meta' non si abbandona.

        Se l'admin irrigidisse le regole a partita in corso e il gate valesse
        anche in scrittura, il compilatore resterebbe chiuso fuori: referto a
        meta', segnapunti normale nascosto, nessun modo di segnare i rack.
        """
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            self._gate_chiuso()

            risposta = TestRotte._client(app, one).post(
                f"/match/matches/{match.id}/tpa/press", json={"command": "1"}
            )
            assert risposta.status_code == 200
            assert risposta.get_json()["state"]["can_write"] is True
            assert referto.id  # il referto e' ancora quello di prima

    def test_senza_referto_la_presentazione_resta_riservata(self, app, players):
        """La pagina che *propone* di prendere il referto e' la funzione da
        sbloccare, e resta dietro il gate."""
        with app.app_context():
            one, two = players
            match = _match(one, two)
            self._gate_chiuso()

            pagina = TestRotte._client(app, one).get(f"/match/matches/{match.id}/tpa")
            assert pagina.status_code == 302


class TestStatisticheDiCarriera:
    """Il TPA nel profilo e nelle statistiche personali."""

    @staticmethod
    def _referto_giocato(one: User, two: User, comandi) -> IndividualMatch:
        match = _match(one, two)
        referto = TpaRefertoService.open_referto(match.id, one.id)
        for comando in comandi:
            TpaRefertoService.press(referto.id, one.id, comando)
        return match

    def test_senza_referti_e_senza_sblocco_il_tpa_non_si_mostra(self, app, players):
        """La condizione che decide se il TPA compare o no."""
        with app.app_context():
            from models.gamification.feature_models import FeatureConfig
            from models.tpa.stats_service import TpaStatsService

            one, _ = players
            # Feature configurata e non raggiunta: senza referti, niente TPA.
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

            assert TpaStatsService.is_visible_for(one.id, user=one) is False
            assert TpaStatsService.profile_summary(one.id, user=one) is None

    def test_un_referto_tenuto_dall_avversario_basta_a_mostrarlo(self, app, players):
        """Il caso che conta: il dato esiste e ti riguarda, anche se non hai
        sbloccato tu la funzione."""
        with app.app_context():
            from models.gamification.feature_models import FeatureConfig
            from models.tpa.stats_service import TpaStatsService

            one, two = players
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

            # Il referto lo tiene `one`; e' `two` a non averlo sbloccato.
            self._referto_giocato(one, two, ["1", "3", "M", "end"])

            assert TpaStatsService.is_visible_for(two.id, user=two) is True
            assert TpaStatsService.profile_summary(two.id, user=two) is not None

    def test_il_tpa_di_carriera_somma_bilie_ed_errori(self, app, players):
        """Non e' la media dei TPA di partita: si somma e si divide una volta.

        Due referti, uno da 3 bilie e 2 errori e uno da 9 bilie e 0: la media
        dei TPA darebbe .800, il conto giusto da' 12/(12+2) = .857.
        """
        with app.app_context():
            from models.tpa.stats_service import TpaStatsService

            one, two = players
            # 3 bilie, miss (1 errore) + errore di posizione = 2 errori
            self._referto_giocato(one, two, ["1", "3", "M", "end"])
            # spacca e chiude: 9 bilie, nessun errore
            self._referto_giocato(one, two, ["1", "9", "end"])

            stats = TpaStatsService.career_stats(one.id)

            assert stats["balls_potted"] == 12
            assert stats["errors"] == 2
            assert stats["tpa"] == 857  # 12/14, troncato
            assert stats["referti"] == 2
            assert stats["best_tpa"] == 1000
            assert stats["errors_by_kind"]["miss"] == 1
            assert stats["errors_by_kind"]["position"] == 1

    def test_ogni_giocatore_vede_i_propri_numeri(self, app, players):
        """Il referto e' uno, i conti sono due: il posto non e' l'identita'."""
        with app.app_context():
            from models.tpa.stats_service import TpaStatsService

            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            for comando in ["1", "3", "M", "end", "2", "S", "end"]:
                TpaRefertoService.press(referto.id, one.id, comando)

            mine = TpaStatsService.career_stats(one.id)
            theirs = TpaStatsService.career_stats(two.id)

            assert mine["balls_potted"] == 3
            assert theirs["balls_potted"] == 2
            assert theirs["errors_by_kind"]["position"] == 1

    def test_sbloccato_ma_senza_referti_il_riassunto_e_vuoto_non_zero(
        self, app, players
    ):
        """«Nessun dato» non e' «.000»: chi ha appena sbloccato non ha un TPA."""
        with app.app_context():
            from models.tpa.stats_service import TpaStatsService

            one, _ = players
            # Nessuna FeatureConfig: la feature e' aperta (fail-open), quindi
            # e' visibile ma non c'e' ancora niente da mostrare.
            summary = TpaStatsService.profile_summary(one.id, user=one)

            assert summary is not None
            assert summary["tpa"] is None
            assert summary["referti"] == 0

    def test_la_pagina_delle_statistiche_mostra_il_tpa(self, app, players):
        with app.app_context():
            one, two = players
            self._referto_giocato(one, two, ["1", "3", "M", "end"])

            response = TestRotte._client(app, one).get("/match/statistics")

            assert response.status_code == 200
            assert b"TPA" in response.data

    def test_il_profilo_mostra_il_tpa(self, app, players):
        with app.app_context():
            one, two = players
            self._referto_giocato(one, two, ["1", "9", "end"])

            response = TestRotte._client(app, one).get("/player/profile")

            assert response.status_code == 200
            # 9 bilie e nessun errore: TPA pieno, scritto `1.000` e non `.1000`.
            assert "1.000".encode() in response.data
            assert ".1000".encode() not in response.data


class TestRefertoChiuso:
    """Il referto chiuso e' un racconto: chi ha vinto, da dove sono venuti gli
    errori, i triangoli chiusi in un turno.

    I numeri non si contano di nuovo: sono i contatori del motore, passati dal
    servizio delle statistiche.
    """

    PARTITA = (
        ("3", "9", "end")  # P1 spacca e chiude                       -> 1-0
        + ("0", "end", "9", "end")  # P2 spacca a vuoto, P1 le imbuca tutte -> 2-0
        + ("1", "4", "M", "end", "2", "S", "end", "3", "end")  # -> 2-1
    )

    def _referto_chiuso(self, one, two):
        match = _match(one, two)
        referto = TpaRefertoService.open_referto(match.id, one.id)
        for command in self.PARTITA:
            TpaRefertoService.press(referto.id, one.id, command)
        TpaRefertoService.close(referto.id, one.id)
        return match, db.session.get(type(referto), referto.id)

    def test_il_riepilogo_porta_i_contatori_del_motore(self, app, players):
        from models.tpa.engine import total_errors, tpa_score
        from models.tpa.stats_service import TpaStatsService

        with app.app_context():
            one, two = players
            match, referto = self._referto_chiuso(one, two)
            state = TpaRefertoService.build_state(referto)

            summary = TpaStatsService.referto_summary(referto)

            assert summary["racks_played"] == 3
            for seat in (1, 2):
                tally = state.tally(seat)
                mine = summary["players"][seat]
                assert mine["racks_won"] == tally.racks_won
                assert mine["tpa"] == tpa_score(tally)
                assert mine["balls_potted"] == tally.balls_potted
                assert mine["errors"] == total_errors(tally)
                assert mine["errors_by_kind"] == {
                    "miss": tally.miss_errors,
                    "break": tally.break_errors,
                    "kick": tally.kick_errors,
                    "safety": tally.safety_errors,
                    "position": tally.position_errors,
                }
            assert summary["players"][1]["name"] == one.username
            assert summary["winner"] == 1

    def test_chiuso_in_un_turno_comprende_lo_spacca_e_chiude(self, app, players):
        """Nel motore i due contatori sono disgiunti; per chi gioca lo «spacca e
        chiude» e' un triangolo chiuso in un turno come gli altri, quindi il
        numero mostrato e' la somma. Stampare il solo `run_outs` ne perde uno."""
        from models.tpa.stats_service import TpaStatsService

        with app.app_context():
            one, two = players
            match, referto = self._referto_chiuso(one, two)
            tally = TpaRefertoService.build_state(referto).tally(1)
            assert (tally.break_and_runs, tally.run_outs) == (1, 1)

            mine = TpaStatsService.referto_summary(referto)["players"][1]
            assert mine["break_and_runs"] == 1
            assert mine["closed_in_one_turn"] == 2

            # Stessa regola nel riepilogo di carriera.
            career = TpaStatsService.career_stats(one.id)
            assert career["closed_in_one_turn"] == 2

    def test_la_pagina_chiusa_racconta_e_non_offre_il_tastierino(self, app, players):
        with app.app_context():
            one, two = players
            match, referto = self._referto_chiuso(one, two)

            html = (
                TestRotte._client(app, one)
                .get(f"/match/matches/{match.id}/tpa")
                .get_data(as_text=True)
            )

            assert "Da dove vengono gli errori" in html
            assert "Chiuse in un turno" in html
            assert 'id="tpaRefertoChiuso"' in html
            assert 'id="tpaDock"' not in html
            assert 'data-closed="true"' in html

    def test_in_parita_non_c_e_un_vincitore(self, app, players):
        from models.tpa.stats_service import TpaStatsService

        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            TpaRefertoService.close(referto.id, one.id)

            summary = TpaStatsService.referto_summary(
                db.session.get(type(referto), referto.id)
            )
            assert summary["winner"] is None
            assert summary["racks_played"] == 0
            assert summary["players"][1]["tpa"] is None


class TestChiSpaccaSiSceglieUnaVoltaSola:
    """Il posto in spaccata non si cambia a spaccata gia' annotata.

    Il tastierino non offre nemmeno il gesto (`can_switch_player` e' falso),
    ma il servizio non si fida del client: una POST costruita a mano verrebbe
    comunque rifiutata, perche' cambiare chi spacca a rack cominciato
    riscriverebbe una partita gia' giocata.
    """

    def test_dopo_le_bilie_della_spaccata_il_posto_e_fissato(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            TpaRefertoService.press(referto.id, one.id, "1")  # bilie sulla spaccata

            with pytest.raises(ValidationError):
                TpaRefertoService.press(referto.id, one.id, "seat:2")

    def test_finche_non_si_annota_il_posto_si_cambia(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)

            state = TpaRefertoService.press(referto.id, one.id, "seat:2")
            assert state.current_player == 2
            assert state.can_choose_seat() is True


class TestIlRefertoSiVedeCambiare:
    """L'avversario deve vedere il referto crescere, non solo il punteggio.

    Le route annunciano ogni tocco sul canale del match, cosi' la pagina di chi
    guarda rilegge lo stato e si ridisegna. Il punteggio invece si annuncia solo
    quando si e' mosso davvero: la pagina del match si **ricarica** su quel
    segnale, e mandarglielo a ogni tocco vorrebbe dire ricaricarla venti volte
    per rack.
    """

    @pytest.fixture(autouse=True)
    def _canale_pulito(self, db_session):
        """Gli id dei match ripartono da 1 a ogni test: senza questa pulizia
        gli eventi di un test finirebbero nella casella di quello dopo — e le
        asserzioni conterebbero roba di altri."""
        from models.live_event import LiveEvent

        LiveEvent.query.delete()
        db_session.commit()
        yield

    @staticmethod
    def _eventi(match_id: int):
        from routes.sse import EventScope, _get_events_since

        return _get_events_since(EventScope.INDIVIDUAL_MATCH, match_id, 0)

    def test_ogni_tocco_si_annuncia(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)
            client = TestRotte._client(app, one)

            client.post(f"/match/matches/{match.id}/tpa/press", json={"command": "2"})

            tocchi = [e for e in self._eventi(match.id) if e["type"] == "tpa_updated"]
            assert len(tocchi) == 1
            assert tocchi[0]["data"]["by"] == one.id

    def test_il_punteggio_si_annuncia_solo_quando_si_muove(self, app, players):
        with app.app_context():
            one, two = players
            match = _match(one, two)
            TpaRefertoService.open_referto(match.id, one.id)
            client = TestRotte._client(app, one)

            # Spaccata annotata: il referto cambia, il punteggio no.
            client.post(f"/match/matches/{match.id}/tpa/press", json={"command": "1"})
            assert not [
                e for e in self._eventi(match.id) if e["type"] == "rack_updated"
            ]

            # Imbuca tutto e chiude il rack: ora il punteggio si e' mosso.
            client.post(f"/match/matches/{match.id}/tpa/press", json={"command": "9"})
            client.post(f"/match/matches/{match.id}/tpa/press", json={"command": "end"})

            rack = [e for e in self._eventi(match.id) if e["type"] == "rack_updated"]
            assert len(rack) == 1
            assert rack[0]["data"]["player1_score"] == 1
            assert rack[0]["data"]["added_by"] == one.id

    def test_anche_l_annulla_si_annuncia(self, app, players):
        """Chi guarda deve vedere tornare indietro, non restare su un dato morto."""
        with app.app_context():
            one, two = players
            match = _match(one, two)
            referto = TpaRefertoService.open_referto(match.id, one.id)
            client = TestRotte._client(app, one)
            client.post(f"/match/matches/{match.id}/tpa/press", json={"command": "1"})
            client.post(f"/match/matches/{match.id}/tpa/press", json={"command": "9"})
            client.post(f"/match/matches/{match.id}/tpa/press", json={"command": "end"})
            prima = len(self._eventi(match.id))

            client.post(f"/match/matches/{match.id}/tpa/undo")

            eventi = self._eventi(match.id)[prima:]
            assert [e["type"] for e in eventi] == ["tpa_updated", "rack_updated"]
            assert eventi[1]["data"]["player1_score"] == 0
            assert referto.id  # il referto resta, e' il rack che torna indietro
