# ⚡ Quick Start - Prossimo Sviluppatore

## 🚀 Setup Immediato (2 minuti)

```bash
# 1. Posizionamento
cd "/Users/paolo/My Drive/Programming/Python/tornei-biliardo"
source venv/bin/activate

# 2. Verifica stato
python scripts/refactor_progress.py

# 3. Test baseline
PYTHONPATH=. pytest tests/new/ -n auto --tb=short

# 4. Verifica type safety
pyright
```

## 🎯 Prossimo Task: Transaction Migration

### Branch Setup
```bash
git checkout -b refactor/transaction-migration-match-service
```

### File Target (Ordine priorità)
1. **models/match/services.py** - 14 commit calls (2 ore)
2. **models/exam/services.py** - 10 commit calls (1.5 ore)
3. **models/playoff/services.py** - 9 commit calls (1.5 ore)

### Pattern da Seguire
```python
# PRIMA:
def some_method(self, ...):
    # business logic
    db.session.commit()
    return result

# DOPO:
@transactional(domain="match")  # o "exam", "playoff"
def some_method(self, ...):
    # business logic (STESSO)
    # NO MORE: db.session.commit()
    return result
```

### Import Necessario
```python
from models.transaction.manager import transactional, read_only
```

## ✅ Success Check

Dopo ogni file:
```bash
# Test specifico
PYTHONPATH=. pytest tests/new/unit/test_match_*.py -v -n auto

# Progresso
python scripts/refactor_progress.py

# Commit
git add . && git commit -m "refactor: migrate MatchService to @transactional pattern"
```

## 📊 Target Session
- **Goal**: 33 commit calls rimossi (match + exam + playoff)
- **Progress**: 21.5% → ~45%
- **Time**: 4-6 ore
- **ROI**: Fondamenta architetturali consolidate

## 🆘 Troubleshooting

### Test Failures
```bash
PYTHONPATH=. pytest path/to/failing/test.py -v -s
```

### Import Errors
Controllare che gli import seguano il pattern UserService (già funzionante).

### Progress Check
```bash
python scripts/refactor_progress.py | grep "Transaction Migration"
```

## 📚 Riferimenti
- **Piano Completo**: `docs/refactoring/NEXT_DEVELOPER_PLAN.md`
- **Progresso**: `docs/refactoring/REFACTOR_PROGRESS.md`
- **Pattern Esempio**: `models/user/services.py` (facade implementato)

---

**🎯 FOCUS: 3 file, pattern semplice, alto impatto architetturale.**