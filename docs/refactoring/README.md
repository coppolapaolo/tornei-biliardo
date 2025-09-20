# Refactoring Documentation

Questa directory contiene tutta la documentazione relativa al refactoring sistemico del progetto tornei-biliardo.

## Stato Attuale

**✅ PROGRESSO AVANZATO: Task 1.1 Fase 8 - models/base.py Migration**

Il refactoring procede sistematicamente con la migrazione da `db.session.commit()` diretti a pattern `@transactional`:
- **Fase 7 COMPLETATA**: routes/player.py (9→0 commit calls) ✅
- **Fase 8 IN CORSO**: models/base.py (8 commit calls target) ⏳
- **Test Status**: 566/566 test passano (100%) ✅

## Principi Fondamentali

### 1. Test-First Policy
- **TUTTI I TEST DEVONO PASSARE** prima di iniziare qualsiasi refactoring
- Dopo ogni step di refactoring, **TUTTI I TEST DEVONO CONTINUARE A PASSARE**
- Mai modificare il codice senza verificare che i test rimangano verdi

### 2. Metodologia Sistematica
Il refactoring segue un approccio TDD rigoroso:
1. **Analisi**: Comprendere le specifiche in `docs/` prima di scrivere codice
2. **Implementazione**: Scrivere codice seguendo i principi di buona programmazione
3. **Quality Gates**: Applicare sempre `black` e `pyright` ai file `.py`
4. **Testing**: Eseguire tutti i test e verificare che passino
5. **Fix Test Issues**: Se i test falliscono, analizzare se è un problema di test fragile o un vero bug

### 3. Priorità di Correzione Errori
Quando si incontrano test che falliscono:
1. Applicare `pyright` per correggere errori di tipo
2. Analizzare se l'errore è nel test (nomi sbagliati, sovraingegnerizzazione) o nel codice
3. Solo se il test è corretto, modificare il codice
4. Applicare `black` e `pyright` ai file modificati

## Documenti

### [REFACTOR_PROGRESS.md](./REFACTOR_PROGRESS.md)
Documentazione completa dello stato del refactoring:
- **Task 1.1**: Transaction Management Migration - Fase 8/N (route/player.py completata, models/base.py in corso)
- **Task 1.2**: GaraService Decomposition - COMPLETATO ✅
- **Milestone Raggiunto**: 59 commit calls migrati su 177 totali (33% completamento)
- Strategia sistematica per file ad alto impatto

### [REFACTOR_PLAN_ROUND_EXTRACTION.md](./REFACTOR_PLAN_ROUND_EXTRACTION.md)
Piano specifico per l'estrazione del RoundService:
- Estrazione logica dei round da GaraService
- Separazione delle responsabilità tra servizi
- Refactoring delle dipendenze e dei test

## Comando per Test

```bash
# Test completo (DEVE passare al 100% prima di continuare)
PYTHONPATH=. pytest tests/new/

# Test con coverage
PYTHONPATH=. pytest tests/new/ --cov --cov-report=term-missing

# Test specifici
PYTHONPATH=. pytest tests/new/unit/ -v
PYTHONPATH=. pytest tests/new/integration/ -v
```

## Stato Attuale e Prossimi Passi

### Completato Recentemente
- **Fase 7**: routes/player.py migrazione completa (9→0 commit calls)
- **Strategia dual-layer**: Service extraction + @transactional decorators
- **Metodi aggiunti**: MatchProposalService.accept_invitation/reject_invitation
- **Test stability**: 566/566 test passano con isolamento risolto

### Fase 8 - models/base.py (IN CORSO)
Target: 8 commit calls in UtilityMixin, ValidationMixin, e utility functions
- **Approccio conservativo**: Aggiungere varianti transactional, mantenere compatibilità
- **Metodi target**: save(), delete(), save_with_validation(), get_or_create(), bulk_create()

### Prossimi Passi
1. **Completare Fase 8**: models/base.py migration con backward compatibility
2. **Candidati Fase 9**: routes/admin/competitions.py (6 commit calls)
3. **Obiettivo**: Raggiungere 50% completion milestone (88+ commit calls migrati)

## Contesto del Progetto

Questo refactoring fa parte di un progetto più ampio di modernizzazione della codebase:
- Implementazione di transaction management distribuito
- Decomposizione di servizi monolitici
- Miglioramento dell'architettura Domain-Driven Design
- Eliminazione di accoppiamenti stretti

**Ricorda**: La qualità del codice e la stabilità dei test hanno sempre la priorità sulla velocità di implementazione.