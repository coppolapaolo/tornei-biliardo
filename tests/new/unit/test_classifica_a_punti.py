"""La classifica a punti (ADR-078, emendamento «la classifica a punti»).

Il sistema `POINTS` ordina **solo sui punti**: ogni partita dà i punti del suo
esito — vittoria, pareggio, sconfitta, di norma 3, 1 e 0 — e fra chi è a pari
punti decide la catena degli spareggi, che a punti parte uguale a quella a
vittorie. Le regole numeriche citate dalla specifica stanno anche in
`test_specifiche_conformita.py::TestLaClassificaAPunti`; qui il resto: motore,
aggregatore, persistenza, classifica generale, vincoli e moduli.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.classification.ordinamento import (
    Criterio,
    Livello,
    catena_di_default,
    criteri_ammessi,
    criterio_principale,
    descrivi_catena,
)
from models.classification.punti import (
    PUNTI_DEFAULT,
    Punti,
    descrivi_punti,
    punti_della_gara,
    punti_proposti,
    valida_punti,
)
from models.classification.score_aggregator import ScoreAggregator
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import (
    ClassificationSystem,
    Discipline,
    GaraStatus,
    MatchStatus,
)
from models.user.models import User
from models.user.role_enum import UserRole

PUNTI = ClassificationSystem.POINTS


def _utente(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"pt_{sigla}",
        email=f"pt_{sigla}@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("prova1234")
    db_session.add(utente)
    db_session.flush()
    return utente


def _gara(db_session, *, sistema: str = PUNTI.value, **campi) -> Gara:
    quante = db_session.query(Gara).count()
    valori = dict(
        name=f"Gara punti {quante + 1}",
        number=quante + 1,
        date=date.today(),
        discipline=Discipline.NINE_BALL.value,
        distance=4,
        is_race_to=False,
        status=GaraStatus.PLAYING.value,
        rounds_count=3,
        current_round=1,
        classification_system=sistema,
        matchmaking_strategy="amalfi",
        odd_number_policy="bye",
    )
    valori.update(campi)
    gara = Gara(**valori)
    db_session.add(gara)
    db_session.flush()
    return gara


def _partita(db_session, gara, uno, due, p1, p2, turno=1, **campi) -> Match:
    partita = Match(
        gara_id=gara.id,
        round_number=turno,
        player1_id=uno.id,
        player2_id=due.id if due else None,
        player1_score=p1,
        player2_score=p2,
        winner_id=campi.pop("winner_id", None),
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        **campi,
    )
    db_session.add(partita)
    db_session.flush()
    return partita


def _punteggi(gara, fino_al_turno=1):
    return {
        v.player_id: v
        for v in ScoreAggregator().aggregate_round_scores(gara.id, fino_al_turno)
    }


# ── Il motore ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestIlMotore:
    def test_il_principale_sono_i_punti(self):
        assert criterio_principale(PUNTI) is Criterio.PUNTI

    def test_i_punti_non_entrano_nella_catena(self):
        for livello in Livello:
            ammessi = criteri_ammessi(livello, PUNTI)
            assert Criterio.PUNTI not in ammessi
            # Le vittorie sì: a punti non sono il principale.
            assert Criterio.VITTORIE in ammessi

    @pytest.mark.parametrize("livello", list(Livello))
    def test_le_catene_di_default_sono_quelle_a_vittorie(self, livello):
        assert catena_di_default(livello, PUNTI) == catena_di_default(
            livello, ClassificationSystem.WINS
        )

    def test_la_frase_dice_a_pari_punti(self, app):
        with app.test_request_context():
            frase = descrivi_catena(
                catena_di_default(Livello.GARA, PUNTI), PUNTI, Livello.GARA
            )
        assert frase.startswith("A pari punti conta la differenza triangoli")


# ── I punti ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestIPunti:
    def test_il_default_e_tre_uno_zero(self):
        assert PUNTI_DEFAULT.come_tupla() == (3, 1, 0)

    def test_la_gara_singola_senza_valori_vale_il_default(self):
        class _G:
            points_win = points_draw = points_loss = None
            campionato = None

        assert punti_della_gara(_G()) == PUNTI_DEFAULT

    def test_la_gara_ripiega_sul_campionato_campo_per_campo(self):
        class _C:
            default_points_win, default_points_draw, default_points_loss = 2, 1, 0

        class _G:
            points_win = 4
            points_draw = points_loss = None
            campionato = _C()

        assert punti_della_gara(_G()) == Punti(4, 1, 0)
        assert punti_proposti(_C()) == Punti(2, 1, 0)

    @pytest.mark.parametrize("terna", [(3, 1, 0), (2, 1, 0), (1, 0, 0), (3, 3, 0)])
    def test_terne_ammesse(self, app, terna):
        with app.test_request_context():
            assert valida_punti(*terna).come_tupla() == terna

    @pytest.mark.parametrize(
        "terna",
        [(1, 1, 1), (0, 1, 0), (3, 1, 2), (-1, 0, 0), (100, 1, 0), ("x", 1, 0)],
    )
    def test_terne_rifiutate(self, app, terna):
        with app.test_request_context(), pytest.raises(ValueError):
            valida_punti(*terna)

    def test_la_frase_del_regolamento(self, app):
        with app.test_request_context():
            assert (
                descrivi_punti(Punti(3, 1, 0))
                == "3 punti la vittoria, 1 il pareggio, 0 la sconfitta"
            )


# ── L'aggregatore ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestLAggregatore:
    def test_vittoria_e_sconfitta(self, db_session):
        gara = _gara(db_session)
        a, b = _utente(db_session), _utente(db_session)
        _partita(db_session, gara, a, b, 4, 1, winner_id=a.id)
        p = _punteggi(gara)
        assert (p[a.id].points, p[b.id].points) == (3, 0)

    def test_il_pareggio_conta_e_vale_un_punto(self, db_session):
        gara = _gara(db_session)
        a, b = _utente(db_session), _utente(db_session)
        _partita(db_session, gara, a, b, 2, 2)
        p = _punteggi(gara)
        for g in (a, b):
            assert p[g.id].matches_drawn == 1
            assert p[g.id].points == 1
            assert p[g.id].matches_won == 0

    def test_i_punti_scelti_dalla_gara(self, db_session):
        gara = _gara(db_session, points_win=2, points_draw=1, points_loss=0)
        a, b, c, d = (_utente(db_session) for _ in range(4))
        _partita(db_session, gara, a, b, 4, 0, winner_id=a.id)
        _partita(db_session, gara, c, d, 2, 2)
        p = _punteggi(gara)
        assert [p[g.id].points for g in (a, b, c, d)] == [2, 0, 1, 1]

    def test_i_punti_si_sommano_sui_turni(self, db_session):
        gara = _gara(db_session, current_round=2)
        a, b = _utente(db_session), _utente(db_session)
        _partita(db_session, gara, a, b, 4, 1, turno=1, winner_id=a.id)
        _partita(db_session, gara, a, b, 2, 2, turno=2)
        p = _punteggi(gara, 2)
        assert (p[a.id].points, p[b.id].points) == (4, 1)

    def test_a_vittorie_i_punti_restano_zero(self, db_session):
        gara = _gara(db_session, sistema=ClassificationSystem.WINS.value)
        a, b = _utente(db_session), _utente(db_session)
        _partita(db_session, gara, a, b, 4, 1, winner_id=a.id)
        assert _punteggi(gara)[a.id].points == 0

    def test_la_x_vale_i_punti_della_vittoria(self, db_session):
        gara = _gara(db_session)
        a = _utente(db_session)
        _partita(db_session, gara, a, None, 0, 0, is_bye=True, winner_id=a.id)
        voce = _punteggi(gara)[a.id]
        assert voce.points == 3
        assert voce.rack_difference == 0


# ── Persistenza e ordine ──────────────────────────────────────────────────


@pytest.mark.unit
class TestLaClassificaDelTurno:
    def test_ordina_sui_punti_non_sulle_vittorie(self, db_session):
        """Due pareggi battono una vittoria e una sconfitta, con 1 a pareggio
        e 1 a vittoria: a vittorie sarebbe il contrario."""
        from models.classification.gara_classification import (
            RoundClassificationService,
        )
        from models.classification.models import RoundClassification

        gara = _gara(
            db_session, current_round=2, points_win=1, points_draw=1, points_loss=0
        )
        a, b, c, d = (_utente(db_session) for _ in range(4))
        # a: vince e perde (1 punto); b: due pareggi (2 punti).
        _partita(db_session, gara, a, c, 4, 0, turno=1, winner_id=a.id)
        _partita(db_session, gara, b, d, 2, 2, turno=1)
        _partita(db_session, gara, a, d, 0, 4, turno=2, winner_id=d.id)
        _partita(db_session, gara, b, c, 2, 2, turno=2)
        db_session.commit()

        RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
        RoundClassificationService.calculate_and_save_round_classification(gara.id, 2)
        righe = {
            r.user_id: r
            for r in db_session.query(RoundClassification).filter_by(
                gara_id=gara.id, round_number=2
            )
        }
        assert righe[b.id].points == 2
        assert righe[a.id].points == 1
        assert righe[b.id].position < righe[a.id].position

    def test_a_vittorie_la_colonna_resta_vuota(self, db_session):
        from models.classification.gara_classification import (
            RoundClassificationService,
        )
        from models.classification.models import RoundClassification

        gara = _gara(db_session, sistema=ClassificationSystem.WINS.value)
        a, b = _utente(db_session), _utente(db_session)
        _partita(db_session, gara, a, b, 4, 1, winner_id=a.id)
        db_session.commit()
        RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
        riga = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, user_id=a.id)
            .one()
        )
        assert riga.points is None


@pytest.mark.unit
class TestLaClassificaGenerale:
    def test_somma_i_punti_delle_gare_pesati(self, db_session):
        from models.campionato.models import Campionato
        from models.campionato.statistics_service import TournamentStatisticsService
        from models.classification.gara_classification import (
            RoundClassificationService,
        )

        campionato = Campionato(
            name=f"Punti {uuid.uuid4().hex[:6]}",
            default_classification_system=PUNTI.value,
        )
        db_session.add(campionato)
        db_session.flush()
        a, b = _utente(db_session), _utente(db_session)
        for numero, peso in ((1, 1), (2, 2)):
            gara = _gara(
                db_session,
                campionato_id=campionato.id,
                number=numero,
                rounds_count=1,
                status=GaraStatus.COMPLETED.value,
                weight=peso,
            )
            _partita(db_session, gara, a, b, 4, 1, winner_id=a.id)
            db_session.commit()
            RoundClassificationService.calculate_and_save_round_classification(
                gara.id, 1
            )
        db_session.commit()

        dati = {
            d["user_id"]: (pos, d)
            for pos, d in TournamentStatisticsService().classifica_generale(
                campionato.id
            )
        }
        assert dati[a.id][1]["total_points"] == 3 * 1 + 3 * 2
        assert dati[b.id][1]["total_points"] == 0
        assert dati[a.id][0] == 1

    def test_le_righe_copiano_i_punti(self, db_session):
        from models.campionato.models import Campionato
        from models.classification.campionato_classification import (
            ClassificationService,
        )
        from models.classification.gara_classification import (
            RoundClassificationService,
        )
        from models.classification.models import Classification

        campionato = Campionato(
            name=f"Punti {uuid.uuid4().hex[:6]}",
            default_classification_system=PUNTI.value,
        )
        db_session.add(campionato)
        db_session.flush()
        a, b = _utente(db_session), _utente(db_session)
        gara = _gara(
            db_session,
            campionato_id=campionato.id,
            rounds_count=1,
            status=GaraStatus.COMPLETED.value,
        )
        _partita(db_session, gara, a, b, 2, 2)
        db_session.commit()
        RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
        ClassificationService.update_campionato_classification(campionato.id)
        db_session.commit()
        riga = (
            db_session.query(Classification)
            .filter_by(campionato_id=campionato.id, user_id=a.id)
            .one()
        )
        assert riga.total_position_points == 1


# ── Vincoli ───────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestIVincoli:
    def test_strategie_ammesse(self):
        from models.matchmaking.configuration import (
            get_strategies_for_classification_system,
        )

        assert set(get_strategies_for_classification_system("POINTS")) == {
            "amalfi",
            "random",
            "round_robin",
        }

    def test_il_tabellone_resta_a_piazzamenti(self):
        from models.matchmaking.configuration import resolve_classification_system

        assert resolve_classification_system("amalfi", "POINTS") == "POINTS"
        assert resolve_classification_system("direct_elimination", "POINTS") == (
            "POSITION"
        )

    def test_vale_come_a_vittorie(self):
        """La X semplice, i set e i pareggi: tutto come a vittorie."""
        from models.competition.validators import (
            DistanceType,
            ForfeitPolicy,
            MatchmakingStrategy,
            OddHandling,
            validate_gara_configuration,
        )

        errori, avvisi = validate_gara_configuration(
            classification_system=PUNTI,
            distance_type=DistanceType.EXACTLY,
            distance=4,
            multi_set=True,
            odd_handling=OddHandling.BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=MatchmakingStrategy.AMALFI,
        )
        assert errori == []
        errori, _ = validate_gara_configuration(
            classification_system=PUNTI,
            distance_type=DistanceType.RACE_TO,
            distance=4,
            multi_set=False,
            odd_handling=OddHandling.BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=MatchmakingStrategy.ELIMINATION,
        )
        assert errori, "il tabellone non classifica a punti"

    def test_i_punti_sono_struttura(self):
        from models.competition.campi_modificabili import STRUTTURA

        assert {"points_win", "points_draw", "points_loss"} <= STRUTTURA
