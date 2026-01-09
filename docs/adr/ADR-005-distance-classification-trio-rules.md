# [005] Regole Distanza, Classifica e Trio

**Data**: 2026-01-08
**Stato**: Accepted
**Decisori**: Paolo, Claude

## Contesto

Il sistema supporta diverse configurazioni per le gare:
- **Distanza**: "Race to N" (primo a N rack) o "Exactly N" (esattamente N rack)
- **Classifica**: basata su vittorie match o su rack vinti
- **Gestione dispari**: Bye (un giocatore salta) o Trio (3 giocatori insieme)
- **Matchmaking**: Random, Amalfi, Round-Robin, Eliminazione diretta

Queste opzioni non sono tutte combinabili liberamente. Alcune combinazioni non hanno senso logico o creano svantaggi per alcuni giocatori.

### Problema Principale

1. Se la classifica conta solo i **rack vinti** (non le vittorie):
   - "Race to N" non ha senso: il vincitore avrebbe sempre N rack, il perdente meno
   - I pareggi sono possibili e validi
   - Il trio è possibile perché non serve un vincitore

2. Se la classifica conta le **vittorie match**:
   - Serve sempre un vincitore
   - "Race to N" ha senso
   - Il trio NON è possibile (3 giocatori → chi vince?)

3. Il **trio** deve garantire equità rispetto ai match normali:
   - Un giocatore nel trio non deve essere svantaggiato in classifica
   - Il numero massimo di rack ottenibili deve essere uguale

## Decisione

### 1. Matrice di Compatibilità

| Tipo Classifica | Distanze Valide | Multi-set | Pareggi | Trio |
|-----------------|-----------------|-----------|---------|------|
| **Rack vinti** | Solo "Exactly N" | No | Sì | Sì (se 2≤N≤5) |
| **Vittorie match** | "Race to N", "Exactly N" | Sì | No | No |

### 2. Vincoli per Matchmaking

| Matchmaking | Richiede Vincitore | Classifica Compatibile | Trio Compatibile |
|-------------|-------------------|------------------------|------------------|
| **Eliminazione** | Sì | Solo vittorie | No |
| **Random** | No | Entrambe | Sì (se rack-based) |
| **Amalfi** | Dipende | Entrambe | Dipende |
| **Round-Robin** | Dipende | Entrambe | Dipende |

### 3. Regole Trio per Distanza

Il trio funziona come **mini-torneo all'italiana** tra 3 giocatori:
- Mentre 2 giocano un rack, il terzo aspetta
- In un "girone" ci sono 3 match: P1vsP2, P1vsP3, P2vsP3
- Ogni giocatore gioca 2 rack per girone (max 2 rack vincibili)

Per garantire equità con i match normali, si aggiunge un **bonus rack**:

| Distanza | Trio Possibile | N. Gironi | Bonus | Max Rack Trio | Max Rack Normale |
|----------|---------------|-----------|-------|---------------|------------------|
| 1 | ❌ No | - | - | - | 1 |
| 2 | ✅ Sì | 1 | 0 | 2 | 2 |
| 3 | ✅ Sì | 1 | +1 | 2+1=3 | 3 |
| 4 | ✅ Sì | 2 | 0 | 4 | 4 |
| 5 | ✅ Sì | 2 | +1 | 4+1=5 | 5 |
| >5 | ❌ No | troppi gironi | - | - | - |

**Formula**:
- Gironi = ceil((distanza - 1) / 2)
- Bonus = distanza mod 2 (1 se dispari, 0 se pari)
- Max rack trio = (Gironi × 2) + Bonus

### 4. Struttura Rack nel Trio

Per distanza N, il trio gioca i seguenti rack:

**Distanza 2 (1 girone, 0 bonus):**
```
Rack 1: P1 vs P2 (P3 aspetta)
Rack 2: P1 vs P3 (P2 aspetta)
Rack 3: P2 vs P3 (P1 aspetta)
```

**Distanza 3 (1 girone, 1 bonus):**
```
Rack 1: P1 vs P2 (P3 aspetta)
Rack 2: P1 vs P3 (P2 aspetta)
Rack 3: P2 vs P3 (P1 aspetta)
Rack 4 (bonus): assegnato a tutti e 3
```

**Distanza 4 (2 gironi, 0 bonus):**
```
Girone 1:
  Rack 1: P1 vs P2
  Rack 2: P1 vs P3
  Rack 3: P2 vs P3
Girone 2:
  Rack 4: P1 vs P2
  Rack 5: P1 vs P3
  Rack 6: P2 vs P3
```

**Distanza 5 (2 gironi, 1 bonus):**
```
Girone 1: 3 rack
Girone 2: 3 rack
Bonus: +1 per tutti
Totale: 6 rack giocati, max 5 per giocatore
```

### 5. UI per Inserimento Risultati Trio

L'interfaccia deve mostrare:
1. Lo stato corrente del girone (quale rack, chi gioca, chi aspetta)
2. I punteggi parziali di tutti e 3 i giocatori
3. Il girone corrente (se più di uno)
4. Se applicabile, il bonus rack finale

## Alternative Considerate

### Alternativa 1: Trio sempre "primo a 2 rack"

**Descrizione**: Il trio vince sempre chi arriva primo a 2 rack, indipendentemente dalla distanza.

- **Pro**:
  - Semplice da implementare
  - Sempre un vincitore chiaro
- **Contro**:
  - Incompatibile con classifica basata su rack (ingiusto)
  - Ignora la distanza configurata
  - Svantaggia chi è nel trio se distanza > 2

### Alternativa 2: Trio non supportato

**Descrizione**: Disabilitare l'opzione trio, usare solo bye per dispari.

- **Pro**:
  - Nessuna complessità aggiuntiva
- **Contro**:
  - Con bye, un giocatore non gioca → meno divertente
  - Spreco di tempo per il giocatore bye

## Conseguenze

### Positive

- Sistema coerente e logicamente corretto
- Nessun giocatore svantaggiato dalla sorte (trio vs normale)
- Validazioni prevengono configurazioni impossibili
- UI chiara per l'inserimento risultati trio

### Negative

- Complessità implementativa maggiore
- Necessità di refactoring UI trio esistente
- Migrazione dati esistenti potrebbe essere necessaria

### Rischi

- Gare esistenti con configurazioni incompatibili potrebbero avere dati inconsistenti
- La UI trio diventa più complessa da usare

## Note Implementative

### File da Modificare

1. **Wizard Campionato** (`templates/admin/campionato/wizard_*.html`):
   - Aggiungere validazioni client-side per nascondere opzioni incompatibili
   - Mostrare warning se combinazione non valida

2. **Backend Validazione** (`models/competition/services.py`):
   - Aggiungere `validate_gara_configuration()`
   - Bloccare creazione gara con configurazione invalida

3. **Model TrioMatch** (`models/match/models.py`):
   - Aggiungere campi per tracking girone corrente
   - Aggiungere campo bonus_applied

4. **UI Risultati Trio** (`templates/components/_trio_result_entry.html`):
   - Riprogettare per mostrare girone corrente
   - Mostrare chi gioca e chi aspetta
   - Tracciare rack per girone

5. **Calcolo Classifica** (`models/classification/`):
   - Aggiornare per contare rack trio correttamente (incluso bonus)

### Esempio Codice

```python
# models/match/trio_config.py
from dataclasses import dataclass

@dataclass
class TrioConfig:
    """Configurazione trio basata sulla distanza."""
    distance: int

    @property
    def is_trio_allowed(self) -> bool:
        return 2 <= self.distance <= 5

    @property
    def num_rounds(self) -> int:
        """Numero di gironi all'italiana."""
        if not self.is_trio_allowed:
            return 0
        return (self.distance + 1) // 2  # ceil((distance-1)/2) + 1 semplificato

    @property
    def bonus_racks(self) -> int:
        """Rack bonus per pareggiare con match normale."""
        if not self.is_trio_allowed:
            return 0
        return self.distance % 2  # 1 se dispari, 0 se pari

    @property
    def max_racks_per_player(self) -> int:
        """Max rack ottenibili = distanza (come match normale)."""
        return self.distance

    @property
    def total_played_racks(self) -> int:
        """Rack totali giocati nel trio (3 per girone)."""
        return self.num_rounds * 3
```

### 6. TrioRack Model per Undo (Aggiornamento 2026-01-09)

Per supportare la funzionalità di **undo** (annullamento ultimo rack), è stato introdotto il modello `TrioRack` seguendo le best practice OO del modello `Rack`.

**Principi di design:**
- I contatori (`player1_racks`, `player2_racks`, `player3_racks`) sono **computed properties** calcolate dai record `TrioRack`
- Ogni rack giocato crea un record `TrioRack` con:
  - `trio_match_id`: riferimento al trio
  - `rack_number`: numero progressivo
  - `winner_id`: chi ha vinto
  - `player1_id`, `player2_id`, `waiting_player_id`: stato del matchup
- **Soft delete** per undo: `is_deleted=True`, `removed_by_id`, `removed_at`

**Vincoli undo:**
- Solo l'**ultimo rack** può essere rimosso (a causa della sequenza fissa round-robin)
- Il pulsante `-` è abilitato solo per il giocatore che ha vinto l'ultimo rack
- Dopo la rimozione, lo stato del trio viene ricalcolato automaticamente

**Metodi chiave:**
```python
# TrioMatch
def add_rack_win(winner_id: int, added_by_id: int = None) -> TrioRack
def remove_last_rack(removed_by_id: int = None) -> Optional[TrioRack]

# Computed properties
@property
def player1_racks(self) -> int
@property
def total_racks_played(self) -> int
@property
def last_rack(self) -> Optional[TrioRack]
```

**UI:**
- Template `_trio_rack_input.html` mostra +/- per ogni giocatore
- Il `-` è disabilitato se quel giocatore non ha vinto l'ultimo rack

## Riferimenti

- File correlati:
  - `models/match/models.py` (Match, TrioMatch, TrioRack)
  - `models/match/trio_config.py` (TrioConfig)
  - `models/competition/services.py` (GaraService)
  - `models/classification/score_aggregator.py`
  - `templates/components/_trio_rack_input.html`
  - `migrations/add_trio_rack_table.py`
- ADR correlato: ADR-001 (Amalfi Strategy Pattern)
