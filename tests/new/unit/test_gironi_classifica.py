"""La classifica di una gara a più gironi, senza database (ADR-076).

`models/classification/gironi.py`: ogni girone si ordina per sé, poi la gara
mette prima i primi, poi i secondi, confrontandoli per partita giocata.
"""

from __future__ import annotations

from fractions import Fraction

from models.classification.gironi import Giocate, ordina_a_gironi, per_partita
from models.classification.ordinamento import (
    Concorrente,
    Criterio,
    Scontro,
    Voce,
)

DIFF = Voce(Criterio.DIFFERENZA_RACK)
SCONTRI = Voce(Criterio.SCONTRI_DIRETTI)
SORTEGGIO = Voce(Criterio.SORTEGGIO)


def _c(pid, punti=0, diff=0, sorteggio=0):
    return Concorrente(pid, punti=punti, differenza_rack=diff, sorteggio=sorteggio)


def _ordine(esito):
    return [[c.player_id for c in f.giocatori] for f in esito.fasce]


class TestPerPartita:
    def test_divide_per_le_partite_giocate(self):
        c = per_partita(_c(1, punti=12), Giocate(partite=4, punti=9, vittorie=3))
        assert c.punti == Fraction(9, 4)
        assert c.vittorie == Fraction(3, 4)

    def test_senza_partite_vale_zero(self):
        assert per_partita(_c(1, punti=3), Giocate()).punti == 0


class TestPrimiPoiSecondi:
    def test_tutti_i_primi_poi_tutti_i_secondi(self):
        girone = {1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 1}
        punti = {1: 9, 2: 6, 3: 2, 4: 3, 5: 1, 6: 0}
        concorrenti = [_c(p, punti=v) for p, v in punti.items()]
        giocate = {p: Giocate(partite=2, punti=v) for p, v in punti.items()}
        esito = ordina_a_gironi(
            concorrenti, girone, giocate, Criterio.PUNTI, (DIFF,)
        )
        assert _ordine(esito) == [[1], [4], [2], [5], [3], [6]]
        assert esito.posizione_nel_girone == {1: 1, 2: 2, 3: 3, 4: 1, 5: 2, 6: 3}
        assert esito.girone == girone

    def test_gironi_di_taglia_diversa_per_partita_giocata_senza_x(self):
        """Il primo del girone da sei e quello del girone da cinque (con la X)."""
        # A (sei): 4 vinte su 5 = 12 punti in 5 partite.
        # B (cinque): 3 vinte su 4 più la X = 12 punti, ma 9 in 4 partite.
        girone = {1: 0, 2: 1}
        concorrenti = [_c(1, punti=12), _c(2, punti=12)]
        giocate = {1: Giocate(partite=5, punti=12), 2: Giocate(partite=4, punti=9)}
        esito = ordina_a_gironi(concorrenti, girone, giocate, Criterio.PUNTI, ())
        assert _ordine(esito) == [[1], [2]]

    def test_lo_scontro_diretto_fra_gironi_non_decide(self):
        girone = {1: 0, 2: 1}
        concorrenti = [_c(1, punti=6, diff=1), _c(2, punti=6, diff=3)]
        giocate = {
            1: Giocate(partite=2, punti=6, differenza_rack=1),
            2: Giocate(partite=2, punti=6, differenza_rack=3),
        }
        # Uno scontro fra i due non esiste (gironi diversi); il motore passa
        # alla differenza.
        esito = ordina_a_gironi(
            concorrenti, girone, giocate, Criterio.PUNTI, (SCONTRI, DIFF)
        )
        assert _ordine(esito) == [[2], [1]]

    def test_dentro_il_girone_lo_scontro_diretto_decide(self):
        girone = {1: 0, 2: 0, 3: 1}
        concorrenti = [_c(1, punti=3, diff=0), _c(2, punti=3, diff=5), _c(3)]
        giocate = {p: Giocate(partite=1) for p in (1, 2, 3)}
        esito = ordina_a_gironi(
            concorrenti,
            girone,
            giocate,
            Criterio.PUNTI,
            (SCONTRI, DIFF),
            scontri=[Scontro(1, 2, 3, 1, vincitore=1)],
        )
        assert esito.posizione_nel_girone[1] == 1
        assert esito.posizione_nel_girone[2] == 2

    def test_i_pari_restano_pari_nella_gara(self):
        girone = {1: 0, 2: 1}
        concorrenti = [_c(1, punti=3), _c(2, punti=3)]
        giocate = {p: Giocate(partite=1, punti=3) for p in (1, 2)}
        esito = ordina_a_gironi(concorrenti, girone, giocate, Criterio.PUNTI, ())
        assert _ordine(esito) == [[1, 2]]
        assert esito.fasce[0].posizione == 1

    def test_lo_ssr_guarda_la_posizione_vera(self):
        """I secondi sono al 3° posto: lo SSR «fino al 2°» non li separa."""
        girone = {1: 0, 2: 0, 3: 1, 4: 1}
        concorrenti = [
            Concorrente(1, punti=6),
            Concorrente(2, punti=3, ssr=5),
            Concorrente(3, punti=6),
            Concorrente(4, punti=3, ssr=1),
        ]
        giocate = {
            1: Giocate(1, punti=6),
            2: Giocate(1, punti=3),
            3: Giocate(1, punti=6),
            4: Giocate(1, punti=3),
        }
        catena = (Voce(Criterio.SPAREGGIO_SSR, 2),)
        esito = ordina_a_gironi(concorrenti, girone, giocate, Criterio.PUNTI, catena)
        assert _ordine(esito)[1] == [2, 4]
        catena = (Voce(Criterio.SPAREGGIO_SSR, 3),)
        esito = ordina_a_gironi(concorrenti, girone, giocate, Criterio.PUNTI, catena)
        assert _ordine(esito)[1:] == [[2], [4]]

    def test_ordine_completo_al_turno(self):
        girone = {1: 0, 2: 1}
        concorrenti = [_c(1, sorteggio=9), _c(2, sorteggio=1)]
        giocate = {p: Giocate() for p in (1, 2)}
        esito = ordina_a_gironi(
            concorrenti, girone, giocate, Criterio.PUNTI, (SORTEGGIO,)
        )
        assert _ordine(esito) == [[2], [1]]

    def test_chi_non_ha_girone_viene_dopo(self):
        girone = {1: 0, 2: 1}
        concorrenti = [_c(1), _c(2), _c(3, punti=99)]
        giocate = {p: Giocate() for p in (1, 2, 3)}
        esito = ordina_a_gironi(
            concorrenti, girone, giocate, Criterio.PUNTI, (SORTEGGIO,)
        )
        assert _ordine(esito)[-1] == [3]
        assert 3 not in esito.girone
