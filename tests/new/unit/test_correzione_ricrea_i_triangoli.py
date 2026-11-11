"""La partita corretta dal direttore resta una partita giocata.

Rilievo della revisione del 2026-11-10. `MatchCorrectionService.correct_result`
cancellava i triangoli e non li ricreava: la partita corretta restava con zero
`Rack`, quindi `is_walkover` la dava per vinta a tavolino e l'ELO — annullato
dalla riapertura — non veniva più riapplicato. Bastava correggere un 5-3 in
5-4 perché la partita uscisse per sempre dall'ELO.

Il risultato secco del direttore (`set_match_result_direct`) i triangoli li
riscrive da sempre con `_replace_all_racks`: la correzione ora fa lo stesso.
Resta vero ciò che la correzione dice a chi la fa: il dettaglio triangolo per
triangolo, coi runout, non si ricostruisce da un punteggio.
"""

from __future__ import annotations

from models.match.correction_service import MatchCorrectionService
from models.match.models import Match, Rack
from models.rating.eligibility import RatingEligibility
from models.rating.models import MatchRatingHistory, RatingSystem
from models.status_enum import MatchStatus

from tests.new.unit._partite_di_prova import crea_gara, crea_partita, segna_triangoli


def _corregge_5_3_in_5_4(db_session, giocatori):
    gara = crea_gara(db_session)
    partita = crea_partita(
        db_session,
        gara,
        giocatori,
        player1_score=5,
        player2_score=3,
        winner_id=giocatori[0].id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    segna_triangoli(db_session, partita, [giocatori[0]] * 5 + [giocatori[1]] * 3)
    MatchCorrectionService.correct_result(
        match_id=partita.id,
        player1_score=5,
        player2_score=4,
        corrected_by_id=giocatori[2].id,
    )
    db_session.commit()
    return db_session.get(Match, partita.id)


def test_la_partita_corretta_ha_i_triangoli_del_punteggio_nuovo(
    db_session, isolated_players
):
    p = isolated_players
    partita = _corregge_5_3_in_5_4(db_session, p)

    attivi = Rack.query.filter_by(match_id=partita.id, is_deleted=False).all()
    assert sum(1 for r in attivi if r.winner_id == p[0].id) == 5
    assert sum(1 for r in attivi if r.winner_id == p[1].id) == 4
    assert (partita.player1_score, partita.player2_score) == (5, 4)
    assert partita.status == MatchStatus.CLOSED_UNILATERALLY.value


def test_la_partita_corretta_non_e_a_tavolino_e_muove_l_elo(
    db_session, isolated_players
):
    partita = _corregge_5_3_in_5_4(db_session, isolated_players)

    assert partita.is_walkover is False
    assert RatingEligibility.exclusion_reason(partita) is None
    righe = MatchRatingHistory.query.filter_by(
        match_id=partita.id, rating_system=RatingSystem.ELO
    ).all()
    assert len(righe) == 2
    assert {r.robustness_increment for r in righe} == {9}


def test_una_correzione_che_fallisce_non_lascia_niente_a_meta(
    db_session, isolated_players, monkeypatch
):
    """La correzione è una transazione sola.

    Senza, ogni triangolo riscritto si salvava per conto suo: un rifiuto
    arrivato dopo lasciava la partita riaperta, coi triangoli nuovi e un
    punteggio di passaggio che sommava i vecchi ai nuovi.
    """
    import pytest

    from models.match.state_service import MatchStateService

    p = isolated_players
    gara = crea_gara(db_session)
    partita = crea_partita(
        db_session,
        gara,
        p,
        player1_score=5,
        player2_score=3,
        winner_id=p[0].id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    segna_triangoli(db_session, partita, [p[0]] * 5 + [p[1]] * 3)
    partita_id = partita.id

    def rifiuta(*args, **kwargs):
        raise ValueError("chiusura rifiutata")

    monkeypatch.setattr(MatchStateService, "to_completed", staticmethod(rifiuta))
    with pytest.raises(ValueError):
        MatchCorrectionService.correct_result(
            match_id=partita_id,
            player1_score=5,
            player2_score=4,
            corrected_by_id=p[2].id,
        )
    db_session.rollback()
    db_session.expire_all()

    partita = db_session.get(Match, partita_id)
    assert (partita.player1_score, partita.player2_score) == (5, 3)
    assert partita.status == MatchStatus.CLOSED_UNILATERALLY.value
    attivi = Rack.query.filter_by(match_id=partita_id, is_deleted=False).count()
    assert attivi == 8
