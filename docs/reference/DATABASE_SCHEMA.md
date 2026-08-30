# Database Schema Reference

> **Auto-generated** from SQLAlchemy models.
> Last updated: 2026-08-30 12:19 UTC
>
> To regenerate: `python scripts/generate_schema_docs.py`

---

## Table of Contents

- [User & Authentication](#user--authentication)
- [Tournament & Competition](#tournament--competition)
- [Match & Scoring](#match--scoring)
- [Classification & Rankings](#classification--rankings)
- [Playoff & Tiebreaker](#playoff--tiebreaker)
- [Challenge & Exam](#challenge--exam)
- [Individual Match](#individual-match)
- [Rating & Handicap](#rating--handicap)
- [Gamification](#gamification)
- [Notification](#notification)
- [Location](#location)
- [KPI & Analytics](#kpi--analytics)
- [System](#system)
- [Other Tables](#other-tables)

---

## User & Authentication

### user

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `username` | VARCHAR(80) | NO | UQ |  |  |
| `email` | VARCHAR(200) | YES | UQ |  |  |
| `email_hash` | VARCHAR(64) | YES |  |  |  |
| `password_hash` | VARCHAR(120) | NO |  |  |  |
| `is_verified` | BOOLEAN | NO |  | False |  |
| `role` | VARCHAR(20) | NO |  | player |  |
| `phone` | VARCHAR(100) | YES |  |  |  |
| `first_name` | VARCHAR(100) | YES |  |  |  |
| `last_name` | VARCHAR(100) | YES |  |  |  |
| `elo_rating` | INTEGER | YES |  |  |  |
| `previous_username` | VARCHAR(80) | YES |  |  |  |
| `home_city` | VARCHAR(100) | YES |  |  |  |
| `squadra` | VARCHAR(100) | YES |  |  |  |
| `timezone` | VARCHAR(64) | YES |  |  |  |
| `onboarding_completed` | BOOLEAN | NO |  | False |  |
| `onboarding_interests` | VARCHAR(100) | YES |  |  |  |
| `signal_radius_km` | INTEGER | NO |  | 30 |  |
| `signal_notified_at` | DATETIME | YES |  |  |  |
| `last_active_at` | DATETIME | YES |  |  |  |
| `gamification_override` | BOOLEAN | NO |  | False |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |
| `deleted_at` | DATETIME | YES |  |  |  |

**Constraints:**
- UNIQUE(email)
- UNIQUE(username)

### director_assignment

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `user_id` | INTEGER | NO | PK, FK→user.id |  |  |
| `entity_type` | VARCHAR(20) | NO | PK |  |  |
| `entity_id` | INTEGER | NO | PK |  |  |
| `assigned_by_id` | INTEGER | NO | FK→user.id |  |  |
| `assigned_at` | DATETIME | YES |  | func |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `assigned_by_id` → `user.id` (ON DELETE NO ACTION)
- `user_id` → `user.id` (ON DELETE NO ACTION)

### director_request

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `requested_at` | DATETIME | YES |  | func |  |
| `status` | VARCHAR(20) | NO |  | pending |  |
| `processed_at` | DATETIME | YES |  |  |  |
| `processed_by_id` | INTEGER | YES | FK→user.id |  |  |
| `notes` | TEXT | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `processed_by_id` → `user.id` (ON DELETE NO ACTION)
- `user_id` → `user.id` (ON DELETE NO ACTION)

### venue_management

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `venue_id` | INTEGER | NO | FK→billiard_hall.id |  |  |
| `assigned_at` | DATETIME | YES |  | func |  |
| `assigned_by_id` | INTEGER | NO | FK→user.id |  |  |
| `is_active` | BOOLEAN | YES |  | True |  |
| `revoked_at` | DATETIME | YES |  |  |  |
| `revoked_by_id` | INTEGER | YES | FK→user.id |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(venue_id, is_active)

**Foreign Keys:**
- `venue_id` → `billiard_hall.id` (ON DELETE NO ACTION)
- `user_id` → `user.id` (ON DELETE NO ACTION)
- `assigned_by_id` → `user.id` (ON DELETE NO ACTION)
- `revoked_by_id` → `user.id` (ON DELETE NO ACTION)

### venue_manager_request

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `venue_id` | INTEGER | NO | FK→billiard_hall.id |  |  |
| `requested_at` | DATETIME | YES |  | func |  |
| `status` | VARCHAR(20) | NO |  | pending |  |
| `processed_at` | DATETIME | YES |  |  |  |
| `processed_by_id` | INTEGER | YES | FK→user.id |  |  |
| `notes` | TEXT | YES |  |  |  |
| `admin_notes` | TEXT | YES |  |  |  |
| `is_contested` | BOOLEAN | YES |  | False |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, venue_id)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE NO ACTION)
- `venue_id` → `billiard_hall.id` (ON DELETE NO ACTION)
- `processed_by_id` → `user.id` (ON DELETE NO ACTION)

### user_privacy_setting

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id, UQ |  |  |
| `show_email` | BOOLEAN | NO |  | False |  |
| `show_phone` | BOOLEAN | NO |  | False |  |
| `show_statistics` | BOOLEAN | NO |  | False |  |
| `show_recent_matches` | BOOLEAN | NO |  | False |  |
| `show_classifications` | BOOLEAN | NO |  | False |  |
| `show_challenge_stats` | BOOLEAN | NO |  | False |  |
| `show_elo` | BOOLEAN | NO |  | True |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)

### hidden_match

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `match_id` | INTEGER | NO | FK→match.id |  |  |
| `hidden_at` | DATETIME | NO |  | func |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, match_id)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)
- `match_id` → `match.id` (ON DELETE CASCADE)

### hidden_inscription

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `inscription_id` | INTEGER | NO | FK→inscription.id |  |  |
| `hidden_at` | DATETIME | NO |  | func |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, inscription_id)

**Foreign Keys:**
- `inscription_id` → `inscription.id` (ON DELETE CASCADE)
- `user_id` → `user.id` (ON DELETE CASCADE)

### hidden_campionato

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `campionato_id` | INTEGER | NO | FK→campionato.id |  |  |
| `hidden_at` | DATETIME | NO |  | func |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, campionato_id)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)
- `campionato_id` → `campionato.id` (ON DELETE CASCADE)

---

## Tournament & Competition

### campionato

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `name` | VARCHAR(100) | NO |  |  |  |
| `campionato_type` | VARCHAR(50) | NO |  | amalfi |  |
| `challenge_mode` | BOOLEAN | YES |  | False |  |
| `planned_gare_count` | INTEGER | NO |  | 10 |  |
| `default_venue_id` | INTEGER | YES | FK→billiard_hall.id |  |  |
| `default_entry_fee` | FLOAT | YES |  |  |  |
| `default_rounds_count` | INTEGER | NO |  | 3 |  |
| `default_odd_policy` | VARCHAR(30) | NO |  | bye |  |
| `default_anti_rematch` | BOOLEAN | NO |  | True |  |
| `default_classification_system` | VARCHAR(10) | NO |  | WINS |  |
| `default_start_rule` | VARCHAR(20) | NO |  | first_player |  |
| `default_break_rule` | VARCHAR(20) | NO |  | alternate |  |
| `position_points` | TEXT | YES |  |  |  |
| `without_x` | BOOLEAN | YES |  | False |  |
| `final_playoffs` | BOOLEAN | YES |  | True |  |
| `scoring_policy` | VARCHAR(50) | NO |  | classic |  |
| `has_handicap` | BOOLEAN | NO |  | False |  |
| `is_active` | BOOLEAN | YES |  | True |  |
| `created_at` | DATETIME | YES |  | func |  |
| `updated_at` | DATETIME | YES |  | func |  |
| `terminated_at` | DATETIME | YES |  |  |  |
| `is_deleted` | BOOLEAN | YES |  | False |  |
| `deleted_at` | DATETIME | YES |  |  |  |
| `deleted_reason` | VARCHAR(255) | YES |  |  |  |

**Foreign Keys:**
- `default_venue_id` → `billiard_hall.id` (ON DELETE NO ACTION)

### gara

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `deleted_reason` | VARCHAR(255) | YES |  |  |  |
| `campionato_id` | INTEGER | YES | FK→campionato.id |  |  |
| `director_id` | INTEGER | YES | FK→user.id |  |  |
| `number` | INTEGER | NO |  |  |  |
| `name` | VARCHAR(100) | YES |  |  |  |
| `public_token` | VARCHAR(32) | YES | UQ | func |  |
| `date` | DATE | NO |  |  |  |
| `time` | TIME | YES |  |  |  |
| `created_at` | DATETIME | YES |  | func |  |
| `billiard_hall_id` | INTEGER | YES | FK→billiard_hall.id |  |  |
| `location` | VARCHAR(200) | YES |  |  |  |
| `available_tables` | TEXT | YES |  |  |  |
| `assign_tables_by_ranking` | BOOLEAN | NO |  | False |  |
| `description` | TEXT | YES |  |  |  |
| `rounds_count` | INTEGER | NO |  | 3 |  |
| `min_participants` | INTEGER | YES |  | 6 |  |
| `max_participants` | INTEGER | YES |  |  |  |
| `entry_fee` | FLOAT | YES |  | 0.0 |  |
| `discipline` | VARCHAR(50) | NO |  |  |  |
| `distance` | INTEGER | NO |  |  |  |
| `is_race_to` | BOOLEAN | YES |  | False |  |
| `is_multi_set` | BOOLEAN | NO |  | False |  |
| `match_distance` | INTEGER | YES |  |  |  |
| `is_race_to_sets` | BOOLEAN | YES |  | True |  |
| `has_handicap` | BOOLEAN | YES |  |  |  |
| `start_rule` | VARCHAR(20) | YES |  |  |  |
| `break_rule` | VARCHAR(20) | YES |  |  |  |
| `inscription_start` | DATETIME | YES |  |  |  |
| `inscription_end` | DATETIME | YES |  |  |  |
| `status` | VARCHAR(20) | YES |  | setup |  |
| `current_round` | INTEGER | YES |  | 0 |  |
| `withdraw_policy` | VARCHAR(10) | NO |  | Forfeit |  |
| `classification_system` | VARCHAR(10) | NO |  | WINS |  |
| `matchmaking_strategy` | VARCHAR(50) | NO |  | amalfi |  |
| `first_round_policy` | VARCHAR(50) | YES |  | random |  |
| `odd_number_policy` | VARCHAR(50) | YES |  | bye |  |
| `anti_rematch_enabled` | BOOLEAN | YES |  | True |  |
| `bye_to_last_inscribed` | BOOLEAN | NO |  | False |  |
| `separate_teammates` | BOOLEAN | NO |  | False |  |
| `third_place_match` | BOOLEAN | NO |  | False |  |
| `draw_seed` | INTEGER | YES |  |  |  |
| `seeding_rating` | VARCHAR(16) | NO |  | elo |  |
| `double_ko_rounds` | INTEGER | YES |  |  |  |
| `tiebreaker_enabled` | BOOLEAN | YES |  | True |  |
| `tiebreaker_until_position` | INTEGER | YES |  | 3 |  |
| `tiebreaker_mode` | VARCHAR(20) | YES |  | playoff_match |  |
| `tiebreaker_challenge_id` | INTEGER | YES | FK→challenge.id |  |  |
| `x_challenge_id` | INTEGER | YES | FK→challenge.id |  |  |
| `weight` | INTEGER | NO |  | 1 |  |
| `playoff_config_id` | INTEGER | YES | FK→playoff_configuration.id |  |  |
| `deleted_at` | DATETIME | YES |  |  |  |

**Constraints:**
- UNIQUE(public_token)

**Foreign Keys:**
- `tiebreaker_challenge_id` → `challenge.id` (ON DELETE SET NULL)
- `campionato_id` → `campionato.id` (ON DELETE CASCADE)
- `billiard_hall_id` → `billiard_hall.id` (ON DELETE SET NULL)
- `x_challenge_id` → `challenge.id` (ON DELETE SET NULL)
- `playoff_config_id` → `playoff_configuration.id` (ON DELETE SET NULL)
- `director_id` → `user.id` (ON DELETE NO ACTION)

### inscription

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `gara_id` | INTEGER | NO | FK→gara.id |  |  |
| `created_at` | DATETIME | YES |  | func |  |
| `initial_order` | INTEGER | YES |  |  |  |
| `is_withdrawn` | BOOLEAN | NO |  | False |  |
| `withdrawn_at` | DATETIME | YES |  |  |  |
| `is_forfeit` | BOOLEAN | NO |  | False |  |
| `forfeit_at` | DATETIME | YES |  |  |  |
| `is_waitlist` | BOOLEAN | NO |  | False |  |
| `waitlist_position` | INTEGER | YES |  |  |  |
| `waitlist_reason` | VARCHAR(20) | YES |  |  |  |
| `squadra_id` | INTEGER | YES | FK→squadra.id |  |  |
| `categoria_id` | INTEGER | YES | FK→categoria.id |  |  |

**Foreign Keys:**
- `categoria_id` → `categoria.id` (ON DELETE SET NULL)
- `user_id` → `user.id` (ON DELETE NO ACTION)
- `squadra_id` → `squadra.id` (ON DELETE SET NULL)
- `gara_id` → `gara.id` (ON DELETE CASCADE)

### round_configuration

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `gara_id` | INTEGER | NO | FK→gara.id |  |  |
| `round_number` | INTEGER | NO |  |  |  |
| `discipline` | VARCHAR(50) | YES |  |  |  |
| `distance` | INTEGER | YES |  |  |  |
| `is_race_to` | BOOLEAN | YES |  |  |  |
| `is_multi_set` | BOOLEAN | YES |  |  |  |
| `match_distance` | INTEGER | YES |  |  |  |
| `is_race_to_sets` | BOOLEAN | YES |  |  |  |
| `best_of` | BOOLEAN | YES |  |  |  |
| `notes` | TEXT | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(gara_id, round_number)

**Foreign Keys:**
- `gara_id` → `gara.id` (ON DELETE CASCADE)

---

## Match & Scoring

### match

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `gara_id` | INTEGER | YES | FK→gara.id |  |  |
| `round_number` | INTEGER | NO |  |  |  |
| `player1_id` | INTEGER | YES | FK→user.id |  |  |
| `player2_id` | INTEGER | YES | FK→user.id |  |  |
| `is_bye` | BOOLEAN | YES |  | False |  |
| `player1_score` | INTEGER | YES |  | 0 |  |
| `player2_score` | INTEGER | YES |  | 0 |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `match_distance` | INTEGER | YES |  | 1 |  |
| `is_multi_set` | BOOLEAN | YES |  | False |  |
| `is_race_to` | BOOLEAN | YES |  |  |  |
| `is_race_to_sets` | BOOLEAN | YES |  |  |  |
| `current_set_number` | INTEGER | YES |  | 1 |  |
| `discipline` | VARCHAR(50) | YES |  |  |  |
| `status` | VARCHAR(20) | YES |  | pending |  |
| `is_locked` | BOOLEAN | YES |  | False |  |
| `round_locked` | BOOLEAN | YES |  | False |  |
| `created_at` | DATETIME | YES |  | func |  |
| `is_trio` | BOOLEAN | YES |  | False |  |
| `bracket_type` | VARCHAR(8) | YES |  |  |  |
| `bracket_round` | INTEGER | YES |  |  |  |
| `bracket_slot` | INTEGER | YES |  |  |  |
| `bracket_group` | INTEGER | YES |  |  |  |
| `started_at` | DATETIME | YES |  |  |  |
| `ended_at` | DATETIME | YES |  |  |  |
| `table_assignment` | VARCHAR(10) | YES |  |  |  |
| `lag_winner_id` | INTEGER | YES | FK→user.id |  |  |
| `first_break_player_id` | INTEGER | YES | FK→user.id |  |  |
| `has_handicap` | BOOLEAN | YES |  |  |  |
| `player1_handicap` | INTEGER | YES |  | 0 |  |
| `player2_handicap` | INTEGER | YES |  | 0 |  |
| `handicap_explanation` | VARCHAR(255) | YES |  |  |  |
| `player1_confirmed` | BOOLEAN | NO |  | False |  |
| `player2_confirmed` | BOOLEAN | NO |  | False |  |
| `player1_confirmed_at` | DATETIME | YES |  |  |  |
| `player2_confirmed_at` | DATETIME | YES |  |  |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `first_break_player_id` → `user.id` (ON DELETE NO ACTION)
- `gara_id` → `gara.id` (ON DELETE SET NULL)
- `player1_id` → `user.id` (ON DELETE NO ACTION)
- `lag_winner_id` → `user.id` (ON DELETE NO ACTION)
- `player2_id` → `user.id` (ON DELETE NO ACTION)
- `winner_id` → `user.id` (ON DELETE NO ACTION)

### rack

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `match_id` | INTEGER | NO | FK→match.id |  |  |
| `rack_number` | INTEGER | NO |  |  |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `break_player_id` | INTEGER | YES | FK→user.id |  |  |
| `is_run_out` | BOOLEAN | NO |  | False |  |
| `reported_by_id` | INTEGER | YES | FK→user.id |  |  |
| `confirmed_by_player` | BOOLEAN | YES |  | False |  |
| `validated_by_admin` | BOOLEAN | YES |  | False |  |
| `admin_note` | TEXT | YES |  |  |  |
| `created_at` | DATETIME | YES |  | func |  |
| `added_by_id` | INTEGER | YES | FK→user.id |  |  |
| `added_at` | DATETIME | YES |  | func |  |
| `removed_by_id` | INTEGER | YES | FK→user.id |  |  |
| `removed_at` | DATETIME | YES |  |  |  |
| `is_deleted` | BOOLEAN | NO |  | False |  |

**Foreign Keys:**
- `winner_id` → `user.id` (ON DELETE NO ACTION)
- `match_id` → `match.id` (ON DELETE CASCADE)
- `added_by_id` → `user.id` (ON DELETE NO ACTION)
- `break_player_id` → `user.id` (ON DELETE NO ACTION)
- `removed_by_id` → `user.id` (ON DELETE NO ACTION)
- `reported_by_id` → `user.id` (ON DELETE NO ACTION)

### match_result

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `match_id` | INTEGER | NO | FK→match.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `player1_score` | INTEGER | YES |  |  |  |
| `player2_score` | INTEGER | YES |  |  |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `created_at` | DATETIME | YES |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE NO ACTION)
- `winner_id` → `user.id` (ON DELETE NO ACTION)
- `match_id` → `match.id` (ON DELETE NO ACTION)

### trio_match

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `match_id` | INTEGER | NO | FK→match.id |  |  |
| `player1_id` | INTEGER | NO | FK→user.id |  |  |
| `player2_id` | INTEGER | NO | FK→user.id |  |  |
| `player3_id` | INTEGER | NO | FK→user.id |  |  |
| `current_player1_id` | INTEGER | YES | FK→user.id |  |  |
| `current_player2_id` | INTEGER | YES | FK→user.id |  |  |
| `waiting_player_id` | INTEGER | YES | FK→user.id |  |  |
| `bonus_applied` | BOOLEAN | YES |  | False |  |
| `is_completed` | BOOLEAN | YES |  | False |  |
| `awaiting_confirmation` | BOOLEAN | YES |  | False |  |
| `player1_confirmed` | BOOLEAN | YES |  | False |  |
| `player2_confirmed` | BOOLEAN | YES |  | False |  |
| `player3_confirmed` | BOOLEAN | YES |  | False |  |
| `forfeit_player_id` | INTEGER | YES | FK→user.id |  |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `created_at` | DATETIME | YES |  | func |  |

**Foreign Keys:**
- `match_id` → `match.id` (ON DELETE NO ACTION)
- `player1_id` → `user.id` (ON DELETE NO ACTION)
- `player3_id` → `user.id` (ON DELETE NO ACTION)
- `winner_id` → `user.id` (ON DELETE NO ACTION)
- `current_player1_id` → `user.id` (ON DELETE NO ACTION)
- `waiting_player_id` → `user.id` (ON DELETE NO ACTION)
- `current_player2_id` → `user.id` (ON DELETE NO ACTION)
- `player2_id` → `user.id` (ON DELETE NO ACTION)
- `forfeit_player_id` → `user.id` (ON DELETE NO ACTION)

### trio_rack

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `trio_match_id` | INTEGER | NO | FK→trio_match.id |  |  |
| `rack_number` | INTEGER | NO |  |  |  |
| `winner_id` | INTEGER | NO | FK→user.id |  |  |
| `player1_id` | INTEGER | NO | FK→user.id |  |  |
| `player2_id` | INTEGER | NO | FK→user.id |  |  |
| `waiting_player_id` | INTEGER | NO | FK→user.id |  |  |
| `added_by_id` | INTEGER | YES | FK→user.id |  |  |
| `created_at` | DATETIME | YES |  | func |  |
| `is_deleted` | BOOLEAN | NO |  | False |  |
| `removed_by_id` | INTEGER | YES | FK→user.id |  |  |
| `removed_at` | DATETIME | YES |  |  |  |

**Foreign Keys:**
- `player2_id` → `user.id` (ON DELETE NO ACTION)
- `trio_match_id` → `trio_match.id` (ON DELETE CASCADE)
- `added_by_id` → `user.id` (ON DELETE NO ACTION)
- `removed_by_id` → `user.id` (ON DELETE NO ACTION)
- `player1_id` → `user.id` (ON DELETE NO ACTION)
- `winner_id` → `user.id` (ON DELETE NO ACTION)
- `waiting_player_id` → `user.id` (ON DELETE NO ACTION)

### set

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `match_id` | INTEGER | NO | FK→match.id |  |  |
| `set_number` | INTEGER | NO |  |  |  |
| `distance` | INTEGER | NO |  | 5 |  |
| `is_race_to` | BOOLEAN | NO |  | True |  |
| `player1_racks` | INTEGER | NO |  | 0 |  |
| `player2_racks` | INTEGER | NO |  | 0 |  |
| `status` | VARCHAR(20) | NO |  | pending |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `started_at` | DATETIME | YES |  |  |  |
| `completed_at` | DATETIME | YES |  |  |  |
| `discipline` | VARCHAR(50) | YES |  |  |  |
| `is_multi_discipline` | BOOLEAN | NO |  | False |  |
| `discipline_rotation` | JSON | YES |  |  |  |
| `discipline_assignment` | JSON | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(match_id, set_number)

**Foreign Keys:**
- `match_id` → `match.id` (ON DELETE CASCADE)
- `winner_id` → `user.id` (ON DELETE NO ACTION)

### set_rack

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `set_id` | INTEGER | NO | FK→set.id |  |  |
| `rack_number` | INTEGER | NO |  |  |  |
| `winner_id` | INTEGER | NO | FK→user.id |  |  |
| `break_player_id` | INTEGER | YES | FK→user.id |  |  |
| `discipline_override` | VARCHAR(50) | YES |  |  |  |
| `notes` | TEXT | YES |  |  |  |
| `reported_by_id` | INTEGER | YES | FK→user.id |  |  |
| `confirmed_by_player` | BOOLEAN | NO |  | False |  |
| `validated_by_admin` | BOOLEAN | NO |  | False |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(set_id, rack_number)

**Foreign Keys:**
- `set_id` → `set.id` (ON DELETE CASCADE)
- `break_player_id` → `user.id` (ON DELETE NO ACTION)
- `winner_id` → `user.id` (ON DELETE NO ACTION)
- `reported_by_id` → `user.id` (ON DELETE NO ACTION)

---

## Classification & Rankings

### classification

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `campionato_id` | INTEGER | NO | FK→campionato.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `position` | INTEGER | YES |  |  |  |
| `total_matches_won` | INTEGER | YES |  | 0 |  |
| `total_racks_won` | INTEGER | YES |  | 0 |  |
| `total_point_difference` | INTEGER | YES |  | 0 |  |
| `gare_played` | INTEGER | YES |  | 0 |  |
| `total_position_points` | INTEGER | YES |  | 0 |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE NO ACTION)
- `campionato_id` → `campionato.id` (ON DELETE CASCADE)

### gara_classification

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `gara_id` | INTEGER | NO | FK→gara.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `position` | INTEGER | NO |  |  |  |
| `matches_won` | INTEGER | YES |  | 0 |  |
| `matches_lost` | INTEGER | YES |  | 0 |  |
| `racks_won` | INTEGER | YES |  | 0 |  |
| `racks_lost` | INTEGER | YES |  | 0 |  |
| `rack_difference` | INTEGER | YES |  | 0 |  |
| `tied_with_player_ids` | JSON | YES |  |  |  |
| `tiebreaker_resolved` | BOOLEAN | YES |  | True |  |
| `spot_shot_wins` | INTEGER | YES |  | 0 |  |
| `campionato_points` | INTEGER | YES |  | 0 |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(gara_id, user_id)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE NO ACTION)
- `gara_id` → `gara.id` (ON DELETE CASCADE)

### round_classification

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `gara_id` | INTEGER | NO | FK→gara.id |  |  |
| `round_number` | INTEGER | NO |  |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `position` | INTEGER | NO |  |  |  |
| `matches_won` | INTEGER | YES |  | 0 |  |
| `rack_difference` | INTEGER | YES |  | 0 |  |
| `racks_won` | INTEGER | YES |  |  |  |
| `previous_position` | INTEGER | YES |  |  |  |
| `created_at` | DATETIME | YES |  | func |  |

**Constraints:**
- UNIQUE(gara_id, round_number, user_id)

**Foreign Keys:**
- `gara_id` → `gara.id` (ON DELETE CASCADE)
- `user_id` → `user.id` (ON DELETE NO ACTION)

### player_encounter

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `gara_id` | INTEGER | NO | FK→gara.id |  |  |
| `player1_id` | INTEGER | NO | FK→user.id |  |  |
| `player2_id` | INTEGER | NO | FK→user.id |  |  |
| `round_number` | INTEGER | NO |  |  |  |
| `created_at` | DATETIME | YES |  | func |  |

**Constraints:**
- CHECK: player1_id < player2_id
- UNIQUE(gara_id, player1_id, player2_id)

**Foreign Keys:**
- `player1_id` → `user.id` (ON DELETE NO ACTION)
- `gara_id` → `gara.id` (ON DELETE CASCADE)
- `player2_id` → `user.id` (ON DELETE NO ACTION)

### leaderboard_entry

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `leaderboard_type` | VARCHAR(17) | NO |  |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `rank` | INTEGER | NO |  |  |  |
| `score` | FLOAT | NO |  |  |  |
| `period_start` | DATE | YES |  |  |  |
| `period_end` | DATE | YES |  |  |  |
| `calculated_at` | DATETIME | NO |  | func |  |
| `is_stale` | BOOLEAN | NO |  | False |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)

---

## Playoff & Tiebreaker

### playoff_configuration

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `campionato_id` | INTEGER | NO | FK→campionato.id |  |  |
| `name` | VARCHAR(100) | NO |  |  |  |
| `playoff_type` | VARCHAR(14) | NO |  |  |  |
| `description` | TEXT | YES |  |  |  |
| `max_participants` | INTEGER | NO |  |  |  |
| `min_garas_played` | INTEGER | YES |  |  |  |
| `positions_from` | INTEGER | YES |  |  |  |
| `positions_to` | INTEGER | YES |  |  |  |
| `qualification_criteria` | TEXT | YES |  |  |  |
| `location` | VARCHAR(255) | YES |  |  |  |
| `scheduled_date` | DATETIME | YES |  |  |  |
| `entry_fee` | NUMERIC(10, 2) | YES |  |  |  |
| `is_active` | BOOLEAN | NO |  | True |  |
| `auto_generate` | BOOLEAN | NO |  | True |  |
| `response_deadline` | DATETIME | YES |  |  |  |
| `final_ranking_mode` | VARCHAR(32) | NO |  | campionato_plus_playoff |  |
| `playoff_weight` | INTEGER | NO |  | 1 |  |
| `discipline` | VARCHAR(50) | YES |  |  |  |
| `distance` | INTEGER | YES |  |  |  |
| `rounds_count` | INTEGER | YES |  |  |  |
| `strategy_type` | VARCHAR(50) | YES |  |  |  |
| `odd_number_policy` | VARCHAR(20) | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `campionato_id` → `campionato.id` (ON DELETE CASCADE)

### playoff_qualification

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `configuration_id` | INTEGER | NO | FK→playoff_configuration.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `qualifying_position` | INTEGER | NO |  |  |  |
| `qualification_reason` | VARCHAR(255) | NO |  |  |  |
| `status` | VARCHAR(9) | NO |  | QualificationStatus.PENDING |  |
| `invited_at` | DATETIME | YES |  |  |  |
| `expires_at` | DATETIME | YES |  |  |  |
| `responded_at` | DATETIME | YES |  |  |  |
| `responded_by_id` | INTEGER | YES | FK→user.id |  |  |
| `notified_at` | DATETIME | YES |  |  |  |
| `replaced_by_id` | INTEGER | YES | FK→user.id |  |  |
| `replacement_position` | INTEGER | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)
- `replaced_by_id` → `user.id` (ON DELETE NO ACTION)
- `responded_by_id` → `user.id` (ON DELETE NO ACTION)
- `configuration_id` → `playoff_configuration.id` (ON DELETE CASCADE)

### playoff_campionato

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `configuration_id` | INTEGER | NO | FK→playoff_configuration.id |  |  |
| `gara_id` | INTEGER | YES | FK→gara.id |  |  |
| `name` | VARCHAR(100) | NO |  |  |  |
| `status` | VARCHAR(20) | NO |  | setup |  |
| `registration_start` | DATETIME | YES |  |  |  |
| `registration_end` | DATETIME | YES |  |  |  |
| `campionato_date` | DATETIME | YES |  |  |  |
| `location` | VARCHAR(255) | YES |  |  |  |
| `entry_fee` | NUMERIC(10, 2) | YES |  |  |  |
| `max_participants` | INTEGER | NO |  |  |  |
| `confirmed_participants` | INTEGER | NO |  | 0 |  |
| `completed_at` | DATETIME | YES |  |  |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `winner_id` → `user.id` (ON DELETE NO ACTION)
- `gara_id` → `gara.id` (ON DELETE NO ACTION)
- `configuration_id` → `playoff_configuration.id` (ON DELETE CASCADE)

### playoff_match

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `tiebreaker_id` | INTEGER | NO | FK→tiebreaker.id |  |  |
| `match_number` | INTEGER | NO |  |  |  |
| `player1_id` | INTEGER | NO | FK→user.id |  |  |
| `player2_id` | INTEGER | NO | FK→user.id |  |  |
| `distance` | INTEGER | YES |  | 3 |  |
| `discipline` | VARCHAR(20) | YES |  | 8_ball |  |
| `player1_score` | INTEGER | YES |  | 0 |  |
| `player2_score` | INTEGER | YES |  | 0 |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `status` | VARCHAR(20) | YES |  | pending |  |
| `created_at` | DATETIME | YES |  | func |  |
| `started_at` | DATETIME | YES |  |  |  |
| `completed_at` | DATETIME | YES |  |  |  |

**Foreign Keys:**
- `player2_id` → `user.id` (ON DELETE NO ACTION)
- `player1_id` → `user.id` (ON DELETE NO ACTION)
- `winner_id` → `user.id` (ON DELETE NO ACTION)
- `tiebreaker_id` → `tiebreaker.id` (ON DELETE NO ACTION)

### tiebreaker

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `match_id` | INTEGER | NO | FK→match.id |  |  |
| `campionato_id` | INTEGER | YES | FK→campionato.id |  |  |
| `gara_id` | INTEGER | YES | FK→gara.id |  |  |
| `tiebreaker_type` | VARCHAR(20) | NO |  |  |  |
| `status` | VARCHAR(20) | YES |  | pending |  |
| `player1_id` | INTEGER | NO | FK→user.id |  |  |
| `player2_id` | INTEGER | NO | FK→user.id |  |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `created_at` | DATETIME | YES |  | func |  |
| `started_at` | DATETIME | YES |  |  |  |
| `completed_at` | DATETIME | YES |  |  |  |
| `configuration` | JSON | YES |  |  |  |
| `notes` | TEXT | YES |  |  |  |

**Foreign Keys:**
- `winner_id` → `user.id` (ON DELETE NO ACTION)
- `player1_id` → `user.id` (ON DELETE NO ACTION)
- `gara_id` → `gara.id` (ON DELETE NO ACTION)
- `player2_id` → `user.id` (ON DELETE NO ACTION)
- `match_id` → `match.id` (ON DELETE NO ACTION)
- `campionato_id` → `campionato.id` (ON DELETE NO ACTION)

### tiebreaker_configuration

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `campionato_id` | INTEGER | YES | FK→campionato.id |  |  |
| `gara_id` | INTEGER | YES | FK→gara.id |  |  |
| `name` | VARCHAR(100) | NO |  |  |  |
| `description` | TEXT | YES |  |  |  |
| `rules` | JSON | NO |  |  |  |
| `is_active` | BOOLEAN | YES |  | True |  |
| `is_default` | BOOLEAN | YES |  | False |  |
| `created_at` | DATETIME | YES |  | func |  |
| `updated_at` | DATETIME | YES |  | func |  |

**Foreign Keys:**
- `gara_id` → `gara.id` (ON DELETE NO ACTION)
- `campionato_id` → `campionato.id` (ON DELETE NO ACTION)

### spot_shot

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `tiebreaker_id` | INTEGER | NO | FK→tiebreaker.id |  |  |
| `round_number` | INTEGER | NO |  |  |  |
| `player_id` | INTEGER | NO | FK→user.id |  |  |
| `order_in_round` | INTEGER | NO |  |  |  |
| `result` | VARCHAR(10) | NO |  |  |  |
| `attempted_at` | DATETIME | YES |  | func |  |
| `notes` | TEXT | YES |  |  |  |

**Foreign Keys:**
- `player_id` → `user.id` (ON DELETE NO ACTION)
- `tiebreaker_id` → `tiebreaker.id` (ON DELETE NO ACTION)

### rally_attempt

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `tiebreaker_id` | INTEGER | NO | FK→tiebreaker.id |  |  |
| `player_id` | INTEGER | NO | FK→user.id |  |  |
| `sequence_number` | INTEGER | NO |  |  |  |
| `points_scored` | INTEGER | YES |  | 0 |  |
| `balls_pocketed` | INTEGER | YES |  | 0 |  |
| `was_successful` | BOOLEAN | YES |  | False |  |
| `ended_rally` | BOOLEAN | YES |  | False |  |
| `started_at` | DATETIME | YES |  | func |  |
| `completed_at` | DATETIME | YES |  |  |  |
| `notes` | TEXT | YES |  |  |  |

**Foreign Keys:**
- `player_id` → `user.id` (ON DELETE NO ACTION)
- `tiebreaker_id` → `tiebreaker.id` (ON DELETE NO ACTION)

---

## Challenge & Exam

### challenge

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `title` | VARCHAR(120) | YES |  |  |  |
| `description` | TEXT | NO |  |  |  |
| `image_path` | VARCHAR(255) | NO |  |  |  |
| `diagram_scene` | TEXT | YES |  |  |  |
| `pass_fail_only` | BOOLEAN | NO |  | False |  |
| `max_score` | INTEGER | YES |  |  |  |
| `created_by_id` | INTEGER | YES | FK→user.id |  |  |
| `is_active` | BOOLEAN | NO |  | True |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `created_by_id` → `user.id` (ON DELETE NO ACTION)

### challenge_attempt

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `challenge_id` | INTEGER | NO | FK→challenge.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `score` | INTEGER | YES |  |  |  |
| `passed` | BOOLEAN | YES |  |  |  |
| `completed` | BOOLEAN | NO |  | False |  |
| `attempted_at` | DATETIME | NO |  | func |  |
| `notes` | TEXT | YES |  |  |  |
| `gara_id` | INTEGER | YES | FK→gara.id |  |  |
| `round_number` | INTEGER | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)
- `challenge_id` → `challenge.id` (ON DELETE CASCADE)
- `gara_id` → `gara.id` (ON DELETE SET NULL)

### challenge_favorite

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `challenge_id` | INTEGER | NO | FK→challenge.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `favorited_at` | DATETIME | NO |  | func |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(challenge_id, user_id)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)
- `challenge_id` → `challenge.id` (ON DELETE CASCADE)

### gara_challenge

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `gara_id` | INTEGER | NO | FK→gara.id |  |  |
| `challenge_id` | INTEGER | NO | FK→challenge.id |  |  |
| `round_number` | INTEGER | NO |  |  |  |
| `max_attempts` | INTEGER | NO |  | 1 |  |
| `is_active` | BOOLEAN | NO |  | True |  |
| `added_by_id` | INTEGER | NO | FK→user.id |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(gara_id, challenge_id, round_number)

**Foreign Keys:**
- `challenge_id` → `challenge.id` (ON DELETE CASCADE)
- `gara_id` → `gara.id` (ON DELETE CASCADE)
- `added_by_id` → `user.id` (ON DELETE NO ACTION)

### gara_challenge_attempt

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `gara_challenge_id` | INTEGER | NO | FK→gara_challenge.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `attempt_number` | INTEGER | NO |  |  |  |
| `score` | INTEGER | YES |  |  |  |
| `passed` | BOOLEAN | YES |  |  |  |
| `completed` | BOOLEAN | NO |  | False |  |
| `attempted_at` | DATETIME | NO |  | func |  |
| `notes` | TEXT | YES |  |  |  |
| `round_when_attempted` | INTEGER | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(gara_challenge_id, user_id, attempt_number)

**Foreign Keys:**
- `gara_challenge_id` → `gara_challenge.id` (ON DELETE CASCADE)
- `user_id` → `user.id` (ON DELETE CASCADE)

### gara_challenge_classification

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `gara_id` | INTEGER | NO | FK→gara.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `position` | INTEGER | NO |  |  |  |
| `total_best_score` | INTEGER | NO |  | 0 |  |
| `total_all_attempts` | INTEGER | NO |  | 0 |  |
| `challenges_completed` | INTEGER | NO |  | 0 |  |
| `last_updated` | DATETIME | NO |  | func |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(gara_id, user_id)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)
- `gara_id` → `gara.id` (ON DELETE CASCADE)

### gara_bye_challenge

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `gara_id` | INTEGER | NO | FK→gara.id |  |  |
| `challenge_attempt_id` | INTEGER | YES | FK→challenge_attempt.id |  |  |
| `round_number` | INTEGER | NO |  |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `match_id` | INTEGER | YES | FK→match.id |  |  |
| `is_completed` | BOOLEAN | NO |  | False |  |
| `completed_at` | DATETIME | YES |  |  |  |
| `validated_by_id` | INTEGER | YES | FK→user.id |  |  |
| `validated_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(gara_id, user_id, round_number)

**Foreign Keys:**
- `validated_by_id` → `user.id` (ON DELETE SET NULL)
- `challenge_attempt_id` → `challenge_attempt.id` (ON DELETE SET NULL)
- `user_id` → `user.id` (ON DELETE CASCADE)
- `gara_id` → `gara.id` (ON DELETE CASCADE)
- `match_id` → `match.id` (ON DELETE SET NULL)

### exam

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `name` | VARCHAR(100) | NO |  |  |  |
| `description` | TEXT | YES |  |  |  |
| `examiner_id` | INTEGER | NO | FK→user.id |  |  |
| `is_active` | BOOLEAN | NO |  | True |  |
| `time_limit_minutes` | INTEGER | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `examiner_id` → `user.id` (ON DELETE NO ACTION)

### exam_examiner

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `exam_id` | INTEGER | NO | FK→exam.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `added_by_id` | INTEGER | NO | FK→user.id |  |  |
| `added_at` | DATETIME | NO |  | func |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(exam_id, user_id)

**Foreign Keys:**
- `exam_id` → `exam.id` (ON DELETE CASCADE)
- `user_id` → `user.id` (ON DELETE NO ACTION)
- `added_by_id` → `user.id` (ON DELETE NO ACTION)

### exam_challenge

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `exam_id` | INTEGER | NO | FK→exam.id |  |  |
| `challenge_id` | INTEGER | NO | FK→challenge.id |  |  |
| `order` | INTEGER | NO |  |  |  |
| `max_score` | INTEGER | YES |  |  |  |
| `max_attempts` | INTEGER | NO |  | 1 |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(exam_id, challenge_id)
- UNIQUE(exam_id, order)

**Foreign Keys:**
- `exam_id` → `exam.id` (ON DELETE CASCADE)
- `challenge_id` → `challenge.id` (ON DELETE CASCADE)

### exam_attempt

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `exam_id` | INTEGER | NO | FK→exam.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `mode` | VARCHAR(20) | NO |  | self_practice |  |
| `status` | VARCHAR(30) | NO |  | in_progress |  |
| `started_at` | DATETIME | NO |  | func |  |
| `completed_at` | DATETIME | YES |  |  |  |
| `passed` | BOOLEAN | YES |  |  |  |
| `total_score` | INTEGER | YES |  |  |  |
| `max_possible_score` | INTEGER | YES |  |  |  |
| `examiner_id` | INTEGER | YES | FK→user.id |  |  |
| `certified_at` | DATETIME | YES |  |  |  |
| `billiard_hall_id` | INTEGER | YES | FK→billiard_hall.id |  |  |
| `exam_request_id` | INTEGER | YES | FK→exam_request.id |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `exam_id` → `exam.id` (ON DELETE CASCADE)
- `user_id` → `user.id` (ON DELETE CASCADE)
- `exam_request_id` → `exam_request.id` (ON DELETE NO ACTION)
- `billiard_hall_id` → `billiard_hall.id` (ON DELETE NO ACTION)
- `examiner_id` → `user.id` (ON DELETE NO ACTION)

### exam_challenge_result

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `exam_attempt_id` | INTEGER | NO | FK→exam_attempt.id |  |  |
| `exam_challenge_id` | INTEGER | NO | FK→exam_challenge.id |  |  |
| `attempt_number` | INTEGER | NO |  | 1 |  |
| `score` | INTEGER | YES |  |  |  |
| `passed` | BOOLEAN | YES |  |  |  |
| `attempted_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(exam_attempt_id, exam_challenge_id, attempt_number)

**Foreign Keys:**
- `exam_challenge_id` → `exam_challenge.id` (ON DELETE CASCADE)
- `exam_attempt_id` → `exam_attempt.id` (ON DELETE CASCADE)

---

## Individual Match

### match_proposal

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `proposer_id` | INTEGER | NO | FK→user.id |  |  |
| `proposal_type` | VARCHAR(6) | NO |  |  |  |
| `status` | VARCHAR(9) | NO |  | ProposalStatus.PENDING |  |
| `billiard_hall_id` | INTEGER | YES | FK→billiard_hall.id |  |  |
| `location` | VARCHAR(255) | YES |  |  |  |
| `scheduled_at` | DATETIME | NO |  |  |  |
| `expires_at` | DATETIME | NO |  |  |  |
| `discipline` | VARCHAR(50) | YES |  | 8_ball |  |
| `distance` | INTEGER | YES |  | 5 |  |
| `is_race_to` | BOOLEAN | YES |  | True |  |
| `break_rule` | VARCHAR(20) | YES |  | alternate |  |
| `start_rule` | VARCHAR(20) | YES |  | first_player |  |
| `description` | TEXT | YES |  |  |  |
| `is_multi_set` | BOOLEAN | YES |  | False |  |
| `match_distance` | INTEGER | YES |  |  |  |
| `is_race_to_sets` | BOOLEAN | YES |  | True |  |
| `accepted_by_id` | INTEGER | YES | FK→user.id |  |  |
| `accepted_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `proposer_id` → `user.id` (ON DELETE CASCADE)
- `accepted_by_id` → `user.id` (ON DELETE SET NULL)
- `billiard_hall_id` → `billiard_hall.id` (ON DELETE SET NULL)

### proposal_invitation

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `proposal_id` | INTEGER | NO | FK→match_proposal.id |  |  |
| `invited_user_id` | INTEGER | NO | FK→user.id |  |  |
| `status` | VARCHAR(9) | NO |  | InvitationStatus.PENDING |  |
| `responded_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(proposal_id, invited_user_id)

**Foreign Keys:**
- `invited_user_id` → `user.id` (ON DELETE CASCADE)
- `proposal_id` → `match_proposal.id` (ON DELETE CASCADE)

### individual_match

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `proposal_id` | INTEGER | YES | FK→match_proposal.id |  |  |
| `player1_id` | INTEGER | NO | FK→user.id |  |  |
| `player2_id` | INTEGER | NO | FK→user.id |  |  |
| `billiard_hall_id` | INTEGER | YES | FK→billiard_hall.id |  |  |
| `location` | VARCHAR(255) | YES |  |  |  |
| `scheduled_at` | DATETIME | NO |  |  |  |
| `status` | VARCHAR(11) | NO |  | scheduled |  |
| `discipline` | VARCHAR(50) | NO |  | 8_ball |  |
| `distance` | INTEGER | YES |  |  |  |
| `is_race_to` | BOOLEAN | NO |  | True |  |
| `break_rule` | VARCHAR(20) | NO |  | alternate |  |
| `start_rule` | VARCHAR(20) | NO |  | first_player |  |
| `lag_winner_id` | INTEGER | YES | FK→user.id |  |  |
| `first_break_player_id` | INTEGER | YES | FK→user.id |  |  |
| `is_multi_set` | BOOLEAN | NO |  | False |  |
| `match_distance` | INTEGER | YES |  |  |  |
| `is_race_to_sets` | BOOLEAN | YES |  | True |  |
| `notes` | TEXT | YES |  |  |  |
| `started_at` | DATETIME | YES |  |  |  |
| `ended_at` | DATETIME | YES |  |  |  |
| `player1_score` | INTEGER | NO |  | 0 |  |
| `player2_score` | INTEGER | NO |  | 0 |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `player1_confirmed` | BOOLEAN | NO |  | False |  |
| `player2_confirmed` | BOOLEAN | NO |  | False |  |
| `player1_confirmed_at` | DATETIME | YES |  |  |  |
| `player2_confirmed_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(proposal_id)

**Foreign Keys:**
- `lag_winner_id` → `user.id` (ON DELETE NO ACTION)
- `proposal_id` → `match_proposal.id` (ON DELETE NO ACTION)
- `player2_id` → `user.id` (ON DELETE CASCADE)
- `player1_id` → `user.id` (ON DELETE CASCADE)
- `first_break_player_id` → `user.id` (ON DELETE NO ACTION)
- `billiard_hall_id` → `billiard_hall.id` (ON DELETE SET NULL)
- `winner_id` → `user.id` (ON DELETE NO ACTION)

### individual_rack

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `match_id` | INTEGER | NO | FK→individual_match.id |  |  |
| `individual_set_id` | INTEGER | YES | FK→individual_set.id |  |  |
| `rack_number` | INTEGER | NO |  |  |  |
| `winner_id` | INTEGER | NO | FK→user.id |  |  |
| `break_player_id` | INTEGER | YES | FK→user.id |  |  |
| `is_run_out` | BOOLEAN | NO |  | False |  |
| `notes` | TEXT | YES |  |  |  |
| `added_by_id` | INTEGER | YES | FK→user.id |  |  |
| `added_at` | DATETIME | YES |  | func |  |
| `removed_by_id` | INTEGER | YES | FK→user.id |  |  |
| `removed_at` | DATETIME | YES |  |  |  |
| `is_deleted` | BOOLEAN | NO |  | False |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(match_id, rack_number)

**Foreign Keys:**
- `added_by_id` → `user.id` (ON DELETE NO ACTION)
- `match_id` → `individual_match.id` (ON DELETE CASCADE)
- `removed_by_id` → `user.id` (ON DELETE NO ACTION)
- `break_player_id` → `user.id` (ON DELETE NO ACTION)
- `individual_set_id` → `individual_set.id` (ON DELETE CASCADE)
- `winner_id` → `user.id` (ON DELETE NO ACTION)

---

## Rating & Handicap

### player_rating

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `rating_system` | VARCHAR(10) | NO |  |  |  |
| `rating_value` | FLOAT | NO |  |  |  |
| `confidence` | FLOAT | YES |  |  |  |
| `robustness` | INTEGER | NO |  | 0 |  |
| `last_updated` | DATETIME | NO |  | func |  |
| `external_id` | VARCHAR(50) | YES |  |  |  |
| `verified` | BOOLEAN | NO |  | False |  |
| `verified_by_id` | INTEGER | YES | FK→user.id |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, rating_system)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)
- `verified_by_id` → `user.id` (ON DELETE NO ACTION)

---

## Gamification

### user_level

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `user_id` | INTEGER | NO | PK, FK→user.id |  |  |
| `current_level` | INTEGER | NO |  | 1 |  |
| `current_xp` | INTEGER | NO |  | 0 |  |
| `total_xp` | INTEGER | NO |  | 0 |  |
| `highest_level_reached` | INTEGER | NO |  | 1 |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)

### xp_transaction

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `transaction_type` | VARCHAR(22) | NO |  |  |  |
| `xp_amount` | INTEGER | NO |  |  |  |
| `reason` | VARCHAR(255) | YES |  |  |  |
| `level_before` | INTEGER | NO |  |  |  |
| `level_after` | INTEGER | NO |  |  |  |
| `related_entities` | TEXT | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)

### achievement

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `slug` | VARCHAR(100) | NO | UQ |  |  |
| `name` | VARCHAR(100) | NO |  |  |  |
| `description` | TEXT | NO |  |  |  |
| `icon_path` | VARCHAR(255) | YES |  |  |  |
| `category` | VARCHAR(11) | NO |  |  |  |
| `difficulty` | VARCHAR(9) | NO |  | AchievementDifficulty.COMMON |  |
| `requirements` | TEXT | NO |  |  |  |
| `is_progressive` | BOOLEAN | YES |  | False |  |
| `xp_reward` | INTEGER | NO |  | 0 |  |
| `is_hidden` | BOOLEAN | YES |  | False |  |
| `is_active` | BOOLEAN | YES |  | True |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(slug)

### user_achievement

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `achievement_id` | INTEGER | NO | FK→achievement.id |  |  |
| `current_progress` | INTEGER | NO |  | 0 |  |
| `is_unlocked` | BOOLEAN | NO |  | False |  |
| `unlocked_at` | DATETIME | YES |  |  |  |
| `is_displayed` | BOOLEAN | YES |  | True |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, achievement_id)

**Foreign Keys:**
- `achievement_id` → `achievement.id` (ON DELETE CASCADE)
- `user_id` → `user.id` (ON DELETE CASCADE)

### streak_tracker

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `user_id` | INTEGER | NO | PK, FK→user.id |  |  |
| `streak_type` | VARCHAR(17) | NO | PK |  |  |
| `current_streak` | INTEGER | NO |  | 0 |  |
| `longest_streak` | INTEGER | NO |  | 0 |  |
| `last_activity_week` | INTEGER | YES |  |  |  |
| `last_activity_year` | INTEGER | YES |  |  |  |
| `freeze_count` | INTEGER | NO |  | 0 |  |
| `total_freeze_earned` | INTEGER | NO |  | 0 |  |
| `last_freeze_earned_at` | DATE | YES |  |  |  |
| `last_freeze_used_at` | DATE | YES |  |  |  |
| `milestone_4_reached` | BOOLEAN | YES |  | False |  |
| `milestone_12_reached` | BOOLEAN | YES |  | False |  |
| `milestone_52_reached` | BOOLEAN | YES |  | False |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)

### streak_milestone

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `weeks` | INTEGER | NO | UQ |  |  |
| `freeze_tokens` | INTEGER | NO |  | 1 |  |
| `xp_bonus_multiplier` | INTEGER | NO |  | 1 |  |
| `is_recurring` | BOOLEAN | NO |  | False |  |
| `is_active` | BOOLEAN | NO |  | True |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(weeks)

### quest

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `name` | VARCHAR(100) | NO |  |  |  |
| `description` | TEXT | NO |  |  |  |
| `quest_type` | VARCHAR(13) | NO |  |  |  |
| `status` | VARCHAR(9) | NO |  | QuestStatus.UPCOMING |  |
| `start_date` | DATETIME | NO |  |  |  |
| `end_date` | DATETIME | NO |  |  |  |
| `requirements` | TEXT | NO |  |  |  |
| `xp_reward` | INTEGER | NO |  | 150 |  |
| `badge_icon` | VARCHAR(255) | YES |  |  |  |
| `participant_count` | INTEGER | NO |  | 0 |  |
| `completion_count` | INTEGER | NO |  | 0 |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

### quest_participation

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `quest_id` | INTEGER | NO | FK→quest.id |  |  |
| `current_progress` | INTEGER | NO |  | 0 |  |
| `target_progress` | INTEGER | NO |  |  |  |
| `is_completed` | BOOLEAN | NO |  | False |  |
| `completed_at` | DATETIME | YES |  |  |  |
| `xp_awarded` | INTEGER | NO |  | 0 |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, quest_id)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)
- `quest_id` → `quest.id` (ON DELETE CASCADE)

### gamification_config

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `key` | VARCHAR(50) | NO | PK |  |  |
| `value` | INTEGER | NO |  |  |  |
| `description` | VARCHAR(255) | YES |  |  |  |
| `category` | VARCHAR(50) | NO |  | general |  |
| `updated_by_id` | INTEGER | YES | FK→user.id |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `updated_by_id` → `user.id` (ON DELETE NO ACTION)

### level_unlock

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `level` | INTEGER | NO | UQ |  |  |
| `feature_code` | VARCHAR(50) | NO |  |  |  |
| `feature_name` | VARCHAR(100) | NO |  |  |  |
| `description` | VARCHAR(255) | YES |  |  |  |
| `is_active` | BOOLEAN | NO |  | True |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(level)

---

## Notification

### notification

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `notification_type` | VARCHAR(24) | NO |  |  |  |
| `title` | VARCHAR(255) | NO |  |  |  |
| `message` | TEXT | NO |  |  |  |
| `priority` | VARCHAR(6) | NO |  | NotificationPriority.NORMAL |  |
| `status` | VARCHAR(9) | NO |  | NotificationStatus.PENDING |  |
| `sent_at` | DATETIME | YES |  |  |  |
| `read_at` | DATETIME | YES |  |  |  |
| `expires_at` | DATETIME | YES |  |  |  |
| `related_entities` | TEXT | YES |  |  |  |
| `action_url` | VARCHAR(255) | YES |  |  |  |
| `action_text` | VARCHAR(100) | YES |  |  |  |
| `delivery_attempts` | INTEGER | NO |  | 0 |  |
| `last_attempt_at` | DATETIME | YES |  |  |  |
| `template_key` | VARCHAR(100) | YES |  |  |  |
| `template_params` | TEXT | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)

### notification_preference

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `notification_type` | VARCHAR(24) | NO |  |  |  |
| `enabled` | BOOLEAN | NO |  | True |  |
| `email_enabled` | BOOLEAN | NO |  | False |  |
| `push_enabled` | BOOLEAN | NO |  | True |  |
| `quiet_hours_start` | TIME | YES |  |  |  |
| `quiet_hours_end` | TIME | YES |  |  |  |
| `max_per_day` | INTEGER | YES |  |  |  |
| `min_interval_minutes` | INTEGER | YES |  |  |  |
| `auto_delete_days` | INTEGER | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, notification_type)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)

### notification_template

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `notification_type` | VARCHAR(24) | NO | UQ |  |  |
| `title_template` | VARCHAR(255) | NO |  |  |  |
| `message_template` | TEXT | NO |  |  |  |
| `default_priority` | VARCHAR(6) | NO |  | NotificationPriority.NORMAL |  |
| `default_expires_hours` | INTEGER | YES |  |  |  |
| `action_text_template` | VARCHAR(100) | YES |  |  |  |
| `action_url_template` | VARCHAR(255) | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(notification_type)

---

## Location

### billiard_hall

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `name` | VARCHAR(255) | NO |  |  |  |
| `address` | TEXT | YES |  |  |  |
| `city` | VARCHAR(100) | YES |  |  |  |
| `province` | VARCHAR(2) | YES |  |  |  |
| `postal_code` | VARCHAR(20) | YES |  |  |  |
| `country` | VARCHAR(100) | NO |  | Italy |  |
| `phone` | VARCHAR(50) | YES |  |  |  |
| `email` | VARCHAR(255) | YES |  |  |  |
| `website` | VARCHAR(255) | YES |  |  |  |
| `number_of_tables` | INTEGER | YES |  |  |  |
| `table_names` | TEXT | YES |  |  |  |
| `table_types` | TEXT | YES |  |  |  |
| `amenities` | TEXT | YES |  |  |  |
| `business_hours` | TEXT | YES |  |  |  |
| `hourly_rate` | NUMERIC(10, 2) | YES |  |  |  |
| `currency` | VARCHAR(3) | NO |  | EUR |  |
| `is_active` | BOOLEAN | NO |  | True |  |
| `verified` | BOOLEAN | NO |  | False |  |
| `added_by_id` | INTEGER | YES | FK→user.id |  |  |
| `latitude` | FLOAT | YES |  |  |  |
| `longitude` | FLOAT | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `added_by_id` → `user.id` (ON DELETE NO ACTION)

### user_location_availability

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `billiard_hall_id` | INTEGER | NO | FK→billiard_hall.id |  |  |
| `is_available` | BOOLEAN | NO |  | True |  |
| `available_days` | VARCHAR(20) | YES |  |  |  |
| `preferred_time_start` | TIME | YES |  |  |  |
| `preferred_time_end` | TIME | YES |  |  |  |
| `notify_on_proposals` | BOOLEAN | NO |  | True |  |
| `notify_on_cancellations` | BOOLEAN | NO |  | True |  |
| `advance_notice_hours` | INTEGER | NO |  | 24 |  |
| `max_distance_km` | FLOAT | YES |  |  |  |
| `matches_played_here` | INTEGER | NO |  | 0 |  |
| `last_played_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, billiard_hall_id)

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)
- `billiard_hall_id` → `billiard_hall.id` (ON DELETE CASCADE)

---

## KPI & Analytics

### kpi_daily_snapshot

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `date` | DATE | NO | UQ |  |  |
| `total_users` | INTEGER | YES |  | 0 |  |
| `new_users` | INTEGER | YES |  | 0 |  |
| `active_users` | INTEGER | YES |  | 0 |  |
| `total_matches` | INTEGER | YES |  | 0 |  |
| `new_matches` | INTEGER | YES |  | 0 |  |
| `total_gare` | INTEGER | YES |  | 0 |  |
| `active_gare` | INTEGER | YES |  | 0 |  |
| `completed_gare` | INTEGER | YES |  | 0 |  |
| `total_xp_awarded` | INTEGER | YES |  | 0 |  |
| `avg_user_level` | FLOAT | YES |  | 0.0 |  |
| `retention_7d` | FLOAT | YES |  | 0.0 |  |
| `retention_30d` | FLOAT | YES |  | 0.0 |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(date)

### kpi_feature_usage

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `feature_name` | VARCHAR(100) | NO |  |  |  |
| `date` | DATE | NO |  |  |  |
| `usage_count` | INTEGER | YES |  | 0 |  |
| `unique_users` | INTEGER | YES |  | 0 |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(feature_name, date)

### kpi_milestone

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `milestone_type` | VARCHAR(50) | NO |  |  |  |
| `milestone_value` | INTEGER | NO |  |  |  |
| `reached_at` | DATETIME | YES |  | func |  |
| `notification_sent` | BOOLEAN | YES |  | False |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(milestone_type, milestone_value)

---

## System

---

## Other Tables

### categoria

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `name` | VARCHAR(50) | NO |  |  |  |
| `normalized_name` | VARCHAR(50) | NO |  |  |  |
| `campionato_id` | INTEGER | YES | FK→campionato.id |  |  |
| `gara_id` | INTEGER | YES | FK→gara.id |  |  |
| `is_active` | BOOLEAN | NO |  | True |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(gara_id, normalized_name)
- CHECK: (campionato_id IS NOT NULL AND gara_id IS NULL) OR (campionato_id IS NULL AND gara_id IS NOT NULL)
- UNIQUE(campionato_id, normalized_name)

**Foreign Keys:**
- `gara_id` → `gara.id` (ON DELETE CASCADE)
- `campionato_id` → `campionato.id` (ON DELETE CASCADE)

### demand_signal

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `latitude` | FLOAT | NO |  |  |  |
| `longitude` | FLOAT | NO |  |  |  |
| `city` | VARCHAR(100) | YES |  |  |  |
| `status` | VARCHAR(20) | NO |  | active |  |
| `expires_at` | DATETIME | NO |  |  |  |
| `reminded_at` | DATETIME | YES |  |  |  |
| `consumed_by_gara_id` | INTEGER | YES | FK→gara.id |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `consumed_by_gara_id` → `gara.id` (ON DELETE SET NULL)
- `user_id` → `user.id` (ON DELETE CASCADE)

### exam_request

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `exam_id` | INTEGER | NO | FK→exam.id |  |  |
| `requester_id` | INTEGER | NO | FK→user.id |  |  |
| `status` | VARCHAR(20) | NO |  | negotiating |  |
| `billiard_hall_id` | INTEGER | NO | FK→billiard_hall.id |  |  |
| `scheduled_at` | DATETIME | NO |  |  |  |
| `expires_at` | DATETIME | NO |  |  |  |
| `last_proposed_by_id` | INTEGER | NO | FK→user.id |  |  |
| `negotiating_with_id` | INTEGER | YES | FK→user.id |  |  |
| `accepted_by_id` | INTEGER | YES | FK→user.id |  |  |
| `accepted_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `accepted_by_id` → `user.id` (ON DELETE NO ACTION)
- `last_proposed_by_id` → `user.id` (ON DELETE NO ACTION)
- `exam_id` → `exam.id` (ON DELETE CASCADE)
- `requester_id` → `user.id` (ON DELETE NO ACTION)
- `negotiating_with_id` → `user.id` (ON DELETE NO ACTION)
- `billiard_hall_id` → `billiard_hall.id` (ON DELETE NO ACTION)

### exam_request_recipient

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `request_id` | INTEGER | NO | FK→exam_request.id |  |  |
| `examiner_id` | INTEGER | NO | FK→user.id |  |  |
| `status` | VARCHAR(20) | NO |  | pending |  |
| `responded_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(request_id, examiner_id)

**Foreign Keys:**
- `request_id` → `exam_request.id` (ON DELETE CASCADE)
- `examiner_id` → `user.id` (ON DELETE NO ACTION)

### exam_time_proposal

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `request_id` | INTEGER | NO | FK→exam_request.id |  |  |
| `proposed_by_id` | INTEGER | NO | FK→user.id |  |  |
| `scheduled_at` | DATETIME | NO |  |  |  |
| `billiard_hall_id` | INTEGER | NO | FK→billiard_hall.id |  |  |
| `superseded_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `request_id` → `exam_request.id` (ON DELETE CASCADE)
- `proposed_by_id` → `user.id` (ON DELETE NO ACTION)
- `billiard_hall_id` → `billiard_hall.id` (ON DELETE NO ACTION)

### feature_config

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `code` | VARCHAR(50) | NO | PK |  |  |
| `name` | VARCHAR(100) | NO |  |  |  |
| `description` | TEXT | YES |  |  |  |
| `rules` | TEXT | NO |  | [] |  |
| `is_active` | BOOLEAN | YES |  | True |  |
| `badge_slug` | VARCHAR(100) | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

### individual_set

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `match_id` | INTEGER | NO | FK→individual_match.id |  |  |
| `set_number` | INTEGER | NO |  |  |  |
| `distance` | INTEGER | NO |  |  |  |
| `is_race_to` | BOOLEAN | NO |  | True |  |
| `player1_racks` | INTEGER | NO |  | 0 |  |
| `player2_racks` | INTEGER | NO |  | 0 |  |
| `status` | VARCHAR(20) | NO |  | pending |  |
| `winner_id` | INTEGER | YES | FK→user.id |  |  |
| `started_at` | DATETIME | YES |  |  |  |
| `completed_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(match_id, set_number)

**Foreign Keys:**
- `match_id` → `individual_match.id` (ON DELETE CASCADE)
- `winner_id` → `user.id` (ON DELETE NO ACTION)

### match_rating_history

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `match_id` | INTEGER | YES | FK→match.id |  |  |
| `individual_match_id` | INTEGER | YES | FK→individual_match.id |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `rating_system` | VARCHAR(10) | NO |  |  |  |
| `old_rating` | FLOAT | NO |  |  |  |
| `new_rating` | FLOAT | NO |  |  |  |
| `delta` | FLOAT | NO |  |  |  |
| `robustness_increment` | INTEGER | NO |  | 1 |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `match_id` → `match.id` (ON DELETE CASCADE)
- `individual_match_id` → `individual_match.id` (ON DELETE CASCADE)
- `user_id` → `user.id` (ON DELETE CASCADE)

### role_grant

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `role` | VARCHAR(30) | NO |  |  |  |
| `granted_by_id` | INTEGER | NO | FK→user.id |  |  |
| `granted_at` | DATETIME | NO |  | func |  |
| `revoked_at` | DATETIME | YES |  |  |  |
| `revoked_by_id` | INTEGER | YES | FK→user.id |  |  |
| `notes` | TEXT | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `revoked_by_id` → `user.id` (ON DELETE NO ACTION)
- `user_id` → `user.id` (ON DELETE NO ACTION)
- `granted_by_id` → `user.id` (ON DELETE NO ACTION)

### role_request

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `role` | VARCHAR(30) | NO |  |  |  |
| `status` | VARCHAR(20) | NO |  | pending |  |
| `requested_at` | DATETIME | NO |  | func |  |
| `notes` | TEXT | YES |  |  |  |
| `processed_at` | DATETIME | YES |  |  |  |
| `processed_by_id` | INTEGER | YES | FK→user.id |  |  |
| `decision_notes` | TEXT | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `processed_by_id` → `user.id` (ON DELETE NO ACTION)
- `user_id` → `user.id` (ON DELETE NO ACTION)

### role_request_recipient

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `request_id` | INTEGER | NO | FK→role_request.id |  |  |
| `recipient_id` | INTEGER | NO | FK→user.id |  |  |
| `status` | VARCHAR(20) | NO |  | pending |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(request_id, recipient_id)

**Foreign Keys:**
- `request_id` → `role_request.id` (ON DELETE NO ACTION)
- `recipient_id` → `user.id` (ON DELETE NO ACTION)

### squadra

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `name` | VARCHAR(100) | NO |  |  |  |
| `normalized_name` | VARCHAR(100) | NO |  |  |  |
| `campionato_id` | INTEGER | YES | FK→campionato.id |  |  |
| `gara_id` | INTEGER | YES | FK→gara.id |  |  |
| `is_active` | BOOLEAN | NO |  | True |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- CHECK: (campionato_id IS NOT NULL AND gara_id IS NULL) OR (campionato_id IS NULL AND gara_id IS NOT NULL)
- UNIQUE(gara_id, normalized_name)
- UNIQUE(campionato_id, normalized_name)

**Foreign Keys:**
- `gara_id` → `gara.id` (ON DELETE CASCADE)
- `campionato_id` → `campionato.id` (ON DELETE CASCADE)

### tpa_comando

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `referto_id` | INTEGER | NO | FK→tpa_referto.id |  |  |
| `sequence` | INTEGER | NO |  |  |  |
| `command` | VARCHAR(16) | NO |  |  |  |
| `pressed_at` | DATETIME | NO |  | func |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(referto_id, sequence)

**Foreign Keys:**
- `referto_id` → `tpa_referto.id` (ON DELETE CASCADE)

### tpa_referto

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `individual_match_id` | INTEGER | NO | FK→individual_match.id, UQ |  |  |
| `compiler_id` | INTEGER | NO | FK→user.id |  |  |
| `game_type` | INTEGER | NO |  |  |  |
| `closed_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(individual_match_id)

**Foreign Keys:**
- `compiler_id` → `user.id` (ON DELETE NO ACTION)
- `individual_match_id` → `individual_match.id` (ON DELETE CASCADE)

### user_feature_usage

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `feature_code` | VARCHAR(50) | NO | FK→feature_config.code |  |  |
| `usage_count` | INTEGER | YES |  | 0 |  |
| `last_used_at` | DATETIME | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Constraints:**
- UNIQUE(user_id, feature_code)

**Foreign Keys:**
- `feature_code` → `feature_config.code` (ON DELETE CASCADE)
- `user_id` → `user.id` (ON DELETE CASCADE)

### user_session

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `started_at` | DATETIME | NO |  | func |  |
| `last_seen_at` | DATETIME | NO |  | func |  |
| `ended_at` | DATETIME | YES |  |  |  |
| `device` | VARCHAR(16) | YES |  |  |  |
| `created_at` | DATETIME | NO |  | func |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE CASCADE)

### user_token

| Column | Type | Nullable | Key | Default | Description |
|--------|------|----------|-----|---------|-------------|
| `id` | INTEGER | NO | PK |  |  |
| `user_id` | INTEGER | NO | FK→user.id |  |  |
| `token` | VARCHAR(100) | NO | UQ |  |  |
| `token_type` | VARCHAR(20) | NO |  |  |  |
| `created_at` | DATETIME | YES |  | func |  |
| `expires_at` | DATETIME | NO |  |  |  |
| `is_used` | BOOLEAN | YES |  | False |  |
| `updated_at` | DATETIME | NO |  | func |  |

**Foreign Keys:**
- `user_id` → `user.id` (ON DELETE NO ACTION)

---

## Summary

- **Total tables**: 85
- **Domains**: 13
