# Architecture Decision Records (ADR)

Questa directory contiene le decisioni architetturali significative del progetto.

## Cos'è un ADR?

Un Architecture Decision Record (ADR) cattura una decisione architetturale importante insieme al suo contesto e alle conseguenze. È un documento che spiega **perché** abbiamo fatto una scelta, non solo **cosa** abbiamo scelto.

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
| - | (nessun ADR ancora) | - | - |

## Come Creare un Nuovo ADR

1. Copia `TEMPLATE.md`
2. Rinomina in `NNNN-titolo-kebab-case.md` (es. `0001-use-transactional-decorator.md`)
3. Compila tutte le sezioni
4. Aggiorna questo README con il nuovo ADR

## Stati

| Stato | Significato |
|-------|-------------|
| **Proposed** | In discussione |
| **Accepted** | Approvato e in uso |
| **Deprecated** | Non più raccomandato |
| **Superseded** | Sostituito (link al nuovo) |

## Riferimenti

- [ADR GitHub](https://adr.github.io/)
- [Michael Nygard - Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
