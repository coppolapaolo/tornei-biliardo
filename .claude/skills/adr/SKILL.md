---
name: adr
description: Crea Architecture Decision Records per decisioni tecniche significative. Attiva quando si sceglie un pattern architetturale, una libreria, una strategia di implementazione, o si prende una decisione tecnica con impatto duraturo.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Architecture Decision Records (ADR)

Questa skill documenta decisioni architetturali significative in file strutturati per preservare il contesto decisionale nel tempo.

## Trigger di Attivazione

Attiva questa skill quando nella conversazione:
- Si sceglie un **pattern architetturale** (Repository, Service Layer, Strategy, etc.)
- Si decide quale **libreria/framework** usare
- Si definisce una **strategia di implementazione** con trade-off
- Si prende una decisione che **impatta più file/moduli**
- Si discute di **alternative** e si sceglie un approccio
- Si modifica un **comportamento fondamentale** del sistema
- Si introduce una **nuova convenzione** di codice

**NON attivare per**:
- Decisioni UI (usa skill `ui-conventions`)
- Bug fix semplici
- Refactoring minori senza impatto architetturale

## Directory e Naming

```
docs/adr/
├── ADR-001-….md
├── …
├── ADR-075-modifiche-tracciate-invece-che-impedite.md
├── TEMPLATE.md
└── README.md   (indice)
```

**Naming convention**: `ADR-NNN-titolo-kebab-case.md` (tre cifre); il titolo
nel file è `# [NNN] Titolo`.

## Template ADR

```markdown
# [NNN] Titolo Decisione

**Data**: YYYY-MM-DD
**Stato**: Proposed | Accepted | Deprecated | Superseded by [NNN]
**Decisori**: Chi ha partecipato alla decisione

## Contesto

Qual è il problema o la situazione che ha richiesto questa decisione?
Quali vincoli o requisiti esistono?

## Decisione

Cosa abbiamo deciso di fare e perché.

## Alternative Considerate

### Alternativa 1: [Nome]
- Pro: ...
- Contro: ...

### Alternativa 2: [Nome]
- Pro: ...
- Contro: ...

## Conseguenze

### Positive
- ...

### Negative
- ...

### Rischi
- ...

## Note Implementative

Dettagli tecnici, esempi di codice, riferimenti a file.
```

## Processo

### 1. Riconoscere una Decisione Architetturale

Segnali che indicano la necessità di un ADR:
- "Dovremmo usare X o Y?"
- "Ho scelto questo pattern perché..."
- "Le alternative erano..."
- Impatto su più di 3 file
- Introduce una nuova dipendenza
- Cambia il comportamento di un modulo core

### 2. Raccogliere Informazioni

Prima di scrivere l'ADR:
```bash
# Trova il prossimo numero disponibile
ls docs/adr/ADR-*.md | tail -1
```

Chiedi o deduci:
- Qual è il problema che stiamo risolvendo?
- Quali alternative sono state considerate?
- Quali sono i trade-off?

### 3. Creare l'ADR

1. Determina il numero sequenziale (il successivo all'ultimo `ADR-NNN`)
2. Crea il file con naming corretto
3. Compila tutte le sezioni del template
4. Status iniziale: "Proposed" o "Accepted"

### 4. Collegare l'ADR

Dopo la creazione:
- Aggiungi riferimento nei file di codice rilevanti
- Aggiorna README.md in docs/adr/ se esiste
- Menziona l'ADR nel commit message se appropriato

## Esempi di ADR per Questo Progetto

### Esempio Completo

Un ADR reale del progetto, con contesto, alternative ed emendamenti:
`docs/adr/ADR-073-classifica-generale-un-calcolo-solo.md`.

## Stati ADR

| Stato | Significato |
|-------|-------------|
| **Proposed** | In discussione, non ancora approvato |
| **Accepted** | Approvato e in uso |
| **Deprecated** | Non più raccomandato ma ancora presente |
| **Superseded** | Sostituito da altro ADR (linkare) |

## Regole

1. **Un ADR per decisione** - Non raggruppare decisioni diverse
2. **Emendamenti datati, non riscritture** - Una correzione o un'estensione di un ADR accepted va in una sezione `## Emendamento (YYYY-MM-DD)` che dice cosa cambia e perché; una decisione che ribalta la precedente è un ADR nuovo, e la vecchia passa a Superseded
3. **Contesto completo** - Chi legge tra 6 mesi deve capire
4. **Alternative documentate** - Spiega perché NON hai scelto le altre
5. **Link bidirezionali** - ADR → codice e codice → ADR
