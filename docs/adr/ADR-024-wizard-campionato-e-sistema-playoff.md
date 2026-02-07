# ADR-024: Wizard Creazione Campionato Multi-Step e Sistema Playoff

**Data**: 2026-01-07
**Stato**: Accepted
**Decisori**: Paolo, Claude

## Contesto

La procedura di creazione campionato attuale presenta diversi problemi:

1. **Form singolo troppo semplice** - Non guida l'utente attraverso le scelte
2. **Sistema punteggio confuso** - `scoring_policy` con opzioni Fargo/Elo non ha senso per classifiche campionato (sono rating globali giocatore)
3. **Ridondanza** - Il flag `without_x` duplica la logica di `odd_policy`
4. **Mancanza di default** - Ogni gara deve essere configurata da zero
5. **Playoff non integrati** - I modelli esistono ma non sono collegati al flusso

### Requisiti emersi:

- Procedura guidata multi-step simile a quella delle gare
- Sistema di punteggio automatico basato sul tipo di campionato
- Default ereditati dalle gare (luogo, costo, turni, gestione dispari, anti-rematch)
- Playoff come gare speciali con sistema di inviti e scadenze
- Flusso inviti batch con scadenza comune gestita dal direttore

## Decisione

### 1. Wizard a 2 Step

**Step 1 - Configurazione Base:**
- Nome campionato
- Numero gare previste (target)
- Tipo campionato (Amalfi/Random) tramite `Enum(MatchmakingStrategy)`
- Modalità Challenge (checkbox)
- Playoff Finali (checkbox) → modale configurazione (Elite/Academy con range posizioni)

**Step 2 - Default Gare:**
- Luogo default (FK a BilliardHall)
- Costo iscrizione default
- Numero turni default
- Gestione dispari default (Bye/Bye con Challenge/Trio)
- Anti-rematch default

### 2. Sistema di Punteggio Automatico

Il sistema di punteggio classifica è determinato automaticamente dal `campionato_type`:

| Tipo | Ordinamento |
|------|-------------|
| AMALFI | Vittorie DESC → Diff. rack DESC → SSR DESC → Ordine precedente |
| RANDOM | Rack vinti DESC → SSR DESC → Ordine precedente |

Questo elimina il campo `scoring_policy` ridondante.

### 3. Modello Campionato Aggiornato

```python
class Campionato(db.Model):
    # Base
    id, name, is_active, created_at, updated_at

    # Configurazione
    campionato_type = db.Column(db.Enum(MatchmakingStrategy), default=MatchmakingStrategy.AMALFI)
    planned_gare_count = db.Column(db.Integer, default=10)
    challenge_mode = db.Column(db.Boolean, default=False)

    # Default gare (NUOVI)
    default_venue_id = db.Column(db.ForeignKey('billiard_hall.id'), nullable=True)
    default_entry_fee = db.Column(db.Float, nullable=True)
    default_rounds_count = db.Column(db.Integer, default=3)
    default_odd_policy = db.Column(db.Enum(OddNumberPolicy), default=OddNumberPolicy.BYE)
    default_anti_rematch = db.Column(db.Boolean, default=True)

    # Relazioni
    playoff_configs = relationship('PlayoffConfiguration')

    # RIMOSSI: scoring_policy, without_x, final_playoffs
```

### 4. Architettura Playoff

I playoff sono implementati come **gare speciali** con iscrizione su invito.

**Regola di dipendenza Elite-Academy:**
- Il **Playoff Academy** esiste solo se è abilitato il **Playoff Elite**
- Nel wizard, disabilitando Elite si disabilita automaticamente Academy
- Motivo: Academy è per i "classificati successivi" (positions N+1 a M), il che presuppone che Elite occupi le posizioni 1-N

```
PlayoffConfiguration (criteri qualificazione)
├── playoff_type: 'elite' | 'academy'
├── positions_from, positions_to (range classifica)
│
└── PlayoffQualification[] (inviti individuali)
    ├── user_id, status (pending|accepted|declined|expired)
    ├── invited_at, expires_at, responded_at
    └── → crea Inscription quando accettato

Gara (con playoff_config_id se è playoff)
└── is_playoff property: return playoff_config_id is not None
```

### 5. Flusso Inviti Batch

Gli inviti vengono inviati in batch con scadenza comune:

1. **Invio iniziale**: Direttore seleziona qualificati, imposta scadenza unica, invia tutti insieme
2. **Sostituzione**: Quando ci sono rifiuti/scaduti, direttore seleziona sostituti, imposta nuova scadenza comune, invia batch
3. **Lazy evaluation**: Le scadenze vengono verificate quando il direttore accede alla dashboard (nessun task schedulato)

### 6. Enum invece di Letterali

Uso di `db.Enum()` per type safety:

```python
campionato_type = db.Column(db.Enum(MatchmakingStrategy), ...)
default_odd_policy = db.Column(db.Enum(OddNumberPolicy), ...)
```

Enum disponibili:
- `MatchmakingStrategy`: AMALFI, RANDOM, ROUND_ROBIN, DIRECT_ELIMINATION, DOUBLE_KNOCKOUT
- `OddNumberPolicy`: BYE, BYE_WITH_CHALLENGE, TRIO

## Alternative Considerate

### Alt 1: Form singolo con tutti i campi
- **Pro**: Implementazione semplice
- **Contro**: UX confusa, troppi campi in una schermata

### Alt 2: Scoring policy configurabile
- **Pro**: Flessibilità
- **Contro**: Fargo/Elo non hanno senso per classifica campionato (sono rating globali)

### Alt 3: Playoff integrati in Inscription
- **Pro**: Meno modelli
- **Contro**: Logica inviti/scadenze inquina modello Inscription

### Alt 4: Task schedulato per scadenze
- **Pro**: Precisione temporale
- **Contro**: Richiede infrastruttura aggiuntiva (Celery/APScheduler)

### Alt 5: Scadenza individuale per ogni invito
- **Pro**: Flessibilità massima
- **Contro**: UX complessa, il direttore deve gestire N scadenze diverse

## Conseguenze

### Positive
- UX guidata e chiara per la creazione campionato
- Sistema punteggio coerente e automatico
- Default riducono lavoro ripetitivo per il direttore
- Playoff ben integrati nel flusso esistente
- Type safety con Enum
- Nessuna dipendenza da task scheduler

### Negative
- Migrazione dati esistenti richiesta
- Rimozione campi può rompere codice che li usa
- Lazy evaluation può ritardare aggiornamento stato scadenze

### Rischi
- Campionati esistenti con `without_x=True` devono essere migrati correttamente
- Codice che usa `scoring_policy` deve essere aggiornato

## Note Implementative

### Migrazione

```python
def upgrade():
    # 1. Aggiungi nuovi campi
    op.add_column('campionato', Column('planned_gare_count', Integer, default=10))
    op.add_column('campionato', Column('default_venue_id', Integer, ForeignKey('billiard_hall.id')))
    op.add_column('campionato', Column('default_entry_fee', Float))
    op.add_column('campionato', Column('default_rounds_count', Integer, default=3))
    op.add_column('campionato', Column('default_odd_policy', String(20), default='bye'))
    op.add_column('campionato', Column('default_anti_rematch', Boolean, default=True))

    # 2. Migra without_x → default_odd_policy
    op.execute("""
        UPDATE campionato
        SET default_odd_policy = CASE
            WHEN without_x = TRUE THEN 'trio'
            ELSE 'bye'
        END
    """)

    # 3. Aggiungi playoff_config_id a Gara
    op.add_column('gara', Column('playoff_config_id', Integer, ForeignKey('playoff_configuration.id')))

    # 4. Rimuovi campi deprecati
    op.drop_column('campionato', 'scoring_policy')
    op.drop_column('campionato', 'without_x')
    op.drop_column('campionato', 'final_playoffs')
```

### File Coinvolti

- `models/campionato/models.py` - Modello Campionato
- `models/competition/models.py` - Modello Gara (aggiunta FK playoff)
- `models/playoff/models.py` - PlayoffConfiguration, PlayoffQualification
- `routes/admin/campionato.py` - Route creazione/modifica
- `templates/admin/campionato_wizard.html` - Nuovo template wizard
- `templates/admin/playoff_dashboard.html` - Dashboard gestione inviti

### Creazione Gara con Eredità

Quando si crea una nuova gara nel campionato:
1. Eredita default da `Campionato` (luogo, costo, turni, odd_policy, anti_rematch)
2. Eredita valori da gara precedente (data +7 giorni, disciplina, distanza)
3. Tipo matchmaking default = `campionato.campionato_type` (sovrascrivibile)

### Lazy Check Scadenze

```python
def check_expired_invitations(playoff_config_id: int) -> None:
    """Chiamato quando direttore accede alla dashboard."""
    now = datetime.utcnow()

    PlayoffQualification.query.filter(
        PlayoffQualification.playoff_config_id == playoff_config_id,
        PlayoffQualification.status == 'pending',
        PlayoffQualification.expires_at < now
    ).update({'status': 'expired'})

    db.session.commit()
```

## Riferimenti

- `models/matchmaking/configuration.py` - Enum MatchmakingStrategy, OddNumberPolicy
- `models/playoff/models.py` - Modelli playoff esistenti (da integrare)
- `docs/usecases/gare.md` - Flusso gare esistente
