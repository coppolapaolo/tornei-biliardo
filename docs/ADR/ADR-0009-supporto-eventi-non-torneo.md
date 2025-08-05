# ADR-0009: Supporto per Eventi Non-Torneo e Approccio Agile

Data: 2025-08-05

## Stato
Accettato

## Contesto
L'architettura attuale richiede che ogni Prova appartenga a un Tournament (FK non nullable) e ogni Match appartenga a una Prova. Questo impedisce:
- Director di organizzare prove singole fuori da tornei
- Player di organizzare match amichevoli

Inoltre, il piano Fase 2 era troppo waterfall con stime rigide.

## Decisione
1. **Implementare entità separate** per eventi non-torneo:
   - `StandaloneCompetition`: Competizione organizzata da Director senza torneo
   - `FriendlyMatch`: Match amichevole organizzato da Player
   
2. **Adottare approccio Agile** con sprint settimanali:
   - Sprint 1: Refactoring puro (domain separation)
   - Sprint 2: StandaloneCompetition
   - Sprint 3: FriendlyMatch
   - Dettagli (stats, privacy) decisi just-in-time

3. **Mantenere modelli esistenti** per backward compatibility

## Conseguenze
### Positive
+ Flessibilità per eventi al di fuori di tornei strutturati
+ Nessun breaking change
+ Rilasci incrementali con feedback rapido
+ Possibilità di pivot basato su feedback utenti

### Negative
- Complessità aggiuntiva nel domain model
- Possibile duplicazione di logica (mitigabile con services condivisi)
- Refactoring futuro possibile se requisiti cambiano

## Alternative Considerate
1. **FK nullable**: Breaking change, migrazione database complessa
2. **Tournament virtuali**: Workaround non elegante
3. **Mantenere vincolo**: Limitante per utenti
4. **Big-bang refactoring**: Rischioso, lungo time-to-market