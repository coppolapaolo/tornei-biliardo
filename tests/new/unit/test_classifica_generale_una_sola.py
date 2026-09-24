"""La classifica generale si calcola in un posto solo.

Fino al 24/09/2026 le classifiche erano due: la pagina sommava le classifiche
delle gare (`calculate_general_classification`), le righe `Classification` —
profilo, export, inviti ai playoff — rifacevano i conti dalle partite
(`ScoreAggregator.aggregate_campionato_scores` più una strategia di
campionato). Ogni regola andava scritta due volte, e tre volte su tre ne è
stata scritta una sola: peso e modalità dei playoff (#335), la zona playoff
(#433), la X (#550, inviti sbagliati nel campionato 5).

`SPECIFICHE.md` riga 292 dice come si fa: «La classifica del campionato
aggrega sommando le classifiche delle singole gare». È il calcolo della
pagina; le righe ne sono la copia. Questi test mettono i due uno accanto
all'altro nei casi in cui divergevano — se un giorno tornano due, lo dicono.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models.campionato.models import Campionato
from models.campionato.tournament_service import TournamentService
from models.classification.campionato_classification import ClassificationService
from models.classification.models import Classification, GaraClassification
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User


def _utente(db_session, prefisso):
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}", email=f"{prefisso}_{s}@test.com", role="player"
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _campionato(db_session, sistema="WINS", tipo="amalfi"):
    camp = Campionato(
        name=f"Camp {uuid.uuid4().hex[:6]}",
        campionato_type=tipo,
        default_classification_system=sistema,
        is_active=True,
        planned_gare_count=3,
        default_rounds_count=1,
    )
    db_session.add(camp)
    db_session.flush()
    return camp


def _gara(db_session, camp, numero, partite, *, turni=1, giocati=1, **campi):
    """Una gara con le sue partite, divise per turno.

    `partite` è una lista di `(turno, vince, perde, punti_vince, punti_perde)`;
    `giocati` dice fino a quale turno la gara è arrivata: meno di `turni`
    vuol dire gara ancora in corso.
    """
    from models.classification.gara_classification import RoundClassificationService

    conclusa = giocati >= turni
    gara = Gara(
        campionato_id=camp.id,
        number=numero,
        name=f"Gara {numero}",
        date=date(2026, 1, 10 + numero),
        time=time(18, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        rounds_count=turni,
        current_round=giocati,
        status=(GaraStatus.COMPLETED if conclusa else GaraStatus.PLAYING).value,
        classification_system=camp.default_classification_system,
        **campi,
    )
    db_session.add(gara)
    db_session.flush()
    for turno, vince, perde, pv, pp in partite:
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=turno,
                player1_id=vince.id,
                player2_id=perde.id,
                player1_score=pv,
                player2_score=pp,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
                winner_id=vince.id,
            )
        )
    db_session.flush()
    for turno in range(1, giocati + 1):
        RoundClassificationService.calculate_and_save_round_classification(
            gara.id, turno
        )
    db_session.flush()
    return gara


def _pagina(camp):
    return [
        (pos, d["user_id"], d["total_matches_won"], d.get("total_points", 0))
        for pos, d in TournamentService().calculate_general_classification(camp.id)
    ]


def _righe(camp):
    ClassificationService.update_campionato_classification(camp.id)
    return [
        (r.position, r.user_id, r.total_matches_won, r.total_position_points or 0)
        for r in Classification.query.filter_by(campionato_id=camp.id)
        .order_by(Classification.position, Classification.user_id)
        .all()
    ]


@pytest.mark.unit
class TestRigheUgualiAllaPagina:
    def test_lo_spareggio_ssr_decide_anche_le_righe(self, db_session):
        """A pari vittorie e differenza, decide lo spot shot rally della gara.

        Le righe ignoravano l'SSR (l'aggregatore non lo leggeva) e sceglievano
        per id: vinceva chi si era registrato prima.
        """
        camp = _campionato(db_session)
        a, b, c, d = (_utente(db_session, n) for n in "abcd")
        gara = _gara(db_session, camp, 1, [(1, a, c, 5, 3), (1, b, d, 5, 3)])
        # B vince lo spareggio con A, che ha l'id più basso.
        db_session.add_all(
            [
                GaraClassification(
                    gara_id=gara.id, user_id=a.id, position=1, spot_shot_wins=0
                ),
                GaraClassification(
                    gara_id=gara.id, user_id=b.id, position=1, spot_shot_wins=1
                ),
            ]
        )
        db_session.commit()

        assert _pagina(camp)[0][1] == b.id
        assert _righe(camp) == _pagina(camp)

    def test_una_gara_ancora_in_corso_non_entra(self, db_session):
        """La pagina somma le gare concluse; le righe prendevano ogni partita
        finita, anche quelle di una gara a metà."""
        camp = _campionato(db_session)
        a, b = _utente(db_session, "a"), _utente(db_session, "b")
        _gara(db_session, camp, 1, [(1, a, b, 5, 3)])
        _gara(db_session, camp, 2, [(1, b, a, 5, 0)], turni=2, giocati=1)
        db_session.commit()

        vittorie = {u: v for _p, u, v, _pt in _pagina(camp)}
        assert vittorie == {a.id: 1, b.id: 0}
        assert _righe(camp) == _pagina(camp)

    def test_a_piazzamenti_la_tabella_e_quella_della_specifica(self, db_session):
        """`CLASSIFICATION_SYSTEM.md` §7.5: 25 / 18 / 15 / 12.

        La pagina usava una sua tabella, 10 / 7 / 5 / 4, dalla posizione
        nell'ultimo turno; le righe quella della specifica, dalla posizione
        finale della gara. In produzione nessun campionato è a piazzamenti.
        """
        camp = _campionato(db_session, sistema="POSITION", tipo="direct_elimination")
        a, b = _utente(db_session, "a"), _utente(db_session, "b")
        gara = _gara(db_session, camp, 1, [(1, a, b, 5, 3)])
        db_session.add_all(
            [
                GaraClassification(gara_id=gara.id, user_id=a.id, position=1),
                GaraClassification(gara_id=gara.id, user_id=b.id, position=2),
            ]
        )
        db_session.commit()

        punti = {u: pt for _p, u, _v, pt in _pagina(camp)}
        assert punti == {a.id: 25, b.id: 18}
        assert _righe(camp) == _pagina(camp)

    def test_a_piazzamenti_i_pari_merito_condividono_la_posizione(self, db_session):
        """ADR-040: nel sistema a piazzamenti il pari merito è l'esito, non
        un'ambiguità. Le righe lo dicevano già, la pagina no."""
        camp = _campionato(db_session, sistema="POSITION", tipo="direct_elimination")
        a, b, c = (_utente(db_session, n) for n in "abc")
        gara = _gara(db_session, camp, 1, [(1, a, b, 5, 3), (1, a, c, 5, 3)])
        db_session.add_all(
            [
                GaraClassification(gara_id=gara.id, user_id=a.id, position=1),
                GaraClassification(gara_id=gara.id, user_id=b.id, position=2),
                GaraClassification(gara_id=gara.id, user_id=c.id, position=2),
            ]
        )
        db_session.commit()

        posizioni = sorted(p for p, _u, _v, _pt in _pagina(camp))
        assert posizioni == [1, 2, 2]
        assert _righe(camp) == _pagina(camp)

    def test_una_gara_chiusa_con_meno_turni_del_previsto_conta(self, db_session):
        """Si legge l'ultimo turno **giocato**, dove la chiusura della gara
        scrive le posizioni finali — non il turno `rounds_count`, che in una
        gara chiusa prima non ha classifica."""
        camp = _campionato(db_session)
        a, b = _utente(db_session, "a"), _utente(db_session, "b")
        gara = _gara(db_session, camp, 1, [(1, a, b, 5, 3)])
        gara.rounds_count = 3  # previsti tre turni, giocato uno
        db_session.commit()

        vittorie = {u: v for _p, u, v, _pt in _pagina(camp)}
        assert vittorie == {a.id: 1, b.id: 0}
        assert _righe(camp) == _pagina(camp)

    def test_ogni_chiamata_scrive_le_righe(self, db_session):
        """`update_campionato_classification` era sotto una cache di cinque
        minuti: una seconda chiamata ravvicinata tornava il risultato di prima
        **senza scrivere niente**. Una funzione che scrive non si mette in
        cache."""
        camp = _campionato(db_session)
        a, b = _utente(db_session, "a"), _utente(db_session, "b")
        _gara(db_session, camp, 1, [(1, a, b, 5, 3)])
        db_session.commit()
        prima = _righe(camp)

        Classification.query.filter_by(campionato_id=camp.id).delete()
        db_session.commit()

        assert _righe(camp) == prima
