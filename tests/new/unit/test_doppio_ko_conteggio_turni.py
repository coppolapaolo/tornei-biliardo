"""I turni di un doppio KO si contano per induzione, non a memoria.

Il numero di turni **programmati** di un doppio KO con tabellone `S = 2^k` e'
`2k`. La bella (grand final reset) e' un turno in piu' che esiste **solo** se
la finale la vince chi arriva dal losers bracket: non e' programmato, e
dichiararlo tale produce il turno fantasma della issue #239 — l'interfaccia
annuncia "Turno 9/9 in corso" su un turno che non contiene partite.

La verifica e' costruita come l'induzione che la giustifica:

* **base**   `P(1) = 2`   — due giocatori: `W1`, poi la finale;
* **passo**  `P(k) = P(k-1) + 2` — un livello in piu' nel winners aggiunge un
  round `W` e **due** round `L` (uno assorbe chi cade dal winners, uno riduce
  i losers fra loro: non si puo' fare in un round solo, o i nuovi arrivati
  salterebbero un giro). Lo schedule mette `W_w` al turno `w` e `L_m` al turno
  `m + 1`, quindi i due round nuovi spingono la finale avanti di due turni;
* **ancoraggio** il numero dichiarato coincide con l'ultimo turno che lo
  schedule popola davvero, escluso il `GFR`. E' il passo che impedisce alla
  formula di divergere dalla struttura senza che nessuno se ne accorga —
  esattamente il difetto descritto nella sezione 0 di CLAUDE.md;
* **corollario** la fase a gironi dura `2w - 1` turni: il girone non deve
  produrre un vincitore, gli bastano i suoi quattro qualificati (due imbattuti
  e due ripescati), quindi si ferma tre turni prima del doppio KO completo
  della stessa taglia — e non ha nessun turno condizionale.
"""

import math

import pytest

from models.matchmaking.bracket import (
    BRACKET_GRAND_FINAL,
    BRACKET_GRAND_FINAL_RESET,
    BRACKET_LOSERS,
    BRACKET_WINNERS,
    QUALIFIERS_PER_GROUP,
    bracket_schedule,
    group_phase_rounds,
    group_schedule,
    group_size_for,
    total_rounds,
)
from models.matchmaking.strategies.double_knockout import DoubleKnockoutStrategy

# `total_rounds` e' aritmetica pura: il pavimento di formato (8 per il doppio
# KO) lo applica chi la chiama, quindi qui si parte da S = 2.
TAGLIE = [2, 4, 8, 16, 32, 64, 128]


def turni_programmati(size: int) -> int:
    """P(k): i turni che la gara giochera' comunque."""
    return total_rounds(size, double_elimination=True)


def ultimo_turno_non_condizionale(size: int) -> int:
    """L'ultimo turno che lo schedule popola con round diversi dalla bella."""
    schedule = bracket_schedule(size, double_elimination=True)
    return max(
        turno
        for turno, rounds in schedule.items()
        if any(r.bracket_type != BRACKET_GRAND_FINAL_RESET for r in rounds)
    )


class TestInduzioneSuiTurniProgrammati:
    def test_base_due_giocatori_giocano_due_turni(self):
        """P(1) = 2: la partita, poi la finale.

        Con due giocatori il losers bracket e' vuoto: il perdente ne e'
        campione d'ufficio senza giocare.
        """
        assert turni_programmati(2) == 2

    @pytest.mark.parametrize("size", TAGLIE[1:])
    def test_passo_un_livello_in_piu_costa_due_turni(self, size):
        """P(k) = P(k-1) + 2, misurato taglia per taglia."""
        assert turni_programmati(size) == turni_programmati(size // 2) + 2

    @pytest.mark.parametrize("size", TAGLIE)
    def test_la_formula_chiusa_e_due_k(self, size):
        """Dalla base e dal passo segue P(k) = 2k."""
        k = int(math.log2(size))
        assert turni_programmati(size) == 2 * k

    @pytest.mark.parametrize("size", TAGLIE)
    def test_ancoraggio_allo_schedule_reale(self, size):
        """Il numero dichiarato e' l'ultimo turno davvero programmato.

        Se un giorno lo schedule cambiasse forma, e' questo test a dirlo:
        senza, formula e struttura possono divergere in silenzio.
        """
        assert turni_programmati(size) == ultimo_turno_non_condizionale(size)

    @pytest.mark.parametrize("size", TAGLIE)
    def test_la_bella_sta_subito_dopo_e_non_e_programmata(self, size):
        """Il `GFR` occupa il turno `2k + 1`, e nessun altro.

        Esiste nella struttura — e' un nodo con le sue coordinate — ma non e'
        un turno che la gara mette in programma.
        """
        schedule = bracket_schedule(size, double_elimination=True)
        turni_con_bella = [
            turno
            for turno, rounds in schedule.items()
            if any(r.bracket_type == BRACKET_GRAND_FINAL_RESET for r in rounds)
        ]
        assert turni_con_bella == [turni_programmati(size) + 1]


class TestCorollarioFaseAGironi:
    """Il girone si ferma quando ha i suoi qualificati, non quando ha un vincitore.

    Attenzione a una coincidenza che invita a spiegarlo male: `G(w) = 2w - 1`
    e `P(w) = 2w`, quindi "il girone costa un turno meno del doppio KO" torna
    a conti fatti — ma confronta il girone con un tabellone che **non e' il
    suo**. La taglia del girone e' `2^(w+1)`, non `2^w`: per `w = 2` sono 8
    giocatori, e un doppio KO da 8 di turni ne vuole 6, non 4. I turni saltati
    sono tre, non uno.

    La ragione vera e' che il girone non deve produrre un vincitore: si ferma
    appena i qualificati sono determinati — due imbattuti (i sopravvissuti del
    winners) e due ripescati (i sopravvissuti del losers), cioe'
    `QUALIFIERS_PER_GROUP`.
    """

    @pytest.mark.parametrize("w", [2, 3, 4, 5])
    def test_la_taglia_del_girone_e_due_alla_w_piu_uno(self, w):
        """Il parametro esposto al director e' `w`, la taglia ne discende."""
        assert group_size_for(w) == 2 ** (w + 1)

    @pytest.mark.parametrize("w", [3, 4, 5])
    def test_passo_un_livello_in_piu_costa_due_turni(self, w):
        """Stessa ricorrenza del doppio KO, base diversa: G(2) = 3."""
        assert group_phase_rounds(w) == group_phase_rounds(w - 1) + 2

    def test_base_il_girone_da_otto_dura_tre_turni(self):
        """`W1`, poi `W2 + L1`, poi `L2`: e i quattro qualificati ci sono."""
        assert group_phase_rounds(2) == 3

    @pytest.mark.parametrize("w", [2, 3, 4, 5])
    def test_ancoraggio_allo_schedule_del_girone(self, w):
        """Il numero dichiarato e' l'ultimo turno popolato."""
        schedule = group_schedule(w)
        atteso = max(turno for turno, rounds in schedule.items() if rounds)
        assert group_phase_rounds(w) == atteso

    @pytest.mark.parametrize("w", [2, 3, 4, 5])
    def test_alla_fine_restano_esattamente_i_qualificati(self, w):
        """La ragione del numero di turni, misurata sui match dello schedule.

        Chi sopravvive al winners e' `taglia / 2^(ultimo round W)`; chi
        sopravvive al losers e' il numero di match del suo ultimo round, uno
        per match. La somma deve fare `QUALIFIERS_PER_GROUP`: e' questo che
        dice quando il girone ha finito.
        """
        schedule = group_schedule(w)
        rounds = [r for entries in schedule.values() for r in entries]

        def ultimo(tipo):
            return max(
                (r for r in rounds if r.bracket_type == tipo),
                key=lambda r: r.bracket_round,
            )

        ultimo_w = ultimo(BRACKET_WINNERS)
        ultimo_l = ultimo(BRACKET_LOSERS)

        imbattuti = ultimo_w.n_matches
        ripescati = ultimo_l.n_matches
        assert imbattuti + ripescati == QUALIFIERS_PER_GROUP
        assert imbattuti == 2 and ripescati == 2

    @pytest.mark.parametrize("w", [2, 3, 4, 5])
    def test_quanto_manca_al_doppio_ko_completo_sono_tre_turni(self, w):
        """Il confronto giusto: girone e tabellone della **stessa** taglia.

        Mancano la finale e gli ultimi due round del losers — quelli che
        servirebbero a stringere i quattro fino a uno.
        """
        assert group_phase_rounds(w) == turni_programmati(group_size_for(w)) - 3


class _GaraFinta:
    """Il minimo che `has_round` legge: formato e turni programmati."""

    def __init__(self, rounds_count: int, double_ko_rounds=None):
        self.rounds_count = rounds_count
        self.double_ko_rounds = double_ko_rounds
        self.matchmaking_strategy = "double_knockout"


class TestLaVarianteAGironiNonHaTurniCondizionali:
    """Nel formato FISBB la bella non esiste, in nessuna delle due fasi.

    Vale la pena dimostrarlo invece di darlo per buono: e' il motivo per cui
    `has_round` puo' rispondere "no" senza nemmeno leggere i nodi quando la
    gara ha una fase a gironi.
    """

    @pytest.mark.parametrize("w", [2, 3, 4, 5])
    def test_il_girone_non_arriva_mai_alla_finale(self, w):
        """Il girone non arriva mai a una finale, quindi mai a una bella."""
        tipi = {r.bracket_type for rounds in group_schedule(w).values() for r in rounds}
        assert BRACKET_GRAND_FINAL not in tipi
        assert BRACKET_GRAND_FINAL_RESET not in tipi

    @pytest.mark.parametrize("size", [4, 8, 16, 32])
    def test_il_tabellone_finale_e_eliminazione_diretta_pura(self, size):
        """La seconda fase non ha ne' losers bracket ne' bella."""
        tipi = {
            r.bracket_type for rounds in bracket_schedule(size).values() for r in rounds
        }
        assert BRACKET_GRAND_FINAL_RESET not in tipi

    def test_has_round_si_ferma_ai_turni_programmati(self):
        """Con i gironi la risposta e' aritmetica, senza guardare i nodi.

        Il doppio KO classico invece, oltre `rounds_count`, deve interrogare
        il tabellone — e con una gara finta come questa solleverebbe. Che non
        succeda e' la prova che il ramo a gironi esce prima.
        """
        gara = _GaraFinta(rounds_count=7, double_ko_rounds=3)
        strategia = DoubleKnockoutStrategy()

        assert strategia.has_round(gara, 7) is True
        assert strategia.has_round(gara, 8) is False
        assert strategia.has_round(gara, 0) is False
