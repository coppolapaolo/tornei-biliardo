---
name: regression-guard
description: Dopo aver corretto un bug o implementato una modifica richiesta dall'utente durante test manuali, crea automaticamente test di regressione e documenta il problema. Attiva quando l'utente riporta un comportamento errato trovato testando la web app, o quando si completa una correzione di bug.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Regression Guard - Test Manuali → Fix → Test Automatici

Questa skill garantisce che ogni bug trovato durante test manuali venga:
1. **Corretto** secondo le specifiche
2. **Documentato** con un ADR o bug report
3. **Coperto da test automatici** per prevenire regressioni

## Trigger di Attivazione

Attiva questa skill quando:
- L'utente riporta un **comportamento errato** trovato testando la web app
- L'utente dice "ho trovato un bug", "non funziona come dovrebbe", "le specifiche dicono X ma fa Y"
- Si **completa una correzione** di un bug
- L'utente chiede di aggiungere test per un caso specifico
- Si implementa una modifica basata su test manuali

## Workflow Completo

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  1. ANALISI     │ ──► │  2. FIX         │ ──► │  3. TEST        │
│  Riproduci bug  │     │  Correggi codice│     │  Scrivi test    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │  4. DOCUMENTA   │
                                               │  ADR + Changelog│
                                               └─────────────────┘
```

## Fase 1: Analisi del Bug

### Raccolta Informazioni

Chiedi o deduci:
1. **Comportamento atteso** (dalle specifiche)
2. **Comportamento osservato** (cosa fa realmente)
3. **Passi per riprodurre** (condizioni specifiche)
4. **Impatto** (chi/cosa è affettato)

### Localizzazione

```bash
# Cerca nei file rilevanti
grep -rn "funzione_sospetta" models/ routes/

# Verifica test esistenti
grep -rn "test.*caso_specifico" tests/new/
```

### Verifica Specifiche

Consulta:
- `docs/SPECIFICHE.md` - Requisiti completi
- `docs/usecases/gare.md` - Workflow dettagliati
- `**/CLAUDE.md` - Convenzioni di dominio

## Fase 2: Correzione

### Prima di Correggere

1. **Scrivi prima il test che fallisce** (TDD)
2. **Identifica la root cause** (non solo il sintomo)
3. **Verifica impatto** su altre funzionalità

### Durante la Correzione

```python
# Commento che spiega il fix
# Fix: [descrizione breve]
# Vedi ADR: docs/decisions/NNNN-*.md
```

### Dopo la Correzione

```bash
# Esegui test esistenti per verificare non-regressione
PYTHONPATH=. pytest tests/new/ -n auto --tb=short
```

## Fase 3: Creazione Test

### Struttura Test di Regressione

```python
# tests/new/unit/test_<modulo>_regression.py
# o aggiungere a test esistente pertinente

class TestNomeFunzionalitaRegression:
    """Test di regressione per bug #NNNN o comportamento specifico."""

    def test_caso_specifico_che_causava_bug(self, ...):
        """
        Regression test: [descrizione bug]

        Bug: [comportamento errato osservato]
        Fix: [cosa è stato corretto]
        Vedi: docs/decisions/NNNN-*.md
        """
        # GIVEN: setup condizioni che causavano il bug
        ...

        # WHEN: azione che triggerava il bug
        ...

        # THEN: comportamento corretto secondo specifiche
        assert risultato == valore_atteso

    def test_edge_case_correlato(self, ...):
        """Verifica edge case scoperto durante fix."""
        ...
```

### Tipi di Test da Creare

| Tipo | Quando | Location |
|------|--------|----------|
| **Unit** | Logica isolata, calcoli | `tests/new/unit/` |
| **Integration** | Workflow multi-componente | `tests/new/integration/` |
| **E2E** | Flusso utente completo | `tests/new/e2e/` |

### Naming Convention

```
test_<modulo>_regression.py          # File dedicato regressioni
test_<funzionalita>_<caso>.py        # Test specifico

# Funzioni
test_<cosa>_should_<comportamento>_when_<condizione>
test_anti_rematch_should_prevent_pairing_when_players_already_faced
```

## Fase 4: Documentazione

### Per Bug Significativi → ADR

Crea ADR in `docs/decisions/` se il bug:
- Rivela un problema architetturale
- Richiede decisioni su come gestire casi edge
- Ha impatto su più moduli

```markdown
# NNNN Bug Fix: [Titolo Descrittivo]

**Data**: YYYY-MM-DD
**Stato**: Accepted
**Tipo**: Bug Fix

## Problema Riscontrato

[Descrizione del bug come riportato dall'utente]

### Comportamento Atteso
[Secondo specifiche]

### Comportamento Osservato
[Cosa faceva realmente]

### Passi per Riprodurre
1. ...
2. ...

## Analisi Root Cause

[Spiegazione tecnica del perché accadeva]

## Soluzione Implementata

[Cosa è stato fatto per correggere]

## Test di Regressione

- `tests/new/unit/test_xxx.py::test_yyy`
- `tests/new/integration/test_xxx.py::test_zzz`

## Note

[Considerazioni aggiuntive, edge case scoperti, etc.]
```

### Per Bug Minori → Commento nel Test

```python
def test_caso_corretto(self):
    """
    Regression: Corretto in data YYYY-MM-DD.
    Bug: [descrizione breve del problema]
    """
```

## Esempio Completo: Anti-Rematch Bug

### Utente Riporta
> "In una gara Amalfi ho visto match tra gli stessi giocatori nonostante anti-rematch attivo"

### Workflow

**1. Analisi**
```python
# Verifico specifiche anti-rematch
# docs/SPECIFICHE.md dice: "evita re-match tra stessi giocatori"

# Cerco implementazione
grep -rn "anti_rematch" models/matchmaking/

# Verifico test esistenti
grep -rn "anti.*rematch" tests/new/
```

**2. Riproduzione**
```python
# Creo test che riproduce il caso
def test_amalfi_anti_rematch_prevents_same_pairing():
    """Verifica che anti-rematch prevenga accoppiamenti ripetuti."""
    # Setup: gara con anti_rematch_enabled=True
    # Round 1: A vs B
    # Round 2: dovrebbe evitare A vs B
    ...
```

**3. Fix**
```python
# Identifico il problema nel codice
# Correggo la logica in models/matchmaking/strategies/amalfi.py
```

**4. Documenta**
```markdown
# docs/decisions/0001-fix-anti-rematch-enforcement.md
```

## Checklist Finale

Prima di considerare completato:

- [ ] Bug riprodotto e compreso
- [ ] Root cause identificata
- [ ] Fix implementato
- [ ] Test di regressione scritto
- [ ] Test passa
- [ ] Test esistenti passano (no regressioni)
- [ ] Documentazione aggiornata (se significativo)
- [ ] Commit message descrittivo

## Comandi Utili

```bash
# Esegui test specifici
PYTHONPATH=. pytest tests/new/unit/test_file.py::test_name -v

# Esegui tutti i test
PYTHONPATH=. pytest tests/new/ -n auto

# Cerca test correlati
grep -rn "def test.*anti_rematch" tests/new/

# Verifica copertura area specifica
PYTHONPATH=. pytest tests/new/unit/test_matchmaking*.py -v --tb=short
```

## Priorità Test

1. **Sempre creare**: Test che riproduce esattamente il bug
2. **Se possibile**: Test per edge case correlati
3. **Se significativo**: Test di integrazione del workflow completo
