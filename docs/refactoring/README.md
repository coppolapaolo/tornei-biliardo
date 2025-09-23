# Refactoring Documentation

Questa directory contiene tutta la documentazione relativa al refactoring sistemico del progetto tornei-biliardo.

## Stato Attuale

**✅ REFACTORING ATTIVO - Transaction Migration in corso**

Il refactoring è attualmente attivo con **Task 1.1: Transaction Management** al 39.5% di completamento. Tutti i test di base sono stabili e il pattern @transactional è stato stabilito con successo.

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

### 4. Service Extraction Safety Protocol ⚠️
**CRITICO**: Per evitare errori durante l'estrazione di servizi, seguire SEMPRE questo protocollo:

#### Pre-Extraction Checklist
1. **Analisi Completa delle Dipendenze**:
   - Identificare TUTTE le dipendenze cross-domain (notifications, logging, caching, etc.)
   - Controllare imports interni e pattern nascosti
   - Verificare chiamate a servizi esterni (NotificationService, etc.)

2. **Behavioral Analysis**:
   - Leggere TUTTO il codice del metodo originale, non solo la logica principale
   - Identificare side effects (notifiche, audit, cleanup, etc.)
   - Documentare comportamenti impliciti

#### During Extraction
3. **Complete Functional Equivalence**:
   - ✅ Copiare TUTTA la logica, inclusi side effects
   - ✅ Mantenere TUTTI gli imports necessari
   - ✅ Preservare la stessa signature e contract
   - ❌ MAI omettere "dettagli secondari" come notifiche

4. **Immediate Testing**:
   - Testare SUBITO dopo l'estrazione con test esistenti
   - Verificare che nessun test fallisca
   - Se test falliscono, analizzare specs in `docs/` per capire cosa è corretto

#### Post-Extraction Verification
5. **Comprehensive Testing**:
   - Eseguire TUTTI i test che usano il servizio estratto
   - Verificare integration tests e use case tests
   - Controllare che i side effects funzionino (es. notifiche arrivino)

6. **Documentation Update**:
   - Aggiornare documentazione del servizio estratto
   - Documentare eventuali breaking changes
   - Aggiornare imports nei test se necessario

#### Lesson Learned (September 2025)
**Errore Critico Evitato**: Durante l'estrazione di VenueManagerService, la logica delle notifiche fu omessa nell'implementazione estratta, causando test failures. L'errore fu corretto analizzando le specifiche e confrontando implementazione originale vs estratta.

**Regola d'Oro**: **SEMPRE verificare behavioral equivalence PRIMA di rimuovere implementazioni originali.**

## Documenti

### [REFACTOR_PROGRESS.md](./REFACTOR_PROGRESS.md)
Documentazione completa dello stato del refactoring:
- Task 1.1: Transaction Management Migration (IN CORSO)
- Task 1.2: GaraService Decomposition (COMPLETATO)
- Statistiche dei commit calls migrati
- Strategia e pianificazione delle fasi successive


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

## Prossimi Passi per Futuri Sviluppatori

1. **PRIMA DI TUTTO**: Verificare che `PYTHONPATH=. pytest tests/new/` passi al 100%
2. **Se ci sono failures**: Seguire la metodologia sistematica per risolverli
3. **Solo dopo test verdi**: Riprendere il refactoring da Task 1.1 dove era stato interrotto
4. **Per ogni modifica**: Mantenere sempre i test verdi

## Contesto del Progetto

Questo refactoring fa parte di un progetto più ampio di modernizzazione della codebase:
- Implementazione di transaction management distribuito
- Decomposizione di servizi monolitici
- Miglioramento dell'architettura Domain-Driven Design
- Eliminazione di accoppiamenti stretti

**Ricorda**: La qualità del codice e la stabilità dei test hanno sempre la priorità sulla velocità di implementazione.