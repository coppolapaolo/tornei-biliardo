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
├── 0001-use-flask-sqlalchemy.md
├── 0002-transactional-decorator-pattern.md
├── 0003-soft-delete-for-users.md
├── TEMPLATE.md
└── README.md
```

**Naming convention**: `NNNN-titolo-kebab-case.md`

## Template ADR

```markdown
# [NNNN] Titolo Decisione

**Data**: YYYY-MM-DD
**Stato**: Proposed | Accepted | Deprecated | Superseded by [NNNN]
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
ls docs/adr/*.md 2>/dev/null | tail -1
```

Chiedi o deduci:
- Qual è il problema che stiamo risolvendo?
- Quali alternative sono state considerate?
- Quali sono i trade-off?

### 3. Creare l'ADR

1. Determina il numero sequenziale (es. 0004)
2. Crea il file con naming corretto
3. Compila tutte le sezioni del template
4. Status iniziale: "Proposed" o "Accepted"

### 4. Collegare l'ADR

Dopo la creazione:
- Aggiungi riferimento nei file di codice rilevanti
- Aggiorna README.md in docs/adr/ se esiste
- Menziona l'ADR nel commit message se appropriato

## Esempi di ADR per Questo Progetto

### ADR già documentabili (da creare retroattivamente):

1. **Uso del decorator @transactional** - Pattern per gestione transazioni
2. **Soft delete per User model** - Perché non hard delete
3. **Strategy pattern per matchmaking** - Amalfi, Round-Robin, etc.
4. **Event-driven notifications** - Decoupling con domain events
5. **Race-to-N terminology** - Convenzione "Al N" vs "Best of N"

### Esempio Completo

```markdown
# 0003 Soft Delete per User Model

**Data**: 2025-01-15
**Stato**: Accepted
**Decisori**: Team sviluppo

## Contesto

Gli utenti hanno relazioni con molte entità (match, iscrizioni,
statistiche). L'eliminazione hard causerebbe violazioni FK o
perdita di dati storici.

## Decisione

Implementiamo soft delete con campo `is_deleted` e filtering
automatico a livello di session SQLAlchemy.

## Alternative Considerate

### Alternativa 1: Hard Delete con CASCADE
- Pro: Semplice, nessun campo extra
- Contro: Perdiamo storico partite, statistiche

### Alternativa 2: Anonimizzazione senza delete
- Pro: Mantiene tutti i dati
- Contro: Complessità gestione, GDPR compliance

## Conseguenze

### Positive
- Storico preservato
- Rollback possibile
- Statistiche accurate

### Negative
- Query più complesse (WHERE is_deleted=False)
- Storage aggiuntivo

## Note Implementative

Vedi `models/user/base.py` per implementazione.
Usa `User.query.with_deleted()` per includere eliminati.
```

## Stati ADR

| Stato | Significato |
|-------|-------------|
| **Proposed** | In discussione, non ancora approvato |
| **Accepted** | Approvato e in uso |
| **Deprecated** | Non più raccomandato ma ancora presente |
| **Superseded** | Sostituito da altro ADR (linkare) |

## Regole

1. **Un ADR per decisione** - Non raggruppare decisioni diverse
2. **Immutabilità** - Non modificare ADR accepted, crea uno nuovo
3. **Contesto completo** - Chi legge tra 6 mesi deve capire
4. **Alternative documentate** - Spiega perché NON hai scelto le altre
5. **Link bidirezionali** - ADR → codice e codice → ADR
