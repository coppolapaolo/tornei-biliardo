# 🎯 Piano Strategico Refactoring - Prossimo Sviluppatore

**Data Creazione**: 2025-09-21
**Stato Attuale**: Phase 1 - Stabilization Starting
**Priorità**: Transaction Migration (Alto Impatto)

## 📊 Analisi Situazione Attuale

### ✅ Completato con Successo
- **UserService Decomposition**: 20.6% progresso - Facade Pattern implementato
  - 4 servizi estratti e operativi (1374 linee totali)
  - 141 linee rimosse dal main service (1304→1163)
  - 133 test TDD passano tutti ✅
  - Backward compatibility mantenuta

- **Transaction Migration**: 39.5% progresso - Pattern @transactional stabilito
  - ✅ **MatchServices**: 13/14 commits migrated (1 excluded per custom logic)
  - ✅ **ExamServices**: 10/10 commits migrated
  - ✅ **PlayoffServices**: 9/9 commits migrated
  - 70 total commit calls migrated su 177 (39.5%)
  - Pattern documentato e test stabilizzati

### 🎯 Priorità Strategiche (Ordine di Impatto)

## 🥇 **PRIORITÀ 1: Transaction Migration (Raccomandato)**

### Perché questa priorità?
1. **Alto Impatto Architetturale**: 107 commit calls rimanenti in 30 file
2. **Fondamenta Solide**: Pattern @transactional già testato e funzionante
3. **Riduzione Rischio**: Eliminare transazioni manuali inconsistenti
4. **Preparazione**: Facilita tutti i refactoring successivi

### File High-Priority Rimanenti (24 commit calls totali)
1. **routes/player.py**: 9 commits (nuovo highest priority)
2. **models/base.py**: 8 commits
3. **models/campionato/services.py**: 7 commits

### Approccio Strategico
**Stima Tempo**: 4-6 ore per i 3 file priority
**ROI**: Alto - pattern già rodato, basso rischio

#### Step 1: MatchService (14 commits - 2 ore)
```bash
# Preparazione
PYTHONPATH=. pytest tests/new/unit/test_match_*.py -v -n auto

# Pattern da seguire (già testato):
from models.transaction.manager import transactional, read_only

# Sostituire:
db.session.commit()
# Con:
@transactional(domain="match")
```

#### Step 2: ExamService (10 commits - 1.5 ore)
```bash
# Stesso pattern, file più piccolo
PYTHONPATH=. pytest tests/new/unit/test_exam_*.py -v -n auto
```

#### Step 3: PlayoffService (9 commits - 1.5 ore)
```bash
# Completamento high-priority files
PYTHONPATH=. pytest tests/new/unit/test_playoff_*.py -v -n auto
```

### Benefici Immediati
- **33/139 commit calls eliminati** (24% del totale)
- **Pattern consolidato** per altri 29 file rimanenti
- **Architettura più robusta** per refactoring successivi

---

## 🥈 **PRIORITÀ 2: Completare UserService (Solo se tempo extra)**

### Situazione
- **Attuale**: 1163 linee (target: 500)
- **Rimanente**: 663 linee da rimuovere
- **Complessità**: Media (rimuovere classi duplicate)

### Quick Wins (1-2 ore)
1. **Rimuovere DirectorRequestService duplicato**: ~60 linee
2. **Rimuovere VenueManagerRequestService duplicato**: ~200 linee
3. **Rimuovere VenueManagementService duplicato**: ~150 linee

```bash
# Test prima di iniziare
PYTHONPATH=. pytest tests/new/refactor/tdd/ -v -n auto

# Pattern: commentare e delegare, non cancellare
# Esempio:
# class DirectorRequestService:  # REMOVED - use UserPermissionService
```

---

## 🥉 **PRIORITÀ 3: GaraService (Future Sprint)**

### Situazione
- **Attuale**: 1286 linee (target: 500)
- **Servizi estratti**: StateService, InscriptionService, RoundService
- **Complessità**: Alta (business logic complessa)

### NON raccomandato per ora
- File molto grande e complesso
- Richiede deep understanding del tournament logic
- Transaction migration deve essere completato prima

---

## 🛠️ Comando Quick Start

```bash
# Setup ambiente
cd "/Users/paolo/My Drive/Programming/Python/tornei-biliardo"
source venv/bin/activate

# Verificare stato
python scripts/refactor_progress.py

# Test baseline
PYTHONPATH=. pytest tests/new/ -n auto --tb=short

# Iniziare con MatchService
git checkout -b refactor/transaction-migration-match-service
```

## 📋 Checklist Pre-Refactoring

### Prima di Iniziare
- [ ] `python scripts/refactor_progress.py` mostra stato corretto
- [ ] `PYTHONPATH=. pytest tests/new/ -n auto` passa (baseline)
- [ ] `pyright` mostra 0 errori
- [ ] Branch feature creato

### Durante Refactoring
- [ ] Test passano dopo ogni file completato
- [ ] Commit incrementali ogni 5-10 metodi migrati
- [ ] `python scripts/refactor_progress.py` mostra progresso
- [ ] Documentare edge cases o problemi trovati

### Dopo Completamento
- [ ] Tutti i test passano: `PYTHONPATH=. pytest tests/new/ -n auto`
- [ ] Progresso verificato: target 33 commit calls rimossi
- [ ] Documentazione aggiornata in `REFACTOR_PROGRESS.md`
- [ ] PR creato con summary progressi

## 🚨 Attenzioni Critiche

### DO
✅ **Seguire pattern esistente** - UserService migration è esempio perfetto
✅ **Test-first approach** - test devono passare sempre
✅ **Commit incrementali** - non big bang changes
✅ **Usare `PYTHONPATH=. pytest -n auto`** - sempre

### DON'T
❌ **Non toccare GaraService** - troppo complesso per ora
❌ **Non cancellare codice** - commentare e delegare
❌ **Non cambiare signature metodi** - solo decoratori
❌ **Non skip test failure** - risolvere sempre

## 📊 Success Metrics

### Target Session (4-6 ore)
- **Transaction Migration**: da 21.5% → ~45% (+24%)
- **Commit calls rimanenti**: da 139 → ~106 (-33)
- **File completati**: 3 high-priority
- **Fondamenta**: Pattern consolidato per sprint futuri

### Long-term Vision
1. **Phase 1 Completion**: Transaction Migration 100% (Sprint 2-3)
2. **Phase 1 Completion**: Service Decomposition 100% (Sprint 3-4)
3. **Phase 2 Start**: Event System & Notification Factory (Sprint 5+)

---

## 🔄 Progress Tracking

Usare sempre:
```bash
python scripts/refactor_progress.py
```

Aggiornare `REFACTOR_PROGRESS.md` dopo ogni milestone.

## 📞 Support

- **Test Failures**: `PYTHONPATH=. pytest path/to/failing/test.py -v -s`
- **Import Errors**: Verificare pattern in UserService completato
- **Transaction Issues**: Riferimento in `models/transaction/manager.py`

---

**🎯 FOCUS: Transaction Migration è la priorità assoluta per consolidare le fondamenta architetturali.**

**Risultato atteso**: Codebase più robusto e preparato per refactoring Phase 2.