# ADR-0019 — Deprecazione `AmalfiEngine.preview_next_round_matches()` e delega alle Policy

**Status:** Accepted
**Date:** 2025-08-10
**Related:** ADR-0013, ADR-0014, ADR-0020

## Contesto

Storicamente l’engine Amalfi eseguiva anche la **preview** (lettura) e conteneva logica per:

* verificare anti‑rematch tramite `PlayerEncounter.have_played(...)`;
* decidere disparità (TRIO/BYE) inline.

Con l’introduzione di **Strategy/Service/Registry** e delle **policy** (anti‑rematch, odd‑resolution), la preview vive nella Strategy come **operazione no‑IO** e l’engine resta focalizzato sui side‑effects.

## Decisione

* **Deprecare** `AmalfiEngine.preview_next_round_matches()` (emette `DeprecationWarning`).
* **Delegare** nell’engine le verifiche a **policy** condivise:

  * `anti_rematch_allowed(prova_id, a, b)`
  * `decide_trio_or_bye(tournament_without_x, can_trio)` con `OddResolution` (TRIO/BYE)

## Conseguenze

* Una sola fonte di verità per le regole (policy).
* Engine semplificato e allineato alla Strategy; riduzione duplicazioni e bug.
* Permette a Strategy e Engine di evolvere coerentemente.

## Dettagli di implementazione

* `amalfi/engine.py`:

  * `_is_valid_pairing()` usa `anti_rematch_allowed(...)`.
  * `_handle_unmatched_player()` usa `decide_trio_or_bye(...)`.
  * `preview_next_round_matches()` marcato come deprecato.
* **Nessun cambio** all’API pubblica di creazione match.

## Alternative considerate

* Mantenere la logica inline nell’engine → scartata (duplicazione e incoerenza con Strategy).
* Rimuovere subito il metodo di preview → scartata per compat con codice legacy; lo rimuoveremo in una fase successiva.

## Testing

* Coperto indirettamente dai test Strategy/Route (round 1/2) e dai test policy.
* Il legacy path resta accessibile ma non più usato dalle route.

## Migrazione

* Nessuna azione lato frontend.
* Il warning serve a intercettare eventuali punti legacy rimasti.
