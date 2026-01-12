# [007] Revisione Gestione SSR (Spot Shot Rally)

**Data**: 2026-01-12
**Stato**: Accepted
**Decisori**: Paolo Coppola, Claude Code

## Contesto

Il sistema SSR (Spot Shot Rally) esistente per la risoluzione dei parimerito presentava diversi problemi:

1. **Visualizzazione**: I punteggi SSR erano visibili solo nella classifica campionato, non nella classifica della singola gara
2. **Gestibilità**: Non esisteva una sezione dedicata nella vista gara per inserire/modificare i punteggi SSR
3. **Workflow confuso**: Il pulsante "Termina Gara" apriva un modal per SSR, mescolando due operazioni diverse
4. **Validazione errata**: I punteggi SSR dovevano essere globalmente unici, ma in realtà gruppi di parimerito diversi (es. 1°/2° e 3°/4°) sono indipendenti
5. **Configurazione nascosta**: I campi `tiebreaker_enabled` e `tiebreaker_until_position` esistevano nel model ma non erano esposti nei form

## Decisione

Abbiamo implementato una revisione completa della gestione SSR con:

### 1. Nuovo Stato Gara: AWAITING_SSR

Aggiunto stato intermedio `GaraStatus.AWAITING_SSR` tra `PLAYING` e `COMPLETED` per rendere esplicita la fase di spareggio.

Transizioni:
- `PLAYING` → `AWAITING_SSR`: quando tutti i turni sono completi e ci sono parimerito da risolvere
- `AWAITING_SSR` → `COMPLETED`: dopo che tutti gli spareggi sono stati risolti

### 2. Workflow UI Migliorato

- **Pulsante "Avvia SSR"**: appare quando turni completati + parimerito nei primi 3 posti
- **Sezione SSR visibile**: nella vista gara, sotto le partite, sempre visibile quando ci sono dati SSR
- **Pulsante "Termina Gara"**: appare solo quando tutti gli spareggi sono risolti

### 3. Validazione per Gruppo

I punteggi SSR sono ora validati per gruppo separato:
- Parimerito 1°/2°: validazione interna al gruppo
- Parimerito 3°/4°: validazione indipendente
- I punteggi possono essere uguali tra gruppi diversi

### 4. Configurazione SSR nei Form

Aggiunti campi nei form di creazione/modifica gara:
- `tiebreaker_enabled`: checkbox per abilitare SSR
- `tiebreaker_until_position`: select per definire fino a quale posizione richiedere spareggio (1, 2, o 3)

### 5. Colonna SSR in Classifica

Aggiunta colonna SSR nella tabella classifica gara per mostrare i punteggi inseriti.

## Alternative Considerate

### Alternativa 1: Mantenere Modal SSR alla Terminazione

**Descrizione**: Continuare a gestire SSR nel modal di terminazione gara

- **Pro**:
  - Nessuna modifica al flusso esistente
  - Meno codice da modificare
- **Contro**:
  - Confusione tra operazioni diverse (terminazione vs spareggio)
  - Impossibile modificare punteggi dopo primo inserimento
  - Non visibile nella classifica gara

### Alternativa 2: SSR come Entità Separata

**Descrizione**: Creare tabella separata per gestire rounds di spareggio

- **Pro**:
  - Maggiore flessibilità (supporto per rounds multipli)
  - Storico completo degli spareggi
- **Contro**:
  - Complessità aggiuntiva non necessaria per il caso d'uso attuale
  - Richiede migrazioni database significative
  - Over-engineering per il flusso attuale

## Conseguenze

### Positive

- **Trasparenza**: I punteggi SSR sono visibili nella classifica gara
- **Workflow chiaro**: Separazione netta tra fase partite e fase spareggio
- **Modificabilità**: Admin/director possono correggere errori nei punteggi SSR
- **Validazione corretta**: Gruppi di parimerito indipendenti validati separatamente
- **Configurabilità**: SSR configurabile per ogni gara

### Negative

- Aggiunto nuovo stato gara da gestire
- Logica di transizione più complessa

### Rischi

- Gare esistenti con SSR inserito potrebbero avere dati nel formato vecchio (mitigato: backward compatible)

## Note Implementative

### File Modificati

- `models/status_enum.py`: Aggiunto `AWAITING_SSR`
- `models/competition/state_service.py`: Nuove transizioni `start_ssr()`, modificato `complete()`
- `models/competition/spareggio_service.py`: Nuovi metodi per validazione e salvataggio per gruppo
- `routes/admin/competition/rounds.py`: Nuovi endpoint `/start_ssr`, `/save_ssr_group`
- `routes/admin/competition/detail.py`: Passaggio dati SSR al template
- `routes/admin/competition/crud.py`: Gestione campi tiebreaker nei form
- `templates/gara_detail.html`: Sezione SSR con editing inline
- `templates/components/_gara_management.html`: Pulsanti workflow SSR
- `templates/components/_detailed_classification.html`: Colonna SSR
- `templates/components/_gara_edit_form.html`: Configurazione SSR
- `templates/admin/gara_create_standalone.html`: Configurazione SSR nel wizard

### Esempio di Utilizzo

```python
from models.competition.state_service import StateService
from models.competition.spareggio_service import SpareggioService

# Avvia fase SSR quando turni completati
gara = StateService.start_ssr(gara)  # PLAYING → AWAITING_SSR

# Ottieni gruppi di parimerito
groups = SpareggioService.get_all_ssr_groups(gara_id)
# [{'position': 1, 'rack_totali': 15, 'players': [...]}, ...]

# Salva punteggi per un gruppo
scores = {user_id_1: 8, user_id_2: 5}
success, message = SpareggioService.save_ssr_scores_for_group(
    gara_id, group_position=1, scores=scores
)

# Termina gara (ora accetta sia PLAYING che AWAITING_SSR)
gara = StateService.complete(gara)
```

## Bug Fix Post-Implementazione

### 1. Template Syntax Error in _gara_management.html
- **Problema**: `{% elif %}` orfano causava errore Jinja2 "Encountered unknown tag 'elif'"
- **Causa**: `{% endif %}` extra chiudeva prematuramente il blocco if/elif principale
- **Fix**: Rimosso endif extra, aggiunto endif finale per chiudere correttamente la catena

### 2. SSR Section Width in gara_detail.html
- **Problema**: Sezione SSR occupava tutta la larghezza invece di stare sotto "Partite"
- **Fix**: Spostata sezione SSR dentro `col-md-8` (stessa colonna delle partite)

### 3. Case-Sensitivity Bug in campionato/services.py
- **Problema**: Confronto `campionato_type == "Random"` falliva perché DB contiene `"random"`
- **Fix**: Uso di `MatchmakingStrategy.RANDOM.value` invece di stringhe letterali

### 4. SSR non visibile in classifica campionato
- **Problema**: Punti SSR non mostrati nella classifica generale del campionato
- **Causa**: Bug case-sensitivity sopra (punto 3)
- **Fix**: Corretto confronto enum

### 5. SSR non visibile nella vista guest (homepage)
- **Problema**: Classifica Top 5 non mostrava punti SSR
- **Fix**: Aggiunto badge SSR in `_index_campionato_cards.html`

### 6. Gare completate non visibili nella card campionato
- **Problema**: Solo gare future mostrate, non quelle giocate
- **Fix**: Aggiunta sezione "Gare Giocate" con link ai dettagli in `routes/main.py` e template

## Riferimenti

- File correlati: `models/competition/spareggio_service.py`
- Documentazione correlata: `docs/usecases/gare.md`
