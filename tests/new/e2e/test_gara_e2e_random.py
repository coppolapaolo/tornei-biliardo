"""Una gara Random intera, dalla creazione alla classifica, solo via HTTP.

Random non è "Amalfi con un sorteggio diverso": è un altro modo di condurre la
serata, e le differenze si vedono tutte dall'interfaccia.

* **I turni nascono tutti insieme** al primo avvio (`creates_all_rounds_at_startup`).
  Il direttore non ha nessun pulsante «avvia turno successivo» da premere — e se
  lo trovasse, deve rifiutarsi.
* **La classifica è una sola**, complessiva, e si aggiorna alla fine di ogni
  partita (`ON_MATCH_COMPLETE`) invece che alla chiusura del turno.
* **L'anti-reincontro è facoltativo**, mentre Amalfi lo esige.

Sono esattamente le tre cose che un test sui service non vede, perché lì il
direttore non c'è.
"""

from __future__ import annotations

import pytest

from gara_driver import GaraDriver, partecipanti
from models.classification.models import RoundClassification
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole

GIOCATORI = 8
TURNI = 3


@pytest.fixture
def gara_avviata(driver: GaraDriver):
    """Gara Random con 8 iscritti, primo turno già avviato."""
    direttore = driver.crea_utente(UserRole.DIRECTOR.value)
    giocatori = driver.crea_giocatori(GIOCATORI)

    driver.entra(direttore)
    gara_id = driver.crea_gara(
        matchmaking_strategy="random", rounds_count=TURNI, min_participants=4
    )
    driver.apri_iscrizioni(gara_id)
    driver.iscrivi_tutti(gara_id, giocatori)

    driver.entra(direttore)
    driver.avvia_primo_turno(gara_id)
    return gara_id, direttore, giocatori


@pytest.mark.e2e
class TestPercorsoCompletoRandom:

    def test_dalla_creazione_alla_classifica(self, driver: GaraDriver):
        direttore = driver.crea_utente(UserRole.DIRECTOR.value)
        giocatori = driver.crea_giocatori(GIOCATORI)

        driver.entra(direttore)
        gara_id = driver.crea_gara(
            matchmaking_strategy="random", rounds_count=TURNI, min_participants=4
        )
        driver.apri_iscrizioni(gara_id)
        driver.iscrivi_tutti(gara_id, giocatori)
        driver.entra(direttore)

        driver.avvia_primo_turno(gara_id)
        gara = driver.gara(gara_id)
        assert gara.status == GaraStatus.PLAYING.value
        assert gara.current_round == 1

        # Un solo avvio, tutti i turni sul tavolo.
        assert driver.turni_creati(gara_id) == set(range(1, TURNI + 1))

        for turno in range(1, TURNI + 1):
            partite = driver.partite(gara_id, turno=turno)
            assert len(partite) == GIOCATORI // 2
            assert sorted(partecipanti(partite)) == sorted(g.id for g in giocatori)

        # Si gioca e basta: nessun pulsante da premere fra un turno e l'altro.
        for turno in range(1, TURNI + 1):
            driver.gioca_turno(gara_id, turno)

        assert all(MatchStatus.is_finished(p.status) for p in driver.partite(gara_id))

        driver.termina(gara_id)
        assert driver.gara(gara_id).status == GaraStatus.COMPLETED.value


@pytest.mark.e2e
class TestTurniTuttiInsieme:
    """Il tratto che distingue Random: il calendario è già scritto."""

    def test_il_pulsante_avvia_turno_rifiuta(self, driver: GaraDriver, gara_avviata):
        """Anche a turno 1 concluso, il turno 2 esiste già e non si riavvia.

        Se un domani la pagina mostrasse per errore il pulsante di Amalfi anche
        qui, premerlo non deve risorteggiare un turno già estratto: sarebbe un
        secondo calendario sopra a quello che i giocatori hanno già visto.
        """
        gara_id, _direttore, _giocatori = gara_avviata
        partite_del_secondo = {p.id for p in driver.partite(gara_id, turno=2)}
        driver.gioca_turno(gara_id, 1)

        esito = driver.avvia_turno(gara_id, 2)

        assert esito["success"] is False
        assert "già stato avviato" in esito["error"].lower()
        assert {p.id for p in driver.partite(gara_id, turno=2)} == partite_del_secondo

    def test_la_pagina_mostra_un_turno_per_volta(
        self, driver: GaraDriver, gara_avviata
    ):
        """Il calendario è tutto sorteggiato, ma se ne vede un turno alla volta.

        Una scelta di leggibilità difendibile — dodici partite tutte insieme
        sono illeggibili — con una conseguenza che vale la pena tenere sotto
        gli occhi: **nessuno può vedere in anticipo con chi giocherà al terzo
        turno**, benché sia già deciso e persistito dal primo avvio. Se un
        giorno si volesse pubblicare il calendario completo, è qui che il test
        cambierà, e sarà un cambiamento voluto invece che una scoperta.
        """
        gara_id, _direttore, _giocatori = gara_avviata

        visibili = driver.partite_nella_pagina(gara_id)

        assert visibili >= {p.id for p in driver.partite(gara_id, turno=1)}
        assert visibili.isdisjoint({p.id for p in driver.partite(gara_id, turno=3)})


@pytest.mark.e2e
class TestClassificaGenerale:

    def test_si_aggiorna_a_ogni_partita_senza_aspettare_il_turno(
        self, driver: GaraDriver, gara_avviata
    ):
        """Il contrario di Amalfi, e senza dover ricaricare la pagina.

        Random dichiara `ON_MATCH_COMPLETE`: la classifica complessiva si
        ricalcola alla fine di ogni singola partita, dentro la transazione che
        chiude il match. Non serve nessuna GET a fare da innesco.

        Non si conta il numero di righe: una classifica esiste già dal
        sorteggio, perché l'ordine di estrazione *è* la classifica di partenza
        (`SeedingService.persist_first_round_seeding`). Quello che cambia dopo
        una partita sono i rack.
        """
        gara_id, _direttore, _giocatori = gara_avviata

        def rack_in_classifica() -> int:
            righe = RoundClassification.query.filter_by(gara_id=gara_id).all()
            assert righe, "il sorteggio scrive già la classifica di partenza"
            return sum(riga.racks_won or 0 for riga in righe)

        assert rack_in_classifica() == 0

        driver.gioca_match(driver.partite(gara_id, turno=1)[0].id)

        assert rack_in_classifica() > 0


@pytest.mark.e2e
class TestConfigurazioneRandom:

    def test_anti_reincontro_facoltativo(self, driver: GaraDriver):
        """Dove Amalfi rifiuta, Random accetta: il vincolo è per strategia.

        Stesso form, stessa casella non spuntata, esito opposto — ed è giusto
        così (`anti_rematch_required` in `STRATEGY_CONSTRAINTS`).
        """
        driver.entra(driver.crea_utente(UserRole.DIRECTOR.value))

        gara_id = driver.crea_gara(
            matchmaking_strategy="random", anti_rematch_enabled=""
        )

        assert driver.gara(gara_id).anti_rematch_enabled is False
