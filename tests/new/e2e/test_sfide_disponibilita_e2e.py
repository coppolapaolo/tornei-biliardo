"""Dalla disponibilità alla partita, tutto d'un fiato.

Le cinque route della disponibilità e della scoperta hanno i loro test di
integrazione, una per una. Il percorso che le tiene insieme — *mi dichiaro
disponibile in una sala, un altro mi trova, mi chiede una partita, giochiamo* —
non era mai stato provato tutto insieme, ed è l'unica forma in cui quelle
cinque route vogliono dire qualcosa: presa da sola, «dichiararsi disponibile»
non è un gesto che qualcuno compie per sé.

È il percorso in cui due persone che non si conoscono arrivano allo stesso
tavolo, quindi le osservazioni cambiano continuamente di punto di vista: mi
dichiaro io, mi trova un altro, la richiesta torna a me. Ogni `entra()` è un
telefono diverso.
"""

from __future__ import annotations

import pytest

from models.status_enum import MatchStatus
from sfida_driver import SfidaDriver

# ══════════════════════════════════════════════════════════════════════
# Mi dichiaro disponibile
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestMiDichiaroDisponibile:
    def test_scelgo_una_sala_e_la_pagina_me_la_mostra(self, sfida: SfidaDriver):
        io_ = sfida.crea_giocatore()
        sala = sfida.crea_sala("Sala Regina")
        sfida.entra(io_)

        sfida.dichiarati_disponibile(sala)

        assert "Sala Regina" in sfida.pagina_disponibilita()
        assert len(sfida.mie_disponibilita(io_)) == 1

    def test_giorni_e_fascia_oraria_restano_scritti(self, sfida: SfidaDriver):
        io_ = sfida.crea_giocatore()
        sala = sfida.crea_sala()
        sfida.entra(io_)

        sfida.dichiarati_disponibile(
            sala, available_days=["1", "3"], preferred_times="18:00-22:00"
        )

        disponibilita = sfida.mie_disponibilita(io_)[0]
        assert disponibilita.preferred_time_start.hour == 18
        assert disponibilita.preferred_time_end.hour == 22
        assert "1" in (disponibilita.available_days or "")
        assert "18:00-22:00" in sfida.pagina_disponibilita()

    def test_una_fascia_scritta_a_parole_sparisce_senza_dirlo(self, sfida: SfidaDriver):
        """Il campo è libero, la lettura no: `set_venue_availability` vuole
        `HH:MM-HH:MM` e su tutto il resto fa `pass`.

        L'etichetta il formato lo dice («Ora di inizio e di fine, separate da
        un trattino»), ma chi scrive «dopo le 21» preme Salva, legge
        «Disponibilità aggiornata» e non ha più la sua fascia. Un campo che
        accetta qualsiasi cosa e ne tiene una sola dovrebbe rifiutare il
        resto, non ingoiarlo.
        """
        io_ = sfida.crea_giocatore()
        sala = sfida.crea_sala()
        sfida.entra(io_)

        risposta = sfida.dichiarati_disponibile(sala, preferred_times="dopo le 21")

        assert risposta.status_code in (200, 302)
        disponibilita = sfida.mie_disponibilita(io_)[0]
        assert disponibilita.preferred_time_start is None
        assert "dopo le 21" not in sfida.pagina_disponibilita()

    def test_ridichiararsi_nella_stessa_sala_non_fa_un_doppione(
        self, sfida: SfidaDriver
    ):
        io_ = sfida.crea_giocatore()
        sala = sfida.crea_sala()
        sfida.entra(io_)

        sfida.dichiarati_disponibile(sala, preferred_times="15:00-18:00")
        sfida.dichiarati_disponibile(sala, preferred_times="21:00-23:00")

        disponibilita = sfida.mie_disponibilita(io_)
        assert len(disponibilita) == 1
        assert disponibilita[0].preferred_time_start.hour == 21

    def test_senza_sala_non_si_dichiara_niente(self, sfida: SfidaDriver):
        io_ = sfida.crea_giocatore()
        sfida.entra(io_)

        sfida.dichiarati_disponibile("")

        assert sfida.mie_disponibilita(io_) == []

    def test_e_poi_ci_ripenso(self, sfida: SfidaDriver):
        io_ = sfida.crea_giocatore()
        sala = sfida.crea_sala("Sala Regina")
        sfida.entra(io_)
        sfida.dichiarati_disponibile(sala)
        disponibilita_id = sfida.mie_disponibilita(io_)[0].id

        # Il nome della sala resta comunque in pagina — è nell'elenco delle
        # sale in cui *ci si può* dichiarare. Quello che sparisce è la riga
        # con il suo comando di rimozione.
        assert f"/venue/{disponibilita_id}/remove" in sfida.pagina_disponibilita()

        sfida.togli_disponibilita(disponibilita_id)

        assert sfida.mie_disponibilita(io_) == []
        assert f"/venue/{disponibilita_id}/remove" not in sfida.pagina_disponibilita()

    def test_non_tolgo_la_disponibilita_di_un_altro(self, sfida: SfidaDriver):
        """L'id sta nell'URL: senza questo controllo basterebbe cambiarlo."""
        io_, altro = sfida.crea_giocatori(2)
        sala = sfida.crea_sala()

        sfida.entra(altro)
        sfida.dichiarati_disponibile(sala)
        altrui_id = sfida.mie_disponibilita(altro)[0].id
        sfida.esci()

        sfida.entra(io_)
        sfida.togli_disponibilita(altrui_id)

        assert len(sfida.mie_disponibilita(altro)) == 1


# ══════════════════════════════════════════════════════════════════════
# Un altro mi trova
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestUnAltroMiTrova:
    def test_chi_cerca_nella_mia_sala_mi_vede(self, sfida: SfidaDriver):
        io_, cercatore = sfida.crea_giocatori(2)
        sala = sfida.crea_sala("Sala Regina")

        sfida.entra(io_)
        sfida.dichiarati_disponibile(sala)
        sfida.esci()

        sfida.entra(cercatore)
        pagina = sfida.pagina_scoperta()

        assert io_.id in sfida.trovati(pagina)
        assert "Sala Regina" in pagina

    def test_e_non_vede_se_stesso(self, sfida: SfidaDriver):
        """Cercare qualcuno con cui giocare e trovare sé stessi è un vicolo cieco."""
        io_ = sfida.crea_giocatore()
        sala = sfida.crea_sala()
        sfida.entra(io_)
        sfida.dichiarati_disponibile(sala)

        assert sfida.trovati(sfida.pagina_scoperta()) == []

    def test_chi_si_e_tirato_indietro_sparisce(self, sfida: SfidaDriver):
        io_, cercatore = sfida.crea_giocatori(2)
        sala = sfida.crea_sala()

        sfida.entra(io_)
        sfida.dichiarati_disponibile(sala)
        sfida.dichiarati_disponibile(sala, is_available="false")
        sfida.esci()

        sfida.entra(cercatore)
        assert sfida.trovati(sfida.pagina_scoperta()) == []

    def test_il_filtro_per_sala_guarda_una_sala_sola(self, sfida: SfidaDriver):
        io_, altrove, cercatore = sfida.crea_giocatori(3)
        qui = sfida.crea_sala("Sala Regina")
        la = sfida.crea_sala("Sala Diana")

        sfida.entra(io_)
        sfida.dichiarati_disponibile(qui)
        sfida.esci()
        sfida.entra(altrove)
        sfida.dichiarati_disponibile(la)
        sfida.esci()

        sfida.entra(cercatore)
        trovati = sfida.trovati(sfida.pagina_scoperta(venue_id=qui))

        assert trovati == [io_.id]
        assert altrove.id not in trovati


# ══════════════════════════════════════════════════════════════════════
# Mi chiede una partita
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestMiChiedeUnaPartita:
    @staticmethod
    def _disponibile(sfida: SfidaDriver):
        """Uno che si è dichiarato disponibile, e uno che lo ha trovato."""
        disponibile, cercatore = sfida.crea_giocatori(2)
        sala = sfida.crea_sala("Sala Regina")
        sfida.entra(disponibile)
        sfida.dichiarati_disponibile(sala)
        sfida.esci()
        sfida.entra(cercatore)
        return disponibile, cercatore

    def test_la_richiesta_diventa_una_proposta_diretta(self, sfida: SfidaDriver):
        disponibile, cercatore = self._disponibile(sfida)

        risposta = sfida.chiedi_partita(disponibile, location="Sala Regina")

        assert risposta.status_code in (200, 302)
        proposta = sfida.ultima_proposta()
        assert proposta is not None
        assert proposta.proposer_id == cercatore.id

    def test_e_l_altro_la_trova_fra_le_sue(self, sfida: SfidaDriver):
        disponibile, cercatore = self._disponibile(sfida)
        sfida.chiedi_partita(disponibile, location="Sala Regina")

        sfida.esci()
        sfida.entra(disponibile)

        assert cercatore.username in sfida.pagina_notifiche()

    def test_senza_sala_la_richiesta_non_parte(self, sfida: SfidaDriver):
        disponibile, _cercatore = self._disponibile(sfida)

        sfida.chiedi_partita(disponibile, location="")

        assert sfida.ultima_proposta() is None

    def test_una_data_scritta_male_lo_dice_invece_di_rompersi(self, sfida: SfidaDriver):
        disponibile, _cercatore = self._disponibile(sfida)

        risposta = sfida.chiedi_partita(
            disponibile,
            location="Sala Regina",
            proposed_date="trentadue marzo",
            proposed_time="25:00",
        )

        assert risposta.status_code in (200, 302, 400)
        assert sfida.ultima_proposta() is None

    def test_l_ora_che_scrivo_e_l_ora_che_rileggo(self, sfida: SfidaDriver):
        """ADR-043: quello che scrivo è nella **mia** ora, non in UTC.

        Il modulo ha due campi, data e ora, e li scrive chi guarda l'orologio
        della sua città. Il DB tiene i naive come UTC e `|datetime_local` in
        lettura ci risomma il fuso: salvare la stringa grezza sposta l'orario
        di tutto il fuso, in silenzio — 21:00 diventano 23:00 a Roma, e le
        22:00 del giorno prima a Tokyo.

        Il fuso qui è dichiarato (Tokyo, +9 tutto l'anno, niente ora legale a
        confondere le idee) proprio perché il test non deve dipendere
        dall'orologio della macchina che lo esegue.
        """
        disponibile, _cercatore = self._disponibile(sfida)
        sfida.imposta_fuso("Asia/Tokyo")

        sfida.chiedi_partita(
            disponibile,
            location="Sala Regina",
            proposed_date="2026-12-01",
            proposed_time="21:00",
        )

        proposta = sfida.ultima_proposta()
        assert proposta is not None
        # Tokyo è +9: le 21:00 di lì sono le 12:00 UTC.
        assert proposta.scheduled_at.hour == 12
        assert proposta.scheduled_at.day == 1

        # E chi l'ha scritta rilegge quello che ha scritto.
        pagina = sfida.client.get(f"/match/proposals/{proposta.id}").get_data(
            as_text=True
        )
        assert "21:00" in pagina


# ══════════════════════════════════════════════════════════════════════
# E poi giochiamo
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.e2e
class TestEPoiGiochiamo:
    def test_il_percorso_intero_dalla_disponibilita_al_risultato(
        self, sfida: SfidaDriver
    ):
        """Il motivo per cui esistono tutte e cinque quelle route.

        Nessuno si dichiara disponibile per il gusto di comparire in un
        elenco: lo fa perché in fondo a quell'elenco c'è una partita giocata.
        Questo è il solo test che percorre la catena intera, ed è il solo
        posto in cui un anello staccato si vede.
        """
        disponibile, cercatore = sfida.crea_giocatori(2)
        sala = sfida.crea_sala("Sala Regina")

        # 1. Mi dichiaro disponibile.
        sfida.entra(disponibile)
        sfida.dichiarati_disponibile(sala, preferred_times="la sera")
        sfida.esci()

        # 2. Un altro mi trova.
        sfida.entra(cercatore)
        assert disponibile.id in sfida.trovati(sfida.pagina_scoperta())

        # 3. E mi chiede una partita.
        sfida.chiedi_partita(disponibile, location="Sala Regina")
        proposta_id = sfida.ultima_proposta().id
        sfida.esci()

        # 4. Accetto.
        sfida.entra(disponibile)
        match_id = sfida.accetta_proposta(proposta_id)
        assert sfida.avvia(match_id).status_code == 200

        # 5. Giochiamo (la richiesta nasce «al 7»).
        sfida.segna_piu_volte(match_id, disponibile, 7)
        sfida.conferma(match_id)
        sfida.esci()

        # 6. E l'altro conferma il risultato.
        sfida.entra(cercatore)
        sfida.conferma(match_id)

        assert sfida.stato(match_id) == MatchStatus.CONFIRMED_BY_BOTH
        assert sfida.partita(match_id).winner_id == disponibile.id
