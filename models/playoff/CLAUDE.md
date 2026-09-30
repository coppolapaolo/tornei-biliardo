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

# Start playoffs: generates qualifications from the classification,
# sets invited_at and sends the invitations
PlayoffService.start_playoff(campionato.id)

# Player answers
PlayoffService.confirm_qualification(qualification_id=qual.id, user_id=player.id)
PlayoffService.decline_qualification(qualification_id=qual.id, user_id=player.id)
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
  Dal 2026-09-29 (ADR-075) a inviti partiti si bloccano solo i **criteri
  di qualificazione** (`CRITERI_DI_QUALIFICAZIONE`: posizioni, posti, gare
  minime); il resto si corregge fino all'avvio della finale. La finale
  nasce copiando i valori e da lì ha i suoi: correggere la configurazione
  **propone** il cambio alla finale (`proposta_finale.py`), come il
  campionato fa con le sue gare. Dopo l'avvio la finale si cambia dal form
  della gara

### PlayoffQualification
Individual player qualification record.

**Key Fields:**
- `configuration_id`, `user_id`, `qualifying_position`, `qualification_reason`
- `status`: PENDING → CONFIRMED / DECLINED / EXPIRED / REPLACED
- `invited_at`, `responded_at`, `replaced_by_id`, `replacement_position`
- `responded_by_id` — chi ha materialmente risposto: il giocatore, oppure il
  direttore che ha registrato la risposta ricevuta a voce
  (`PlayoffService.respond_on_behalf`). `answered_on_behalf` li distingue

### PlayoffTournament
Links the configuration to the final's Gara.

**Key Fields:**
- `configuration_id`, `gara_id`
- `status`, `completed_at`, `winner_id`

---

## Qualification Flow

```
Classification Complete
        ↓
start_playoff() → PlayoffQualification records (PENDING), invited_at, notifications
        ↓
    ┌───────┴───────┐
    ↓               ↓
confirm_qualification()   decline_qualification()
    ↓               ↓
CONFIRMED      DECLINED → find_replacement_player() invites the next eligible
```

---

## Storia dei playoff (ADR-075)

Ogni servizio che cambia la configurazione o la lista scrive una voce con
`playoff_config_id` (`_scrivi_nella_storia`): `update_configuration`,
`update_min_garas`, `add_configuration`, `deactivate_configuration`,
`update_scoring`, `aggiorna_calendario`, e gli strumenti a mano
`admin_add_player` / `admin_remove_player` / `respond_on_behalf` (azioni
`giocatore_aggiunto`, `giocatore_tolto`, `risposta_per_conto`, con la riga
`giocatore`). Chi il direttore iscrive alla finale porta `inscribed_by_id`.

Una correzione che sposta la classifica dopo gli inviti (peso di una gara,
punti per posizione) produce una **proposta** (`proposta_inviti.py`): è il
piano di `riallineamento.pianifica`, che il direttore accetta (`esegui` con
`classifica_corretta=True`, testi e notifiche dicono «classifica corretta»)
o rifiuta. Una proposta rifiutata non si ripresenta finché non cambia.

## Do Not

- **Do not manually create qualifications** - Use `start_playoff()` (or `admin_add_player` for a manual addition)
- **Do not skip min_garas_played check** - Players must meet minimum participation
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
