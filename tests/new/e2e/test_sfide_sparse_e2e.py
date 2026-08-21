"""Le ultime quattro route delle sfide individuali.

Non formano un percorso e non si somigliano fra loro: una pagina di numeri,
una chiusura d'ufficio, la correzione degli orari, il quadro d'insieme
dell'amministrazione. Stanno insieme perché erano quello che restava.

Due sono più interessanti di quanto il nome faccia pensare.

`complete_match` è una **chiusura unilaterale**: un giocatore solo dichiara chi
ha vinto, senza che l'altro confermi niente. Con ADR-051 la doppia conferma è
*l'accettazione* della sfida, quindi vale la pena guardare da vicino cosa
succede — e cosa non succede — quando si passa di lì.

`update_match_times` scrive due orari che altrove li scrive `utc_now()`: è uno
dei posti dove un fuso sbagliato non si vede finché qualcuno non conta la
durata di una partita.
"""

from __future__ import annotations

import pytest

from models.status_enum import MatchStatus
from sfida_driver import SfidaDriver

# ══════════════════════════════════════════════════════════════════════
# I miei numeri
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestIMieiNumeri:
    def test_senza_partite_la_pagina_si_apre_lo_stesso(self, sfida: SfidaDriver):
        """Il caso da cui nessuno parte, e in cui tutti si trovano il primo giorno."""
        io_ = sfida.crea_giocatore()
        sfida.entra(io_)

        assert sfida.statistiche()["total_matches"] == 0
        assert sfida.pagina_statistiche()

    def test_una_partita_vinta_e_una_persa_si_contano(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)

        sfida.entra(io_)
        vinta = sfida.apri_partita(avversario, distance="2")
        sfida.segna_piu_volte(vinta, io_, 2)
        sfida.conferma(vinta)
        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(vinta)
        persa = sfida.apri_partita(io_, distance="2")
        sfida.segna_piu_volte(persa, avversario, 2)
        sfida.conferma(persa)
        sfida.esci()

        sfida.entra(io_)
        sfida.conferma(persa)

        numeri = sfida.statistiche()
        assert numeri["total_matches"] == 2
        assert numeri["won_matches"] == 1
        assert numeri["lost_matches"] == 1

    def test_le_partite_in_corso_non_si_contano(self, sfida: SfidaDriver):
        """Si conta quello che è successo, non quello che sta succedendo."""
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        sfida.segna_piu_volte(match_id, io_, 3)

        assert sfida.statistiche()["total_matches"] == 0

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Un pareggio è contato come sconfitta. `get_user_statistics` fa "
            "`lost_matches = total_matches - won_matches`, e chi non ha vinto "
            "ha perso: una partita finita 2-2 su «esattamente 4» compare "
            "fra le sconfitte. Lo stesso `else` sta nel dettaglio per "
            "disciplina, nel testa a testa e nel riepilogo per mese, quindi "
            "il numero è coerentemente sbagliato dappertutto. Correggerlo "
            "vuol dire anche decidere come la schermata mostra i pareggi — "
            "oggi non li nomina — quindi non è solo una sottrazione."
        ),
    )
    def test_un_pareggio_non_e_una_sconfitta(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="4", is_race_to="false")
        sfida.segna_piu_volte(match_id, io_, 2)
        sfida.segna_piu_volte(match_id, avversario, 2)
        sfida.conferma(match_id)
        sfida.esci()
        sfida.entra(avversario)
        sfida.conferma(match_id)

        sfida.esci()
        sfida.entra(io_)
        numeri = sfida.statistiche()

        assert numeri["total_matches"] == 1
        assert numeri["won_matches"] == 0
        assert numeri["lost_matches"] == 0


# ══════════════════════════════════════════════════════════════════════
# La chiusura d'ufficio
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestLaChiusuraDUfficio:
    """Un giocatore chiude e dichiara il vincitore, senza chiedere all'altro."""

    def test_chiude_la_partita_e_scrive_il_vincitore(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        sfida.segna_piu_volte(match_id, io_, 3)

        risposta = sfida.chiudi_unilateralmente(match_id, io_)

        assert risposta.status_code == 200
        assert sfida.stato(match_id) == MatchStatus.CLOSED_UNILATERALLY
        assert sfida.partita(match_id).winner_id == io_.id

    def test_ma_l_elo_non_si_muove(self, sfida: SfidaDriver):
        """Il patto di ADR-051 tiene anche di qui, ed è il punto.

        L'Elo globale si muove **solo** sulla doppia conferma
        (`IndividualMatchCompletedEvent`, emesso da `CONFIRMED_BY_BOTH`). Una
        partita che uno solo dei due ha dichiarato finita resta nel suo
        storico, ma non gli sposta il rating: se lo spostasse, questa route
        sarebbe un modo per farsi il punteggio da soli.
        """
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        sfida.segna_piu_volte(match_id, io_, 3)

        sfida.chiudi_unilateralmente(match_id, io_)

        assert sfida.rating_globale(io_) is None
        assert sfida.rating_globale(avversario) is None

    def test_un_vincitore_che_non_gioca_e_rifiutato(self, sfida: SfidaDriver):
        io_, avversario, estraneo = sfida.crea_giocatori(3)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")

        risposta = sfida.chiudi_unilateralmente(match_id, estraneo)

        assert risposta.status_code == 400
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS

    def test_e_non_la_chiude_chi_non_ci_gioca(self, sfida: SfidaDriver):
        io_, avversario, estraneo = sfida.crea_giocatori(2 + 1)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        sfida.esci()

        sfida.entra(estraneo)
        risposta = sfida.chiudi_unilateralmente(match_id, avversario)

        assert risposta.status_code == 400
        assert sfida.stato(match_id) == MatchStatus.IN_PROGRESS

    def test_una_partita_gia_chiusa_non_si_richiude(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        sfida.chiudi_unilateralmente(match_id, io_)

        risposta = sfida.chiudi_unilateralmente(match_id, avversario)

        assert risposta.status_code == 400
        assert sfida.partita(match_id).winner_id == io_.id


# ══════════════════════════════════════════════════════════════════════
# Gli orari, corretti dopo
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestGliOrariCorrettiDopo:
    @staticmethod
    def _partita_da_proposta(sfida: SfidaDriver) -> int:
        """Una partita nata da una proposta, con il proponente già entrato.

        È l'**unica** strada che arriva a questa route. Gli orari li corregge
        «il proponente o un admin» (`IndividualMatchService.update_times`), ma
        l'admin qui non passa: la route è
        `@RoleRequirement.player_or_director_required`, che gli amministratori
        li esclude apposta. E una partita da avvio rapido un proponente non ce
        l'ha — vedi `test_i_due_giocatori_non_correggono_la_loro_partita_veloce`.
        """
        proponente, invitato = sfida.crea_giocatori(2)
        sfida.entra(proponente)
        proposta_id = sfida.proponi([invitato])
        sfida.esci()
        sfida.entra(invitato)
        match_id = sfida.accetta_proposta(proposta_id)
        sfida.esci()
        sfida.entra(proponente)
        return match_id

    def test_l_ora_che_scrivo_e_l_ora_che_rileggo(self, sfida: SfidaDriver):
        """ADR-043 di nuovo, e qui su una colonna scritta anche da `utc_now()`.

        `started_at` lo scrive il server quando la partita parte, in UTC; qui
        lo riscrive una persona, nella sua ora. Se i due non si accordano
        finiscono due scale diverse nella stessa colonna, e la durata della
        partita è sbagliata di un fuso senza che niente lo segnali.
        """
        match_id = self._partita_da_proposta(sfida)
        sfida.imposta_fuso("Asia/Tokyo")

        risposta = sfida.aggiorna_orari(
            match_id, started_at="2026-12-01T21:00", ended_at="2026-12-01T23:00"
        )

        assert risposta.status_code == 200
        partita = sfida.partita(match_id)
        # Tokyo è +9: le 21:00 di lì sono le 12:00 UTC.
        assert partita.started_at.hour == 12
        assert partita.ended_at.hour == 14

    def test_un_orario_scritto_male_lo_dice(self, sfida: SfidaDriver):
        match_id = self._partita_da_proposta(sfida)
        prima = sfida.partita(match_id).started_at

        risposta = sfida.aggiorna_orari(match_id, started_at="ieri sera")

        assert risposta.status_code == 400
        assert sfida.partita(match_id).started_at == prima

    def test_la_fine_non_puo_precedere_l_inizio(self, sfida: SfidaDriver):
        match_id = self._partita_da_proposta(sfida)

        risposta = sfida.aggiorna_orari(
            match_id, started_at="2026-12-01T23:00", ended_at="2026-12-01T21:00"
        )

        assert risposta.status_code == 400
        assert sfida.partita(match_id).ended_at is None

    def test_senza_nessun_orario_non_si_scrive_niente(self, sfida: SfidaDriver):
        match_id = self._partita_da_proposta(sfida)

        risposta = sfida.aggiorna_orari(match_id, note="niente")

        assert risposta.status_code == 400

    def test_ne_corregge_gli_orari_chi_non_ci_gioca(self, sfida: SfidaDriver):
        io_, avversario, estraneo = sfida.crea_giocatori(3)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        prima = sfida.partita(match_id).started_at
        sfida.esci()

        sfida.entra(estraneo)
        risposta = sfida.aggiorna_orari(match_id, started_at="2026-12-01T21:00")

        assert risposta.status_code == 400
        assert sfida.partita(match_id).started_at == prima

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Gli orari di una partita da avvio rapido non li corregge "
            "nessuno dei due giocatori. `IndividualMatchService.update_times` "
            "ammette «il proponente o un admin», e una partita quick un "
            "proponente non ce l'ha: `proposal_id` è `None` per costruzione "
            "(ADR-051), quindi `is_proposer` è falso per tutti e due. E "
            "l'«o un admin» del servizio non li salva: la route è "
            "`player_or_director_required`, che gli amministratori li esclude "
            "apposta, quindi quel ramo non lo raggiunge nessuno. Il pannello "
            "«Orari» sulla pagina della partita, per una quick, non compare "
            "proprio. La regola è di quando ogni partita nasceva da una "
            "proposta; il percorso nuovo l'ha lasciata indietro. Da decidere "
            "chi può: i due giocatori sono simmetrici — `IndividualMatch` non "
            "ricorda chi l'ha aperta — quindi la scelta è fra «tutti e due» e "
            "«nessuno, e allora si toglie il pannello»."
        ),
    )
    def test_i_due_giocatori_non_correggono_la_loro_partita_veloce(
        self, sfida: SfidaDriver
    ):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")

        risposta = sfida.aggiorna_orari(match_id, started_at="2026-12-01T21:00")

        assert risposta.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# Il quadro d'insieme
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestIlQuadroDInsieme:
    def test_l_admin_vede_le_sfide_di_tutti(self, sfida: SfidaDriver):
        io_, avversario = sfida.crea_giocatori(2)
        sfida.entra(io_)
        match_id = sfida.apri_partita(avversario, distance="5")
        sfida.esci()

        sfida.entra(sfida.crea_admin())
        risposta = sfida.pagina_quadro_admin()

        assert risposta.status_code == 200
        pagina = risposta.get_data(as_text=True)
        assert io_.username in pagina
        assert avversario.username in pagina
        assert str(match_id) in pagina

    def test_un_giocatore_non_ci_entra(self, sfida: SfidaDriver):
        """È l'unica di queste route con `set()` in `ENDPOINT_ROLES`: solo admin."""
        io_ = sfida.crea_giocatore()
        sfida.entra(io_)

        risposta = sfida.pagina_quadro_admin()

        assert risposta.status_code in (302, 403)
