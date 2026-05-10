# TODO Backlog

## ✅ AUDIT COMPLETATO - 31 Dicembre 2025

**Riepilogo Audit**:
- **Sprint completati**: 14
- **Commit effettuati**: ~30
- **Risultato finale**: 0 FAIL, 0 WARNING
- **TODO rimanenti**: 7 (tutti P3 minor, non urgenti)

**Sprint eseguiti**:
| Sprint | Focus | Risultato |
|--------|-------|-----------|
| 1-8 | Documentazione P0, ADR consolidation | ✅ |
| 9 | DST Timezone handling | ✅ |
| 10 | Location FK migration | ✅ |
| 11 | Challenge/Gara decoupling | ✅ |
| 12 | Match/Rack design validation | ✅ |
| 13 | IndividualMatchService decomposition (1190→560 lines) | ✅ |
| 14 | Circular imports optimization (14→13) | ✅ |

---

## Statistiche Finali

| Metrica | Iniziale | Finale |
|---------|----------|--------|
| TODO comments | 28 | 7 |
| File > 1000 linee | 2 | 1 (dashboard/services.py - alta coesione) |
| Import circolari | 14 | 13 (minimo architetturale) |
| ADR directories | 2 | 1 (consolidato) |
| Pyright errors | 0 | 0 |

---

## ✅ Resolved in Sprint 9

### ~~DST Timezone Handling~~ ✅ FIXED
- **File**: `utils/jinja.py:45`
- **Risolto in**: Commit `553d1a5`
- **Soluzione**: `zoneinfo.ZoneInfo("Europe/Rome")` per conversione automatica DST

---

## ✅ Resolved in Sprint 10

### ~~P1 - Location/Venue Refactoring~~ ✅ RESOLVED
- `billiard_hall_id` FK aggiunto a `Gara`, `MatchProposal`, `IndividualMatch`
- UI datalist implementata per selezione venue

---

## ✅ Resolved in Sprint 11

### ~~P2 - Challenge/Gara Coupling~~ ✅ RESOLVED
- Vedi `docs/adr/ADR-004-challenge-gara-decoupling.md`
- Dependency direction inverted: Competition → Challenge (correct DDD)

---

## ✅ Resolved in Sprint 12

### ~~P2 - Match/Rack Abstraction~~ ✅ RESOLVED
- Design esistente validato
- Score già implementato in `models/match/score.py`

---

## ✅ Resolved in Sprint 13

### ~~IndividualMatchService God Object~~ ✅ RESOLVED
- Decomposto da 1190 → 560 linee (facade)
- 4 nuovi servizi specializzati creati

---

## ✅ Resolved in Sprint 14

### ~~Circular Imports~~ ✅ OPTIMIZED
- Ridotti da 14 a 13 (minimo per architettura Flask)
- Documentato in `utils/__init__.py`

---

## Planned Features (non urgenti)

### Playoff System
- **File**: `models/playoff/models.py`
- **Stato**: Modelli esistono, integrazione pendente
- **Documentazione**: `docs/TODO_PLAYOFF_IMPLEMENTATION.md`

---

## P3 - Minor / Low Priority (7 rimanenti)

Questi TODO sono a bassa priorità e possono essere affrontati quando si lavora sui file correlati:

1. **Discipline Field Structure** (`models/match/models.py:407`)
2. **Availability Time Format Validation** (`models/individual_match/availability_service.py:73`)
3. **IndividualMatch Score Delegation** (`models/individual_match/models.py:481`)
4. **Unknown Context TODO** (`models/individual_match/models.py:570`)
5. Altri TODO minori nei modelli

**Nota**: Nessuno di questi TODO è bloccante. Affrontarli solo se si modifica il codice correlato.

---

## Riferimenti

- **ADR**: `docs/adr/`
- **Verifica audit**: `./scripts/audit/verify_audit_completion.sh`
- **Piano originale**: `docs/AUDIT_REFACTORING_PLAN.md`

---

*Documento finalizzato il 31 Dicembre 2025.*
