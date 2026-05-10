# Data Models — Catalogo Completo Modelli SQLAlchemy

> **Snapshot del 2026-04-04** (BMad full-scan). Per lo schema corrente delle tabelle (incluso quanto introdotto dalle migrazioni successive) vedere [`docs/reference/DATABASE_SCHEMA.md`](../reference/DATABASE_SCHEMA.md), rigenerabile con `python scripts/generate_schema_docs.py`.
> Aggiornamenti rilevanti post-2026-04: `Match` ha guadagnato `RoundConfiguration` ([ADR-027](../adr/ADR-027-round-level-configuration-enforcement.md)) e i campi `started_at`/`ended_at` sono stati portati a regime.
> **80+ classi modello** | **70+ tabelle** | **15 domini** (al 2026-04-04)

---

## Riepilogo

| Metrica | Valore |
|---------|--------|
| Classi modello totali | 80+ |
| Tabelle database | 70+ |
| Domini funzionali | 15 |
| Classi base/mixin | 6 |
| Classi servizio | 40+ |
| Vincoli unique | 20+ |
| Relazioni cascade | 40+ |
| Enum | 20+ |

---

## Infrastruttura Core

### Classi Base

| Classe | File | Uso |
|--------|------|-----|
| **BaseModel** | `models/base.py` | `db.Model + TimestampMixin + UtilityMixin` — Maggior parte entità |
| **SimpleModel** | `models/base.py` | `UtilityMixin + db.Model` — Tabelle leggere senza timestamp |
| **SoftDeleteMixin** | `models/base.py` | `deleted_at` + `is_deleted` — GDPR compliance |

### Mixin

| Mixin | Funzionalità |
|-------|-------------|
| **UtilityMixin** | `save()`, `delete()`, `to_dict()`, `find_by_id()`, `find_all()` |
| **TimestampMixin** | `created_at`, `updated_at` auto-gestiti |
| **SoftDeleteMixin** | `deleted_at` + property `is_deleted` |
| **AuditMixin** | `created_by_id`, `updated_by_id` |
| **ValidationMixin** | `validate()` + `save_with_validation()` |
| **BaseMatchMixin** | Validazione/conferma condivisa Match e IndividualMatch |

### Value Objects

| Classe | File | Descrizione |
|--------|------|-------------|
| **Distance** | `models/match/distance.py` | Configurazione immutabile race-to-N (singolo/multi-set) |
| **RackScore** | `models/match/score.py` | Punteggio rack immutabile |
| **MatchScore** | `models/match/score.py` | Punteggio match immutabile |

---

## 1. USER MANAGEMENT

### User
**File**: `models/user/models.py` | **Tabella**: `user`

| Colonna | Tipo | Note |
|---------|------|------|
| id | Integer | PK |
| username | String(80) | Unique |
| email | EncryptedString(200) | Crittografato Fernet |
| phone | EncryptedString(100) | Crittografato Fernet |
| password_hash | String(256) | Werkzeug hash |
| role | String(20) | `admin\|director\|player` |
| language | String(5) | Lingua preferita |
| is_verified | Boolean | Verifica email |
| gamification_override | Boolean | Bypass unlock checks |
| deleted_at | DateTime | Soft delete (SoftDeleteMixin) |
| previous_username | String(80) | Pre-anonimizzazione |

**Relazioni**: `→ DirectorAssignment, VenueManagement, Inscription, Match, UserLevel, Notification, PrivacySettings`

**Metodi chiave**: `anonymize()`, `can_manage_campionato()`, `can_access(feature_code)`, `has_unlocked_achievement()`

### DirectorAssignment
**Tabella**: `director_assignment` | **PK composita**: `(user_id, entity_type, entity_id)`

| Colonna | Tipo | Note |
|---------|------|------|
| user_id | Integer | FK → user |
| entity_type | String | `campionato\|gara` |
| entity_id | Integer | ID entità gestita |

### DirectorRequest / VenueManagerRequest / VenueManagement
Modelli per workflow richieste ruolo e assegnazione gestione sale.

---

## 2. PRIVACY & GDPR

### UserPrivacySetting
**File**: `models/user/privacy_models.py` | **1-to-1 con User**

Tutti i toggle default `False` (opt-in):
- `show_statistics`, `show_match_history`, `show_rating`, `show_level`, etc.

### HiddenMatch / HiddenInscription / HiddenCampionato
Entità nascoste dall'utente (vincolo unique `user_id + entity_id`).

---

## 3. LOCATION / VENUE

### BilliardHall
**File**: `models/location/models.py` | **Tabella**: `billiard_hall`

| Colonna | Tipo | Note |
|---------|------|------|
| id | Integer | PK |
| name | String(200) | Nome sala |
| address, city, province | String | Indirizzo |
| latitude, longitude | Float | Geolocalizzazione |
| phone, email, website | String | Contatti |
| business_hours | Text (JSON) | Orari apertura |
| table_names | Text (JSON) | Nomi tavoli |
| amenities | Text (JSON) | Servizi |
| num_tables | Integer | Numero tavoli |
| is_active, is_verified | Boolean | Stato |
| photo_path | String | Foto sala |

### UserLocationAvailability
Disponibilità giocatore presso una sala specifica.

---

## 4. TOURNAMENT / COMPETITION

### Campionato
**File**: `models/campionato/models.py` | **Tabella**: `campionato`

| Colonna | Tipo | Note |
|---------|------|------|
| id | Integer | PK |
| name | String(200) | Nome campionato |
| description | Text | Descrizione |
| is_active | Boolean | Attivo |
| default_matchmaking | String | Strategia matchmaking default |
| default_distance | Integer | Distance default per gare |
| default_best_of | Boolean | Best-of mode default |
| venue_id | Integer | FK → billiard_hall |
| deleted_at | DateTime | Soft delete |

**Relazioni**: `→ Gara (CASCADE), DirectorAssignment, PlayoffConfiguration`

### Gara
**File**: `models/competition/models.py` | **Tabella**: `gara` | **52 simboli**

| Colonna | Tipo | Note |
|---------|------|------|
| id | Integer | PK |
| nome | String(200) | Nome gara |
| number | Integer | Ordine nel campionato |
| campionato_id | Integer | FK → campionato (nullable per standalone) |
| status | String | `setup\|inscription\|playing\|awaiting_ssr\|completed\|cancelled` |
| date, time | Date, Time | Data/ora gara |
| inscription_open_date/close_date | DateTime | Periodo iscrizioni |
| distance | Integer | Race-to-N (racks per vincere) |
| best_of | Boolean | Modalità best-of |
| is_multi_set | Boolean | Multi-set abilitato |
| match_distance | Integer | Set per vincere (multi-set) |
| matchmaking_strategy | String | Strategia accoppiamento |
| classification_system | String | `RACK\|WINS\|POSITION` |
| odd_number_policy | String | Politica numero dispari |
| max_participants | Integer | Limite partecipanti |
| available_tables | Text (JSON) | Override tavoli disponibili |
| current_round | Integer | Turno corrente |
| venue_id | Integer | FK → billiard_hall |
| deleted_at, deleted_reason | DateTime, String | Soft delete con motivo |

**Relazioni**: `→ Inscription, Match, Round, GaraClassification`

### Inscription
**File**: `models/competition/models.py` | **Tabella**: `inscription`

| Colonna | Tipo | Note |
|---------|------|------|
| id | Integer | PK |
| gara_id | Integer | FK → gara |
| user_id | Integer | FK → user |
| status | String | `active\|waitlisted\|withdrawn\|removed` |
| waitlist_reason | String | `capacity\|parity` |
| waitlist_position | Integer | Posizione in waitlist |

---

## 5. MATCH

### Match
**File**: `models/match/models.py` | **Tabella**: `match` | **51 simboli**

| Colonna | Tipo | Note |
|---------|------|------|
| id | Integer | PK |
| gara_id | Integer | FK → gara (nullable se soft-deleted) |
| round_number | Integer | Numero turno |
| player1_id, player2_id | Integer | FK → user |
| score1, score2 | Integer | Punteggio |
| winner_id | Integer | FK → user |
| status | String | `pending\|playing\|completed\|validated\|cancelled` |
| is_multi_set | Boolean | Multi-set |
| match_distance | Integer | Set per vincere |
| current_set_number | Integer | Set corrente |
| distance | Integer | Race-to-N per set |
| has_handicap | Boolean | Handicap attivo |
| player1_handicap, player2_handicap | Integer | Valori handicap |
| table_number | String | Tavolo assegnato |
| is_bye | Boolean | Match bye |
| started_at, completed_at | DateTime | Timestamps |

**Relazioni**: `→ Rack, MatchSet, MatchResult, Tiebreaker`

### Rack
**Tabella**: `rack`

| Colonna | Tipo | Note |
|---------|------|------|
| id | Integer | PK |
| match_id | Integer | FK → match |
| set_id | Integer | FK → match_set (nullable) |
| rack_number | Integer | Numero progressivo |
| winner_id | Integer | FK → user |
| is_break_and_run | Boolean | Break and run |
| is_deleted | Boolean | Soft delete per undo |

### MatchSet
**Tabella**: `match_set` | **Vincolo unique**: `(match_id, set_number)`

### TrioMatch
**Tabella**: `trio_match` | Match a 3 giocatori (numero dispari)

| Colonna | Tipo | Note |
|---------|------|------|
| player1/2/3_id | Integer | FK → user |
| schulze_ranking | Text (JSON) | Classifica Schulze |
| state_data | Text (JSON) | Stato serializzato |

### TrioRack
**Tabella**: `trio_rack` | Rack del match trio.

---

## 6. INDIVIDUAL MATCH

### MatchProposal
**File**: `models/individual_match/proposal_models.py`

| Colonna | Tipo | Note |
|---------|------|------|
| type | String | `direct\|open` |
| creator_id | Integer | FK → user |
| target_user_id | Integer | FK → user (nullable per open) |
| status | String | `pending\|accepted\|declined\|cancelled\|expired` |
| distance | Integer | Nullable (formato libero) |
| is_multi_set | Boolean | Multi-set |
| expires_at | DateTime | Scadenza proposta |

### IndividualMatch
**File**: `models/individual_match/match_models.py` | **41 simboli**

Simile a Match ma per partite casuali. Supporta multi-set, distance nullable (formato libero).

### IndividualSet / IndividualRack
Set e rack per match individuali.

---

## 7. CLASSIFICATION

### Classification
**File**: `models/classification/models.py` | Classifica campionato globale.

### RoundClassification
**Vincolo unique**: `(gara_id, round_number, user_id)`

| Colonna | Tipo | Note |
|---------|------|------|
| position | Integer | Posizione |
| points | Float | Punti |
| wins, losses, draws | Integer | Risultati |
| racks_won, racks_lost | Integer | Rack |
| total_racks_won | Integer | Rack totali vinti |

### GaraClassification
Classifica finale della gara.

### PlayerEncounter
Storico incontri tra giocatori (anti-rematch).

---

## 8. CHALLENGE

### Challenge
**File**: `models/challenge/models.py`

| Colonna | Tipo | Note |
|---------|------|------|
| title, description | String, Text | Info sfida |
| difficulty | String | Difficoltà |
| pass_fail_only | Boolean | True = pass/fail, False = punteggio numerico |
| pass_threshold | Float | Soglia superamento |
| image_path | String | Immagine sfida |

### ChallengeAttempt / ChallengeFavorite
Tentativi e preferiti (unique constraint su user+challenge).

---

## 9. GAMIFICATION

### UserLevel
**File**: `models/gamification/models.py` | **Tabella**: `user_level`

| Colonna | Tipo | Note |
|---------|------|------|
| user_id | Integer | FK → user (unique) |
| current_level | Integer | Livello attuale |
| current_xp | Integer | XP nel livello corrente |
| total_xp | Integer | XP totali guadagnati |

### XPTransaction
Log audit di ogni transazione XP.

| Colonna | Tipo | Note |
|---------|------|------|
| user_id | Integer | FK → user |
| amount | Integer | XP guadagnati |
| transaction_type | String | `match_win\|match_loss\|tournament_*\|achievement_unlock\|admin_grant` |
| level_before, level_after | Integer | Snapshot livello |
| source_type, source_id | String, Integer | Entità sorgente |

### Achievement
Achievement predefiniti con categorie e difficoltà.

| Colonna | Tipo | Note |
|---------|------|------|
| slug | String | Identificatore unique |
| category | Enum | `match\|tournament\|social\|skill\|consistency\|exploration\|milestone` |
| difficulty | Enum | `common\|uncommon\|rare\|epic\|legendary` |
| requirements | Text (JSON) | Criteri sblocco |
| is_progressive | Boolean | Progresso incrementale |
| xp_reward | Integer | XP premio |

### UserAchievement
Progresso giocatore su achievement (unique: user_id + achievement_id).

### StreakTracker
Serie consecutive settimanali.

| Colonna | Tipo | Note |
|---------|------|------|
| streak_type | Enum | `weekly_activity\|weekly_match\|weekly_tournament\|weekly_drill` |
| current_streak | Integer | Serie corrente |
| longest_streak | Integer | Record |
| freeze_count | Integer | Pause disponibili |

### Quest / QuestParticipation
Missioni con obiettivi JSON e partecipazione giocatori.

### LeaderboardEntry
Classifiche cached per periodo e tipo.

---

## 10. RATING / HANDICAP

### PlayerRating
**Vincolo unique**: `(user_id, rating_system)`

| Colonna | Tipo | Note |
|---------|------|------|
| rating_system | String | `fargo\|elo\|internal` |
| rating_value | Float | Valore rating |
| confidence | Float | Confidenza |
| games_played | Integer | Partite giocate |

### PlayerCategory
Categoria giocatore (A/B/C/D) con scadenza.

### HandicapRule
Regole handicap tra coppie di categorie.

---

## 11. NOTIFICATION

### Notification
**File**: `models/notification/models.py`

| Colonna | Tipo | Note |
|---------|------|------|
| user_id | Integer | FK → user |
| type | Enum | 20+ tipi (match, tournament, gamification, system, admin, kpi) |
| priority | Enum | `low\|normal\|high\|urgent` |
| status | Enum | `pending\|sent\|read\|dismissed\|expired` |
| title, message | String, Text | Contenuto |
| template_key | String | Template i18n |
| template_params | Text (JSON) | Parametri template |
| related_entities | Text (JSON) | Entità correlate |

### NotificationPreference
Preferenze notifica 1-to-1 con User.

### NotificationTemplate
Template notifiche con supporto i18n.

---

## 12. PLAYOFF

### PlayoffConfiguration
**File**: `models/playoff/models.py`

| Colonna | Tipo | Note |
|---------|------|------|
| campionato_id | Integer | FK → campionato |
| playoff_type | Enum | `top_n\|elite_academy\|conditional\|bottom_exclude` |
| top_n | Integer | Giocatori qualificati |
| response_deadline_hours | Integer | Deadline risposta |

### PlayoffQualification
Status qualificazione: `pending\|confirmed\|declined\|expired\|replaced`.

### PlayoffTournament
Link campionato sorgente → campionato playoff.

---

## 13. TIEBREAKER

### Tiebreaker
**File**: `models/tiebreaker/models.py`

Tipo: `spot_shot\|rally\|playoff_match\|coin_flip\|etc`.

### SpotShot / RallyAttempt / PlayoffMatch
Sotto-modelli per tipi specifici di spareggio.

---

## 14. KPI & METRICHE

### KpiFeatureUsage
Uso feature giornaliero aggregato (anonimo, GDPR compliant).

### KpiDailySnapshot
Metriche giornaliere piattaforma (utenti, match, retention, XP).

### KpiMilestone
Milestone raggiunti (de-duplicazione per notifiche).

---

## 15. EXAM

### Exam
Esami creati da director (time limit, grading criteria JSON).

### ExamChallenge
Sfida nell'esame (ordine, peso, is_required).

### ExamAttempt
Tentativo studente (total_score, final_grade A-F).

### ExamChallengeResult
Risultato per-sfida nell'esame.

---

## Enumerazioni Principali

### Status

| Enum | Valori |
|------|--------|
| `GaraStatus` | setup, inscription, playing, awaiting_ssr, completed, cancelled |
| `MatchStatus` | pending, playing, completed, validated, scheduled, in_progress, cancelled |
| `TournamentStatus` | setup, registration_open, in_progress, completed |
| `Discipline` | 8_ball, 9_ball, 10_ball, one_pocket, straight_pool, bank_pool, rotation |

### Gamification

| Enum | Valori |
|------|--------|
| `AchievementCategory` | match, tournament, social, skill, consistency, exploration, milestone |
| `AchievementDifficulty` | common, uncommon, rare, epic, legendary |
| `StreakType` | weekly_activity, weekly_match, weekly_tournament, weekly_drill |
| `QuestType` | weekly, monthly, special_event |
| `LeaderboardType` | xp_all_time, xp_weekly, xp_monthly, level_highest, streak, win_rate, elo_rating |

### Notification

| Enum | Valori |
|------|--------|
| `NotificationType` | 20+ tipi (match, tournament, gamification, system, admin, kpi) |
| `NotificationPriority` | low, normal, high, urgent |
| `NotificationStatus` | pending, sent, read, dismissed, expired |

---

## Pattern Chiave

### Soft Delete
- **User, Gara, Campionato**: campo `deleted_at` + property `is_deleted`
- Gara include `deleted_reason` per audit trail
- Match conservati standalone se gara soft-deleted (gara_id → NULL)
- Filtro globale SQLAlchemy per query User

### Crittografia
- `EncryptedString` per PII: email, phone
- Fernet (symmetric) con PBKDF2-SHA256 key derivation
- Transparent encrypt/decrypt via SQLAlchemy TypeDecorator

### JSON Storage
- `BilliardHall`: business_hours, table_names, amenities
- `Gara`: available_tables
- `Challenge/Exam/Quest/Playoff`: requirements, grading_criteria, objectives
- `Notification`: related_entities, template_params

### Vincoli Unique Principali
- `User`: (username), (email)
- `DirectorAssignment`: (user_id, entity_type, entity_id)
- `MatchSet`: (match_id, set_number)
- `PlayerRating`: (user_id, rating_system)
- `RoundClassification`: (gara_id, round_number, user_id)
- `VenueManagement`: (venue_id, is_active)
- `ChallengeFavorite`: (user_id, challenge_id)
- `QuestParticipation`: (quest_id, user_id)
