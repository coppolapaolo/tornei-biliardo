# ADR-0010: Domain Separation Phase 2 Sprint 1

Data: 2025-08-05

## Stato
In Progress

## Contesto
Dopo il successo della Fase 1 con la separazione del dominio User, procediamo con la Fase 2 usando approccio Agile con sprint settimanali. Il file `models/legacy_models.py` contiene 800+ righe con 12+ modelli mischiati.

## Decisione
Sprint 1 (1 settimana) - Domain separation pura:
1. Separare Tournament → `models/tournament/`
2. Separare Prova, Inscription → `models/competition/`
3. Separare Match, Rack, MatchResult, TrioMatch → `models/match/`
4. Separare Classification, RoundClassification, PlayerEncounter → `models/classification/`
5. Mantenere 100% backward compatibility
6. NON aggiungere nuove features in questo sprint

## Implementazione
- Iniziamo con Tournament come proof of concept
- Ogni dominio segue struttura: `__init__.py`, `models.py`, `services.py`
- Import aliases in `models/__init__.py` per backward compatibility
- Test suite per verificare che nulla si rompa

## Conseguenze
### Positive
+ Separazione chiara delle responsabilità
+ Foundation per future features (StandaloneCompetition, FriendlyMatch)
+ Codice più manutenibile e testabile
+ Nessun breaking change

### Negative
- Temporanea duplicazione di import
- Complessità durante la transizione
- Necessità di aggiornare documentazione

## Alternative Considerate
1. **Big-bang refactoring**: Troppo rischioso
2. **Feature-first approach**: Violerebbe principio di refactoring puro
3. **Mantenere monolite**: Technical debt insostenibile