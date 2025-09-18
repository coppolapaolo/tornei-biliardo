# Refactoring Documentation

Questa directory contiene tutta la documentazione relativa al refactoring sistemico del progetto tornei-biliardo.

## Stato Attuale

**⚠️ IMPORTANTE: IL REFACTORING È SOSPESO**

Prima di continuare con qualsiasi attività di refactoring, è **OBBLIGATORIO** che tutti i test passino al 100%. Attualmente ci sono test che falliscono che devono essere risolti prima di procedere.

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