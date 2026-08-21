"""Le sfide individuali dall'inizio alla fine, passando solo dalle route.

Nato da una prova sul campo: una sfida «senza limite», il giocatore preme
**Termina la sfida** e non succede niente di visibile; l'altro deve premere a
sua volta. Nessun test se ne era accorto perché i test che c'erano guardavano
le route una per una — e ognuna, presa da sola, rispondeva correttamente.

Qui si guardano i **percorsi**: la sequenza di gesti che fa una persona, e
quello che la pagina le dice dopo ognuno. È il livello a cui quel difetto si
vede, perché il difetto non è in una risposta HTTP: è nel fatto che due gesti
diversi producono la stessa schermata.

Le osservazioni sono in quest'ordine, sempre: prima cosa mostra la pagina, poi
cosa dice il DB. Una partita chiusa nel DB e una pagina che non lo dice sono
un guasto quanto il contrario.
"""

from __future__ import annotations

import re

import pytest

from models.status_enum import MatchStatus
from sfida_driver import SfidaDriver


def _tasti_segnapunti(pagina: str) -> list[str]:
    """I due tasti «+1» così come stanno nella pagina, attributi compresi."""
    return re.findall(r"<button[^>]*c7-rackpad__btn[^>]*>", pagina)


# ══════════════════════════════════════════════════════════════════════
# Dalla sala al segnapunti (ADR-051)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestAvvioRapido:
    def test_scelgo_chi_ho_davanti_e_sono_al_segnapunti(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        match_id = sfida.apri_partita(avversario)

        pagina = sfida.pagina(match_id)
        # Niente da avviare: la partita è già cominciata.
        assert "Inizia la sfida" not in pagina
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS
        assert sfida.partita(match_id).proposal_id is None

    def test_l_avversario_la_trova_senza_aver_accettato_niente(
        self, sfida: SfidaDriver
    ):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)

        sfida.esci()
        sfida.entra(avversario)

        assert io_.username in sfida.pagina_elenco()
        assert f"/match/matches/{match_id}" in sfida.pagina_elenco()

    def test_un_secondo_avvio_riporta_alla_stessa_partita(self, sfida: SfidaDriver):
        """Due partite in corso fra le stesse due persone non esistono."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        primo = sfida.apri_partita(avversario)
        secondo = sfida.apri_partita(avversario)

        assert primo == secondo
        assert sfida.quante_partite() == 1

    def test_non_si_gioca_contro_se_stessi(self, sfida: SfidaDriver):
        io_ = sfida.crea_giocatore()
        sfida.entra(io_)

        risposta = sfida.avvio_rapido(io_)

        assert risposta.status_code == 422
        assert sfida.quante_partite() == 0


# ══════════════════════════════════════════════════════════════════════
# La partita alla distanza: chi vince firma, chi perde accetta
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestPartitaAllaDistanza:
    def test_percorso_intero_fino_alla_doppia_conferma(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="single", distance=3)

        sfida.segna_piu_volte(match_id, io_, 3)

        # Chi arriva alla distanza ha già firmato: la pagina glielo dice, e non
        # gli propone di firmare una seconda volta.
        pagina = sfida.pagina(match_id)
        assert "Hai confermato" in pagina
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS

        sfida.esci()
        sfida.entra(avversario)
        pagina_altro = sfida.pagina(match_id)
        assert "Accetta" in pagina_altro
        assert "Rifiuta" in pagina_altro

        sfida.conferma(match_id)

        assert sfida.stato(match_id) == MatchStatus.CONFIRMED_BY_BOTH
        assert sfida.punteggio(match_id) == (3, 0)

    def test_alla_distanza_l_interfaccia_non_offre_piu_di_segnare(
        self, sfida: SfidaDriver
    ):
        """Il traguardo spegne i tasti: la regola si vede prima di infrangerla.

        Il freno è **nell'interfaccia**, non nella route: `add_rack` accetterebbe
        ancora un triangolo se qualcuno la chiamasse a mano. Qui si verifica la
        garanzia che l'app dà davvero — nessun comando per farlo — e non una che
        non ha mai dato.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="single", distance=2)
        sfida.segna_piu_volte(match_id, io_, 2)

        # Chi ha vinto è già confermato: a lui il segnapunti sparisce del tutto.
        pagina = sfida.pagina(match_id)
        assert "Distanza raggiunta" in pagina
        assert _tasti_segnapunti(pagina) == []

        # All'altro resta visibile ma spento: dice la regola invece di tacere.
        sfida.esci()
        sfida.entra(avversario)
        tasti = _tasti_segnapunti(sfida.pagina(match_id))
        assert len(tasti) == 2
        assert all("disabled" in tasto for tasto in tasti)

    def test_chi_rifiuta_riapre_la_partita(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="single", distance=2)
        sfida.segna_piu_volte(match_id, io_, 2)

        sfida.esci()
        sfida.entra(avversario)
        sfida.rifiuta(match_id)

        # Il rifiuto toglie l'ultimo triangolo: si torna a giocare.
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS
        assert sfida.punteggio(match_id) == (1, 0)
        assert not sfida.partita(match_id).player1_confirmed


# ══════════════════════════════════════════════════════════════════════
# Senza limite: «finisce quando lo decidete voi»
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestSfidaSenzaLimite:
    def test_segnare_non_chiude_niente(self, sfida: SfidaDriver):
        """Senza distanza non c'è traguardo: nessun triangolo mette una firma.

        Auto-confermare chi è in vantaggio dopo ogni triangolo renderebbe la
        doppia conferma un'illusione: al primo «Termina» dell'altro la partita
        si chiuderebbe con la firma di chi non l'ha mai data.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="free")

        sfida.segna_piu_volte(match_id, io_, 3)
        sfida.segna(match_id, avversario)

        partita = sfida.partita(match_id)
        assert not partita.player1_confirmed
        assert not partita.player2_confirmed
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS

    def test_termina_dice_che_hai_firmato_e_manca_l_altro(self, sfida: SfidaDriver):
        """Il difetto trovato provando l'app: premere e non vedere niente."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="free")
        sfida.segna_piu_volte(match_id, io_, 3)
        sfida.segna(match_id, avversario)

        assert "Termina la sfida" in sfida.pagina(match_id)
        sfida.conferma(match_id)

        dopo = sfida.pagina(match_id)
        # Il gesto ha lasciato un segno: non si ripropone lo stesso pulsante
        # come se non fosse successo niente.
        assert "Termina la sfida" not in dopo
        assert "Hai chiuso la sfida" in dopo
        assert avversario.username in dopo
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS

    def test_l_altro_vede_che_tocca_a_lui(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="free")
        sfida.segna_piu_volte(match_id, io_, 2)
        sfida.conferma(match_id)

        sfida.esci()
        sfida.entra(avversario)
        pagina = sfida.pagina(match_id)

        assert io_.username in pagina
        assert "Accetta" in pagina
        assert "Rifiuta" in pagina

    def test_quando_firmano_in_due_la_partita_e_chiusa(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="free")
        sfida.segna_piu_volte(match_id, io_, 2)
        sfida.conferma(match_id)

        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)

        assert sfida.stato(match_id) == MatchStatus.CONFIRMED_BY_BOTH
        assert sfida.punteggio(match_id) == (2, 0)

    def test_il_segnapunti_sa_che_si_puo_ancora_segnare(self, sfida: SfidaDriver):
        """`can_add` è quello che il tabellone guarda per non ricaricarsi.

        Senza distanza `is_ready_for_validation` è vera dal primo triangolo, e
        chi la scambiasse per «la partita è finita» ricaricherebbe la pagina a
        ogni tocco — buttando via il blocco dello schermo, che è il motivo per
        cui il telefono sulla sponda si spegneva.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="free")

        esito = sfida.segna(match_id, io_).get_json()

        assert esito["is_ready_for_validation"] is True
        assert esito["can_add"] is True, "senza distanza si segna quanto si vuole"

    def test_alla_distanza_il_segnapunti_dice_che_si_e_chiuso(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="single", distance=2)
        sfida.segna(match_id, io_)

        esito = sfida.segna(match_id, io_).get_json()

        assert esito["can_add"] is False

    def test_senza_nemmeno_un_triangolo_non_c_e_niente_da_terminare(
        self, sfida: SfidaDriver
    ):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="free")

        pagina = sfida.pagina(match_id)

        assert "Termina la sfida" not in pagina
        assert sfida.conferma(match_id).status_code == 400


# ══════════════════════════════════════════════════════════════════════
# Casi limite
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestCasiLimite:
    def test_un_estraneo_non_entra_nella_partita_altrui(self, sfida: SfidaDriver):
        io_, avversario, estraneo = sfida.crea_giocatori(3)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)

        sfida.esci()
        sfida.entra(estraneo)

        risposta = sfida.client.get(
            f"/match/matches/{match_id}", follow_redirects=False
        )
        assert risposta.status_code == 302
        assert sfida.segna(match_id, estraneo).status_code == 400

    def test_il_forfait_chiude_senza_la_firma_dell_altro(self, sfida: SfidaDriver):
        """Il forfait è una chiusura unilaterale: non è la doppia conferma."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="single", distance=5)
        sfida.segna(match_id, io_)

        assert sfida.forfait(match_id).status_code == 200

        partita = sfida.partita(match_id)
        assert partita.status == MatchStatus.CLOSED_UNILATERALLY
        assert partita.winner_id == avversario.id

    def test_togliere_un_triangolo_riapre_il_risultato(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="single", distance=2)
        sfida.segna_piu_volte(match_id, io_, 2)

        sfida.togli_ultimo(match_id, io_)

        partita = sfida.partita(match_id)
        assert not partita.player1_confirmed
        assert sfida.punteggio(match_id) == (1, 0)
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS

    def test_la_proposta_resta_la_strada_per_giocare_domani(self, sfida: SfidaDriver):
        """L'avvio rapido non ha sostituito la proposta: sono due percorsi."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = sfida.proponi([avversario])

        sfida.esci()
        sfida.entra(avversario)
        match_id = sfida.accetta_proposta(proposta_id)

        # Una partita concordata nasce da giocare, non già cominciata.
        assert sfida.stato(match_id) == MatchStatus.SCHEDULED
        assert "Inizia la sfida" in sfida.pagina(match_id)

        assert sfida.avvia(match_id).status_code == 200
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS


# ══════════════════════════════════════════════════════════════════════
# Al meglio dei set
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestSfidaAlMeglioDeiSet:
    def test_il_set_finito_lascia_cominciare_il_successivo(self, sfida: SfidaDriver):
        """Un set non tira dietro il seguente: qualcuno deve cominciarlo.

        Il segnapunti offre «Inizia il set 2» — e deve funzionare davvero. È
        l'unico punto in cui una sfida al meglio dei set può restare bloccata
        per sempre: senza il set nuovo non si segna più niente, e la partita
        non si può nemmeno chiudere.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(
            avversario, match_format="multi", distance=2, match_distance=2
        )

        sfida.segna_piu_volte(match_id, io_, 2)

        assert sfida.punteggio(match_id) == (1, 0), "il set vinto vale un punto"
        assert "Inizia il set 2" in sfida.pagina(match_id)

        assert sfida.inizia_set_successivo(match_id).status_code == 200
        assert sfida.set_giocati(match_id) == 2

    def test_percorso_intero_di_una_sfida_a_due_set(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(
            avversario, match_format="multi", distance=2, match_distance=2
        )

        sfida.segna_piu_volte(match_id, io_, 2)
        sfida.inizia_set_successivo(match_id)
        sfida.segna_piu_volte(match_id, io_, 2)

        # Due set a zero: il punteggio della partita conta i **set**.
        assert sfida.punteggio(match_id) == (2, 0)
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS

        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)

        assert sfida.stato(match_id) == MatchStatus.CONFIRMED_BY_BOTH

    def test_il_set_successivo_non_si_apre_a_set_ancora_aperto(
        self, sfida: SfidaDriver
    ):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(
            avversario, match_format="multi", distance=3, match_distance=2
        )
        sfida.segna(match_id, io_)

        risposta = sfida.inizia_set_successivo(match_id)

        assert risposta.status_code == 400
        assert sfida.set_giocati(match_id) == 1


# ══════════════════════════════════════════════════════════════════════
# La proposta: giocare un altro giorno
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestProposte:
    def test_proposta_aperta_la_prende_chi_vuole(self, sfida: SfidaDriver):
        io_, tizio = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = sfida.proponi([], proposal_type="open", invited_user_ids=[])

        sfida.esci()
        sfida.entra(tizio)
        match_id = sfida.accetta_proposta(proposta_id)

        assert sfida.stato(match_id) == MatchStatus.SCHEDULED
        partita = sfida.partita(match_id)
        assert {partita.player1_id, partita.player2_id} == {io_.id, tizio.id}

    def test_chi_rifiuta_l_invito_non_puo_ripensarci(self, sfida: SfidaDriver):
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = sfida.proponi([invitato])

        sfida.esci()
        sfida.entra(invitato)
        assert sfida.rifiuta_proposta(proposta_id).status_code == 200

        risposta = sfida.client.post(f"/match/proposals/{proposta_id}/accept", json={})
        assert risposta.status_code == 400
        assert sfida.quante_partite() == 0

    def test_chi_ha_proposto_puo_ritirare(self, sfida: SfidaDriver):
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = sfida.proponi([invitato])

        assert sfida.annulla_proposta(proposta_id).status_code == 200

        sfida.esci()
        sfida.entra(invitato)
        risposta = sfida.client.post(f"/match/proposals/{proposta_id}/accept", json={})
        assert risposta.status_code == 400
        assert sfida.quante_partite() == 0

    def test_una_partita_concordata_si_puo_annullare(self, sfida: SfidaDriver):
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = sfida.proponi([invitato])
        sfida.esci()
        sfida.entra(invitato)
        match_id = sfida.accetta_proposta(proposta_id)

        assert sfida.annulla(match_id).status_code == 200
        assert sfida.stato(match_id) == MatchStatus.CANCELLED


# ══════════════════════════════════════════════════════════════════════
# Dopo la partita
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestDopoLaPartita:
    def _partita_chiusa(self, sfida: SfidaDriver, io_, avversario) -> int:
        match_id = sfida.apri_partita(avversario, match_format="single", distance=2)
        sfida.segna_piu_volte(match_id, io_, 2)
        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)
        sfida.esci()
        sfida.entra(io_)
        return match_id

    def test_l_elo_globale_si_muove_solo_alla_doppia_conferma(self, sfida: SfidaDriver):
        """Il patto di ADR-051: senza accettazione iniziale, niente effetti.

        È la ragione per cui l'avvio rapido può fare a meno del sì dell'altro.
        Se un giorno il rating cominciasse a muoversi prima, qui si spacca.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="single", distance=2)
        sfida.segna_piu_volte(match_id, io_, 2)

        assert sfida.rating_globale(io_) is None, "nessuno ha ancora riconosciuto"

        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)

        assert sfida.rating_globale(io_) is not None
        assert sfida.rating_globale(avversario) is not None

    def test_la_partita_finisce_nello_storico_e_nel_profilo(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = self._partita_chiusa(sfida, io_, avversario)

        storico = sfida.client.get("/player/history").get_data(as_text=True)
        profilo = sfida.client.get("/player/profile").get_data(as_text=True)

        assert f"/match/matches/{match_id}" in storico
        assert f"/match/matches/{match_id}" in profilo

    def test_si_rigioca_subito_con_lo_stesso_avversario(self, sfida: SfidaDriver):
        """«Rigioca adesso»: l'avversario è ancora al tavolo (issue #176)."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        self._partita_chiusa(sfida, io_, avversario)

        pagina = sfida.pagina_avvio_rapido(opponent_id=avversario.id)

        assert avversario.username in pagina
        assert f'value="{avversario.id}"' in pagina

    def test_oppure_si_propone_un_altra_data(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = self._partita_chiusa(sfida, io_, avversario)

        risposta = sfida.client.get(f"/match/matches/{match_id}/rematch")

        assert risposta.status_code == 302
        assert "/match/proposals/create" in risposta.headers["Location"]
        assert f"opponent_id={avversario.id}" in risposta.headers["Location"]


# ══════════════════════════════════════════════════════════════════════
# Chi può giocare
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestChiPuoGiocare:
    def test_non_si_sfida_chi_non_ha_sbloccato_le_sfide(self, sfida: SfidaDriver):
        """Stesso filtro dell'elenco avversari: una porta dipinta sul muro no."""
        io_ = sfida.crea_giocatore()
        novellino = sfida.crea_giocatore(sbloccato=False)
        sfida.entra(io_)

        risposta = sfida.avvio_rapido(novellino)

        assert risposta.status_code == 409
        assert sfida.quante_partite() == 0

    def test_il_novellino_non_compare_fra_gli_avversari(self, sfida: SfidaDriver):
        io_ = sfida.crea_giocatore()
        novellino = sfida.crea_giocatore(sbloccato=False)
        sfida.entra(io_)

        trovati = sfida.client.get(
            "/match/players/search", query_string={"q": novellino.username[:6]}
        ).get_json()

        assert all(t["username"] != novellino.username for t in trovati)

    def test_togliere_un_triangolo_dentro_il_set(self, sfida: SfidaDriver):
        """L'annulla al meglio dei set agisce sul **set**, non sui set vinti."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(
            avversario, match_format="multi", distance=3, match_distance=2
        )
        sfida.segna_piu_volte(match_id, io_, 2)

        assert sfida.togli_ultimo(match_id, io_).status_code == 200

        # I set vinti sono ancora zero: si è tolto un triangolo, non un set.
        assert sfida.punteggio(match_id) == (0, 0)
        assert sfida.set_giocati(match_id) == 1

    def test_togliere_l_ultimo_triangolo_riapre_il_set_chiuso(self, sfida: SfidaDriver):
        """È il momento in cui un triangolo di troppo fa più danno."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(
            avversario, match_format="multi", distance=2, match_distance=2
        )
        sfida.segna_piu_volte(match_id, io_, 2)
        assert sfida.punteggio(match_id) == (1, 0)

        assert sfida.togli_ultimo(match_id, io_).status_code == 200

        assert sfida.punteggio(match_id) == (0, 0), "il set vinto torna indietro"
        assert "Inizia il set 2" not in sfida.pagina(match_id)
        assert _tasti_segnapunti(sfida.pagina(match_id)) != []
