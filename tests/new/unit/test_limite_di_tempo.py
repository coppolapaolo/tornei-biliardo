"""Il limite di tempo delle partite (ADR-077).

La partita ha sempre una distanza. Il limite di tempo è un'**opzione** che si
aggiunge: minuti a disposizione, proposti dal campionato, decisi dalla gara e
fissati sulla partita quando nasce (ADR-075). Il conto alla rovescia parte una
volta sola — all'acchito, o con «Avvia partita» — ed è **solo visivo**: a tempo
scaduto non succede niente da sé.

Qui si difendono le regole che la CI deve vedere (esegue solo i test unitari):

* quanto vale il limite di una gara, dentro e fuori da un campionato;
* il limite si fissa sulla partita alla nascita e un cambio della gara non la
  raggiunge;
* a set, trio e X il limite non si applica, in questa versione;
* il conto alla rovescia si scrive una volta sola, e lo scadere non chiude
  niente;
* la card del direttore di una partita a tempo scaduto sale in cima.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _gara(suffix, **overrides):
    base = dict(
        number=1,
        name=f"Gara {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="8_ball",
        distance=3,
        rounds_count=3,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="round_robin",
        status=GaraStatus.PLAYING.value,
    )
    base.update(overrides)
    return Gara(**base)


def _giocatori(quanti=2):
    batch = uuid.uuid4().hex[:8]
    utenti = []
    for i in range(quanti):
        u = User(
            username=f"lt{i}_{batch}",
            email=f"lt{i}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        u.set_password("test123")
        utenti.append(u)
    db.session.add_all(utenti)
    db.session.commit()
    return utenti


def _partita(gara, giocatori, **overrides):
    base = dict(
        gara_id=gara.id,
        round_number=1,
        player1_id=giocatori[0].id,
        player2_id=giocatori[1].id,
        status=MatchStatus.PLAYING.value,
        match_distance=gara.distance,
        table_assignment="1",
    )
    base.update(overrides)
    match = Match(**base)
    db.session.add(match)
    db.session.commit()
    return match


# ---------------------------------------------------------------------------
# Quanto vale il limite di una gara
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLimiteDellaGara:
    def test_gara_singola_senza_valore_non_ha_limite(self, db_session):
        gara = _gara(uuid.uuid4().hex[:6])
        db.session.add(gara)
        db.session.commit()
        assert gara.effective_time_limit_minutes is None

    def test_gara_singola_con_trenta_minuti(self, db_session):
        gara = _gara(uuid.uuid4().hex[:6], time_limit_minutes=30)
        db.session.add(gara)
        db.session.commit()
        assert gara.effective_time_limit_minutes == 30

    def test_zero_vuol_dire_senza_limite(self, db_session):
        """Zero è la scelta esplicita «senza limite», anche dentro un campionato
        che ne propone uno: NULL invece vorrebbe dire «come il campionato»."""
        camp = Campionato(
            name=f"C {uuid.uuid4().hex[:6]}", default_time_limit_minutes=30
        )
        db.session.add(camp)
        db.session.flush()
        gara = _gara(uuid.uuid4().hex[:6], campionato_id=camp.id, time_limit_minutes=0)
        db.session.add(gara)
        db.session.commit()
        assert gara.effective_time_limit_minutes is None

    def test_null_dentro_un_campionato_eredita(self, db_session):
        camp = Campionato(
            name=f"C {uuid.uuid4().hex[:6]}", default_time_limit_minutes=30
        )
        db.session.add(camp)
        db.session.flush()
        gara = _gara(
            uuid.uuid4().hex[:6], campionato_id=camp.id, time_limit_minutes=None
        )
        db.session.add(gara)
        db.session.commit()
        assert gara.effective_time_limit_minutes == 30

    def test_il_campionato_parte_senza_limite(self, db_session):
        camp = Campionato(name=f"C {uuid.uuid4().hex[:6]}")
        db.session.add(camp)
        db.session.commit()
        assert camp.default_time_limit_minutes == 0

    def test_la_gara_nuova_copia_il_valore_del_campionato(self, db_session):
        """ADR-075: il campionato propone, la gara decide. Il valore si copia
        alla nascita, così un cambio successivo del campionato si propone
        invece di arrivare da solo."""
        from models.competition.services import GaraService

        camp = Campionato(
            name=f"C {uuid.uuid4().hex[:6]}", default_time_limit_minutes=30
        )
        db.session.add(camp)
        db.session.commit()
        valori = {"time_limit_minutes": None}
        GaraService._copia_dal_campionato(camp.id, valori)
        assert valori["time_limit_minutes"] == 30

        camp.default_time_limit_minutes = 0
        db.session.commit()
        valori = {"time_limit_minutes": None}
        GaraService._copia_dal_campionato(camp.id, valori)
        assert valori["time_limit_minutes"] == 0

    def test_una_scelta_della_gara_non_si_sovrascrive(self, db_session):
        from models.competition.services import GaraService

        camp = Campionato(
            name=f"C {uuid.uuid4().hex[:6]}", default_time_limit_minutes=30
        )
        db.session.add(camp)
        db.session.commit()
        valori = {"time_limit_minutes": 45}
        GaraService._copia_dal_campionato(camp.id, valori)
        assert valori["time_limit_minutes"] == 45


# ---------------------------------------------------------------------------
# Il limite si fissa sulla partita (ADR-075)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLimiteFissatoSullaPartita:
    def test_la_partita_nasce_col_limite_della_gara(self, db_session):
        gara = _gara(uuid.uuid4().hex[:6], time_limit_minutes=30)
        db.session.add(gara)
        db.session.commit()
        match = _partita(gara, _giocatori())
        assert match.time_limit_minutes == 30

    def test_un_cambio_della_gara_non_raggiunge_la_partita_nata(self, db_session):
        gara = _gara(uuid.uuid4().hex[:6], time_limit_minutes=30)
        db.session.add(gara)
        db.session.commit()
        match = _partita(gara, _giocatori())

        gara.time_limit_minutes = 45
        db.session.commit()

        assert db.session.get(Match, match.id).time_limit_minutes == 30

    def test_senza_limite_la_partita_resta_senza(self, db_session):
        gara = _gara(uuid.uuid4().hex[:6], time_limit_minutes=0)
        db.session.add(gara)
        db.session.commit()
        match = _partita(gara, _giocatori())
        assert match.time_limit_minutes is None
        assert match.has_time_limit is False

    def test_a_set_e_x_il_limite_non_si_applica(self, db_session):
        """Prima versione: partite a set, trio e X restano fuori (ADR-077)."""
        gara = _gara(uuid.uuid4().hex[:6], time_limit_minutes=30)
        db.session.add(gara)
        db.session.commit()
        gioc = _giocatori(3)
        a_set = _partita(gara, gioc[:2], is_multi_set=True, match_distance=2)
        x = _partita(gara, [gioc[2], gioc[2]], player2_id=None, is_bye=True)
        trio = _partita(gara, gioc[:2], is_trio=True)
        for match in (a_set, x, trio):
            assert match.has_time_limit is False, match


# ---------------------------------------------------------------------------
# Il conto alla rovescia
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContoAllaRovescia:
    def _partita_a_tempo(self):
        gara = _gara(uuid.uuid4().hex[:6], time_limit_minutes=30)
        db.session.add(gara)
        db.session.commit()
        return _partita(gara, _giocatori())

    def test_parte_una_volta_sola(self, db_session):
        from models.match import tempo

        match = self._partita_a_tempo()
        inizio = datetime(2026, 10, 6, 20, 0)
        assert tempo.avvia_conto_alla_rovescia(match, adesso=inizio) is True
        assert match.timer_started_at == inizio

        dopo = inizio + timedelta(minutes=5)
        assert tempo.avvia_conto_alla_rovescia(match, adesso=dopo) is False
        assert match.timer_started_at == inizio

    def test_senza_limite_non_parte(self, db_session):
        from models.match import tempo

        gara = _gara(uuid.uuid4().hex[:6])
        db.session.add(gara)
        db.session.commit()
        match = _partita(gara, _giocatori())
        assert tempo.avvia_conto_alla_rovescia(match) is False
        assert match.timer_started_at is None

    def test_scadenza_e_tempo_restante(self, db_session):
        from models.match import tempo

        match = self._partita_a_tempo()
        inizio = datetime(2026, 10, 6, 20, 0)
        tempo.avvia_conto_alla_rovescia(match, adesso=inizio)

        assert tempo.scadenza(match) == inizio + timedelta(minutes=30)
        adesso = inizio + timedelta(minutes=24)
        assert tempo.secondi_restanti(match, adesso=adesso) == 6 * 60
        assert tempo.tempo_scaduto(match, adesso=adesso) is False

        oltre = inizio + timedelta(minutes=32)
        assert tempo.secondi_restanti(match, adesso=oltre) == -2 * 60
        assert tempo.tempo_scaduto(match, adesso=oltre) is True

    def test_lo_scadere_non_chiude_la_partita(self, db_session):
        """Solo visivo: la partita resta in corso e non aspetta il direttore."""
        from models.match import tempo

        match = self._partita_a_tempo()
        inizio = datetime(2026, 10, 6, 20, 0)
        tempo.avvia_conto_alla_rovescia(match, adesso=inizio)
        db.session.commit()

        assert tempo.tempo_scaduto(match, adesso=inizio + timedelta(hours=2))
        assert match.status == MatchStatus.PLAYING.value
        assert match.is_awaiting_validation is False

    def test_una_partita_chiusa_non_e_mai_scaduta(self, db_session):
        from models.match import tempo

        match = self._partita_a_tempo()
        inizio = datetime(2026, 10, 6, 20, 0)
        tempo.avvia_conto_alla_rovescia(match, adesso=inizio)
        match.status = MatchStatus.CLOSED_UNILATERALLY.value
        assert tempo.tempo_scaduto(match, adesso=inizio + timedelta(hours=2)) is False

    def test_non_avviato_non_e_scaduto(self, db_session):
        from models.match import tempo

        match = self._partita_a_tempo()
        assert tempo.scadenza(match) is None
        assert tempo.tempo_scaduto(match) is False


# ---------------------------------------------------------------------------
# Chi avvia il conto alla rovescia
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAvviaPartita:
    def _partita_a_tempo(self, **gara_kw):
        gara = _gara(uuid.uuid4().hex[:6], time_limit_minutes=30, **gara_kw)
        db.session.add(gara)
        db.session.commit()
        gioc = _giocatori(3)
        return _partita(gara, gioc[:2]), gioc

    def test_un_giocatore_della_partita_la_avvia(self, db_session):
        from models.match.match_service import MatchService

        match, gioc = self._partita_a_tempo(start_rule="first_player")
        MatchService.avvia_partita(match.id, gioc[0])
        assert db.session.get(Match, match.id).timer_started_at is not None

    def test_chi_non_gioca_e_non_dirige_no(self, db_session):
        from models.exceptions import PermissionDeniedError
        from models.match.match_service import MatchService

        match, gioc = self._partita_a_tempo(start_rule="first_player")
        with pytest.raises(PermissionDeniedError):
            MatchService.avvia_partita(match.id, gioc[2])
        assert db.session.get(Match, match.id).timer_started_at is None

    def test_senza_limite_non_c_e_niente_da_avviare(self, db_session):
        from models.exceptions import ValidationError
        from models.match.match_service import MatchService

        gara = _gara(uuid.uuid4().hex[:6], start_rule="first_player")
        db.session.add(gara)
        db.session.commit()
        gioc = _giocatori()
        match = _partita(gara, gioc)
        with pytest.raises(ValidationError):
            MatchService.avvia_partita(match.id, gioc[0])

    def test_una_partita_chiusa_non_si_avvia(self, db_session):
        from models.exceptions import ConflictError
        from models.match.match_service import MatchService

        match, gioc = self._partita_a_tempo(start_rule="first_player")
        match.status = MatchStatus.CLOSED_UNILATERALLY.value
        db.session.commit()
        with pytest.raises(ConflictError):
            MatchService.avvia_partita(match.id, gioc[0])

    def test_premere_due_volte_non_sposta_l_inizio(self, db_session):
        from models.match.match_service import MatchService

        match, gioc = self._partita_a_tempo(start_rule="first_player")
        MatchService.avvia_partita(match.id, gioc[0])
        primo = db.session.get(Match, match.id).timer_started_at
        MatchService.avvia_partita(match.id, gioc[1])
        assert db.session.get(Match, match.id).timer_started_at == primo

    def test_l_acchito_avvia_il_conto_alla_rovescia(self, db_session):
        from models.match.scoring_service import ScoringService

        match, gioc = self._partita_a_tempo(start_rule="lag")
        ScoringService.register_lag(match.id, gioc[0].id, gioc[1].id)
        assert db.session.get(Match, match.id).timer_started_at is not None

    def test_l_acchito_senza_limite_non_avvia_niente(self, db_session):
        from models.match.scoring_service import ScoringService

        gara = _gara(uuid.uuid4().hex[:6], start_rule="lag")
        db.session.add(gara)
        db.session.commit()
        gioc = _giocatori()
        match = _partita(gara, gioc)
        ScoringService.register_lag(match.id, gioc[0].id, gioc[1].id)
        assert db.session.get(Match, match.id).timer_started_at is None

    def test_la_partenza_e_un_evento_live_per_gara_e_partita(self, db_session):
        """ADR-057: avversario, direttore e schermo sala lo sanno al poll."""
        from models.live_event import LiveEvent
        from models.match.match_service import MatchService

        match, gioc = self._partita_a_tempo(start_rule="first_player")
        MatchService.avvia_partita(match.id, gioc[0])
        eventi = {
            (e.scope, e.event_type)
            for e in LiveEvent.query.filter(
                LiveEvent.scope_id.in_((match.id, match.gara_id))
            ).all()
        }
        assert ("match", "timer_started") in eventi
        assert ("gara", "match_updated") in eventi


# ---------------------------------------------------------------------------
# Il direttore: la card a tempo scaduto sale fra quelle da guardare
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_la_card_a_tempo_scaduto_sale_in_cima(db_session):
    from models.competition.direttore_view import partite_del_turno

    gara = _gara(uuid.uuid4().hex[:6], time_limit_minutes=30)
    db.session.add(gara)
    db.session.commit()
    gioc = _giocatori(4)
    normale = _partita(gara, gioc[:2])
    scaduta = _partita(gara, gioc[2:])
    scaduta.timer_started_at = datetime(2000, 1, 1, 20, 0)
    db.session.commit()

    ordine = [m.id for m in partite_del_turno([normale, scaduta], 1)]
    assert ordine == [scaduta.id, normale.id]


# ---------------------------------------------------------------------------
# Il limite è una regola di gioco (ADR-075)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_il_limite_e_una_regola_che_vale_dal_turno_dopo():
    from models.competition.campi_modificabili import REGOLE

    assert "time_limit_minutes" in REGOLE


@pytest.mark.unit
def test_il_campionato_propone_il_limite_alle_gare():
    from models.campionato.proposte import CAMPI_PROPOSTI, _valore_da_scrivere

    assert CAMPI_PROPOSTI["default_time_limit_minutes"] == "time_limit_minutes"
    assert _valore_da_scrivere("time_limit_minutes", "30") == {"time_limit_minutes": 30}
    assert _valore_da_scrivere("time_limit_minutes", "0") == {"time_limit_minutes": 0}


@pytest.mark.unit
def test_la_storia_dice_il_limite_a_parole(app):
    from models.storia.etichette import etichetta, valore

    with app.test_request_context():
        assert str(etichetta("time_limit_minutes")) == "Limite di tempo per partita"
        assert valore("time_limit_minutes", "30") == "30 minuti"
        assert valore("time_limit_minutes", "0") == "senza limite"
        assert valore("default_time_limit_minutes", "0") == "senza limite"
