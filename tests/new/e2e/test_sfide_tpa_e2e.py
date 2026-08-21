"""Il referto TPA dal punto di vista di chi gioca (ADR-044).

Le route del referto hanno già i loro test: cinquantatré, fra
`tests/new/integration/test_tpa_referto.py` e `tests/new/unit/test_tpa_engine*.py`.
Guardano una risposta per volta, ed è il livello giusto per le regole
Accu-Stats — che con l'interfaccia non c'entrano niente.

Quello che manca è il livello del **percorso**, e lì vive il patto più
delicato del dominio: col referto aperto il punteggio *discende* dal referto,
quindi il segnapunti normale deve sparire. Non è una regola del motore né una
risposta HTTP: è una cosa che si vede — o non si vede — nell'HTML della pagina
del match. Un referto perfettamente funzionante e una pagina che continua a
offrire i «+1» sono due segnapunti che si contraddicono al primo tocco, e
nessun test che guardi una route per volta se ne accorge.

Da cui la disciplina di sempre: prima cosa mostra la pagina, poi cosa dice il
DB.

C'è poi una cosa che questi percorsi hanno fatto venire fuori guardandoli
tutti insieme. L'avvio rapido porta dritti al segnapunti, e il referto va
aperto **prima del primo triangolo**: la finestra per prenderlo era larga
esattamente un tocco, e si chiudeva senza dire niente. Per questo l'avvio
rapido adesso lo chiede — è la journey `TestIlRefertoSiSceglieAllAvvio`.
"""

from __future__ import annotations

import re

import pytest

from models.status_enum import Discipline, MatchStatus
from sfida_driver import SfidaDriver


def _tasti_segnapunti(pagina: str) -> list[str]:
    """I due tasti «+1» del segnapunti verticale."""
    return re.findall(r"<button[^>]*c7-rackpad__btn[^>]*>", pagina)


def _c_e_il_tabellone(pagina: str) -> bool:
    """Il tabellone orizzontale (issue #170), che segna dagli stessi endpoint."""
    return 'id="matchBoard"' in pagina


# ══════════════════════════════════════════════════════════════════════
# Un segnapunti solo (ADR-044)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestUnSegnapuntiSolo:
    """Aperto il referto, i «+1» non ci sono più: il punteggio viene di lì."""

    def test_prendo_il_referto_e_i_tasti_del_segnapunti_spariscono(
        self, sfida: SfidaDriver
    ):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)

        prima = sfida.pagina(match_id)
        assert len(_tasti_segnapunti(prima)) == 2
        assert _c_e_il_tabellone(prima)

        sfida.prendi_referto(match_id)

        dopo = sfida.pagina(match_id)
        assert _tasti_segnapunti(dopo) == []
        assert not _c_e_il_tabellone(dopo)

    def test_spariscono_anche_all_avversario(self, sfida: SfidaDriver):
        """Il referto lo tiene uno, ma il patto vale per tutti e due.

        Se all'altro restassero i «+1» sarebbe lui a contraddire il referto,
        e per giunta senza saperlo.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.prendi_referto(match_id)

        sfida.esci()
        sfida.entra(avversario)

        pagina = sfida.pagina(match_id)
        assert _tasti_segnapunti(pagina) == []
        assert not _c_e_il_tabellone(pagina)

    def test_chiuso_il_referto_il_segnapunti_normale_torna(self, sfida: SfidaDriver):
        """Chiudere il referto è dire «da qui in poi segniamo a mano».

        Il punteggio non riparte da zero: resta quello che il referto ha
        scritto, e si continua da lì.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        sfida.prendi_referto(match_id)
        sfida.vinci_rack_nel_referto(match_id, posto=1)

        sfida.chiudi_referto(match_id)

        pagina = sfida.pagina(match_id)
        assert len(_tasti_segnapunti(pagina)) == 2
        assert _c_e_il_tabellone(pagina)
        assert sfida.punteggio(match_id) == (1, 0)

        # E il triangolo segnato a mano si somma a quelli del referto.
        sfida.segna(match_id, io_)
        assert sfida.punteggio(match_id) == (2, 0)


# ══════════════════════════════════════════════════════════════════════
# Il punteggio discende dal referto
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestIlPunteggioDiscendeDalReferto:
    def test_un_rack_annotato_si_vede_sulla_pagina_del_match(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        sfida.prendi_referto(match_id)

        sfida.vinci_rack_nel_referto(match_id, posto=1)

        assert sfida.punteggio(match_id) == (1, 0)
        # La pagina del match lo dice, pur non avendo più un segnapunti.
        assert "1" in sfida.pagina(match_id)

    def test_l_annulla_riporta_indietro_anche_il_match(self, sfida: SfidaDriver):
        """Il registro dei comandi è l'unica verità: si annulla di lì.

        Se il punteggio del match fosse un totale salvato a parte, qui
        divergerebbe — ed è il motivo per cui non lo è.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        sfida.prendi_referto(match_id)
        sfida.vinci_rack_nel_referto(match_id, posto=1)

        # L'ultimo tocco del rack è `end`: annullarlo riapre il turno vinto,
        # quindi il rack non è più chiuso e il punto se ne va con lui.
        risposta = sfida.annulla_tocco(match_id)

        assert risposta.status_code == 200
        assert sfida.punteggio(match_id) == (0, 0)

    def test_alla_distanza_la_partita_chiede_conferma_ai_due(self, sfida: SfidaDriver):
        """Il percorso intero: dal referto alla doppia conferma (ADR-051).

        È qui che le due decisioni si incontrano — il punteggio arriva dal
        referto, ma a chiudere la partita restano i due giocatori.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(
            avversario,
            distance="2",
            is_race_to="true",
            discipline=Discipline.NINE_BALL.value,
        )
        sfida.prendi_referto(match_id)

        sfida.vinci_rack_nel_referto(match_id, posto=1)
        sfida.vinci_rack_nel_referto(match_id, posto=1)

        assert sfida.punteggio(match_id) == (2, 0)
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS

        sfida.conferma(match_id)
        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)

        assert sfida.stato(match_id) == MatchStatus.CONFIRMED_BY_BOTH
        assert sfida.partita(match_id).winner_id == io_.id


# ══════════════════════════════════════════════════════════════════════
# Chi tiene il referto, chi lo guarda
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestChiTieneIlRefertoEChiLoGuarda:
    def test_l_avversario_lo_segue_ma_non_ci_scrive(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.prendi_referto(match_id)
        sfida.vinci_rack_nel_referto(match_id, posto=1)

        sfida.esci()
        sfida.entra(avversario)

        stato = sfida.stato_referto(match_id)
        assert stato.status_code == 200
        assert stato.get_json()["state"]["can_write"] is False

        rifiutato = sfida.premi(match_id, "seat:1")
        assert rifiutato.status_code == 403
        assert io_.username in rifiutato.get_json()["message"]

    def test_la_pagina_del_match_dice_a_ciascuno_cosa_puo_fare(
        self, sfida: SfidaDriver
    ):
        """Stesso referto, due frasi diverse: «apri» a chi scrive, «guarda» a chi no."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.prendi_referto(match_id)

        assert "Apri il referto TPA" in sfida.pagina(match_id)

        sfida.esci()
        sfida.entra(avversario)
        assert "Guarda il referto TPA" in sfida.pagina(match_id)

    def test_un_estraneo_non_arriva_al_referto(self, sfida: SfidaDriver):
        io_, avversario, terzo = sfida.crea_giocatori(3)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.prendi_referto(match_id)

        sfida.esci()
        sfida.entra(terzo)

        assert sfida.pagina_referto(match_id).status_code == 302
        assert sfida.stato_referto(match_id).status_code == 404
        assert sfida.premi(match_id, "seat:1").status_code == 404


# ══════════════════════════════════════════════════════════════════════
# Il referto chiuso
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestIlRefertoChiuso:
    def test_chiuso_si_rilegge_e_basta(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.prendi_referto(match_id)
        sfida.vinci_rack_nel_referto(match_id, posto=1)

        sfida.chiudi_referto(match_id)

        assert "Rivedi il referto TPA" in sfida.pagina(match_id)
        assert sfida.premi(match_id, "seat:2").status_code == 409
        assert sfida.annulla_tocco(match_id).status_code == 409
        # Ma lo stato resta leggibile: il referto è un documento, non una sessione.
        assert sfida.stato_referto(match_id).status_code == 200

    def test_i_numeri_del_referto_restano_dopo_la_chiusura(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.prendi_referto(match_id)
        sfida.vinci_rack_nel_referto(match_id, posto=1)
        sfida.chiudi_referto(match_id)

        stato = sfida.stato_referto(match_id).get_json()["state"]
        # Il rack intero imbucato e nessun errore: TPA pieno (`1000` = 1.000).
        bilie_del_rack = sfida.referto(match_id).game_type
        assert stato["score"]["1"]["balls_potted"] == bilie_del_rack
        assert stato["score"]["1"]["total_errors"] == 0
        assert stato["score"]["1"]["tpa"] == 1000


# ══════════════════════════════════════════════════════════════════════
# La finestra di un istante
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestLaFinestraDiUnIstante:
    def test_a_triangolo_segnato_il_referto_non_si_apre_piu(self, sfida: SfidaDriver):
        """La regola: il referto parte da 0-0, quindi va preso prima del primo rack."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)

        sfida.segna(match_id, io_)
        sfida.apri_referto(match_id)

        assert sfida.referto(match_id) is None

    def test_e_il_perche_sta_scritto_sulla_pagina_del_referto(self, sfida: SfidaDriver):
        """Il pulsante sparisce dalla pagina del match; il motivo si legge qui.

        Non è un dettaglio: chi ci arriva dal segnalibro, o dopo aver segnato
        per sbaglio, deve poter capire cos'è successo.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)
        sfida.segna(match_id, io_)

        pagina = sfida.html_referto(match_id)
        assert "prima del primo triangolo" in pagina

    def test_sulla_pagina_del_match_il_pulsante_non_c_e_piu(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)

        assert "Prendi il referto TPA" in sfida.pagina(match_id)
        sfida.segna(match_id, io_)
        assert "Prendi il referto TPA" not in sfida.pagina(match_id)


# ══════════════════════════════════════════════════════════════════════
# Il referto si sceglie all'avvio
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestIlRefertoSiSceglieAllAvvio:
    """La finestra di un istante, chiusa scegliendo prima.

    L'avvio rapido è fatto per non fare domande: si sceglie chi si ha davanti
    e si è al segnapunti. Ma il referto è l'unica cosa che *dopo* non si può
    più decidere, e chiederla a segnapunti aperto vuol dire chiederla troppo
    tardi. Quindi la domanda si fa lì, una volta, a chi la funzione ce l'ha.
    """

    def test_il_modulo_di_avvio_lo_propone(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        modulo = sfida.pagina_avvio_rapido()

        assert 'name="tpa_referto"' in modulo
        assert "referto TPA" in modulo

    def test_scelto_il_referto_la_partita_nasce_col_referto_gia_aperto(
        self, sfida: SfidaDriver
    ):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        match_id = sfida.apri_partita(avversario, tpa_referto="true")

        referto = sfida.referto(match_id)
        assert referto is not None
        assert referto.compiler_id == io_.id
        # E niente segnapunti doppio: il patto vale da subito.
        assert _tasti_segnapunti(sfida.pagina(match_id)) == []

    def test_e_si_va_dritti_al_referto_invece_che_al_segnapunti(
        self, sfida: SfidaDriver
    ):
        """Chi ha chiesto il referto sta per annotare la spaccata, non i «+1»."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        risposta = sfida.avvio_rapido(avversario, tpa_referto="true")

        assert risposta.status_code == 200
        assert risposta.get_json()["url"].endswith("/tpa")

    def test_anche_col_modulo_vero_e_non_solo_via_json(self, sfida: SfidaDriver):
        """La casella manda `1`, non `true`: il modulo è quello del browser.

        Il resto di queste journey passa dalla chiamata JSON che fa la pagina;
        qui si manda quello che manda davvero un `<input type="checkbox">`
        premuto — cioè il suo `value`. Sono due formati diversi della stessa
        richiesta, e uno solo dei due arriva dai telefoni.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        risposta = sfida.client.post(
            "/match/quick",
            data={"opponent_id": str(avversario.id), "tpa_referto": "1"},
            follow_redirects=False,
        )

        assert risposta.status_code == 302
        assert risposta.headers["Location"].endswith("/tpa")
        match_id = int(
            re.search(r"/matches/(\d+)/tpa", risposta.headers["Location"])[1]
        )
        assert sfida.referto(match_id) is not None

    def test_senza_la_spunta_niente_referto(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        match_id = sfida.apri_partita(avversario)

        assert sfida.referto(match_id) is None

    def test_su_una_disciplina_senza_tpa_la_spunta_non_blocca_l_avvio(
        self, sfida: SfidaDriver
    ):
        """Chiedere l'impossibile non deve costare la partita.

        La disciplina si sceglie nello stesso modulo, e a One Pocket il TPA non
        vuol dire niente: la partita parte lo stesso, senza referto.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        match_id = sfida.apri_partita(
            avversario,
            tpa_referto="true",
            discipline=Discipline.ONE_POCKET.value,
        )

        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS
        assert sfida.referto(match_id) is None

    def test_ne_su_un_match_a_set(self, sfida: SfidaDriver):
        """Il referto conta i rack di **una** partita, non i set di una sfida."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        match_id = sfida.apri_partita(
            avversario, tpa_referto="true", match_format="multi", match_distance="3"
        )

        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS
        assert sfida.referto(match_id) is None
