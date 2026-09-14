# Playoff Domain

## Purpose

Playoff system for campionato end-of-season tournaments with qualification management.

**Core Responsibilities:**
- Playoff configuration per campionato
- Qualification criteria and position-based selection
- Player invitation and confirmation workflow
- Elite/Academy division support

---

## Quick Reference

```python
from models.playoff.models import (
    PlayoffConfiguration, PlayoffQualification, PlayoffTournament,
    PlayoffType, QualificationStatus
)
from models.playoff.services import PlayoffService

# Create playoff configuration
config = PlayoffConfiguration(
    campionato_id=campionato.id,
    name="Elite Playoff",
    playoff_type=PlayoffType.TOP_N,
    max_participants=6,
    positions_from=1,
    positions_to=6,
    min_garas_played=5
)

# Generate qualifications from classification
PlayoffService.generate_qualifications(config.id)

# Invite player
PlayoffService.invite_player(qualification_id=qual.id)

# Player confirms
PlayoffService.confirm_participation(qualification_id=qual.id, user_id=player.id)
```

---

## Playoff Types

| Type | Description |
|------|-------------|
| `TOP_N` | Top N players by position |
| `ELITE_ACADEMY` | Split into Elite and Academy divisions |
| `BOTTOM_EXCLUDE` | Exclude top players (e.g., 3rd and below only) |
| `CONDITIONAL` | Custom criteria via JSON |

---

## Models

### PlayoffConfiguration
Defines playoff rules for a campionato.

**Key Fields:**
- `campionato_id`, `name`, `playoff_type`
- `max_participants`, `min_garas_played`
- `positions_from`, `positions_to` (position range)
- `qualification_criteria` (JSON for complex rules)
- `location`, `scheduled_date`, `entry_fee`
- `is_active`, `auto_generate`
- `final_ranking_mode`, `playoff_weight` — come il playoff entra nella
  classifica finale del campionato (ADR-053)
- `discipline`, `distance`, `rounds_count`, `strategy_type`,
  `odd_number_policy`, `classification_system` — le opzioni della finale.
  NULL = eredita: dalla **prima gara conclusa** (anche «al N»), e dai
  valori del campionato solo se non ce n'è ancora una (`get_gara_params`).
  Con `campionato_plus_playoff` la finale deve avere il sistema del
  campionato; con `playoff_only` è libero e il tabellone porta POSITION
  (`PlayoffService._verifica_finale_sommabile`, SPECIFICHE.md riga 289).
  Si modificano solo prima dell'avvio: dopo, la finale esiste e la si
  cambia dal form della gara, che non le impone strategia e sistema del
  campionato

### PlayoffQualification
Individual player qualification record.

**Key Fields:**
- `playoff_config_id`, `user_id`, `classification_position`
- `status`: PENDING → CONFIRMED / DECLINED / EXPIRED / REPLACED
- `invited_at`, `responded_at`, `replaced_by_id`
- `responded_by_id` — chi ha materialmente risposto: il giocatore, oppure il
  direttore che ha registrato la risposta ricevuta a voce
  (`PlayoffService.respond_on_behalf`). `answered_on_behalf` li distingue

### PlayoffTournament
Actual playoff tournament (links to generated Campionato).

**Key Fields:**
- `playoff_config_id`, `generated_campionato_id`
- `status`, `started_at`, `completed_at`

---

## Qualification Flow

```
Classification Complete
        ↓
generate_qualifications() → Creates PlayoffQualification records
        ↓
invite_player() → Sets status=PENDING, sends notification
        ↓
    ┌───────┴───────┐
    ↓               ↓
confirm()       decline()
    ↓               ↓
CONFIRMED      DECLINED → invite next eligible
```

---

## Do Not

- **Do not manually create qualifications** - Use `generate_qualifications()`
- **Do not skip min_garas_played check** - Players must meet minimum participation
- **Do not forget to invite** - Qualifications are created but not auto-invited
- **Do not call `db.session.commit()`** - Services use `@transactional`

---

---

## La classifica finale del campionato (ADR-053)

La gara di playoff **è** una gara del campionato: `create_playoff_gara` le
mette `campionato_id`, quindi `ScoreAggregator` la contava già da sempre. Da
qui due conseguenze da non dimenticare:

- il default `campionato_plus_playoff` **è** il comportamento storico, non una
  scelta nuova. Cambiarlo cambierebbe la classifica di ogni campionato
  archiviato;
- in `playoff_only` il peso efficace della gara è **0**
  (`Gara.classification_weight`): il playoff detta l'ordine dei suoi
  partecipanti, e sommarne anche il punteggio sposterebbe la posizione di chi
  al playoff non è andato.

Il peso letto dall'aggregatore è `Gara.weight`; `PlayoffConfiguration.playoff_weight`
è il valore di configurazione, copiato sulla gara alla creazione.
`PlayoffService.update_scoring` li tiene allineati e ricalcola la classifica —
ed è l'unico percorso di modifica che **non** è bloccato dall'avvio dei
playoff, perché il punteggio non è la qualificazione.

---

## Cross-References

- **Campionato**: [../campionato/CLAUDE.md](../campionato/CLAUDE.md) - Source of playoffs
- **Classification**: [../classification/](../classification/) - Position-based qualification
