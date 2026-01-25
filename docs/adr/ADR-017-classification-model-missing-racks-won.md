# [017] Campo Mancante racks_won nel Modello Classification

**Data**: 2026-01-25
**Stato**: Accepted
**Decisori**: Sistema

## Contesto

Il modello `Classification` (classifica campionato) ha un bug di design che causa la visualizzazione di dati errati per campionati con strategia `random`.

### Il Problema

Il modello `Classification` ha questi campi:

```python
class Classification(db.Model):
    total_matches_won = db.Column(db.Integer)      # match vinti
    total_point_difference = db.Column(db.Integer) # rack_difference
    gare_played = db.Column(db.Integer)
```

Ma le strategie di classificazione campionato ordinano diversamente:

| Strategia | Criterio Primario | Criterio Secondario |
|-----------|------------------|---------------------|
| `amalfi_campionato` | `matches_won` | `rack_difference` |
| `random_campionato` | **`racks_won`** | `spot_shot_wins` |

Il codice di salvataggio in `ClassificationService.update_campionato_classification()`:

```python
classification.total_point_difference = entry.score.rack_difference
```

Salva **sempre** `rack_difference`, indipendentemente dalla strategia.

### Conseguenze

1. **Posizione calcolata correttamente**: L'ordinamento avviene in memoria usando la strategia corretta
2. **Valore visualizzato errato**: Il campo `total_point_difference` mostra `rack_difference` invece di `racks_won` per campionati Random
3. **UI fuorviante**: La classifica campionato mostra numeri che non corrispondono al criterio di ordinamento

### Esempio Reale

Campionato "La Garetta del MerColedì 2026" (strategia `random`):

| Giocatore | racks_won (corretto) | rack_difference (salvato) |
|-----------|---------------------|---------------------------|
| PAOLO | 33 | +15 |
| MAX P | 31 | +13 |
| PIETRO | 21 | +6 |

L'UI mostra "+15, +13, +6" ma l'ordinamento è basato su "33, 31, 21".

## Decisione

### Soluzione Proposta

1. **Aggiungere campo `total_racks_won`** al modello `Classification`:

```python
class Classification(db.Model):
    total_matches_won = db.Column(db.Integer, default=0)
    total_racks_won = db.Column(db.Integer, default=0)      # NUOVO
    total_point_difference = db.Column(db.Integer, default=0)  # = rack_difference
    gare_played = db.Column(db.Integer, default=0)
```

2. **Aggiornare il salvataggio** in `ClassificationService`:

```python
classification.total_matches_won = entry.score.matches_won
classification.total_racks_won = entry.score.racks_won          # NUOVO
classification.total_point_difference = entry.score.rack_difference
```

3. **Aggiornare l'UI** per mostrare il campo appropriato in base alla strategia:

```jinja2
{% if campionato.campionato_type == 'random' %}
    {{ c.total_racks_won }} rack
{% else %}
    {{ c.total_point_difference|format_diff }}
{% endif %}
```

### Migrazione Database

```python
# migrations/20260125_add_total_racks_won.py
def upgrade():
    op.add_column('classification',
        sa.Column('total_racks_won', sa.Integer(), nullable=True, default=0))

    # Populate from existing data
    # (requires recalculating from matches)

def downgrade():
    op.drop_column('classification', 'total_racks_won')
```

## Alternative Considerate

### Alternativa 1: Rinominare total_point_difference

**Descrizione**: Usare un nome generico come `primary_sort_value` e salvare il valore corretto per la strategia.

- **Pro**:
  - Un solo campo da gestire
  - Sempre coerente con l'ordinamento
- **Contro**:
  - Perdita di informazione (non si può mostrare sia racks_won che rack_difference)
  - Breaking change per UI esistenti
  - Semantica confusa

### Alternativa 2: Campo JSON per tutti i valori

**Descrizione**: Salvare tutti i valori in un campo JSON.

```python
stats = db.Column(db.JSON)  # {"racks_won": 33, "rack_diff": 15, "matches_won": 5}
```

- **Pro**:
  - Flessibile, estendibile
  - Un solo campo
- **Contro**:
  - Non indicizzabile per query
  - Più complesso da usare
  - Overhead serializzazione

### Alternativa 3: Non salvare, calcolare on-demand

**Descrizione**: Non salvare nulla, calcolare sempre dalla `ScoreAggregator`.

- **Pro**:
  - Sempre aggiornato
  - Nessuna duplicazione
- **Contro**:
  - Performance peggiori (query complesse)
  - Non utilizzabile per ordinamento SQL
  - Attualmente c'è caching, perderemmo i benefici

## Implementazione

### File da Modificare

1. `models/classification/models.py` - Aggiungere campo
2. `models/classification/services.py` - Aggiornare salvataggio
3. `migrations/20260125_add_total_racks_won.py` - Migrazione
4. `templates/campionato/detail.html` - UI classifica
5. `templates/campionato/classification_table.html` - Componente tabella

### Test da Aggiungere

```python
def test_random_campionato_saves_racks_won():
    """Verify Random campionato saves total_racks_won correctly."""
    # Create campionato with random strategy
    # Add completed gare with matches
    # Update classification
    # Assert total_racks_won == sum of racks_won across gare
```

## Conseguenze

### Positive
- Dati coerenti con ordinamento visualizzato
- UI può mostrare il valore corretto per ogni strategia
- Possibilità di mostrare entrambi i valori se utile

### Negative
- Migrazione database richiesta
- Leggero aumento storage (1 integer per record)
- UI deve gestire due casi

## Note

Scoperto durante l'inserimento manuale della gara del 14 gennaio 2026 per il campionato "La Garetta del MerColedì". La classifica mostrava valori di `rack_difference` ma era ordinata per `racks_won`.

Workaround temporaneo applicato: aggiornamento manuale del campo `total_point_difference` con il valore di `racks_won` per questo campionato specifico.
