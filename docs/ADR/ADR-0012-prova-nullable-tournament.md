# ADR-0012: FK Nullable invece di Entità Separate per Competizioni Standalone

Data: 2025-08-06

## Stato
Accettato

## Contesto
ADR-0009 proponeva di creare entità separate (`StandaloneCompetition`, `FriendlyMatch`) per supportare eventi non legati a tornei. Tuttavia, un'analisi più approfondita del design OO ha rivelato che rendere `tournament_id` nullable in `Prova` è una soluzione superiore.

Il database non è in produzione e possiamo fare reset completo, eliminando l'unico ostacolo tecnico.

## Decisione
Modificare il modello `Prova` rendendo `tournament_id` nullable invece di creare nuove entità. Questo permette di:
- Riutilizzare tutto il codice esistente
- Mantenere un singolo modello per tutte le competizioni
- Rispettare i principi DRY e SOLID
- Semplificare drasticamente l'implementazione

## Implementazione
1. **Modello Prova**:
   - `tournament_id` diventa nullable
   - Aggiunta property `is_standalone` 
   - Aggiunta method `get_organizer()`
   - Aggiunta FK `director_id` per standalone

2. **Reset Database**:
   - Aggiornamento script reset per nuovo schema
   - Nessuna migrazione necessaria

3. **UI/UX**:
   - Director può creare Prova scegliendo torneo o standalone
   - Stesse UI per gestione, solo con logica condizionale

## Conseguenze

### Positive
+ **Zero duplicazione**: Un solo modello invece di due
+ **Semplicità**: Nessuna gerarchia complessa
+ **Riuso totale**: Tutti i service/UI esistenti funzionano
+ **Manutenibilità**: Un posto solo per modifiche future
+ **Testing semplificato**: Stessi test per entrambi i casi

### Negative
- Necessità di reset DB (ma non è un problema)
- Campo nullable aggiunge minima complessità condizionale

## Alternative Scartate
1. **Entità separate** (ADR-0009): Duplicazione non necessaria
2. **Ereditarietà**: Complessità senza benefici
3. **Composizione**: Over-engineering per questo caso

## Note
Questo ADR sostituisce parzialmente ADR-0009 per quanto riguarda `StandaloneCompetition`. La decisione su `FriendlyMatch` rimane da valutare separatamente nello Sprint 3.