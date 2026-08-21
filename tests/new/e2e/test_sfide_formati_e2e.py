"""I formati di gioco di una sfida individuale, percorsi per intero.

Le sfide non si giocano tutte allo stesso modo, e i tre formati non sono
varianti dello stesso: «al N» finisce quando uno arriva alla distanza,
«esattamente N» quando i triangoli sono finiti — e può finire pari —, «al
meglio dei set» conta due cose per volta, i triangoli del set e i set della
sfida.

Le regole di ciascuno hanno i loro test di unità. Quello che si vede solo
percorrendo il formato dall'inizio alla fine è cosa succede **ai bordi**: cosa
risponde il server quando la partita è finita e qualcuno segna lo stesso, cosa
resta scritto quando non ha vinto nessuno, cosa arriva a chi non stava
guardando.

Il primo di questi bordi era rotto, e si vede solo qui: cfr.
`TestOltreLaDistanza`.
"""

from __future__ import annotations

import pytest

from models.base import utc_now
from models.status_enum import MatchStatus
from sfida_driver import SfidaDriver

# ══════════════════════════════════════════════════════════════════════
# «Esattamente N»
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestEsattamenteN:
    """Si giocano tutti i triangoli, e vince chi ne ha di più."""

    def test_a_meta_strada_non_e_ancora_finita(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="4", is_race_to="false")

        # Due triangoli di fila non chiudono niente: ne restano due da giocare.
        sfida.segna_piu_volte(match_id, io_, 2)

        assert sfida.partita(match_id).is_ready_for_validation() is False
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS

    def test_al_n_gli_stessi_due_triangoli_l_avrebbero_chiusa(self, sfida: SfidaDriver):
        """Il confronto che rende «esattamente N» una scelta e non un dettaglio."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="2", is_race_to="true")

        sfida.segna_piu_volte(match_id, io_, 2)

        assert sfida.partita(match_id).is_ready_for_validation() is True

    def test_la_pagina_dice_che_si_giocano_tutti(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="4", is_race_to="false")

        assert "Esattamente" in sfida.pagina(match_id)


# ══════════════════════════════════════════════════════════════════════
# Oltre la distanza
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestOltreLaDistanza:
    """A partita finita non si segna più — e il server deve saperlo.

    La pagina i «+1» li toglie da sola (`can_add` in `match_scoring_state`), e
    per questo il difetto non si vedeva: dall'interfaccia il tasto non c'era.
    Ma il tabellone orizzontale resta aperto sul telefono appoggiato alla
    sponda, e una pagina lasciata aperta non sa che nel frattempo la partita è
    finita: il triangolo di troppo parte da lì, e il server lo accettava.

    In «esattamente N» non è un dettaglio contabile. A 2-2 su quattro la
    partita è **pari**; un triangolo in più la porta a 3-2 e assegna la
    vittoria — a chi ha premuto, dopo che era finita.
    """

    def test_al_n_il_triangolo_di_troppo_e_rifiutato(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="2", is_race_to="true")
        sfida.segna_piu_volte(match_id, io_, 2)

        risposta = sfida.segna(match_id, io_)

        assert risposta.status_code == 400
        assert sfida.punteggio(match_id) == (2, 0)

    def test_e_il_pareggio_non_si_puo_trasformare_in_vittoria(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="4", is_race_to="false")
        sfida.segna_piu_volte(match_id, io_, 2)
        sfida.segna_piu_volte(match_id, avversario, 2)

        risposta = sfida.segna(match_id, io_)

        assert risposta.status_code == 400
        assert sfida.punteggio(match_id) == (2, 2)

    def test_nel_formato_libero_si_segna_finche_si_vuole(self, sfida: SfidaDriver):
        """La guardia non deve toccare chi un traguardo non ce l'ha.

        Nel formato libero `is_ready_for_validation` è vera dal primo
        triangolo: prenderla per «finita» fermerebbe la partita subito.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, match_format="free")

        sfida.segna_piu_volte(match_id, io_, 5)

        assert sfida.punteggio(match_id) == (5, 0)

    def test_il_triangolo_di_troppo_si_puo_ancora_togliere(self, sfida: SfidaDriver):
        """Segnato uno di troppo per sbaglio *prima* della distanza, si corregge.

        La guardia è sull'aggiunta, non sulla rimozione: chiudere anche quella
        vorrebbe dire che un errore all'ultimo triangolo non si aggiusta più.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="2", is_race_to="true")
        sfida.segna_piu_volte(match_id, io_, 2)

        risposta = sfida.togli_ultimo(match_id, io_)

        assert risposta.status_code == 200
        assert sfida.punteggio(match_id) == (1, 0)
        # E da lì si riprende a segnare.
        assert sfida.segna(match_id, avversario).status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Il pareggio
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestIlPareggio:
    """Una partita senza vincitore è un esito, non un errore."""

    @staticmethod
    def _pari(sfida: SfidaDriver, io_, avversario) -> int:
        match_id = sfida.apri_partita(avversario, distance="4", is_race_to="false")
        sfida.segna_piu_volte(match_id, io_, 2)
        sfida.segna_piu_volte(match_id, avversario, 2)
        return match_id

    def test_due_a_due_su_quattro_chiude_senza_vincitore(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = self._pari(sfida, io_, avversario)

        sfida.conferma(match_id)
        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)

        assert sfida.stato(match_id) == MatchStatus.CONFIRMED_BY_BOTH
        assert sfida.partita(match_id).winner_id is None

    def test_e_l_elo_non_si_muove(self, sfida: SfidaDriver):
        """Senza vincitore non c'è niente da spostare (ADR-051 + rating).

        È la controprova del patto dell'avvio rapido: l'Elo si muove **solo**
        sulla doppia conferma, e qui la doppia conferma c'è — ma non c'è un
        vincitore, quindi il rating resta dov'era.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = self._pari(sfida, io_, avversario)

        sfida.conferma(match_id)
        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)

        assert sfida.rating_globale(io_) is None
        assert sfida.rating_globale(avversario) is None

    def test_a_confronto_una_vittoria_l_elo_lo_muove(self, sfida: SfidaDriver):
        """Il termine di paragone: senza, il test qui sopra non dimostra niente.

        Un Elo fermo può voler dire «pareggio» oppure «non è mai partito
        niente». Qui si vede che parte davvero.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="2", is_race_to="true")
        sfida.segna_piu_volte(match_id, io_, 2)

        sfida.conferma(match_id)
        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)

        assert sfida.rating_globale(io_) is not None
        assert sfida.rating_globale(io_) > sfida.rating_globale(avversario)


# ══════════════════════════════════════════════════════════════════════
# Al meglio dei set
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestAlMeglioDeiSet:
    def test_un_set_si_chiude_e_il_successivo_comincia(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(
            avversario, match_format="multi", distance="2", match_distance="2"
        )

        # Due triangoli chiudono il **set**, non la sfida.
        sfida.segna_piu_volte(match_id, io_, 2)

        assert sfida.punteggio(match_id) == (1, 0)
        assert sfida.set_giocati(match_id) == 1

        assert sfida.inizia_set_successivo(match_id).status_code == 200
        assert sfida.set_giocati(match_id) == 2

    def test_vinti_i_set_la_sfida_chiede_conferma(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(
            avversario, match_format="multi", distance="2", match_distance="2"
        )

        sfida.segna_piu_volte(match_id, io_, 2)
        sfida.inizia_set_successivo(match_id)
        sfida.segna_piu_volte(match_id, io_, 2)

        assert sfida.punteggio(match_id) == (2, 0)

        sfida.conferma(match_id)
        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)

        assert sfida.stato(match_id) == MatchStatus.CONFIRMED_BY_BOTH
        assert sfida.partita(match_id).winner_id == io_.id

    def test_i_set_di_una_sfida_individuale_sono_sempre_al_n(self, sfida: SfidaDriver):
        """«Esattamente N set» il modello lo sa fare, i moduli non lo chiedono.

        `IndividualMatch.is_race_to_sets` esiste e il conteggio a set esatti è
        implementato (`match_models.py`), ma **nessuna route lo scrive**:
        l'avvio rapido lo fissa a `True`, e il modulo della proposta non legge
        il campo. Un `?is_race_to_sets=false` nel link di rivincita viene
        precompilato nel modulo e poi ignorato.

        Il livello e2e non può provare quello che dall'interfaccia non si può
        chiedere: quello che può fare è dire che non si può, così la prossima
        persona non va a cercare il bottone. Se un giorno il formato si aprirà,
        questo test è il posto da cui partire.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)

        match_id = sfida.apri_partita(
            avversario,
            match_format="multi",
            distance="2",
            match_distance="2",
            is_race_to_sets="false",
        )

        assert sfida.partita(match_id).is_race_to_sets is True
        assert "Al" in sfida.pagina(match_id)


# ══════════════════════════════════════════════════════════════════════
# La proposta scaduta
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestLaPropostaScaduta:
    """Una proposta ha una finestra, e chiusa quella non si accetta più."""

    @staticmethod
    def _proposta_scaduta(sfida: SfidaDriver, invitati) -> int:
        """Una proposta la cui finestra è già passata.

        `expires_at = scheduled_at - expires_hours` (route della proposta):
        un appuntamento a domani con una finestra di due giorni scade *ieri*.
        Passare da lì e non dal DB è il punto: è così che la finestra si
        calcola davvero, fusi orari compresi (ADR-043).
        """
        return sfida.proponi(invitati, expires_hours="48")

    def test_scaduta_non_si_accetta_piu(self, sfida: SfidaDriver):
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = self._proposta_scaduta(sfida, [invitato])

        sfida.esci()
        sfida.entra(invitato)

        risposta = sfida.client.post(f"/match/proposals/{proposta_id}/accept", json={})

        assert risposta.status_code == 400
        assert sfida.quante_partite() == 0

    def test_la_finestra_e_gia_chiusa_alla_nascita(self, sfida: SfidaDriver):
        """Il fatto grezzo, per non dipendere dall'orologio del test."""
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = self._proposta_scaduta(sfida, [invitato])

        from models.individual_match.models import MatchProposal
        from models import db

        db.session.expire_all()
        proposta = db.session.get(MatchProposal, proposta_id)
        assert proposta is not None
        assert proposta.expires_at < utc_now()
        assert proposta.is_expired() is True

    def test_una_proposta_viva_invece_si_accetta(self, sfida: SfidaDriver):
        """Il termine di paragone: la stessa strada, con la finestra aperta."""
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = sfida.proponi([invitato])

        sfida.esci()
        sfida.entra(invitato)
        match_id = sfida.accetta_proposta(proposta_id)

        assert sfida.stato(match_id) == MatchStatus.SCHEDULED

    def test_scaduta_non_compare_fra_le_proposte_aperte(self, sfida: SfidaDriver):
        """Chi guarda l'elenco non deve vedere una porta che non si apre."""
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        self._proposta_scaduta(sfida, [invitato])
        viva = sfida.proponi([invitato])

        sfida.esci()
        sfida.entra(invitato)

        pagina = sfida.client.get("/match/proposals").get_data(as_text=True)
        assert f"/match/proposals/{viva}" in pagina


# ══════════════════════════════════════════════════════════════════════
# Le notifiche
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestLeNotifiche:
    """Chi non stava guardando lo scopre da qui.

    Sono la sola parte della sfida che si legge su un'altra pagina, e la sola
    che riguarda chi in quel momento non c'era: l'avvio rapido apre una
    partita **senza chiedere niente all'avversario** (ADR-051), quindi la
    notifica non è un di più — è come lo viene a sapere.
    """

    def test_l_avvio_rapido_avvisa_l_avversario(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario)

        sfida.esci()
        sfida.entra(avversario)

        pagina = sfida.pagina_notifiche()
        assert "Partita iniziata" in pagina
        assert io_.username in pagina
        assert f"/match/matches/{match_id}" in pagina

    def test_e_non_avvisa_chi_l_ha_aperta(self, sfida: SfidaDriver):
        """Nessuno ha bisogno che gli si dica cosa ha appena fatto."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        sfida.apri_partita(avversario)

        assert sfida.notifiche(io_) == []

    def test_la_proposta_avvisa_l_invitato(self, sfida: SfidaDriver):
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        sfida.proponi([invitato])

        sfida.esci()
        sfida.entra(invitato)

        assert sfida.notifiche(invitato) != []
        assert io_.username in sfida.pagina_notifiche()

    def test_accettare_avvisa_chi_aveva_proposto(self, sfida: SfidaDriver):
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = sfida.proponi([invitato])

        sfida.esci()
        sfida.entra(invitato)
        sfida.accetta_proposta(proposta_id)

        sfida.esci()
        sfida.entra(io_)
        pagina = sfida.pagina_notifiche()
        assert invitato.username in pagina

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Rifiutare una proposta non avvisa nessuno. `MatchProposalService."
            "reject_proposal` — la sola cosa che la route `/decline` chiama — "
            "porta l'invito a REJECTED e finisce lì; `ProposalService."
            "reject_invitation`, che pure c'è, non manda niente e da una route "
            "non ci arriva nessuno. Accettare avvisa, scadere avvisa, essere "
            "scartati per l'accettazione di un altro avvisa: rifiutare no. "
            "Chi ha proposto resta ad aspettare una risposta che c'è già "
            "stata, e la vede solo riaprendo l'elenco delle proposte. "
            "Sulle proposte **aperte** il silenzio si può difendere (un "
            "rifiuto per invitato sarebbe rumore); su quelle **dirette** — un "
            "invito a una persona sola — è una risposta persa. Da decidere: "
            "il codice sa già distinguere i due casi, `accept_proposal` lo fa "
            "già per gli scartati."
        ),
    )
    def test_rifiutare_avvisa_chi_aveva_proposto(self, sfida: SfidaDriver):
        io_, invitato = sfida.crea_giocatori(2)
        sfida.entra(io_)
        proposta_id = sfida.proponi([invitato])

        sfida.esci()
        sfida.entra(invitato)
        assert sfida.rifiuta_proposta(proposta_id).status_code == 200

        sfida.esci()
        sfida.entra(io_)
        assert sfida.notifiche(io_) != []

    def test_segnare_un_triangolo_non_manda_notifiche(self, sfida: SfidaDriver):
        """Il segnapunti si segue in diretta, non a colpi di notifica.

        Venti triangoli sono venti notifiche: la casella diventa illeggibile e
        con lei tutte le altre.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        quante_prima = len(sfida.notifiche(avversario))

        sfida.segna_piu_volte(match_id, io_, 3)

        assert len(sfida.notifiche(avversario)) == quante_prima
