# ADR-0020 — Policy minime & Preview senza IO (Amalfi)

**Stato:** Accepted
**Data:** 2025-08-09
**Autori:** team tornei-biliardo

## Contesto

Dopo lo Sprint 1 (Adapter Amalfi con DI: `validate_fn`, `propose_fn`), vogliamo migliorare la struttura OO introducendo:

* un confine chiaro **Query vs Command (CQS)** per il matchmaking;
* regole basilari **separate** e **testabili** per anti‑reincontro e gestione dispari (trio/bye).

Non affrontiamo qui il *tiebreaker finale di classifica* (es. spot‑shot rally): è responsabilità del modulo **Classifiche** e verrà trattato in una ADR dedicata.

## Decisione

1. Aggiungere `preview(prova, round_number)` all’interfaccia Strategy e implementarla in `AmalfiStrategy` in **sola lettura** (nessun `db.session.add/commit`).

   * **Round 1:** usa iscrizioni ordinate in modo deterministico, accoppia in sequenza; se dispari applica regola trio/bye.
   * **Round ≥ 2:** usa *solo* la classifica del round precedente già persistita e i `PlayerEncounter` per evitare reincontri; applica il salto Amalfi.
2. Estrarre due **policy minime** come funzioni pure in `models/matchmaking/policies.py`:

   * `anti_rematch_allowed(prova_id, a, b) -> bool`
     (ritorna `True` se i giocatori **non** hanno ancora giocato tra loro in quella prova; usa `PlayerEncounter.have_played` in **sola lettura**).
   * `decide_trio_or_bye(without_x: bool, can_trio: bool) -> OddResolution`
     con `OddResolution = {BYE, TRIO}`; regola: se il torneo consente trio **e** esiste almeno un pairing 1v1 già costruito, scegli **TRIO**, altrimenti **BYE**.
3. **Non cambiare la DI** di `AmalfiStrategy` introdotta in Sprint 1: il costruttore rimane
   `AmalfiStrategy(validate_fn=..., propose_fn=...)`.
   La preview usa solo letture dal dominio e le funzioni di policy.

## Conseguenze

* **CQS chiaro**: `preview()` simula, `propose()` esegue (engine legacy con side‑effects).
* **Testabilità** migliorata: policy testate in unit (senza ORM pesante) e test di preview con asserzioni no‑side‑effects.
* **Nessun impatto** sulle route: `start_round` continua a passare da `MatchmakingService`/`propose`.

## Fuori scope

* **Tiebreaker finale** (es. spot‑shot rally): verrà modellato nel modulo Classifiche in futura ADR (es. ADR‑0021), con scelta metodo (`NONE`, `HEAD_TO_HEAD`, `SPOTSHOT`) e integrazione nella finalizzazione della classifica.

## Alternative considerate

* Introdurre classi/Protocol per ciascuna policy → **rimandato**: oggi bastano funzioni pure; promuoveremo a oggetti se/quando servirà configurazione per torneo.
* Calcolo *ephemerale* della classifica quando manca quella persistita → **rimandato** per semplicità e per evitare doppioni di logica.

## Migrazione

Nessuna migrazione dati. Solo codice applicativo e test.

## Test

* `tests/test_policy_trio_or_bye.py`
* `tests/test_policy_anti_rematch.py`
* `tests/test_amalfi_preview_no_side_effects.py`

## Riferimenti

* ADR‑0014 — Engine & Strategy Registry
* ADR‑0015 — Contratto Strategy Amalfi (Adapter)
* Sprint 1 — Amalfi adapter via Service (DI: `validate_fn`, `propose_fn`)
