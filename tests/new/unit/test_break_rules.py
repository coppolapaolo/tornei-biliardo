"""Chi apre ogni triangolo: la funzione pura dell'ADR-056.

Non tocca il DB. Le due regole «a turno» dipendono solo dalla posizione, le due
che guardano indietro dipendono dallo storico: la differenza conta, perché è
quella che rende le prime immuni a un triangolo annullato e le seconde no.
"""

import pytest

from models.match.break_rules import (
    DEFAULT_BREAK_RULE,
    DEFAULT_START_RULE,
    BreakRule,
    StartRule,
    break_player_for_rack,
)

A, B = 11, 22


def chi_apre(regola, indice, vincitori=()):
    return break_player_for_rack(regola, indice, A, B, list(vincitori))


class TestAlternate:
    def test_a_turno_si_scambia_a_ogni_triangolo(self):
        assert [chi_apre(BreakRule.ALTERNATE, n) for n in range(6)] == [
            A,
            B,
            A,
            B,
            A,
            B,
        ]

    def test_a_turno_ogni_due_cambia_ogni_due(self):
        assert [chi_apre(BreakRule.ALTERNATE_TWO, n) for n in range(8)] == [
            A,
            A,
            B,
            B,
            A,
            A,
            B,
            B,
        ]

    def test_le_alternate_non_guardano_lo_storico(self):
        """Chi ha vinto non c'entra: è per questo che un annullo non le sposta."""
        assert chi_apre(BreakRule.ALTERNATE, 3, [B, B, B]) == B
        assert chi_apre(BreakRule.ALTERNATE, 3, [A, A, A]) == B


class TestGuardanoIndietro:
    def test_spacca_chi_ha_vinto(self):
        assert chi_apre(BreakRule.WINNER_BREAKS, 1, [B]) == B
        assert chi_apre(BreakRule.WINNER_BREAKS, 2, [B, A]) == A

    def test_spacca_chi_ha_perso(self):
        assert chi_apre(BreakRule.LOSER_BREAKS, 1, [B]) == A
        assert chi_apre(BreakRule.LOSER_BREAKS, 2, [B, A]) == B

    def test_storico_incompleto_non_si_inventa_niente(self):
        """Meglio nessuna pastiglia che una sbagliata."""
        assert chi_apre(BreakRule.WINNER_BREAKS, 3, [B]) is None
        assert chi_apre(BreakRule.LOSER_BREAKS, 3, [B]) is None


class TestPrimoTriangolo:
    @pytest.mark.parametrize("regola", list(BreakRule))
    def test_il_primo_lo_apre_sempre_chi_ha_l_apertura(self, regola):
        assert chi_apre(regola, 0) == A

    def test_senza_acchito_registrato_non_si_sa_chi_apre(self):
        """`None` non è un ripiego: è il segnale che fa comparire le domande."""
        for n in range(4):
            assert break_player_for_rack(BreakRule.ALTERNATE, n, None, B, []) is None


class TestValoriIgnoti:
    def test_una_regola_ignota_ricade_sul_default(self):
        """Il chiamante è un segnapunti al tavolo: preferisce una risposta."""
        assert chi_apre("regola_che_non_esiste", 1) == chi_apre(DEFAULT_BREAK_RULE, 1)

    def test_normalize_torna_none_sull_ignoto(self):
        assert BreakRule.normalize("boh") is None
        assert StartRule.normalize("boh") is None
        assert BreakRule.normalize(None) is None
        assert BreakRule.normalize("alternate") is BreakRule.ALTERNATE
        assert BreakRule.normalize(BreakRule.LOSER_BREAKS) is BreakRule.LOSER_BREAKS

    def test_i_default(self):
        """Acchito per ciò che nasce (2026-09-24); a turno fra i triangoli."""
        assert DEFAULT_START_RULE is StartRule.LAG
        assert DEFAULT_BREAK_RULE is BreakRule.ALTERNATE


class TestBreakAndRun:
    """La sigla sul trattino: B se aveva aperto lui, R se ha risposto."""

    @pytest.mark.parametrize(
        "regola,indice,vincitori,apre_il_vincitore",
        [
            # A apre il primo e lo vince: break and run.
            (BreakRule.ALTERNATE, 0, [A], True),
            # Il secondo lo apre B, ma lo vince A: run-out da risposta.
            (BreakRule.ALTERNATE, 1, [A, A], False),
            # Spacca chi ha vinto: chi vince due di fila apre il secondo.
            (BreakRule.WINNER_BREAKS, 1, [A, A], True),
            # Spacca chi ha perso: chi vince non riapre mai.
            (BreakRule.LOSER_BREAKS, 1, [A, A], False),
        ],
    )
    def test_si_deduce_da_chi_apriva(
        self, regola, indice, vincitori, apre_il_vincitore
    ):
        apre = chi_apre(regola, indice, vincitori[:indice])
        assert (apre == vincitori[indice]) is apre_il_vincitore
