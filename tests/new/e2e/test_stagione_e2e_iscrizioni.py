"""Le iscrizioni della prima gara, in tutti i modi in cui vanno e non vanno.

Sono i gesti che il direttore e i giocatori fanno di più, e quelli in cui una
serata si rovina prima ancora di cominciare: uno che si iscrive due volte, uno
che si cancella all'ultimo, il sedicesimo che arriva quando i posti sono
quindici, la gara che martedì sera non raggiunge i sei iscritti.

Nessuna partita viene giocata: costano pochi secondi l'una e si possono
lasciare girare a ogni commit.
"""

from __future__ import annotations

import pytest

from campionato_driver import CampionatoDriver
from stagione import (
    MASSIMO_ISCRITTI,
    MINIMO_ISCRITTI,
    crea_stagione,
)
from models.competition.models import Inscription
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole


@pytest.fixture
def prima_gara(campionato: CampionatoDriver):
    """La prima gara della stagione, ancora in `setup`."""
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    campionato_id, gare = crea_stagione(campionato, direttore)
    return campionato_id, gare[1], direttore


def _iscritti(gara_id: int) -> list[Inscription]:
    return Inscription.query.filter_by(gara_id=gara_id, is_waitlist=False).all()


def _in_attesa(gara_id: int) -> list[Inscription]:
    return Inscription.query.filter_by(gara_id=gara_id, is_waitlist=True).all()


@pytest.mark.e2e
class TestLaFinestraDiIscrizione:
    def test_prima_dell_apertura_non_ci_si_iscrive(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, _direttore = prima_gara
        giocatore = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.iscrivi(gara_id, giocatore)

        assert _iscritti(gara_id) == []
        assert campionato.gara(gara_id).status == GaraStatus.SETUP.value

    def test_aperta_la_finestra_il_giocatore_si_iscrive_da_solo(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, direttore = prima_gara
        giocatore = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi(gara_id, giocatore)

        assert [i.user_id for i in _iscritti(gara_id)] == [giocatore.id]
        assert campionato.gara(gara_id).status == GaraStatus.INSCRIPTION.value

    def test_le_iscrizioni_si_chiudono_solo_se_non_c_e_nessuno(
        self, campionato: CampionatoDriver, prima_gara
    ):
        """Chiudere riporta la gara in `setup`, e cancellerebbe il lavoro fatto."""
        _campionato_id, gara_id, direttore = prima_gara
        giocatore = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.chiudi_iscrizioni(gara_id)
        assert campionato.gara(gara_id).status == GaraStatus.SETUP.value

        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi(gara_id, giocatore)
        campionato.entra(direttore)
        risposta = campionato.chiudi_iscrizioni(gara_id)

        assert "già degli iscritti" in risposta.get_data(as_text=True)
        assert campionato.gara(gara_id).status == GaraStatus.INSCRIPTION.value

    def test_a_gara_avviata_le_iscrizioni_sono_finite(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, direttore = prima_gara
        giocatori = campionato.crea_giocatori(MINIMO_ISCRITTI)
        ritardatario = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi_tutti(gara_id, giocatori)
        campionato.entra(direttore)
        campionato.avvia_primo_turno(gara_id)

        campionato.iscrivi(gara_id, ritardatario)

        assert ritardatario.id not in {i.user_id for i in _iscritti(gara_id)}


@pytest.mark.e2e
class TestIlTettoDeiQuindici:
    def test_il_sedicesimo_finisce_in_lista_d_attesa(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, direttore = prima_gara
        giocatori = campionato.crea_giocatori(MASSIMO_ISCRITTI + 1)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi_tutti(gara_id, giocatori)

        assert len(_iscritti(gara_id)) == MASSIMO_ISCRITTI
        attesa = _in_attesa(gara_id)
        assert [i.user_id for i in attesa] == [giocatori[-1].id]
        assert attesa[0].waitlist_position == 1

    def test_anche_il_direttore_non_supera_il_tetto(
        self, campionato: CampionatoDriver, prima_gara
    ):
        """L'iscrizione d'ufficio non è una scorciatoia sulla capienza."""
        _campionato_id, gara_id, direttore = prima_gara
        giocatori = campionato.crea_giocatori(MASSIMO_ISCRITTI)
        in_piu = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi_tutti(gara_id, giocatori)

        campionato.entra(direttore)
        html = campionato.iscrivi_dal_direttore(gara_id, in_piu)

        assert "lista d'attesa" in html
        assert len(_iscritti(gara_id)) == MASSIMO_ISCRITTI


@pytest.mark.e2e
class TestRipensamenti:
    def test_non_ci_si_iscrive_due_volte(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, direttore = prima_gara
        giocatore = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi(gara_id, giocatore)
        campionato.iscrivi(gara_id, giocatore)

        assert len(_iscritti(gara_id)) == 1

    def test_il_giocatore_si_toglie_da_solo(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, direttore = prima_gara
        giocatore = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi(gara_id, giocatore)
        campionato.disiscriviti(gara_id, giocatore)

        assert _iscritti(gara_id) == []

    def test_il_direttore_iscrive_chi_ha_pagato_al_banco(
        self, campionato: CampionatoDriver, prima_gara
    ):
        """Il giocatore non tocca il telefono: lo iscrive il direttore."""
        _campionato_id, gara_id, direttore = prima_gara
        giocatore = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        html = campionato.iscrivi_dal_direttore(gara_id, giocatore)

        assert "iscritto con successo" in html
        assert [i.user_id for i in _iscritti(gara_id)] == [giocatore.id]

    def test_e_lo_cancella_se_non_si_presenta(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, direttore = prima_gara
        giocatore = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi_dal_direttore(gara_id, giocatore)
        campionato.cancella_iscrizione(gara_id, giocatore)

        assert _iscritti(gara_id) == []

    def test_a_gara_avviata_il_direttore_non_iscrive_piu(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, direttore = prima_gara
        giocatori = campionato.crea_giocatori(MINIMO_ISCRITTI)
        tardivo = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi_tutti(gara_id, giocatori)
        campionato.entra(direttore)
        campionato.avvia_primo_turno(gara_id)

        html = campionato.iscrivi_dal_direttore(gara_id, tardivo)

        assert "non è in fase di iscrizione" in html
        assert tardivo.id not in {i.user_id for i in _iscritti(gara_id)}


@pytest.mark.e2e
class TestQuandoNonSiArrivaASei:
    """Il caso limite della serata storta: gli iscritti non bastano."""

    def test_con_cinque_iscritti_la_gara_non_parte(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, direttore = prima_gara
        giocatori = campionato.crea_giocatori(MINIMO_ISCRITTI - 1)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi_tutti(gara_id, giocatori)

        campionato.entra(direttore)
        risposta = campionato.avvia_primo_turno(gara_id)

        assert f"almeno {MINIMO_ISCRITTI}" in risposta.get_data(as_text=True)
        gara = campionato.gara(gara_id)
        assert gara.status == GaraStatus.INSCRIPTION.value
        assert gara.current_round == 0
        assert campionato.partite(gara_id) == []

    def test_il_sesto_arriva_e_la_gara_parte(
        self, campionato: CampionatoDriver, prima_gara
    ):
        """La via d'uscita: il direttore iscrive lui il sesto e si gioca."""
        _campionato_id, gara_id, direttore = prima_gara
        giocatori = campionato.crea_giocatori(MINIMO_ISCRITTI - 1)
        sesto = campionato.crea_utente(UserRole.PLAYER.value)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi_tutti(gara_id, giocatori)

        campionato.entra(direttore)
        campionato.avvia_primo_turno(gara_id)
        assert campionato.gara(gara_id).status == GaraStatus.INSCRIPTION.value

        campionato.iscrivi_dal_direttore(gara_id, sesto)
        campionato.avvia_primo_turno(gara_id)

        gara = campionato.gara(gara_id)
        assert gara.status == GaraStatus.PLAYING.value
        assert len(campionato.partite(gara_id, turno=1)) == MINIMO_ISCRITTI // 2

    def test_una_disiscrizione_dell_ultimo_minuto_riporta_sotto_il_minimo(
        self, campionato: CampionatoDriver, prima_gara
    ):
        _campionato_id, gara_id, direttore = prima_gara
        giocatori = campionato.crea_giocatori(MINIMO_ISCRITTI)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.iscrivi_tutti(gara_id, giocatori)
        campionato.disiscriviti(gara_id, giocatori[0])

        campionato.entra(direttore)
        risposta = campionato.avvia_primo_turno(gara_id)

        assert f"almeno {MINIMO_ISCRITTI}" in risposta.get_data(as_text=True)
        assert campionato.gara(gara_id).status == GaraStatus.INSCRIPTION.value
