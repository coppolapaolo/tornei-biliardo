"""L'handicap: le categorie degli iscritti, e l'Elo che ne dipende.

Nel campionato l'handicap è acceso. Vale la pena dire subito cosa **non** fa,
perché il nome suggerisce altro: non cambia le distanze. Nessuno gioca al 5
contro uno che gioca al 3. Quello che fa (ADR-049) è due cose:

1. ogni iscritto può avere una **categoria**, che vive nella competizione — non
   sull'utente — e che il direttore assegna scrivendone il nome nel combo
   accanto al nome dell'iscritto: la categoria nasce lì, non c'è un elenco da
   preparare prima;
2. l'**Elo** si aggiorna solo fra giocatori della **stessa** categoria. Fra
   categorie diverse la partita conta per la classifica di gara ma non tocca il
   rating, perché il risultato riflette l'handicap e non la forza. E «non lo
   so» non è «sono uguali»: senza categoria il rating non si muove.

La finestra per assegnarle si chiude all'avvio del primo turno, e prima
dell'avvio la pagina avvisa quanti iscritti sono ancora senza.
"""

from __future__ import annotations

import pytest

from campionato_driver import CampionatoDriver
from stagione import CATEGORIE, MINIMO_ISCRITTI, crea_stagione
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole


@pytest.fixture
def gara_con_iscritti(campionato: CampionatoDriver):
    """Prima gara della stagione, iscrizioni aperte e sei iscritti."""
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    campionato_id, gare = crea_stagione(campionato, direttore)
    giocatori = campionato.crea_giocatori(MINIMO_ISCRITTI)

    campionato.entra(direttore)
    campionato.apri_iscrizioni(gare[1])
    campionato.iscrivi_tutti(gare[1], giocatori)
    campionato.entra(direttore)
    return campionato_id, gare, direttore, giocatori


@pytest.mark.e2e
class TestLHandicapSiEredita:
    def test_il_campionato_ce_l_ha_e_le_gare_lo_prendono_da_lui(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        """Il direttore lo accende una volta sola, sul campionato.

        Il campo della gara resta su «eredita» (`None`), che non è la stessa
        cosa di «no»: se domani il campionato cambiasse idea, le gare
        seguirebbero.
        """
        campionato_id, gare, _direttore, _giocatori = gara_con_iscritti

        assert campionato.campionato(campionato_id).has_handicap is True
        for gara_id in gare.values():
            gara = campionato.gara(gara_id)
            assert gara.has_handicap is None, "la gara non deve decidere da sé"
            assert gara.effective_has_handicap is True


@pytest.mark.e2e
class TestAssegnareLeCategorie:
    def test_la_categoria_nasce_scrivendola_sul_primo_iscritto(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        _campionato_id, gare, _direttore, giocatori = gara_con_iscritti
        gara_id = gare[1]

        assert campionato.categorie_della_gara(gara_id) == []

        esito = campionato.assegna_categoria(gara_id, giocatori[0], "B")

        assert esito["status"] == 200, esito
        assert campionato.categoria_di(gara_id, giocatori[0]) == "B"
        assert campionato.categorie_della_gara(gara_id) == ["B"]

    def test_dal_secondo_in_poi_la_si_ritrova_in_tendina(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        """Scrivere lo stesso nome due volte non crea due categorie."""
        _campionato_id, gare, _direttore, giocatori = gara_con_iscritti
        gara_id = gare[1]

        campionato.assegna_categoria(gara_id, giocatori[0], "B")
        campionato.assegna_categoria(gara_id, giocatori[1], "B")

        assert campionato.categorie_della_gara(gara_id) == ["B"]
        assert campionato.categoria_di(gara_id, giocatori[1]) == "B"

    def test_tutte_e_tre_le_categorie_della_stagione(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        _campionato_id, gare, _direttore, giocatori = gara_con_iscritti
        gara_id = gare[1]

        for indice, giocatore in enumerate(giocatori):
            campionato.assegna_categoria(
                gara_id, giocatore, CATEGORIE[indice % len(CATEGORIE)]
            )

        assert sorted(campionato.categorie_della_gara(gara_id)) == sorted(CATEGORIE)
        assert all(
            campionato.categoria_di(gara_id, giocatore) is not None
            for giocatore in giocatori
        )

    def test_la_categoria_si_toglie_con_un_nome_vuoto(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        _campionato_id, gare, _direttore, giocatori = gara_con_iscritti
        gara_id = gare[1]

        campionato.assegna_categoria(gara_id, giocatori[0], "B")
        campionato.assegna_categoria(gara_id, giocatori[0], "")

        assert campionato.categoria_di(gara_id, giocatori[0]) is None

    def test_la_pagina_avvisa_chi_e_ancora_senza(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        """L'avviso prima dell'avvio: dopo non si cambia più."""
        _campionato_id, gare, _direttore, giocatori = gara_con_iscritti
        gara_id = gare[1]

        campionato.assegna_categoria(gara_id, giocatori[0], "B")

        pagina = campionato.pagina_gara(gara_id)

        assert "non hanno una categoria" in pagina
        assert "non conteranno per l" in pagina

    def test_avviato_il_turno_le_categorie_sono_congelate(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        """Sono loro a decidere quali partite contano: cambiarle dopo l'avvio
        riscriverebbe le regole a partita in corso."""
        _campionato_id, gare, direttore, giocatori = gara_con_iscritti
        gara_id = gare[1]
        for giocatore in giocatori:
            campionato.assegna_categoria(gara_id, giocatore, "B")

        campionato.entra(direttore)
        campionato.avvia_primo_turno(gara_id)

        esito = campionato.assegna_categoria(gara_id, giocatori[0], "C")

        assert esito["status"] >= 400, esito
        assert campionato.categoria_di(gara_id, giocatori[0]) == "B"

    def test_un_giocatore_non_assegna_le_categorie(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        _campionato_id, gare, _direttore, giocatori = gara_con_iscritti
        gara_id = gare[1]

        campionato.entra(giocatori[0])
        esito = campionato.assegna_categoria(gara_id, giocatori[1], "A")

        assert esito["status"] >= 400, esito
        assert campionato.categoria_di(gara_id, giocatori[1]) is None


@pytest.mark.e2e
class TestLaCategoriaSiRiportaAllaGaraSuccessiva:
    """Otto prove significherebbero riassegnare tutti otto volte."""

    def test_iscrivendosi_alla_gara_dopo_la_categoria_viene_con_lui(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        _campionato_id, gare, direttore, giocatori = gara_con_iscritti
        prima, seconda = gare[1], gare[2]
        for indice, giocatore in enumerate(giocatori):
            campionato.assegna_categoria(
                prima, giocatore, CATEGORIE[indice % len(CATEGORIE)]
            )

        campionato.entra(direttore)
        campionato.apri_iscrizioni(seconda)
        campionato.iscrivi_tutti(seconda, giocatori)

        campionato.entra(direttore)
        for giocatore in giocatori:
            assert campionato.categoria_di(seconda, giocatore) == (
                campionato.categoria_di(prima, giocatore)
            ), f"{giocatore.username} ha perso la categoria fra una gara e l'altra"

    def test_e_il_direttore_corregge_solo_chi_e_cambiato(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        _campionato_id, gare, direttore, giocatori = gara_con_iscritti
        prima, seconda = gare[1], gare[2]
        for giocatore in giocatori:
            campionato.assegna_categoria(prima, giocatore, "C")

        campionato.entra(direttore)
        campionato.apri_iscrizioni(seconda)
        campionato.iscrivi_tutti(seconda, giocatori)

        campionato.entra(direttore)
        promosso = giocatori[0]
        campionato.assegna_categoria(seconda, promosso, "B")

        assert campionato.categoria_di(seconda, promosso) == "B"
        assert (
            campionato.categoria_di(prima, promosso) == "C"
        ), "la promozione non deve riscrivere la gara già giocata"
        for altro in giocatori[1:]:
            assert campionato.categoria_di(seconda, altro) == "C"


@pytest.mark.e2e
class TestLEloSeguoLeCategorie:
    """La regola che l'handicap davvero governa (ADR-049)."""

    def _gara_avviata(
        self, campionato: CampionatoDriver, gara_con_iscritti, categorie: list[str]
    ):
        """Assegna una categoria per giocatore, poi avvia il primo turno."""
        _campionato_id, gare, direttore, giocatori = gara_con_iscritti
        gara_id = gare[1]
        for giocatore, nome in zip(giocatori, categorie):
            if nome:
                campionato.assegna_categoria(gara_id, giocatore, nome)

        campionato.entra(direttore)
        campionato.avvia_primo_turno(gara_id)
        return gara_id, direttore, giocatori

    def test_fra_pari_categoria_l_elo_si_muove(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        gara_id, direttore, giocatori = self._gara_avviata(
            campionato, gara_con_iscritti, ["B"] * MINIMO_ISCRITTI
        )
        partita = campionato.partite(gara_id, turno=1)[0]
        per_id = {g.id: g for g in giocatori}
        uno, due = per_id[partita.player1_id], per_id[partita.player2_id]
        assert campionato.elo(uno) is None and campionato.elo(due) is None

        campionato.entra(direttore)
        campionato.gioca_match(partita.id)

        assert MatchStatus.is_finished(campionato.partite(gara_id, turno=1)[0].status)
        assert (
            campionato.elo(uno) is not None
        ), "l'Elo non si è mosso fra pari categoria"
        assert campionato.elo(due) is not None

    def test_fra_categorie_diverse_l_elo_resta_fermo(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        """La partita conta per la gara, non per il rating: il risultato è
        figlio dell'handicap, non della forza."""
        gara_id, direttore, giocatori = self._gara_avviata(
            campionato,
            gara_con_iscritti,
            ["A", "B", "C", "A", "B", "C"],
        )
        per_id = {g.id: g for g in giocatori}
        diverse = [
            partita
            for partita in campionato.partite(gara_id, turno=1)
            if not partita.is_bye
            and campionato.categoria_di(gara_id, per_id[partita.player1_id])
            != campionato.categoria_di(gara_id, per_id[partita.player2_id])
        ]
        assert diverse, "il sorteggio non ha prodotto nessuna coppia mista"
        partita = diverse[0]
        uno, due = per_id[partita.player1_id], per_id[partita.player2_id]

        campionato.entra(direttore)
        campionato.gioca_match(partita.id)

        chiusa = [p for p in campionato.partite(gara_id, turno=1) if p.id == partita.id]
        assert MatchStatus.is_finished(chiusa[0].status)
        assert campionato.elo(uno) is None
        assert campionato.elo(due) is None

    def test_senza_categoria_l_elo_non_si_muove(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        """«Non lo so» non è «sono uguali»."""
        gara_id, direttore, giocatori = self._gara_avviata(
            campionato, gara_con_iscritti, [""] * MINIMO_ISCRITTI
        )
        partita = campionato.partite(gara_id, turno=1)[0]
        per_id = {g.id: g for g in giocatori}
        uno, due = per_id[partita.player1_id], per_id[partita.player2_id]

        campionato.entra(direttore)
        campionato.gioca_match(partita.id)

        assert MatchStatus.is_finished(campionato.partite(gara_id, turno=1)[0].status)
        assert campionato.elo(uno) is None
        assert campionato.elo(due) is None

    def test_la_classifica_di_gara_conta_comunque_tutte_le_partite(
        self, campionato: CampionatoDriver, gara_con_iscritti
    ):
        """L'handicap toglie l'Elo, non il risultato: la gara si gioca uguale."""
        gara_id, direttore, _giocatori = self._gara_avviata(
            campionato,
            gara_con_iscritti,
            ["A", "B", "C", "A", "B", "C"],
        )

        campionato.entra(direttore)
        campionato.gioca_turno(gara_id, 1)
        campionato.pagina_gara(gara_id)

        partite = campionato.partite(gara_id, turno=1)
        assert all(MatchStatus.is_finished(p.status) for p in partite)
        assert all(
            p.player1_score + p.player2_score == 5 for p in partite if not p.is_bye
        )
