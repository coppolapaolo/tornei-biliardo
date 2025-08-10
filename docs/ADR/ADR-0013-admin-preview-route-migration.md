# ADR-0013 — Migrazione della route di anteprima su Strategy+Service (Amalfi)

**Status:** Accepted
**Date:** 2025-08-10
**Related:** ADR-0014 (Registry/Service), ADR-0015 (Strategy Contract), ADR-0020 (Policy + Preview no‑IO)

## Contesto

La route `GET /admin/prova/<id>/amalfi/preview_round/<n>` usava l'engine legacy (`AmalfiEngine.preview_next_round_matches`) per generare un'anteprima degli abbinamenti. Questo comportava:

* logica duplicata rispetto alla nuova `AmalfiStrategy.preview()`;
* coupling al motore legacy e difficoltà di test unitari/no‑IO;
* assenza di pluggabilità via `Registry` e `MatchmakingService`.

## Decisione

* La route **usa ora il Service** (`MatchmakingService.preview(strategy_name="Amalfi", ...)`) che a sua volta chiama **`AmalfiStrategy.preview()`** (no side‑effects).
* **Compatibilità JSON**: mantenuta (`type: normal|trio|bye`, campi `player1/2/3`, `salto_applied` default 0).
* **Anti‑rematch** e **gestione disparità (TRIO/BYE)** sono demandate alle **policy** (vedi ADR‑0020).

## Conseguenze

* L’anteprima è ora **deterministica e priva di IO**, quindi più testabile e veloce.
* Ridotto il debito tecnico: nessuna logica duplicata tra route/engine/strategy.
* Facilita l’introduzione di nuove strategie tramite il `Registry`.

## Dettagli di implementazione (modifiche)

* `routes/admin.py`: switch a `get_matchmaking_service().preview(...)` e rimozione import inutilizzati dell’engine.
* `models/matchmaking/service.py`: aggiunta `preview()` (validazione + delega a Strategy).
* `models/matchmaking/strategies/amalfi_adapter.py`: `preview()` usa policy `anti_rematch_allowed` + `decide_trio_or_bye`.

## Alternative considerate

* Continuare a usare l’engine legacy in lettura → scartata: coupling e impossibilità di riuso di policy/strategy.

## Testing

* **Nuovi**: `tests/test_admin_preview_route_integration.py` (round 1), `tests/test_admin_preview_route_integration_round2.py` (round 2 anti‑rematch), `tests/test_admin_preview_route_errors.py` (error path).
* **Esistenti**: `test_amalfi_preview_no_side_effects.py`, `test_amalfi_adapter_binding.py`, `test_matchmaking_contract.py`.

## Migrazione & Compatibilità

* Nessun breaking change per il frontend: risposta JSON invariata.
* L’engine legacy mantiene un metodo di *preview* **deprecato** (vedi ADR‑0019).

## Metriche/Quality Gates

* Tempo di risposta: preview < 2s.
* Copertura test > 90% su module Strategy/Service/Route.
