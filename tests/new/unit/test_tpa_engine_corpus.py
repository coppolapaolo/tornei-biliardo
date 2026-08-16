"""Il motore Python deve dare gli stessi numeri dell'app JS. Sempre.

`tests/new/fixtures/tpa_js_reference_corpus.json.gz` contiene 600 partite
generate a caso (200 per disciplina) **eseguite dall'app JS di riferimento**
(`TPA-scorekeeper`): per ogni partita c'e' la sequenza di comandi premuti, il
tastierino che il JS mostrava a ogni passo e i totali finali dei due giocatori.

Le sequenze sono valide per costruzione: a ogni passo il generatore sceglieva
solo fra i comandi che il JS stesso proponeva. Il corpus copre quindi le
combinazioni che un compilatore puo' davvero produrre, comprese quelle che
nessuno penserebbe di scrivere a mano — spaccate a vuoto seguite da push out,
tre falli di fila, difese premeditate dentro un run-out.

Il file si rigenera solo se cambia l'app JS: e' una fotografia del suo
comportamento, non un dato da aggiornare quando un test si rompe. Un test che
si rompe qui significa che il motore Python ha cambiato idea su una regola.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from models.tpa.engine import TpaState, total_errors, tpa_score

CORPUS_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "tpa_js_reference_corpus.json.gz"
)


@pytest.fixture(scope="module")
def corpus():
    with gzip.open(CORPUS_PATH, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _replay(case) -> TpaState:
    """Rigioca una partita del corpus, verificando il tastierino a ogni passo."""
    state = TpaState(case["gameType"])
    for entry in case["log"]:
        kind = entry[0]
        if kind == "buttons":
            expected_buttons, expected_can_end = entry[1], entry[2]
            # Il JS puo' ripetere lo stesso pulsante nella lista; il confronto
            # e' sull'insieme, che e' cio' che l'utente vede.
            assert set(state.available_buttons()) == set(expected_buttons)
            assert state.can_switch_player() == expected_can_end
        elif kind == "end":
            state.toggle_player()
        else:
            state.annotate(entry[1])
    return state


def test_il_corpus_e_quello_atteso(corpus):
    """Guardia sul corpus stesso: se si assottiglia, il test sotto vale meno."""
    assert len(corpus) == 600
    assert {case["gameType"] for case in corpus} == {8, 9, 10}
    assert (
        sum(1 for case in corpus for entry in case["log"] if entry[0] != "buttons")
        > 30_000
    )


def test_stessi_totali_e_stesso_tastierino_dell_app_js(corpus):
    """Le 600 partite, confrontate voce per voce."""
    divergent = []
    for case in corpus:
        state = _replay(case)
        for number, key in ((1, "player1"), (2, "player2")):
            tally = state.tally(number)
            score = tpa_score(tally)
            got = {
                "racks": tally.racks_won,
                "balls": tally.balls_potted,
                "miss": tally.miss_errors,
                "brk": tally.break_errors,
                "kick": tally.kick_errors,
                "safety": tally.safety_errors,
                "position": tally.position_errors,
                "errors": total_errors(tally),
                "tpa": score if score is not None else "-",
                "BR": tally.break_and_runs,
                "RO": tally.run_outs,
                "PR": tally.perfect_racks,
            }
            if got != case["out"][key]:
                divergent.append(
                    (
                        case["seed"],
                        key,
                        {
                            field: (case["out"][key][field], got[field])
                            for field in got
                            if got[field] != case["out"][key][field]
                        },
                    )
                )
    assert divergent == []
