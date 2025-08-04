# ADR-0008: Rimozione utils.py Duplicato

Data: 2025-08-04

## Stato
Implementato

## Contesto
Durante la review finale della Fase 1, è emerso che esistevano sia `utils.py` che `utils/__init__.py` con contenuto identico. Questa duplicazione:
- Violava il pattern stabilito in ADR-0007 per models
- Creava confusione su quale file fosse il punto di ingresso
- Richiedeva manutenzione duplicata

## Decisione
Rimuovere `utils.py` e mantenere solo `utils/__init__.py`, seguendo lo stesso pattern applicato ai models in ADR-0007.

## Implementazione
1. Verificato che `utils/__init__.py` contenesse tutto il codice di `utils.py`
2. Testato che tutti gli import funzionassero prima della rimozione
3. Rimosso `utils.py`
4. Verificato che tutti gli import continuassero a funzionare
5. Nessuna modifica al codice richiesta

## Conseguenze
### Positive
+ **Coerenza architetturale**: Stesso pattern di models
+ **Singolo punto di manutenzione**: Eliminata duplicazione
+ **Supporto submodules**: `utils.reset_data` già funzionante
+ **Zero breaking changes**: 100% backward compatible

### Negative
- Nessuna

## Alternative Considerate
1. **Mantenere utils.py**: Avrebbe perpetuato l'inconsistenza
2. **Modularizzare tutto**: Avrebbe richiesto refactor di tutti gli import (breaking change)

## Validazione
- ✅ Tutti i test passano
- ✅ Import `from utils import X` funzionano
- ✅ Import `from utils.reset_data import Y` funzionano
- ✅ Applicazione funzionante