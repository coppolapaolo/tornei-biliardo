"""Lo spareggio dice quali posti sono in palio, non solo da dove parte.

Rilievo della gara del 2026-09-23: prima di avviare lo spareggio il direttore
leggeva «2° posto a pari merito» accanto a ogni giocatore, e non sapeva se lo
spot shot rally valesse il 2° e il 3° posto o solo il 2°. I posti contesi
vanno dalla posizione del gruppo fino a ``tiebreaker_until_position``: sotto
quella soglia il pari merito è legittimo (issue #63), e i posti oltre non
sono in palio.
"""

import pytest

from models.competition.spareggio_service import SpareggioService


@pytest.mark.parametrize(
    "giocatori, posizione, limite, attesi",
    [
        (2, 1, 3, [1, 2]),  # primo e secondo
        (2, 2, 3, [2, 3]),  # secondo e terzo
        (3, 1, 3, [1, 2, 3]),  # tutto il podio
        (3, 2, 3, [2, 3]),  # il quarto posto non si decide
        (4, 3, 3, [3]),  # issue #63: basta un vincitore
        (2, 3, 3, [3]),
        (1, 1, 3, []),  # nessun gruppo
    ],
)
def test_posti_in_palio(giocatori, posizione, limite, attesi):
    assert SpareggioService.posti_in_palio(giocatori, posizione, limite) == attesi


def test_i_posti_in_palio_sono_uno_piu_dei_punteggi_da_separare():
    """Stessa regola di ``positions_to_discriminate``, detta in posti."""
    for giocatori in range(2, 6):
        for posizione in range(1, 4):
            posti = SpareggioService.posti_in_palio(giocatori, posizione, 3)
            da_separare = SpareggioService.positions_to_discriminate(
                giocatori, posizione, 3
            )
            assert da_separare == min(len(posti), giocatori - 1)


@pytest.mark.parametrize(
    "posti, testo",
    [
        ([3], "Spareggio per il 3° posto"),
        ([1, 2], "Spareggio per il 1° e il 2° posto"),
        ([2, 3], "Spareggio per il 2° e il 3° posto"),
        ([1, 2, 3], "Spareggio dal 1° al 3° posto"),
    ],
)
def test_il_titolo_dice_i_posti(app, posti, testo):
    with app.test_request_context():
        pagina = app.jinja_env.from_string(
            '{% import "components/_posti_in_palio.html" as pp %}'
            "{{ pp.titolo(posti) }}"
        ).render(posti=posti)
    assert pagina.strip() == testo
