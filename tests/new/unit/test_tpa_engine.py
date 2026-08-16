"""Il motore del referto TPA, verificato sulla sessione d'esempio ufficiale.

La sessione qui sotto e' quella stampata in *Accu-Stats Scoresheet
Instructions* (21 inning, Tom Fisher contro Paul Clark). E' il solo referto
pubblico di cui esista anche il risultato atteso, quindi e' il banco di prova
naturale del motore.

Il confronto e' su due fronti, e vanno tenuti distinti:

- **contro l'app JS di riferimento**: combacia tutto, per entrambi i giocatori
  e per tutte le voci. E' il vincolo piu' stretto e il piu' importante, perche'
  i referti gia' compilati con quell'app devono continuare a dare gli stessi
  numeri. Oltre a questa sessione lo verifica `test_tpa_engine_corpus.py` su
  600 partite generate a caso.
- **contro il PDF**: combaciano il punteggio finale (7-2) e quasi tutte le
  categorie, ma non tutte. Gli scarti sono tre, elencati nel docstring di
  `models/tpa/engine.py`, e sono ereditati dall'app JS.
"""

from __future__ import annotations

import pytest

from models.tpa.engine import TpaButton, TpaState, tpa_score, total_errors

# Ogni voce: (giocatore che va al tavolo, comandi premuti).
# Una lista vuota significa "chiudi il turno che il motore ha creato da solo"
# — succede sul terzo fallo, dove il rack passa senza che si tocchi il tavolo.
SAMPLE_SESSION = [
    (1, ["1", "3", "M"]),  # I1  spacca, 1+2 bilie, sbaglia un tiro difficile
    (2, ["2", "S"]),  # I1  2 bilie, poi difesa
    (1, ["4"]),  # I2  chiude il rack                       -> 1-0
    (1, ["2", "2", "P"]),  # I3  2 sulla spaccata e battente in buca
    (2, ["0", "S"]),  # I3  difesa
    (1, ["0", "K"]),  # I4  kick, battuta buona
    (2, ["2", "P"]),  # I4  2 bilie, battente in buca sulla terza
    (1, ["3", "M", "n"]),  # I5  3 bilie, sbaglia un tiro facile (2 errori)
    (2, ["1", "G"]),  # I5  imbuca l'ultima                      -> 1-1
    (2, ["0"]),  # I6  spaccata a vuoto
    (1, ["4", "G"]),  # I7  4 bilie, vince di combinazione       -> 2-1
    (1, ["2", "2", "G"]),  # I8  la 9 sulla spaccata                  -> 3-1
    (1, ["2", "2", "S", "p"]),  # I9  2 sulla spaccata, poi push out
    (2, ["0", "S"]),  # I9  rifiuta il tiro (vale come difesa)
    (1, ["1", "K", "P"]),  # I10 1 bilia, kick, battente in buca
    (2, ["0", "S"]),  # I10 difesa
    (1, ["0", "N"]),  # I11 fallo intenzionale
    (2, ["1", "S", "x"]),  # I11 1 bilia e difesa premeditata
    (1, ["0", "K", "N"]),  # I12 kick fallito: e' il terzo fallo
    (2, []),  # I12 il rack va a P2 per la regola dei tre falli -> 3-2
    (2, ["1", "3", "M", "n"]),  # I13 spacca, 1+2 bilie, sbaglia un tiro facile
    (1, ["1", "M", "P"]),  # I14 1 bilia, sbaglia, battente in buca
    (2, ["3", "S", "P"]),  # I14 3 bilie, difesa, battente in buca
    (1, ["2"]),  # I15 chiude il rack                       -> 4-2
    (1, ["3", "9"]),  # I16 spacca e chiude tutto                -> 5-2
    (1, ["0", "P"]),  # I17 spaccata a vuoto e battente in buca
    (2, ["3", "M"]),  # I17 3 bilie, sbaglia una sponda
    (1, ["0", "S"]),  # I18 difesa
    (2, ["0", "S"]),  # I18 difesa
    (1, ["1", "G"]),  # I19 chiude di kiss sulla 9               -> 6-2
    (1, ["2", "2", "S"]),  # I20 2 sulla spaccata, poi difesa
    (2, ["3", TpaButton.KICK_IN, "M", "N"]),  # I20 entra di sponda, +2, sbaglia, fallo
    (1, ["4"]),  # I21 chiude il rack                       -> 7-2
]


def play(session, game_type: int = 9) -> TpaState:
    """Rigioca una sessione di referto e restituisce lo stato finale."""
    state = TpaState(game_type)
    for player, buttons in session:
        if state.current_player != player:
            state.toggle_player()
        for button in buttons:
            state.annotate(button)
        state.toggle_player()
    return state


@pytest.fixture(scope="module")
def sample() -> TpaState:
    return play(SAMPLE_SESSION)


def test_punteggio_finale_e_sette_a_due(sample):
    """Il testo Accu-Stats chiude la sessione d'esempio sul 7-2."""
    assert sample.tally(1).racks_won == 7
    assert sample.tally(2).racks_won == 2


def test_categorie_che_combaciano_col_referto_ufficiale(sample):
    """Le voci che il PDF e il motore leggono allo stesso modo.

    Sono la maggior parte, e coprono tutte e cinque le famiglie di errore su
    almeno un giocatore: se una regola fosse tradotta male, qui si vedrebbe.
    """
    first, second = sample.tally(1), sample.tally(2)

    # Tom Fisher
    assert first.miss_errors == 4  # 2 (facile, I5) + 1 (I1) + 1 (I14)
    assert first.break_errors == 2  # I3, I17
    assert first.safety_errors == 0  # I20 e' salva grazie al kick-in di P2
    assert first.position_errors == 4  # I1, I10, I14 (due volte)

    # Paul Clark
    assert second.balls_potted == 18
    assert second.miss_errors == 4  # 2 (facile, I13) + 1 (I17) + 1 (I20)
    assert second.break_errors == 0
    assert second.kick_errors == 0
    assert second.safety_errors == 4  # I1, I9, I14, I18


def test_le_divergenze_dal_pdf_sono_quelle_note(sample):
    """I tre scarti dall'esempio Accu-Stats, fissati perche' non scivolino.

    Non sono un difetto da correggere di nascosto: sono la lettura dell'app JS
    con cui i referti si compilano oggi. Se un giorno si decide di allinearsi
    al PDF, questo test si rompe — ed e' il segnale che i referti gia' salvati
    vanno migrati, non ricalcolati in silenzio.
    """
    first, second = sample.tally(1), sample.tally(2)

    # 1. I10: kick riuscito che finisce con battente in buca. Il PDF lo conta
    #    solo come errore di posizione, il motore ci aggiunge il kick.
    assert first.kick_errors == 2  # il PDF ne conta 1 (solo I12)

    # 2. I4 di Paul Clark: bilie imbucate *e* battente in buca. Il motore conta
    #    due errori, come fa per la stessa situazione a I14; il PDF a I14 ne
    #    conta due e a I4 uno solo, contraddicendo se stesso.
    assert second.position_errors == 7  # il PDF ne conta 6

    # 3. Bilie accreditate a Tom Fisher: il PDF ne dichiara 38 senza dire quali
    #    due non accredita, e il referto originale non e' allegato.
    assert first.balls_potted == 40  # il PDF ne dichiara 38


def test_riproduce_i_numeri_dell_app_js_di_riferimento(sample):
    """I due TPA finali, come li calcola l'app JS sulla stessa sessione."""
    first, second = sample.tally(1), sample.tally(2)
    assert (first.balls_potted, total_errors(first), tpa_score(first)) == (40, 12, 769)
    assert (second.balls_potted, total_errors(second), tpa_score(second)) == (
        18,
        15,
        545,
    )


def test_tpa_e_troncato_non_arrotondato():
    """Il TPA si tronca ai millesimi, come una media di battuta."""
    from models.tpa.engine import PlayerTally

    assert tpa_score(PlayerTally(balls_potted=18, position_errors=14)) == 562  # .5625
    assert (
        tpa_score(PlayerTally(balls_potted=0, miss_errors=0)) is None
    )  # niente da dire
    assert tpa_score(PlayerTally(balls_potted=5)) == 1000  # nessun errore


def test_riconoscimenti_di_rack(sample):
    """Break & run, run-out e rack perfetti della sessione d'esempio."""
    first, second = sample.tally(1), sample.tally(2)
    assert first.break_and_runs == 2  # I8 (la 9 sulla spaccata) e I16
    assert first.run_outs == 0
    assert first.perfect_racks == 4
    assert (second.break_and_runs, second.run_outs, second.perfect_racks) == (0, 0, 0)
