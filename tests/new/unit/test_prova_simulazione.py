"""Competizione di prova (ADR-058), tappa 2: la simulazione dei risultati.

Tre azioni — una partita, il turno, tutta la gara — che chiudono le partite
**nei due modi** che il direttore deve imparare: la doppia conferma dei
giocatori (partite con id pari, `CONFIRMED_BY_BOTH`) e la validazione del
direttore (id dispari, lasciate a distanza raggiunta con la firma di un solo
giocatore). «Simula tutta la gara» chiude tutto, validando le dispari come
farebbe lui. Specifica in `docs/usecases/competizione-di-prova.md`,
«Decisioni successive all'intervista».

Ogni rack passa dallo stesso servizio della route del giocatore, con l'id del
fittizio: la simulazione non reimplementa il segnapunti, lo usa. Per questo i
rack esistono davvero sul tabellino e il segnapunti vero resta usabile dopo.

I test lavorano fuori da una richiesta: le prove sono invisibili senza
`prova_visibili()`, esattamente come per servizi e job.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from models.base import db
from models.competition.models import Gara
from models.competition.round_configuration import RoundConfiguration
from models.competition.services import GaraService, RoundService
from models.exceptions import ConflictError
from models.match.models import Match, Rack
from models.match.scoring_service import ScoringService
from models.match.validation_service import MatchValidationService
from models.prova.service import ProvaService
from models.prova.simulation_service import EsitoSimulazione, SimulationService
from models.prova.visibility import prova_visibili
from models.status_enum import (
    Discipline,
    GaraStatus,
    MatchStatus,
    ProvaDerivedStatus,
)
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]


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


def _prova_avviata(
    db_session,
    direttore: User,
    *,
    iscritti: int = 4,
    turni: int = 3,
    turno_1_al: int | None = None,
    **extra,
) -> int:
    """Una prova con `iscritti` fittizi e il primo turno avviato. Torna l'id.

    `turno_1_al`: un override di distanza sul primo turno (ADR-027), scritto
    **prima** dell'avvio perché le partite lo ricevono quando nascono.
    """
    campi = {
        "campionato_id": None,
        "number": 1,
        "name": f"Prova {uuid.uuid4().hex[:4]}",
        "date": date.today() + timedelta(days=1),
        "discipline": Discipline.NINE_BALL.value,
        "distance": 5,
        "is_race_to": True,
        "director_id": direttore.id,
        "min_participants": iscritti,
        "max_participants": iscritti,
        "rounds_count": turni,
        "matchmaking_strategy": "amalfi",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "status": GaraStatus.INSCRIPTION.value,
    }
    campi.update(ProvaService.campi_di_creazione())
    campi.update(extra)
    with prova_visibili():
        gara = GaraService.create_gara(**campi)
        db_session.commit()
        gara_id = gara.id
        assert ProvaService.iscrivi_fittizi(gara_id, "minimo") == iscritti
        if turno_1_al is not None:
            RoundConfiguration.create_or_update(
                gara_id=gara_id, round_number=1, distance=turno_1_al, is_race_to=True
            )
            db_session.commit()
        RoundService.start_first_round(gara_id)
        db_session.commit()
    return gara_id


def _partite(gara_id: int, turno: int | None = None) -> list[Match]:
    query = Match.query.filter_by(gara_id=gara_id)
    if turno is not None:
        query = query.filter_by(round_number=turno)
    return [m for m in query.order_by(Match.id).all() if not m.is_bye]


def _firme(match: Match) -> int:
    return int(bool(match.player1_confirmed)) + int(bool(match.player2_confirmed))


def _stato_derivato(gara_id: int) -> str:
    """Lo stato che la pagina della gara mostrerebbe, letto da zero."""
    db.session.expire_all()
    gara = db.session.get(Gara, gara_id)
    assert gara is not None
    return gara.get_real_status()


class _RngPareggio:
    """Un generatore che sceglie sempre la metà esatta: in «esattamente N»
    con N pari è il pareggio."""

    @staticmethod
    def randint(a: int, b: int) -> int:
        return (a + b) // 2

    @staticmethod
    def choice(seq):
        return seq[0]


# ------------------------------------------------------------ una partita


class TestSimulaUnaPartita:
    def test_chiude_una_partita_sola_nel_modo_deciso_dalla_parita(self, db_session):
        gara_id = _prova_avviata(db_session, _direttore(db_session))
        with prova_visibili():
            esito = SimulationService.simula_partita(gara_id, rng=random.Random(1))
            assert isinstance(esito, EsitoSimulazione)
            assert esito.partite_chiuse == 1
            assert esito.partita_id is not None

            partita = db.session.get(Match, esito.partita_id)
            assert partita is not None
            assert partita.is_at_distance
            if SimulationService.chiusa_dai_giocatori(partita):
                assert partita.status == MatchStatus.CONFIRMED_BY_BOTH.value
                assert _firme(partita) == 2
            else:
                # Il risultato c'è, segnato da un giocatore: tocca al direttore.
                assert partita.status == MatchStatus.PLAYING.value
                assert _firme(partita) == 1
                assert (
                    partita.winner_id is None
                    or partita.player1_confirmed
                    or (partita.player2_confirmed)
                )

            # Le altre partite del turno sono ancora da giocare.
            altre = [m for m in _partite(gara_id, 1) if m.id != partita.id]
            assert altre and all(not m.is_at_distance for m in altre)

    def test_i_rack_esistono_davvero_sul_tabellino(self, db_session):
        gara_id = _prova_avviata(db_session, _direttore(db_session))
        with prova_visibili():
            esito = SimulationService.simula_partita(gara_id, rng=random.Random(2))
            partita = db.session.get(Match, esito.partita_id)
            assert partita is not None
            rack = Rack.query.filter_by(match_id=partita.id, is_deleted=False).count()
            assert rack == partita.player1_score + partita.player2_score
            # Chi ha segnato ogni rack è un fittizio della partita, non il direttore.
            for riga in Rack.query.filter_by(match_id=partita.id).all():
                assert riga.added_by_id in (partita.player1_id, partita.player2_id)

    def test_il_punteggio_e_valido_per_la_corsa(self, db_session):
        gara_id = _prova_avviata(db_session, _direttore(db_session))
        with prova_visibili():
            esito = SimulationService.simula_partita(gara_id, rng=random.Random(3))
            partita = db.session.get(Match, esito.partita_id)
            assert partita is not None
            traguardo = partita.distance_config.get_winning_racks()
            assert max(partita.player1_score, partita.player2_score) == traguardo
            assert min(partita.player1_score, partita.player2_score) < traguardo

    def test_una_partita_in_attesa_del_direttore_non_viene_ripescata(self, db_session):
        """Le dispari restano da validare: la simulazione non le tocca più."""
        gara_id = _prova_avviata(db_session, _direttore(db_session))
        with prova_visibili():
            viste = set()
            for seme in range(10):
                esito = SimulationService.simula_partita(
                    gara_id, rng=random.Random(seme)
                )
                if esito.partite_chiuse == 0:
                    break
                assert esito.partita_id not in viste
                viste.add(esito.partita_id)
            # Il turno ha due partite: la terza chiamata non trova niente.
            assert len(viste) == 2
            assert esito.partite_chiuse == 0

    def test_senza_partite_da_simulare_lo_dice(self, db_session):
        gara_id = _prova_avviata(db_session, _direttore(db_session))
        with prova_visibili():
            SimulationService.simula_gara(gara_id, rng=random.Random(4))
            esito = SimulationService.simula_partita(gara_id, rng=random.Random(4))
            assert esito.partite_chiuse == 0
            assert esito.partita_id is None

    def test_una_gara_non_iniziata_rifiuta(self, db_session):
        direttore = _direttore(db_session)
        with prova_visibili():
            gara = GaraService.create_gara(
                campionato_id=None,
                number=1,
                name="Ferma",
                date=date.today() + timedelta(days=1),
                discipline=Discipline.NINE_BALL.value,
                distance=5,
                director_id=direttore.id,
                **ProvaService.campi_di_creazione(),
            )
            db_session.commit()
            with pytest.raises(ConflictError):
                SimulationService.simula_partita(gara.id)
            with pytest.raises(ConflictError):
                SimulationService.simula_turno(gara.id)
            with pytest.raises(ConflictError):
                SimulationService.simula_gara(gara.id)


# --------------------------------------------------------------- il turno


class TestSimulaIlTurno:
    def test_un_secondo_giro_sulle_dispari_in_attesa_non_conta_niente(self, db_session):
        """Rilievo sulla #318: «simula il turno» ripescava le dispari già a
        distanza, in attesa del direttore, e le contava come chiuse un'altra
        volta — il messaggio diceva partite simulate che non lo erano."""
        gara_id = _prova_avviata(db_session, _direttore(db_session), iscritti=6)
        with prova_visibili():
            primo = SimulationService.simula_turno(gara_id, rng=random.Random(5))
            assert primo.partite_chiuse == 3
            secondo = SimulationService.simula_turno(gara_id, rng=random.Random(5))
            assert secondo.partite_chiuse == 0
            assert secondo.turno == 1

    def test_le_pari_le_chiudono_i_giocatori_le_dispari_aspettano_il_direttore(
        self, db_session
    ):
        gara_id = _prova_avviata(db_session, _direttore(db_session), iscritti=6)
        with prova_visibili():
            esito = SimulationService.simula_turno(gara_id, rng=random.Random(5))
            assert esito.turno == 1
            partite = _partite(gara_id, 1)
            assert esito.partite_chiuse == len(partite) == 3

            pari = [m for m in partite if SimulationService.chiusa_dai_giocatori(m)]
            dispari = [m for m in partite if m not in pari]
            assert pari and dispari, "servono entrambe le parità per il test"
            for m in pari:
                assert m.status == MatchStatus.CONFIRMED_BY_BOTH.value
            for m in dispari:
                assert m.status == MatchStatus.PLAYING.value
                assert m.is_at_distance
                assert _firme(m) == 1

            # Il turno non è concluso finché il direttore non valida.
            assert _stato_derivato(gara_id) != ProvaDerivedStatus.ROUND_COMPLETED.value

            for m in dispari:
                MatchValidationService.validate_and_complete(m.id)
            for m in dispari:
                assert m.status == MatchStatus.CLOSED_UNILATERALLY.value
            assert _stato_derivato(gara_id) == ProvaDerivedStatus.ROUND_COMPLETED.value

    def test_chiude_anche_una_partita_aperta_a_mano_sul_segnapunti(self, db_session):
        gara_id = _prova_avviata(db_session, _direttore(db_session))
        with prova_visibili():
            aperta = _partite(gara_id, 1)[0]
            ScoringService.add_rack_for_player(
                aperta.id, user_id=aperta.player1_id, winner_id=aperta.player1_id
            )
            ScoringService.add_rack_for_player(
                aperta.id, user_id=aperta.player1_id, winner_id=aperta.player1_id
            )
            SimulationService.simula_turno(gara_id, rng=random.Random(6))
            partita = db.session.get(Match, aperta.id)
            assert partita is not None
            assert partita.is_at_distance
            traguardo = partita.distance_config.get_winning_racks()
            assert max(partita.player1_score, partita.player2_score) == traguardo
            rack = Rack.query.filter_by(match_id=partita.id, is_deleted=False).count()
            assert rack == partita.player1_score + partita.player2_score

    def test_rispetta_la_distanza_del_turno(self, db_session):
        """ADR-027: un turno «al 3» dentro una gara «al 5» chiude a 3."""
        gara_id = _prova_avviata(
            db_session, _direttore(db_session), distance=5, turno_1_al=3
        )
        with prova_visibili():
            SimulationService.simula_turno(gara_id, rng=random.Random(7))
            for m in _partite(gara_id, 1):
                assert m.effective_distance == 3
                assert max(m.player1_score, m.player2_score) == 3
                assert min(m.player1_score, m.player2_score) < 3

    def test_il_pareggio_esiste_con_n_pari(self, db_session):
        """«Esattamente 4»: a 2-2 la partita è chiusa senza vincitore."""
        gara_id = _prova_avviata(
            db_session, _direttore(db_session), distance=4, is_race_to=False
        )
        with prova_visibili():
            SimulationService.simula_turno(gara_id, rng=_RngPareggio())
            for m in _partite(gara_id, 1):
                assert (m.player1_score, m.player2_score) == (2, 2)
                assert m.is_at_distance
                assert m.winner_id is None
                if SimulationService.chiusa_dai_giocatori(m):
                    assert m.status == MatchStatus.CONFIRMED_BY_BOTH.value
                else:
                    # Nessuno dei due ha vinto: nessuna firma automatica.
                    assert m.status == MatchStatus.PLAYING.value
                    assert _firme(m) == 0

    def test_il_segnapunti_vero_resta_usabile_dopo(self, db_session):
        """Quel che i giocatori hanno concordato possono disfarlo."""
        gara_id = _prova_avviata(db_session, _direttore(db_session), iscritti=6)
        with prova_visibili():
            SimulationService.simula_turno(gara_id, rng=random.Random(8))
            confermata = next(
                m
                for m in _partite(gara_id, 1)
                if m.status == MatchStatus.CONFIRMED_BY_BOTH.value
            )
            vincitore = confermata.winner_id
            assert vincitore is not None
            ScoringService.remove_rack_for_player(
                confermata.id, user_id=vincitore, player_id=vincitore
            )
            riaperta = db.session.get(Match, confermata.id)
            assert riaperta is not None
            assert riaperta.status == MatchStatus.PLAYING.value
            assert not riaperta.is_at_distance


# -------------------------------------------------------------- la gara


class TestSimulaTuttaLaGara:
    def test_chiude_tutto_nei_due_modi(self, db_session):
        gara_id = _prova_avviata(
            db_session, _direttore(db_session), iscritti=6, turni=3
        )
        with prova_visibili():
            esito = SimulationService.simula_gara(gara_id, rng=random.Random(9))
            partite = _partite(gara_id)
            assert esito.partite_chiuse == len(partite)
            assert esito.turni_avviati == 2
            stati = {m.status for m in partite}
            assert stati == {
                MatchStatus.CONFIRMED_BY_BOTH.value,
                MatchStatus.CLOSED_UNILATERALLY.value,
            }
            for m in partite:
                dai_giocatori = SimulationService.chiusa_dai_giocatori(m)
                atteso = (
                    MatchStatus.CONFIRMED_BY_BOTH.value
                    if dai_giocatori
                    else MatchStatus.CLOSED_UNILATERALLY.value
                )
                assert m.status == atteso
            gara = db.session.get(Gara, gara_id)
            assert gara is not None
            assert gara.current_round == 3
            assert (
                _stato_derivato(gara_id)
                == ProvaDerivedStatus.TOURNAMENT_COMPLETED.value
            )

    def test_convalida_la_prova_della_x_e_registra_gli_esercizi(self, db_session):
        """Il turno dopo aspetta prova della X ed esercizi (SPECIFICHE.md riga
        102): la simulazione li fa come farebbe il direttore, altrimenti una
        prova con la X con esercizio si fermerebbe al primo turno."""
        from models.challenge.models import Challenge
        from models.competition.gara_bye_challenge import GaraByeChallenge
        from models.competition.gara_challenge import (
            GaraChallenge,
            GaraChallengeAttempt,
        )

        direttore = _direttore(db_session)
        sfida = Challenge(
            description="Spot shot",
            image_path="/x.png",
            is_active=True,
            created_by_id=direttore.id,
        )
        db_session.add(sfida)
        db_session.commit()
        gara_id = _prova_avviata(
            db_session,
            direttore,
            iscritti=5,
            turni=3,
            odd_number_policy="bye_with_challenge",
            x_challenge_id=sfida.id,
        )
        with prova_visibili():
            db_session.add(
                GaraChallenge(
                    gara_id=gara_id,
                    challenge_id=sfida.id,
                    round_number=1,
                    max_attempts=1,
                    added_by_id=direttore.id,
                )
            )
            db_session.commit()

            esito = SimulationService.simula_gara(gara_id, rng=random.Random(4))

            assert esito.fermata is None
            gara = db.session.get(Gara, gara_id)
            assert gara is not None and gara.current_round == 3
            # Le prove dei turni 1 e 2 le aspettava un turno dopo; quella
            # dell'ultimo turno resta al direttore, come la chiusura della gara.
            convalidate = {
                p.round_number
                for p in GaraByeChallenge.query.filter_by(gara_id=gara_id)
                if p.is_validated
            }
            assert convalidate == {1, 2}
            assert GaraChallengeAttempt.query.count() == 5

    def test_riprende_da_un_turno_lasciato_a_meta(self, db_session):
        gara_id = _prova_avviata(db_session, _direttore(db_session), turni=2)
        with prova_visibili():
            SimulationService.simula_partita(gara_id, rng=random.Random(10))
            esito = SimulationService.simula_gara(gara_id, rng=random.Random(10))
            assert esito.partite_chiuse >= 1
            assert all(MatchStatus.is_finished(m.status) for m in _partite(gara_id))


# ---------------------------------------------------- una sola implementazione


class TestLeRouteDiDebugUsanoIlServizio:
    def test_routes_main_non_ha_piu_una_copia(self):
        sorgente = (REPO / "routes" / "main.py").read_text(encoding="utf-8")
        assert "_debug_random_score" not in sorgente
        assert "_debug_first_active_round" not in sorgente
        assert "SimulationService" in sorgente
