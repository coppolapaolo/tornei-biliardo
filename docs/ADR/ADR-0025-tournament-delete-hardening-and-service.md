# ADR-0025 — Hardening cancellazione torneo & Service Layer

**Data:** 2025-08-15  
**Stato:** Accepted

## Contesto
Dopo ADR-0024 (cascade su `TournamentDirector`), la cancellazione torneo poteva
ancora fallire su altre relazioni senza cascade (es. `Classification`, figli di `Prova`).

## Decisione
1. Introdurre `TournamentService.delete_tournament(tournament_id)` per incapsulare
   il comando applicativo (rule check + delete + commit con gestione `IntegrityError`).
2. Estendere le cascade ORM e gli `ondelete="CASCADE"`:
   - `Tournament → TournamentDirector` (già in ADR-0024, ora con `ondelete` + `passive_deletes`).
   - `Tournament → Classification` (cascade + `ondelete` + `passive_deletes`).
   - `Prova → Inscription`, `Prova → Match`, `Match → Rack` (cascade + `ondelete` + `passive_deletes`).
   - `Prova → RoundClassification`, `Prova → PlayerEncounter` (backref con cascade + `ondelete` + `passive_deletes`).

## Alternative
- Delete manuali “a mano” per ogni tabella: fragile e non scalabile.
- Solo `ON DELETE CASCADE` a livello DB: robusto ma meno esplicito per chi legge il codice
  e non copre i casi ORM senza `passive_deletes`.
- Trigger DB: eccesso di complessità per il dominio.

## Conseguenze
- Cancellazione **atomica** e **robusta** del grafo consentito dalla regola di dominio.
- Route sottile; migliore separazione responsabilità (Clean Architecture).
- Test di integrazione `test_tournament_service_delete_hardening.py` a presidio.
