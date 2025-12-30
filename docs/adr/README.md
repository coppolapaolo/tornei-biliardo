# Architecture Decision Records (ADR)

Questa directory contiene le decisioni architetturali significative del progetto.

## Cos'e un ADR?

Un Architecture Decision Record (ADR) cattura una decisione architetturale importante insieme al suo contesto e alle conseguenze. E un documento che spiega **perche** abbiamo fatto una scelta, non solo **cosa** abbiamo scelto.

## Quando Creare un ADR

Crea un ADR quando:
- Scegli un pattern architetturale
- Introduci una nuova libreria/dipendenza
- Definisci una convenzione di codice significativa
- Prendi una decisione con trade-off importanti
- Modifichi un comportamento fondamentale del sistema

## Indice Decisioni

| # | Titolo | Stato | Data |
|---|--------|-------|------|
| ADR-001 | [Amalfi Strategy Pattern Unification](ADR-001-Amalfi-Strategy-Pattern-Unification.md) | Accepted | 2025-09 |
| ADR-002 | [Fix Anti-Rematch Encounter Cleanup](ADR-002-fix-anti-rematch-encounter-cleanup.md) | Accepted | 2025-12-28 |
| ADR-003 | [User Privacy System](ADR-003-user-privacy-system.md) | Accepted | 2025-12-28 |
| ADR-004 | [Challenge/Gara Decoupling](ADR-004-challenge-gara-decoupling.md) | Accepted | 2025-12-29 |

## Come Creare un Nuovo ADR

1. Copia `TEMPLATE.md`
2. Rinomina in `ADR-NNN-titolo-kebab-case.md` (es. `ADR-004-use-transactional-decorator.md`)
3. Compila tutte le sezioni
4. Aggiorna questo README con il nuovo ADR

## Stati

| Stato | Significato |
|-------|-------------|
| **Proposed** | In discussione |
| **Accepted** | Approvato e in uso |
| **Deprecated** | Non piu raccomandato |
| **Superseded** | Sostituito (link al nuovo) |

## Riferimenti

- [ADR GitHub](https://adr.github.io/)
- [Michael Nygard - Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
