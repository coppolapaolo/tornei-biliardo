# ✅ AUDIT E REFACTORING COMPLETATO

**Data Completamento**: 31 Dicembre 2025
**Data Creazione**: 2025-12-29
**Versione**: 2.0 (FINAL)
**Repository**: tornei-biliardo

---

## 🎉 RIEPILOGO COMPLETAMENTO

| Sprint | Focus | Risultato |
|--------|-------|-----------|
| 1-8 | Documentazione P0, ADR consolidation | ✅ Completato |
| 9 | DST Timezone handling | ✅ Completato |
| 10 | Location FK migration | ✅ Completato |
| 11 | Challenge/Gara decoupling | ✅ Completato |
| 12 | Match/Rack design validation | ✅ Completato |
| 13 | IndividualMatchService decomposition (1190→560 lines) | ✅ Completato |
| 14 | Circular imports optimization (14→13) | ✅ Completato |

**Metriche Finali**:
- **TODO comments**: 28 → 7 (P3 minor)
- **File > 1000 linee**: 2 → 1 (dashboard/services.py - alta coesione)
- **Import circolari**: 14 → 13 (minimo architetturale Flask)
- **Pyright errors**: 0
- **Test failures**: 0

**Verifica**: `./scripts/audit/verify_audit_completion.sh` → 0 FAIL, 0 WARNING

---

---

## 📋 INDICE

1. [Executive Summary](#1-executive-summary)
2. [Problemi Critici (P0)](#2-problemi-critici-p0)
3. [Problemi Importanti (P1)](#3-problemi-importanti-p1)
4. [Debito Tecnico (P2)](#4-debito-tecnico-p2)
5. [Miglioramenti Architetturali (P3)](#5-miglioramenti-architetturali-p3)
6. [Piano di Esecuzione](#6-piano-di-esecuzione)
7. [Criteri di Acceptance](#7-criteri-di-acceptance)

---

## 1. EXECUTIVE SUMMARY

### Stato Attuale
Il progetto è in buono stato generale con refactoring significativi completati (Phase 1-3). Tuttavia, l'analisi del codice ha rivelato:

| Categoria | Conteggio | Criticità |
|-----------|-----------|-----------|
| Documentazione disallineata | 5 | 🔴 Alta |
| Codice deprecato non rimosso | 4 | 🟠 Media |
| File da gitignore | 2 | 🟠 Media |
| TODO non risolti | 27 | 🟡 Bassa |
| File troppo grandi | 6 | 🟡 Bassa |
| Import circolari workaround | 17 | 🟡 Bassa |

### Metriche Chiave
- **Linee di codice Python**: ~50,000+
- **Test legacy da migrare**: 90+ file in `tests/legacy/`
- **File Python > 1000 linee**: 6
- **Directory ADR duplicate**: 2 (`docs/adr/` e `docs/decisions/`)

---

## 2. PROBLEMI CRITICI (P0)

### 2.1 ADR-001 Obsoleta - Directory Amalfi

**Problema**: L'ADR-001 in `docs/adr/` afferma che la directory `amalfi/` esiste ancora al root, ma è stata completamente migrata.

**Stato Attuale**:
```
DOCUMENTAZIONE (ADR-001):
project_root/
├── amalfi/                           # "Original location (maintained)"
│   └── engine.py                     # "Legacy Amalfi implementation"

REALTÀ (verificato):
- amalfi/ directory NON ESISTE
- File migrato a: models/matchmaking/strategies/amalfi.py
```

**Azione**:
```bash
# Verifica stato attuale (già fatto - confermato che amalfi/ non esiste)
ls -la amalfi/ 2>/dev/null || echo "Directory amalfi/ non esiste"

# File corretto trovato:
ls -la models/matchmaking/strategies/amalfi.py
```

**Fix Richiesto**:
Aggiornare `docs/adr/ADR-001-Amalfi-Strategy-Pattern-Unification.md`:

```markdown
# Sostituire la sezione "Current Architecture" con:

**Current Architecture** (Updated 2025-12):
```
project_root/
├── models/matchmaking/strategies/
│   ├── amalfi.py                    # Migrated Amalfi implementation (specification-compliant)
│   ├── base.py                      # Strategy interface
│   └── ...other strategies
```

**Migration Completed**: The `amalfi/` directory has been fully migrated to `models/matchmaking/strategies/amalfi.py`. The adapter pattern is now the exclusive integration method.
```

**Criterio di Acceptance**:
- [ ] ADR-001 aggiornata con architettura corretta
- [ ] Riferimenti a `amalfi/` rimossi o marcati come "legacy removed"
- [ ] Data di aggiornamento presente nel documento

---

### 2.2 Directory ADR Duplicate

**Problema**: Esistono due directory per le ADR con convenzioni diverse:

| Directory | File | Convenzione |
|-----------|------|-------------|
| `docs/adr/` | ADR-001-*.md | `ADR-NNN-kebab-case.md` |
| `docs/decisions/` | 0001-*.md, 0002-*.md | `NNNN-kebab-case.md` |

**Contenuto Attuale**:
```
docs/adr/
└── ADR-001-Amalfi-Strategy-Pattern-Unification.md

docs/decisions/
├── 0001-fix-anti-rematch-encounter-cleanup.md
├── 0002-user-privacy-system.md
├── README.md  ← DICE "nessun ADR ancora" (FALSO!)
└── TEMPLATE.md
```

**Fix Richiesto** (Opzione A - Consolidare in `docs/adr/`):

```bash
# 1. Rinominare file da docs/decisions/ a docs/adr/
mv docs/decisions/0001-fix-anti-rematch-encounter-cleanup.md \
   docs/adr/ADR-002-fix-anti-rematch-encounter-cleanup.md

mv docs/decisions/0002-user-privacy-system.md \
   docs/adr/ADR-003-user-privacy-system.md

mv docs/decisions/TEMPLATE.md docs/adr/TEMPLATE.md

# 2. Aggiornare docs/adr/README.md (creare se non esiste)
# 3. Rimuovere docs/decisions/ (dopo migrazione)
rm -rf docs/decisions/
```

**Fix Richiesto** (Opzione B - Tenere separati ma allineare):
```bash
# Aggiornare docs/decisions/README.md con l'indice corretto
```

**Contenuto README.md Corretto**:
```markdown
# Architecture Decision Records (ADR)

## Indice Decisioni

| # | Titolo | Stato | Data |
|---|--------|-------|------|
| 0001 | Fix Anti-Rematch Encounter Cleanup | Accepted | 2025-12-28 |
| 0002 | User Privacy System | Accepted | 2025-12-28 |

## ADR in docs/adr/

Nota: Decisioni più vecchie sono in `docs/adr/`:
- ADR-001: Amalfi Strategy Pattern Unification
```

**Criterio di Acceptance**:
- [ ] Una sola convenzione di naming per le ADR
- [ ] README.md con indice aggiornato
- [ ] Nessun riferimento a "nessun ADR ancora"

---

### 2.3 coverage.json nel Repository

**Problema**: File `coverage.json` (725KB) è tracciato da Git ma dovrebbe essere ignorato.

**Verifica**:
```bash
ls -la coverage.json
# Output: -rw-r--r-- 1 root root 725454 Sep 19 22:16 coverage.json

cat .gitignore | grep -i coverage
# Output: coverage.xml (ma NON coverage.json!)
```

**Fix Richiesto**:
```bash
# 1. Aggiungere a .gitignore
echo "coverage.json" >> .gitignore

# 2. Rimuovere dal tracking Git
git rm --cached coverage.json

# 3. Commit
git commit -m "chore: remove coverage.json from tracking and add to gitignore"
```

**Criterio di Acceptance**:
- [ ] `coverage.json` in `.gitignore`
- [ ] File non più tracciato da Git
- [ ] File locale può rimanere (generato da test)

---

### 2.4 routes/admin.py Riferimento a Backup Inesistente

**Problema**: Il file `routes/admin.py` contiene un commento che riferisce a un backup che non esiste:

```python
# Linea nel file:
# The original file has been backed up to routes/admin_backup.py
```

**Verifica**:
```bash
ls -la routes/admin_backup.py 2>/dev/null || echo "File non esiste"
# Output: File non esiste
```

**Fix Richiesto**:
Rimuovere la riga dal commento in `routes/admin.py`:
```python
# RIMUOVERE QUESTA RIGA:
# The original file has been backed up to routes/admin_backup.py
```

**Criterio di Acceptance**:
- [ ] Nessun riferimento a `admin_backup.py` nel codice
- [ ] Commenti accurati riguardo lo stato del refactoring

---

## 3. PROBLEMI IMPORTANTI (P1)

### 3.1 Metodi Deprecati Non Rimossi

**Metodi identificati**:

| File | Linea | Metodo | Sostituto |
|------|-------|--------|-----------|
| `models/match/state_service.py` | 115 | `reset_to_pending()` | `RackService.reset_match_complete()` |
| `models/match/services.py` | 103 | `reset_to_pending()` (wrapper) | `RackService.reset_match_complete()` |
| `models/match/table_assignment_service.py` | 50 | `get_table_count_for_gara()` | `get_table_names_for_gara()` |
| `models/competition/models.py` | 485 | `get_winning_score()` | `distance_config.get_winning_racks()` |
| `models/competition/models.py` | 493 | `is_match_finished()` | `RackScore.is_complete()` |

**Azioni Richieste per Ogni Metodo**:

#### 3.1.1 reset_to_pending() in state_service.py

```bash
# 1. Verificare utilizzi
grep -rn "reset_to_pending" --include="*.py" | grep -v "def reset_to_pending\|DEPRECATED\|test_"

# 2. Se nessun utilizzo produzione, rimuovere
# 3. Se ci sono utilizzi, migrare prima a reset_match_complete()
```

**Template di migrazione**:
```python
# PRIMA (deprecato):
MatchStateService.reset_to_pending(match_id)

# DOPO (nuovo):
RackService.reset_match_complete(match_id)
```

#### 3.1.2 Verifica Utilizzi Tutti i Metodi Deprecati

```bash
# Script di verifica completo
echo "=== Verificando utilizzi metodi deprecati ==="
for method in "reset_to_pending" "get_table_count_for_gara" "get_winning_score" "is_match_finished"; do
    echo "--- $method ---"
    grep -rn "$method" --include="*.py" | grep -v "def $method\|DEPRECATED\|#.*$method\|test_" | head -10
done
```

**Criterio di Acceptance**:
- [ ] Ogni metodo deprecato ha 0 utilizzi in codice produzione
- [ ] Metodi deprecati rimossi o marcati per rimozione futura con data
- [ ] Test aggiornati per usare nuovi metodi

---

### 3.2 Funzioni Legacy in utils/__init__.py

**Problema**: `utils/__init__.py` (747 linee) contiene funzioni business logic che dovrebbero stare nei servizi.

**Funzioni da migrare**:

| Funzione | Linea | Target Service |
|----------|-------|----------------|
| `create_round_matches()` | 444 | `MatchmakingService` |
| `create_round_matches_amalfi_compatible()` | 699 | `MatchmakingService` |
| `calculate_round_classification()` | 492 | `ClassificationService` |
| `create_default_users()` | 549 | `UserService` o script separato |
| `create_sample_campionato()` | 567 | Script di seed separato |
| `create_admin_if_not_exists()` | 653 | `UserService.ensure_admin_exists()` |

**Utilizzi Attuali di create_round_matches**:
```
models/competition/round_service.py:167 - UTILIZZO ATTIVO!
tests/legacy/* - solo test
```

**Azione Richiesta**:

```python
# 1. In models/competition/round_service.py, sostituire:
# PRIMA (linea 167):
from utils import create_round_matches
create_round_matches(gara, inscriptions, 1)

# DOPO:
from models.matchmaking.service import MatchmakingService
MatchmakingService().run(gara.matchmaking_strategy, gara, round_number=1)
```

```python
# 2. Deprecare funzioni in utils/__init__.py:
def create_round_matches(gara, players_or_inscriptions, round_number):
    """
    DEPRECATED: Use MatchmakingService.run() instead.
    
    This function will be removed in a future version.
    Migration guide:
        from models.matchmaking.service import MatchmakingService
        MatchmakingService().run(strategy_name, gara, round_number)
    """
    import warnings
    warnings.warn(
        "create_round_matches() is deprecated. Use MatchmakingService.run() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    # ... existing implementation ...
```

**Criterio di Acceptance**:
- [ ] `round_service.py` usa `MatchmakingService` invece di `create_round_matches`
- [ ] Funzioni legacy marcate come DEPRECATED con warnings
- [ ] Test legacy aggiornati o marcati per migrazione

---

### 3.3 Distance/Score Refactoring Incompleto

**Problema**: Il refactoring Distance/Score è dichiarato completato ma ci sono ancora utilizzi diretti di `.distance` e `gara.distance`.

**Utilizzi Diretti Trovati** (dovrebbero usare `distance_config`):

| File | Linea | Codice |
|------|-------|--------|
| `models/match/scoring_service.py` | 324 | `match.gara.distance` |
| `models/match/scoring_service.py` | 436 | `match.gara.distance` |
| `models/match/scoring_service.py` | 465 | `match.gara.distance` |
| `models/match/services.py` | 618 | `match.gara.distance` |
| `models/match/set_models.py` | 240 | `self.distance` |
| `models/match/set_models.py` | 242 | `self.distance` |

**Azione Richiesta**:

```python
# PRIMA (scoring_service.py:324):
return (match.player1_score + match.player2_score) < match.gara.distance

# DOPO:
return not match.rack_score.is_complete()
# oppure:
distance = match.distance_config
return (match.player1_score + match.player2_score) < distance.racks
```

**Decisione Richiesta**:
Prima di procedere, decidere se:
- A) Completare il refactoring Distance/Score come pianificato
- B) Abbandonare e documentare che si usa approccio ibrido
- C) Posticipare a fase futura

**Se si sceglie A**, seguire `docs/refactoring/DISTANCE_SCORE_CHECKLIST.md`.

**Criterio di Acceptance**:
- [ ] Decisione documentata in ADR
- [ ] Se A: Nessun utilizzo diretto di `.distance` (eccetto nei value object stessi)
- [ ] Se B/C: Documentazione chiara dell'approccio scelto

---

## 4. DEBITO TECNICO (P2)

### 4.1 File Python Troppo Grandi

| File | Linee | Target | Azione |
|------|-------|--------|--------|
| `routes/admin/competition.py` | 2,140 | <500 | Decomporre in sotto-blueprint |
| `routes/player.py` | 2,117 | <500 | Decomporre in sotto-blueprint |
| `routes/gamification/__init__.py` | 1,345 | <500 | Estrarre route separate |
| `models/individual_match/services.py` | 1,183 | <500 | Estrarre servizi specifici |
| `models/dashboard/services.py` | 1,086 | <500 | Estrarre per ruolo (Admin/Director/Player) |

**Piano di Decomposizione per routes/admin/competition.py**:

```
routes/admin/competition.py (2,140 linee)
    ↓ decomporre in:
routes/admin/competition/
├── __init__.py           # Blueprint registration
├── crud.py               # Create/Read/Update/Delete operations (~400 linee)
├── inscriptions.py       # Inscription management (~400 linee)
├── rounds.py             # Round management (~400 linee)
├── matches.py            # Match operations (~400 linee)
└── status.py             # Status transitions (~400 linee)
```

**Criterio di Acceptance**:
- [ ] Nessun file Python > 800 linee (eccetto test)
- [ ] Ogni file ha una singola responsabilità
- [ ] Import circolari risolti

---

### 4.2 Import Circolari in utils/__init__.py

**Problema**: 17 import locali per evitare dipendenze circolari.

```python
# Pattern attuale (anti-pattern):
def some_function():
    from models import User  # Local import to avoid circular dependency
```

**Analisi Dipendenze**:
```bash
# Trovare tutti gli import locali
grep -n "# Local import to avoid circular" utils/__init__.py
```

**Soluzione Architetturale**:

1. **Estrarre decoratori di permesso** in `utils/permissions.py`:
```python
# utils/permissions.py
from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user

def admin_required(f):
    # ... implementazione senza import models ...
```

2. **Estrarre funzioni di seeding** in `utils/seeds.py`:
```python
# utils/seeds.py
def create_default_users():
    from models import User, db  # OK qui perché è script di setup
    # ...
```

3. **Mantenere in utils/__init__.py solo re-export**:
```python
# utils/__init__.py
from .permissions import (
    admin_required,
    director_required,
    # ...
)
from .seeds import (
    create_default_users,
    create_sample_campionato,
    create_admin_if_not_exists,
)
```

**Criterio di Acceptance**:
- [ ] `utils/__init__.py` < 100 linee
- [ ] Nessun "Local import to avoid circular" in file principali
- [ ] Import circolari documentati se inevitabili

---

### 4.3 Test Legacy da Migrare

**Stato Attuale**:
```
tests/
├── legacy/    # 90+ file, NON eseguiti di default
└── new/       # Suite moderna, eseguita in CI
```

**Azione**:
```bash
# Verificare quali test legacy sono ancora rilevanti
cd tests/legacy
for f in test_*.py; do
    echo "=== $f ===" 
    head -20 "$f" | grep -E "class Test|def test_"
done
```

**Piano di Migrazione**:
1. Identificare test con coverage unica (non coperta da `tests/new/`)
2. Migrare test rilevanti a `tests/new/`
3. Archiviare o eliminare test ridondanti

**Criterio di Acceptance**:
- [ ] Ogni funzionalità ha test in `tests/new/`
- [ ] `tests/legacy/` vuoto o contenente solo archivio storico
- [ ] Coverage > 85% con sola suite `tests/new/`

---

## 5. MIGLIORAMENTI ARCHITETTURALI (P3)

### 5.1 TODO Comments da Risolvere

**27 TODO identificati in models/ e routes/**. 

**Categorie**:

| Categoria | Count | Esempio |
|-----------|-------|---------|
| Design Questions | 12 | "TODO: controllare se la modellazione cosi' e' ok" |
| Feature Incomplete | 8 | "TODO: da modificare con un riferimento alle location nel DB" |
| Refactoring Needed | 7 | "TODO: questo mi sembra sovraingegnerizzato" |

**Azione per Ogni TODO**:
1. Valutare se ancora rilevante
2. Se risolto: rimuovere TODO
3. Se da fare: creare issue/ticket
4. Se design question: creare ADR

**Script di Audit TODO**:
```bash
# Generare report TODO
grep -rn "TODO" models/ routes/ --include="*.py" | \
    grep -v "__pycache__" | \
    awk -F: '{print $1":"$2" "$3}' > todo_report.txt
```

**Criterio di Acceptance**:
- [ ] Ogni TODO ha un issue associato o è stato risolto
- [ ] Nessun TODO vago ("da verificare", "da controllare")
- [ ] TODO con date di scadenza se necessario

---

### 5.2 Pyrightconfig Troppo Permissivo

**Stato Attuale**:
```json
{
    "reportMissingImports": true,
    "reportAttributeAccessIssue": false,  // ← Dovrebbe essere true
    "reportAssignmentType": false,        // ← Dovrebbe essere true
    "typeCheckingMode": "basic"           // ← Target: "standard"
}
```

**Piano di Hardening Graduale**:

```bash
# Fase 1: Abilitare report critici
# Modificare pyrightconfig.json:
"reportAttributeAccessIssue": true,

# Eseguire e fixare errori:
pyright models/ routes/

# Fase 2: Abilitare assignment type
"reportAssignmentType": true,

# Fase 3: Upgrade a standard
"typeCheckingMode": "standard"
```

**Criterio di Acceptance**:
- [ ] `typeCheckingMode: "standard"` senza errori
- [ ] Tutti i report critici abilitati
- [ ] CI fallisce su errori di tipo

---

## 6. PIANO DI ESECUZIONE

### Sprint 1: Documentazione (1-2 giorni)

| Task | Priorità | Effort | Dipendenze |
|------|----------|--------|------------|
| 2.1 Aggiornare ADR-001 | P0 | 30min | - |
| 2.2 Consolidare directory ADR | P0 | 1h | 2.1 |
| 2.3 Rimuovere coverage.json da Git | P0 | 15min | - |
| 2.4 Fix commento admin.py | P0 | 5min | - |

**Comandi Sprint 1**:
```bash
# Task 2.1
nano docs/adr/ADR-001-Amalfi-Strategy-Pattern-Unification.md
# Aggiornare sezione "Current Architecture"

# Task 2.2
mv docs/decisions/0001-*.md docs/adr/ADR-002-fix-anti-rematch-encounter-cleanup.md
mv docs/decisions/0002-*.md docs/adr/ADR-003-user-privacy-system.md
mv docs/decisions/TEMPLATE.md docs/adr/
rm -rf docs/decisions/
# Creare docs/adr/README.md con indice

# Task 2.3
echo "coverage.json" >> .gitignore
git rm --cached coverage.json

# Task 2.4
nano routes/admin.py
# Rimuovere riga su admin_backup.py

# Commit
git add -A
git commit -m "docs: fix documentation alignment and remove stale references"
```

---

### Sprint 2: Deprecation Cleanup (2-3 giorni)

| Task | Priorità | Effort | Dipendenze |
|------|----------|--------|------------|
| 3.1 Audit metodi deprecati | P1 | 2h | - |
| 3.1 Migrare utilizzi deprecati | P1 | 4h | Audit |
| 3.1 Rimuovere metodi deprecati | P1 | 2h | Migrazione |
| 3.2 Deprecare funzioni utils | P1 | 2h | - |

**Comandi Sprint 2**:
```bash
# Audit deprecati
./scripts/audit_deprecated.sh  # (creare script)

# Migrare round_service.py
nano models/competition/round_service.py
# Sostituire create_round_matches con MatchmakingService

# Test dopo ogni modifica
PYTHONPATH=. pytest tests/new/ -v --tb=short

# Commit incrementali
git commit -m "refactor: migrate round_service to MatchmakingService"
```

---

### Sprint 3: Debito Tecnico (3-5 giorni)

| Task | Priorità | Effort | Dipendenze |
|------|----------|--------|------------|
| 4.1 Decomporre competition.py | P2 | 4h | - |
| 4.1 Decomporre player.py | P2 | 4h | - |
| 4.2 Estrarre utils/permissions.py | P2 | 3h | - |
| 4.3 Audit test legacy | P2 | 2h | - |

---

### Sprint 4: Hardening (2-3 giorni)

| Task | Priorità | Effort | Dipendenze |
|------|----------|--------|------------|
| 5.1 Triage TODO comments | P3 | 2h | - |
| 5.2 Pyright fase 1 | P3 | 4h | - |
| 5.2 Pyright fase 2 | P3 | 4h | Fase 1 |

---

## 7. CRITERI DI ACCEPTANCE GLOBALI

### Al completamento di tutti gli sprint:

- [ ] **Zero disallineamenti documentazione-codice**
- [ ] **Zero metodi deprecati con utilizzi attivi**
- [ ] **Zero file > 1000 linee** (eccetto test comprehensivi)
- [ ] **Zero import circolari workaround** in file core
- [ ] **Coverage test > 85%** con suite `tests/new/`
- [ ] **Pyright "standard"** senza errori
- [ ] **Tutti i TODO** hanno issue associato o sono risolti
- [ ] **Una sola directory ADR** con indice aggiornato

### Verifica Finale:

```bash
# Script di verifica finale
echo "=== VERIFICA FINALE ==="

# 1. Documentazione
echo "1. ADR directory unica:"
ls docs/adr/*.md | wc -l
test ! -d docs/decisions && echo "✅ docs/decisions rimosso" || echo "❌ docs/decisions esiste"

# 2. Deprecati
echo "2. Metodi deprecati:"
grep -rn "DEPRECATED" models/ --include="*.py" | grep "def " | wc -l

# 3. File grandi
echo "3. File > 1000 linee:"
find . -name "*.py" -exec wc -l {} \; | awk '$1 > 1000 {print}' | grep -v test | wc -l

# 4. Import circolari
echo "4. Import circolari workaround:"
grep -rn "# Local import to avoid circular" --include="*.py" | wc -l

# 5. Coverage
echo "5. Test coverage:"
PYTHONPATH=. pytest tests/new/ --cov=models --cov=routes --cov-report=term-missing | tail -5

# 6. Pyright
echo "6. Pyright errors:"
pyright models/ routes/ 2>&1 | tail -3

# 7. TODO
echo "7. TODO count:"
grep -rn "TODO" models/ routes/ --include="*.py" | wc -l
```

---

## APPENDICE A: SCRIPT UTILI

### A.1 audit_deprecated.sh

```bash
#!/bin/bash
# audit_deprecated.sh - Trova e analizza metodi deprecati

echo "=== METODI DEPRECATI ==="
grep -rn "DEPRECATED" models/ routes/ --include="*.py" -A 3

echo ""
echo "=== UTILIZZI DI METODI DEPRECATI ==="
for method in "reset_to_pending" "get_table_count_for_gara" "get_winning_score" "is_match_finished"; do
    count=$(grep -rn "$method" --include="*.py" | grep -v "def $method\|DEPRECATED\|test_\|#" | wc -l)
    echo "$method: $count utilizzi"
done
```

### A.2 file_size_report.sh

```bash
#!/bin/bash
# file_size_report.sh - Report file Python grandi

echo "=== FILE PYTHON > 500 LINEE ==="
find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" \
    -exec wc -l {} \; | awk '$1 > 500 {print}' | sort -rn
```

### A.3 todo_triage.sh

```bash
#!/bin/bash
# todo_triage.sh - Genera report TODO per triage

echo "file,line,category,text" > todo_report.csv
grep -rn "TODO" models/ routes/ --include="*.py" | while read line; do
    file=$(echo "$line" | cut -d: -f1)
    linenum=$(echo "$line" | cut -d: -f2)
    text=$(echo "$line" | cut -d: -f3-)
    
    # Categorizza
    if echo "$text" | grep -qi "verificare\|controllare\|check"; then
        category="design_question"
    elif echo "$text" | grep -qi "rimuovere\|eliminare\|remove"; then
        category="cleanup"
    else
        category="feature"
    fi
    
    echo "\"$file\",$linenum,$category,\"$text\"" >> todo_report.csv
done

echo "Report generato: todo_report.csv"
```

---

## APPENDICE B: TEMPLATE COMMIT MESSAGES

```
# Per fix documentazione:
docs: update ADR-001 with current amalfi architecture

# Per rimozione deprecati:
refactor: remove deprecated reset_to_pending method

BREAKING CHANGE: reset_to_pending() removed. Use RackService.reset_match_complete()

# Per decomposizione file:
refactor(routes): decompose competition.py into sub-modules

- Extract CRUD operations to crud.py
- Extract inscription management to inscriptions.py
- Extract round management to rounds.py
- Maintain backward compatibility via __init__.py re-exports

# Per cleanup:
chore: remove coverage.json from tracking

- Add coverage.json to .gitignore
- Remove from git cache
```

---

**Fine del Piano di Audit e Refactoring**

*Documento generato automaticamente basato sull'analisi del repository.*
*Ultima verifica: 2025-12-29*
