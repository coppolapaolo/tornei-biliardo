"""Una gara Amalfi intera, dalla creazione alla classifica, solo via HTTP.

Nessun service viene chiamato: ogni passo è la richiesta che farebbe il browser
del direttore o del giocatore. È il percorso che nessun test attraversava — i
test dei casi d'uso (`tests/new/integration/test_gare_usecase_*.py`) chiamano i
service, quindi non vedono le route, i permessi, i redirect né ciò che la pagina
mostra davvero.

Il tratto distintivo di Amalfi è che i turni nascono **uno alla volta**: la
classifica del turno appena chiuso è l'input degli accoppiamenti del successivo.
Il direttore deve quindi premere "avvia turno" fra un turno e l'altro, e quel
pulsante deve rifiutarsi di funzionare finché il turno in corso non è finito.
"""

from __future__ import annotations

import pytest

from gara_driver import GaraDriver, partecipanti
from models.classification.models import RoundClassification
from models.competition.models import Inscription
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole

GIOCATORI = 8
TURNI = 3


@pytest.fixture
def gara_pronta(driver: GaraDriver):
    """Gara Amalfi con 8 iscritti, ferma un istante prima del sorteggio."""
    direttore = driver.crea_utente(UserRole.DIRECTOR.value)
    giocatori = driver.crea_giocatori(GIOCATORI)

    driver.entra(direttore)
    gara_id = driver.crea_gara(
        matchmaking_strategy="amalfi", rounds_count=TURNI, min_participants=4
    )
    driver.apri_iscrizioni(gara_id)

    driver.iscrivi_tutti(gara_id, giocatori)

    driver.entra(direttore)
    return gara_id, direttore, giocatori


@pytest.mark.e2e
class TestPercorsoCompletoAmalfi:
    """Il percorso che un direttore fa davvero, dall'inizio alla fine."""

    def test_dalla_creazione_alla_classifica(self, driver: GaraDriver):
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        giocatori = driver.crea_giocatori(GIOCATORI)

        # ── Creazione ────────────────────────────────────────────
        driver.entra(direttore)
        gara_id = driver.crea_gara(
            matchmaking_strategy="amalfi", rounds_count=TURNI, min_participants=4
        )
        assert driver.gara(gara_id).status == GaraStatus.SETUP.value

        # ── Iscrizioni ───────────────────────────────────────────
        driver.apri_iscrizioni(gara_id)
        assert driver.gara(gara_id).status == GaraStatus.INSCRIPTION.value

        driver.iscrivi_tutti(gara_id, giocatori)
        driver.entra(direttore)

        iscritti = Inscription.query.filter_by(gara_id=gara_id, is_waitlist=False).all()
        assert len(iscritti) == GIOCATORI

        # ── Sorteggio del primo turno ────────────────────────────
        driver.avvia_primo_turno(gara_id)
        gara = driver.gara(gara_id)
        assert gara.status == GaraStatus.PLAYING.value
        assert gara.current_round == 1

        # Amalfi crea un turno per volta: dopo il primo avvio esiste solo il 1.
        assert driver.turni_creati(gara_id) == {1}

        primo_turno = driver.partite(gara_id, turno=1)
        assert len(primo_turno) == GIOCATORI // 2
        # Chi incontra chi lo decide il sorteggio, ma nessuno gioca due volte.
        assert sorted(partecipanti(primo_turno)) == sorted(g.id for g in giocatori)

        # E le partite si vedono nella pagina, non solo nel database.
        assert driver.partite_nella_pagina(gara_id) >= {p.id for p in primo_turno}

        # ── I tre turni ──────────────────────────────────────────
        for turno in range(1, TURNI + 1):
            if turno > 1:
                esito = driver.avvia_turno(gara_id, turno)
                assert esito["success"] is True, esito.get("error")

            partite = driver.partite(gara_id, turno=turno)
            assert len(partite) == GIOCATORI // 2
            assert sorted(partecipanti(partite)) == sorted(g.id for g in giocatori)

            driver.gioca_turno(gara_id, turno)
            assert all(
                MatchStatus.is_finished(p.status)
                for p in driver.partite(gara_id, turno=turno)
            )

            # La classifica di turno di Amalfi nasce **quando si apre la
            # pagina**, non quando finisce l'ultima partita: la calcola
            # `gara_detail`, e il percorso rack-per-rack non chiama mai
            # `update_round_progression` (lo fanno solo `validate` e
            # `set_result`). Nell'uso vero non si nota, perché il direttore la
            # pagina la apre sempre; ma è una dipendenza implicita, e questo è
            # il test che la tiene ferma.
            assert (
                RoundClassification.query.filter_by(
                    gara_id=gara_id, round_number=turno
                ).first()
                is None
            )
            driver.pagina_gara(gara_id)
            assert RoundClassification.query.filter_by(
                gara_id=gara_id, round_number=turno
            ).first()

        # ── Chiusura ─────────────────────────────────────────────
        driver.termina(gara_id)
        assert driver.gara(gara_id).status == GaraStatus.COMPLETED.value

        # La pagina finale regge: è quella che tutti aprono dopo la premiazione.
        assert "html" in driver.pagina_gara(gara_id).lower()


@pytest.mark.e2e
class TestSequenzaDeiTurni:
    """Il pulsante «avvia turno» deve rifiutare quello che il formato non ammette."""

    def test_non_si_salta_un_turno(self, driver: GaraDriver, gara_pronta):
        gara_id, _direttore, _giocatori = gara_pronta
        driver.avvia_primo_turno(gara_id)
        driver.gioca_turno(gara_id, 1)
        driver.pagina_gara(gara_id)

        esito = driver.avvia_turno(gara_id, 3)

        assert esito["success"] is False
        assert "turno 2" in esito["error"].lower()
        assert driver.turni_creati(gara_id) == {1}

    def test_il_turno_successivo_aspetta_che_finisca_quello_in_corso(
        self, driver: GaraDriver, gara_pronta
    ):
        gara_id, _direttore, _giocatori = gara_pronta
        driver.avvia_primo_turno(gara_id)

        # Una sola partita giocata su quattro: il turno non è finito.
        driver.gioca_match(driver.partite(gara_id, turno=1)[0].id)

        esito = driver.avvia_turno(gara_id, 2)

        assert esito["success"] is False
        assert "completa prima" in esito["error"].lower()
        assert driver.turni_creati(gara_id) == {1}

    def test_il_turno_successivo_pretende_che_la_pagina_sia_stata_aperta(
        self, driver: GaraDriver, gara_pronta
    ):
        """Rilievo: il turno 2 di Amalfi dipende da una *visita alla pagina*.

        Gli accoppiamenti del turno successivo si calcolano sulla classifica
        del turno appena chiuso — ma a scrivere quella classifica è
        `gara_detail`, cioè l'apertura della pagina. Segnato l'ultimo rack, il
        pulsante «avvia turno 2» risponde «Classificazione del round 1 non
        trovata» finché nessuno ricarica.

        Nell'uso reale non si vede, perché dopo aver segnato si ricarica sempre.
        Ma il turno dipende da un effetto collaterale di una GET, e questo test
        fissa il fatto invece di lasciarlo alla fortuna: se un domani si toglie
        il ricalcolo dalla pagina, o si aggiunge un pulsante che avvia il turno
        senza ricaricare, qui si accende una luce rossa.
        """
        gara_id, _direttore, _giocatori = gara_pronta
        driver.avvia_primo_turno(gara_id)
        driver.gioca_turno(gara_id, 1)

        senza_visita = driver.avvia_turno(gara_id, 2)
        assert senza_visita["success"] is False
        assert "classificazione" in senza_visita["error"].lower()

        driver.pagina_gara(gara_id)

        assert driver.avvia_turno(gara_id, 2)["success"] is True

    def test_lo_stesso_turno_non_si_avvia_due_volte(
        self, driver: GaraDriver, gara_pronta
    ):
        gara_id, _direttore, _giocatori = gara_pronta
        driver.avvia_primo_turno(gara_id)
        driver.gioca_turno(gara_id, 1)
        driver.pagina_gara(gara_id)  # vedi il test qui sopra
        assert driver.avvia_turno(gara_id, 2)["success"] is True

        esito = driver.avvia_turno(gara_id, 2)

        assert esito["success"] is False
        assert "già stato avviato" in esito["error"].lower()
        assert len(driver.partite(gara_id, turno=2)) == GIOCATORI // 2


@pytest.mark.e2e
class TestConfigurazioniRifiutate:
    """Configurazioni che il formato non regge: vanno fermate al form."""

    def test_amalfi_senza_anti_reincontro_non_si_crea(self, driver: GaraDriver):
        """Amalfi è un anti-reincontro: senza, la gara non ha senso.

        `STRATEGY_CONSTRAINTS` lo dichiara `anti_rematch_required`. Il form lo
        manda come casella di spunta, quindi «non spuntata» significa «assente»:
        è la forma in cui il rifiuto deve arrivare davvero dal browser.
        """
        driver.entra(driver.crea_utente(UserRole.DIRECTOR.value))

        html = driver.crea_gara_rifiutata(
            matchmaking_strategy="amalfi", anti_rematch_enabled=""
        )

        assert "non valida" in html.lower()

    def test_gara_sotto_il_minimo_iscritti_non_parte(self, driver: GaraDriver):
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        giocatori = driver.crea_giocatori(3)

        driver.entra(direttore)
        gara_id = driver.crea_gara(matchmaking_strategy="amalfi", min_participants=6)
        driver.apri_iscrizioni(gara_id)
        driver.iscrivi_tutti(gara_id, giocatori)

        driver.entra(direttore)
        risposta = driver.avvia_primo_turno(gara_id)

        assert risposta.status_code == 200
        assert "almeno 6" in risposta.get_data(as_text=True)
        assert driver.gara(gara_id).status == GaraStatus.INSCRIPTION.value
        assert driver.partite(gara_id) == []
