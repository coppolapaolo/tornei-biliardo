# Architecture Decision Records (ADR)

Questa directory contiene le decisioni architetturali significative del progetto.

## Cos'è un ADR?

Un ADR documenta una decisione architetturale importante, incluso il contesto, le alternative considerate e le conseguenze. Serve a preservare il "perché" delle scelte nel tempo.

## Formato

Ogni ADR segue il formato:
- **NNNN-titolo-kebab-case.md**
- Contiene: Contesto, Decisione, Alternative, Conseguenze, Note Implementative

## Stati

| Stato | Significato |
|-------|-------------|
| Proposed | In discussione |
| Accepted | Approvato e in uso |
| Deprecated | Non più raccomandato |
| Superseded | Sostituito da altro ADR |

## Indice ADR

| # | Titolo | Stato | Data |
|---|--------|-------|------|
| [0001](0001-wizard-campionato-e-sistema-playoff.md) | Wizard Campionato Multi-Step e Sistema Playoff | Accepted | 2026-01-07 |

## Come Aggiungere un ADR

1. Trova il prossimo numero: `ls docs/decisions/*.md | tail -1`
2. Crea file: `NNNN-titolo-kebab-case.md`
3. Usa il template in `.claude/skills/adr/`
4. Aggiorna questo README
