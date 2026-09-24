"""La X conta anche nella classifica da cui partono gli inviti ai playoff.

Campionato 5 in produzione, 24/09/2026: la pagina mostrava serpico67 ottavo
(5 vittorie, −7) e RIZA nono (4 vittorie, +1), ma all'avvio dei playoff
l'invito per l'ottavo posto è andato a RIZA. serpico67 aveva avuto una X alla
gara 1.

I due percorsi della classifica generale leggevano la X in due modi. La
pagina somma le `RoundClassification`, dove la X vale una vittoria e zero
differenza (`SPECIFICHE.md` righe 147 e 154). Le righe `Classification`, da
cui `start_playoff` sceglie gli invitati, venivano da
`ScoreAggregator.aggregate_campionato_scores`, che **scartava** le partite con
la X: una vittoria in meno, e a pari vittorie RIZA passava davanti per
differenza triangoli. La zona playoff disegnata sulla pagina diceva il giusto
fino all'ultimo, e proprio per questo nessuno poteva accorgersene prima.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from models.campionato.models import Campionato
from models.classification.campionato_classification import ClassificationService
from models.classification.models import Classification
from models.competition.models import Gara
from models.match.models import Match
from models.playoff.models import PlayoffConfiguration, PlayoffType
from models.playoff.services import PlayoffService
from models.playoff.zona import zone_playoff
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


def _campionato_con_la_x(db_session):
    """Due gare, un posto ai playoff.

    * gara 1: S ha la X, T batte U 5–0;
    * gara 2: S batte U 5–4, R batte T 5–0.

    In pagina S ha 2 vittorie (+1), R 1 (+5), T 1 (0), U 0: il posto è di S.
    Senza la X, S e R hanno una vittoria a testa e R passa per differenza.
    """
    from models.classification.gara_classification import RoundClassificationService

    camp = Campionato(
        name=f"Camp {uuid.uuid4().hex[:6]}",
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=2,
        default_rounds_count=1,
    )
    db_session.add(camp)
    db_session.flush()
    s, r, t, u = (_utente(db_session, n) for n in ("s", "r", "t", "u"))

    for numero, giorno, partite in (
        (1, 10, ((s, None, 0, 0), (t, u, 5, 0))),
        (2, 15, ((s, u, 5, 4), (r, t, 5, 0))),
    ):
        gara = Gara(
            campionato_id=camp.id,
            number=numero,
            name=f"Gara {numero}",
            date=date(2026, 1, giorno),
            time=time(18, 0),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            rounds_count=1,
            current_round=1,
            status=GaraStatus.COMPLETED.value,
            odd_number_policy="bye",
        )
        db_session.add(gara)
        db_session.flush()
        for uno, due, p1, p2 in partite:
            db_session.add(
                Match(
                    gara_id=gara.id,
                    round_number=1,
                    player1_id=uno.id,
                    player2_id=due.id if due else None,
                    is_bye=due is None,
                    player1_score=p1,
                    player2_score=p2,
                    status=MatchStatus.CLOSED_UNILATERALLY.value,
                    winner_id=uno.id,
                )
            )
        db_session.flush()
        RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
    db_session.commit()
    ClassificationService.update_campionato_classification(camp.id)

    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        is_active=True,
        max_participants=1,
        positions_from=1,
        positions_to=1,
        min_garas_played=0,
    )
    db_session.add(cfg)
    db_session.commit()
    return {"campionato": camp, "cfg": cfg, "s": s, "r": r, "t": t, "u": u}


def _righe(camp):
    return (
        Classification.query.filter_by(campionato_id=camp.id)
        .order_by(Classification.position)
        .all()
    )


def test_la_x_e_una_vittoria_nelle_righe_della_classifica_generale(db_session):
    dati = _campionato_con_la_x(db_session)

    riga_s = next(r for r in _righe(dati["campionato"]) if r.user_id == dati["s"].id)

    assert riga_s.total_matches_won == 2
    assert riga_s.total_point_difference == 1
    assert riga_s.position == 1


def test_righe_e_pagina_danno_lo_stesso_ordine_con_la_x(db_session):
    from models.campionato.tournament_service import TournamentService

    dati = _campionato_con_la_x(db_session)

    pagina = TournamentService().calculate_general_classification(dati["campionato"].id)
    assert [d["user_id"] for _pos, d in pagina] == [
        r.user_id for r in _righe(dati["campionato"])
    ]


def test_l_invito_va_a_chi_la_zona_segna(db_session):
    """Lo scenario del campionato 5: zona e inviti devono scegliere S."""
    dati = _campionato_con_la_x(db_session)

    (zona,) = zone_playoff(dati["campionato"])
    invitati = {
        user_id
        for user_id, _pos, _motivo in PlayoffService.candidati_per_posizione(
            dati["cfg"], _righe(dati["campionato"])
        )
    }

    assert zona.user_ids == invitati == {dati["s"].id}
