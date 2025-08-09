# ADR-0015 — Contratto Strategy per Amalfi (Adapter al legacy engine)

**Stato:** Accepted
**Data:** 2025-08-09
**Autore:** team tornei-biliardo

## Contesto

Lo Sprint 1 richiede di esporre il metodo di abbinamento **Amalfi** come **Strategy** registrata nel **Registry** e invocata tramite **MatchmakingService**. L’engine Amalfi legacy già gestisce anti‑reincontro, bye/X, trii e il calcolo del *salto* dai round ≥ 2, ma presentava uno storico **mismatch d’ordine parametri** nella registrazione degli incontri (`PlayerEncounter.record_encounter`).

## Decisione

1. Introdurre `AmalfiStrategy` come **Adapter** dell’engine legacy dietro l’interfaccia comune `PairingStrategy`.
2. Correggere il contratto di registrazione incontri in tutti i punti che invocano il dominio:

   ```python
   PlayerEncounter.record_encounter(prova_id, player1_id, player2_id, round_number)
   ```
3. Fare in modo che la route di avvio turno (`start_round`) usi **MatchmakingService**:

   ```python
   svc = get_matchmaking_service()
   pairings = svc.run("Amalfi", prova=prova, round_number=round_number)
   ```
4. Fino all’introduzione di **Unit of Work** (Sprint successivi), accettiamo che l’engine legacy esegua side‑effects (creazione `Match`, aggiornamento `PlayerEncounter`).

## Invarianti (contratti funzionali)

1. **No self‑match**: mai `p1 == p2`.
2. **Anti‑reincontro**: evitare accoppiamenti già avvenuti tramite `PlayerEncounter.have_played(prova_id, p1_id, p2_id)`.
3. **Salto Amalfi** (round ≥ 2): `salto = rounds_count − round_number`; la destinazione si cerca scorrendo la classifica del round precedente con wrapping e saltando i giocatori già accoppiati.
4. **Disparità giocatori**:

   * se il torneo è `without_x=True` e c’è disparità, l’ultimo match diventa **trio** (p1‑p2‑p3) mantenendo `target_score` coerente con `distance/best_of`;
   * altrimenti si genera un **bye** (X) assegnando vittoria al giocatore rimasto.
5. **Preview**: idealmente **senza side‑effects**; durante la fase Adapter può riflettersi sui dati esistenti ma la migrazione a `Strategy.preview()` *dry‑run* è demandata allo **Sprint 2**.

## Contratti API Strategy

* `validate(prova) -> ValidationResult(ok: bool, messages: tuple[str, ...])`
* `propose(prova, round_number) -> Sequence[Pairing]`

  * `Pairing.players: tuple[int, ...]` (es. `(p1,)` per bye, `(p1,p2)` per 1v1, `(p1,p2,p3)` per trio)
  * `Pairing.is_bye: bool`

## Implementazione

* **Registry/Service** già presenti; l’Adapter Amalfi effettua:

  * `validate` delegando al validator legacy e traducendo il risultato in `ValidationResult`.
  * `propose` invocando l’engine legacy, poi mappando gli oggetti `Match` in `Pairing` (gestione robusta di `TrioMatch`).
* **Route admin** `amalfi_start_round`: usa `MatchmakingService` e messaggi basati su `pairings` (conteggio normali / bye / trio).
* **Fix dominio**: tutte le chiamate a `PlayerEncounter.record_encounter` riallineate all’ordine corretto; uso di `PlayerEncounter.have_played(prova_id, p1, p2)` nei controlli.

## Conseguenze

**Pro**

* Strategy Amalfi disponibile via registry; route più pulite e testabili.
* Contratti uniformi (`Pairing`, `ValidationResult`).
* Invarianti documentate e coperte dai test.

**Contro**

* Side‑effects ancora nell’engine legacy fino allo Sprint UoW.

## Migrazione / Dati

Nessuna migrazione dati. Solo correzioni di chiamata e wiring delle route.

## Test

* **E2E**: `tests/test_amalfi_adapter_binding.py` verifica che `run("Amalfi", …)` produca `Pairing` coerenti (trio o bye+match) con 3 giocatori e `without_x=True`.
* **Anti‑reincontro**: i `PlayerEncounter` vengono aggiornati al termine della creazione dei match.

## Alternative considerate

* Aggiungere alias tolleranti in `PlayerEncounter` per l’ordine errato: **scartato** (copre l’errore e prolunga il debito).
* Unificare preview e create in un’unica API *idempotente*: rimandato allo Sprint UoW/Preview.

## Riferimenti

* ADR‑0014 — Engine & Strategy Registry

