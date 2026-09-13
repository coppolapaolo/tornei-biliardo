"""Il tabellone intero con i nodi futuri (issue #240).

Copre `models/competition/tabellone_view.py`: i nomi dei round, dove va chi
vince e contro chi, i nodi futuri presenti subito dopo il sorteggio, i bye del
primo turno che non producono perdenti, la finale e la bella del doppio KO, la
finalina, la forma prima del sorteggio e le bande finali.

Test puri: i match sono oggetti finti con le coordinate e i giocatori.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from models.competition.tabellone_view import (
    NomeRound,
    bande_finali,
    costruisci_tabellone,
    destinazione,
    forma_tabellone,
    nome_colonna,
)
from models.matchmaking.bracket import (
    BRACKET_GRAND_FINAL,
    BRACKET_GRAND_FINAL_RESET,
    BRACKET_LOSERS,
    BRACKET_THIRD_PLACE,
    BRACKET_WINNERS,
    standard_bracket_order,
)
from models.status_enum import MatchStatus

pytestmark = pytest.mark.unit

DE = "direct_elimination"
DKO = "double_knockout"
FINITA = MatchStatus.CLOSED_UNILATERALLY.value
IN_CORSO = MatchStatus.PLAYING.value


@dataclass
class U:
    id: int
    username: str


@dataclass
class M:
    id: int
    bracket_type: str
    bracket_round: int
    bracket_slot: int
    round_number: int
    player1: Optional[U]
    player2: Optional[U] = None
    status: str = IN_CORSO
    winner_id: Optional[int] = None
    is_bye: bool = False
    bracket_group: Optional[int] = None

    @property
    def player1_id(self):
        return self.player1.id if self.player1 else None

    @property
    def player2_id(self):
        return self.player2.id if self.player2 else None


def giocatori(n):
    return {i: U(i, f"g{i}") for i in range(1, n + 1)}


def primo_turno(n_iscritti, taglia, *, tipo=BRACKET_WINNERS, gruppo=None, id0=1):
    """Il turno 1 come lo sorteggia la strategia: seed sugli slot canonici."""
    utenti = giocatori(n_iscritti)
    ordine = standard_bracket_order(taglia)
    matches = []
    for j in range(taglia // 2):
        a, b = ordine[2 * j], ordine[2 * j + 1]
        pa, pb = utenti.get(a), utenti.get(b)
        if pa and pb:
            matches.append(M(id0 + j, tipo, 1, j, 1, pa, pb, bracket_group=gruppo))
        else:
            matches.append(
                M(
                    id0 + j,
                    tipo,
                    1,
                    j,
                    1,
                    pa or pb,
                    None,
                    status=FINITA,
                    winner_id=(pa or pb).id,
                    is_bye=True,
                    bracket_group=gruppo,
                )
            )
    return matches, utenti


def chiudi(match, vince_p1=True):
    match.status = FINITA
    match.winner_id = match.player1_id if vince_p1 else match.player2_id


def colonne(tabellone):
    return [
        (c.bracket_type, c.bracket_round, c.turno, c.size, c.nome)
        for lavagna in tabellone.lavagne
        for sezione in lavagna.sections
        for c in sezione.columns
    ]


# ── I nomi ────────────────────────────────────────────────────────────────


class TestNomi:
    def test_eliminazione_da_otto(self):
        nomi = [nome_colonna("W", r, taglia=8, con_ripescati=False) for r in (1, 2, 3)]
        assert nomi == [
            NomeRound("quarti"),
            NomeRound("semifinali"),
            NomeRound("finale"),
        ]

    def test_eliminazione_da_sedici(self):
        nomi = [
            nome_colonna("W", r, taglia=16, con_ripescati=False) for r in (1, 2, 3, 4)
        ]
        assert [n.chiave for n in nomi] == ["ottavi", "quarti", "semifinali", "finale"]

    def test_oltre_i_sedicesimi_resta_il_numero(self):
        assert nome_colonna("W", 1, taglia=64, con_ripescati=False) == NomeRound(
            "turno", 1
        )

    def test_doppio_ko_ripescati_finale_bella_finalina(self):
        assert nome_colonna("W", 2, taglia=8, con_ripescati=True) == NomeRound(
            "turno", 2
        )
        assert nome_colonna("L", 3, taglia=8, con_ripescati=True) == NomeRound(
            "recupero", 3
        )
        assert nome_colonna("GF", 1, taglia=8, con_ripescati=True) == NomeRound(
            "finale"
        )
        assert nome_colonna("GFR", 1, taglia=8, con_ripescati=True) == NomeRound(
            "bella"
        )
        assert nome_colonna("3P", 3, taglia=8, con_ripescati=False) == NomeRound(
            "finalina"
        )


# ── I nodi futuri ─────────────────────────────────────────────────────────


class TestNodiFuturi:
    def test_subito_dopo_il_sorteggio_c_e_tutto_l_albero(self):
        """#240, punto 2: quarti giocati, semifinali e finale gia' disegnate."""
        matches, _ = primo_turno(8, 8)
        t = costruisci_tabellone(matches, strategy=DE)

        assert colonne(t) == [
            ("W", 1, 1, 4, NomeRound("quarti")),
            ("W", 2, 2, 2, NomeRound("semifinali")),
            ("W", 3, 3, 1, NomeRound("finale")),
        ]
        semifinali = [n for n in t.nodi if n.bracket_round == 2]
        assert all(n.futuro for n in semifinali)
        assert all(
            p.fonte and p.fonte.esito == "vincitore"
            for n in semifinali
            for p in n.posti
        )

    def test_la_finalina_sta_nel_turno_della_finale(self):
        matches, _ = primo_turno(8, 8)
        t = costruisci_tabellone(matches, strategy=DE, finalina=True)
        finalina = [n for n in t.nodi if n.bracket_type == BRACKET_THIRD_PLACE]
        assert len(finalina) == 1 and finalina[0].turno == 3
        assert all(p.fonte.esito == "perdente" for p in finalina[0].posti)
        # Il nome del turno 3 resta «finale»: la finalina ci sta dentro.
        assert t.nomi_turni()[3] == [NomeRound("finale")]

    def test_chi_passa_il_turno_e_gia_in_semifinale(self):
        """6 iscritti su 8: le teste di serie 1 e 2 hanno la X."""
        matches, utenti = primo_turno(6, 8)
        t = costruisci_tabellone(matches, strategy=DE)
        noti = {
            p.giocatore.username
            for n in t.nodi
            if n.bracket_round == 2
            for p in n.posti
            if p.giocatore
        }
        assert noti == {"g1", "g2"}

    def test_un_quarto_chiuso_riempie_il_posto_in_semifinale(self):
        matches, utenti = primo_turno(8, 8)
        chiudi(matches[0])  # g1 batte g8
        t = costruisci_tabellone(matches, strategy=DE)
        semi = next(n for n in t.nodi if n.chiave == ("W", 2, 0))
        assert semi.posti[0].giocatore.username == "g1"
        assert semi.posti[1].giocatore is None

    def test_prima_del_sorteggio_non_c_e_tabellone(self):
        assert costruisci_tabellone([], strategy=DE) is None


class TestDoppioKO:
    def test_dopo_il_sorteggio_i_due_rami_e_la_finale(self):
        matches, _ = primo_turno(8, 8)
        t = costruisci_tabellone(matches, strategy=DKO)
        cols = colonne(t)
        tipi = [(c[0], c[1], c[2]) for c in cols]
        assert ("L", 1, 2) in tipi and ("L", 4, 5) in tipi
        assert ("GF", 1, 6) in tipi
        # La bella c'e' come nodo condizionale, al turno 7.
        bella = next(n for n in t.nodi if n.bracket_type == BRACKET_GRAND_FINAL_RESET)
        assert bella.condizionale and bella.turno == 7

    def test_un_bye_non_produce_perdenti(self):
        """5 iscritti su 8: tre X al primo turno, due nella stessa coppia di L1."""
        matches, _ = primo_turno(5, 8)
        t = costruisci_tabellone(matches, strategy=DKO)
        l1 = [
            n
            for n in t.nodi
            if n.bracket_type == BRACKET_LOSERS and n.bracket_round == 1
        ]
        # Coppie (W1 0,1) e (W1 2,3): la seconda ha due X, il nodo non esiste.
        assert [n.slot for n in l1] == [0]
        assert l1[0].is_x  # un solo perdente vero
        l2 = [
            n
            for n in t.nodi
            if n.bracket_type == BRACKET_LOSERS and n.bracket_round == 2
        ]
        assert len(l2) == 2  # i maggiori hanno sempre chi scende dai vincenti

    def test_la_bella_sparisce_se_la_finale_la_vince_l_imbattuto(self):
        imbattuto, ripescato = U(1, "a"), U(2, "b")
        matches, _ = primo_turno(8, 8)
        gf = M(99, BRACKET_GRAND_FINAL, 1, 0, 6, imbattuto, ripescato)
        chiudi(gf, vince_p1=True)
        t = costruisci_tabellone(matches + [gf], strategy=DKO)
        assert not any(n.bracket_type == BRACKET_GRAND_FINAL_RESET for n in t.nodi)

        chiudi(gf, vince_p1=False)
        t = costruisci_tabellone(matches + [gf], strategy=DKO)
        bella = next(n for n in t.nodi if n.bracket_type == BRACKET_GRAND_FINAL_RESET)
        assert [p.giocatore.username for p in bella.posti] == ["a", "b"]

    def test_nomi_dei_turni(self):
        matches, _ = primo_turno(8, 8)
        nomi = costruisci_tabellone(matches, strategy=DKO).nomi_turni()
        assert nomi[2] == [NomeRound("vincenti", 2), NomeRound("recupero", 1)]
        assert nomi[6] == [NomeRound("finale")]
        assert nomi[7] == [NomeRound("bella")]


# ── Dove va chi vince ─────────────────────────────────────────────────────


class TestDestinazione:
    def test_quarto_verso_la_semifinale_contro_il_quarto_vicino(self):
        """wb_feed: il vincitore dello slot 0 incontra quello dello slot 1."""
        matches, _ = primo_turno(8, 8)
        t = costruisci_tabellone(matches, strategy=DE)
        dest = destinazione(t, matches[0].id)
        assert dest.tipo == "nodo"
        assert dest.nome == NomeRound("semifinali")
        assert dest.avversario.fonte.nodo.match is matches[1]
        assert dest.perdente is None

    def test_contro_chi_ha_gia_passato_il_turno(self):
        matches, _ = primo_turno(6, 8)
        t = costruisci_tabellone(matches, strategy=DE)
        # Slot 1 accoppia g4-g5; lo slot 0 e' la X di g1.
        dest = destinazione(t, matches[1].id)
        assert dest.avversario.giocatore.username == "g1"

    def test_la_finale_dell_eliminazione_incorona(self):
        matches, _ = primo_turno(4, 4)
        for m in matches:
            chiudi(m)
        finale = M(10, BRACKET_WINNERS, 2, 0, 2, matches[0].player1, matches[1].player1)
        t = costruisci_tabellone(matches + [finale], strategy=DE)
        assert destinazione(t, finale.id).tipo == "campione"

    def test_nel_doppio_ko_chi_perde_scende_al_recupero(self):
        matches, _ = primo_turno(8, 8)
        t = costruisci_tabellone(matches, strategy=DKO)
        dest = destinazione(t, matches[0].id)
        assert dest.nome == NomeRound("turno", 2)
        assert dest.perdente == NomeRound("recupero", 1)

    def test_seat_della_finale_del_doppio_ko(self):
        """ADR-038: player1 della finale e' il campione dei vincenti."""
        matches, _ = primo_turno(8, 8)
        t = costruisci_tabellone(matches, strategy=DKO)
        finale = next(n for n in t.nodi if n.bracket_type == BRACKET_GRAND_FINAL)
        seat0, seat1 = finale.posti
        assert seat0.fonte.nodo.bracket_type == BRACKET_WINNERS
        assert seat1.fonte.nodo.bracket_type == BRACKET_LOSERS

    def test_la_finale_del_doppio_ko_puo_portare_alla_bella(self):
        gf = M(99, BRACKET_GRAND_FINAL, 1, 0, 6, U(1, "a"), U(2, "b"))
        matches, _ = primo_turno(8, 8)
        t = costruisci_tabellone(matches + [gf], strategy=DKO)
        assert destinazione(t, gf.id).tipo == "finale_doppio"

    def test_semifinale_perdente_va_in_finalina(self):
        matches, _ = primo_turno(4, 4)
        t = costruisci_tabellone(matches, strategy=DE, finalina=True)
        assert destinazione(t, matches[0].id).nome == NomeRound("finale")


# ── La forma prima del sorteggio ──────────────────────────────────────────


class TestForma:
    def test_sei_iscritti_a_eliminazione(self):
        forma = forma_tabellone(6, DE)
        assert (forma.posti, forma.passano, forma.turni) == (8, 2, 3)

    def test_il_doppio_ko_ha_il_pavimento_a_otto(self):
        assert forma_tabellone(6, DKO) is None
        forma = forma_tabellone(9, DKO)
        assert (forma.posti, forma.passano, forma.turni, forma.con_bella) == (
            16,
            7,
            8,
            True,
        )

    def test_amalfi_non_ha_forma(self):
        assert forma_tabellone(8, "amalfi") is None


# ── Le bande finali ───────────────────────────────────────────────────────


class TestBande:
    def test_due_quartifinalisti_stessa_posizione_con_l_uscita(self):
        matches, utenti = primo_turno(8, 8)
        for m in matches:
            chiudi(m)
        s0 = M(10, "W", 2, 0, 2, utenti[1], utenti[4])
        s1 = M(11, "W", 2, 1, 2, utenti[3], utenti[2])
        chiudi(s0)
        chiudi(s1)
        f = M(12, "W", 3, 0, 3, utenti[1], utenti[3])
        chiudi(f)
        t = costruisci_tabellone(matches + [s0, s1, f], strategy=DE)
        posizioni = {1: 1, 3: 2, 4: 3, 2: 3, 8: 5, 5: 5, 6: 5, 7: 5}

        bande = bande_finali(posizioni, t)

        assert [(b.posizione, b.ultima) for b in bande] == [
            (1, 1),
            (2, 2),
            (3, 4),
            (5, 8),
        ]
        quarti = bande[3]
        assert quarti.condivisa
        assert {r.uscita for r in quarti.righe} == {NomeRound("quarti")}
        assert bande[0].righe[0].vinta
