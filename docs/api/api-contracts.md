# API Contracts — Inventario Completo Endpoint

> **Snapshot del 2026-04-04** (BMad full-scan). I conteggi e gli URL listati riflettono lo stato di quella data; **per la lista corrente di endpoint visibili in produzione vedere [`docs/reference/PRODUCTION_INVENTORY.md`](../reference/PRODUCTION_INVENTORY.md) e la matrice ruoli in `utils/feature_flags.ENDPOINT_ROLES`** ([ADR-028](../adr/ADR-028-production-endpoint-allowlist.md)).
> **275 endpoint totali** (al 2026-04-04) | 10 blueprint principali + 8 sotto-blueprint

---

## Riepilogo

| Blueprint | Prefisso | Endpoint | Accesso |
|-----------|----------|----------|---------|
| `main` | `/` | 14 | Pubblico + debug |
| `auth` | `/auth` | 6 | Pubblico (rate limited) |
| `dashboard` | `/dashboard` | 1 | Login |
| `i18n` | `/set_language` | 1 | Pubblico |
| `admin/campionato` | `/admin/campionato` | 12 | Director/Admin |
| `admin/competition` | `/admin/gara` | ~35 | Manager |
| `admin/match` | `/admin/match` | 1 | Login |
| `admin/user` | `/admin` | 10 | Admin |
| `admin/venue` | `/admin` | 15 | Admin/VenueManager |
| `admin/kpi` | `/admin/kpi` | 6 | Admin |
| `challenge` | `/challenges` | 12 | Director/Login |
| `rating` | `/rating` | 15 | Login/Director/Admin |
| `individual_match` | `/match` | 25 | Player/Director |
| `player` | `/player` | ~50 | Player/Login |
| `gamification` | `/gamification` | ~35 | Login/Admin |
| `sse` | `/sse` | 9 | Login |

---

## Blueprint: `main` (nessun prefisso)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/` | nessuna | Homepage (redirect a dashboard se autenticato) |
| GET | `/campionatos` | nessuna | Lista pubblica campionati |
| GET | `/campionato/<id>/public` | nessuna | Dettaglio campionato pubblico |
| GET | `/garas` | nessuna | Lista gare standalone pubbliche |
| GET | `/gara/<id>` | nessuna | Redirect a dettaglio gara unificato |
| GET | `/public/gara/<id>` | nessuna | Redirect a dettaglio gara unificato |
| GET | `/reset` | debug | Interfaccia reset database (solo DEBUG_MODE) |
| POST | `/reset/confirm` | debug | Conferma reset database |
| POST | `/reset/save` | debug | Salva snapshot database |
| POST | `/reset/delete/<snapshot_id>` | debug | Elimina snapshot |
| GET | `/debug/login/<username>` | debug | Login rapido (solo DEBUG_MODE) |
| GET | `/debug/create_player` | debug | Crea giocatore test |
| GET | `/debug/fill_gara/<id>` | debug | Riempi gara con giocatori |
| GET | `/debug/complete_current_round/<id>` | debug | Completa turno con risultati random |

---

## Blueprint: `auth` (prefisso: `/auth`)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET, POST | `/login` | nessuna | Login (rate: 10/min POST) |
| GET, POST | `/register` | nessuna | Registrazione (rate: 5/min POST) |
| GET, POST | `/logout` | login | Logout |
| GET | `/verify-email/<token>` | nessuna | Verifica email via token |
| GET, POST | `/forgot-password` | nessuna | Richiesta reset password (rate: 3/min) |
| GET, POST | `/reset-password/<token>` | nessuna | Form reset password |

---

## Blueprint: `admin/campionato` (prefisso: `/admin/campionato`)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/wizard` | director | Wizard creazione campionato step 1 |
| POST | `/wizard/step2` | director | Wizard step 2 |
| POST | `/wizard/create` | director | Crea campionato da wizard |
| GET, POST | `/wizard/cancel` | login | Annulla wizard |
| POST | `/create` | director | Creazione campionato (legacy) |
| GET | `/<id>` | manager | Dettaglio campionato |
| GET, POST | `/<id>/edit` | manager | Modifica campionato |
| POST | `/<id>/delete` | manager | Elimina campionato |
| POST | `/<id>/soft-delete` | admin | Soft-delete campionato |
| POST | `/<id>/toggle_active` | manager | Toggle stato attivo |
| POST | `/<id>/add_director` | manager | Aggiungi co-director |
| POST | `/<id>/remove_director` | manager | Rimuovi co-director |

---

## Blueprint: `admin/competition` (prefisso: `/admin/gara`)

### CRUD e Gestione Stato

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET, POST | `/create_standalone` | director | Crea gara standalone |
| POST | `/create` | director | Crea gara in campionato |
| GET | `/<id>` | qualsiasi | Dettaglio gara unificato (role-adaptive) |
| GET, POST | `/<id>/edit` | manager | Modifica gara |
| POST | `/<id>/delete` | manager | Elimina gara |
| POST | `/<id>/soft-delete` | admin | Soft-delete gara |
| POST | `/<id>/cancel` | manager | Annulla gara |
| POST | `/<id>/terminate` | manager | Termina gara |

### Iscrizioni

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| POST | `/<id>/open_inscriptions` | manager | Apri iscrizioni |
| POST | `/<id>/close_inscriptions` | manager | Chiudi iscrizioni |
| POST | `/<id>/modify_inscription_dates` | manager | Modifica date iscrizione |
| POST | `/<id>/admin_inscribe` | manager | Iscrivi giocatore (admin) |
| POST | `/<id>/admin_uninscribe/<user_id>` | manager | Rimuovi iscrizione (admin) |

### Turni

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| POST | `/<id>/start_first_round` | manager | Avvia primo turno |
| POST | `/<id>/start_round/<round_number>` | manager | Avvia turno specifico |
| POST | `/<id>/cancel_first_round` | manager | Annulla primo turno |
| POST | `/<id>/cancel_current_round` | manager | Annulla turno corrente |
| GET | `/<id>/round_status` | manager | Stato turno (JSON) |

### SSR (Swiss System Round)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| POST | `/<id>/start_ssr` | manager | Avvia turno Swiss System |
| POST | `/<id>/save_ssr_group` | manager | Salva raggruppamento SSR |
| POST | `/<id>/save_ssr_scores` | manager | Salva punteggi SSR |

### Sfide e Classifiche

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/<id>/challenge_classification` | login | Classifica sfide |
| GET | `/<id>/challenges` | login | Sfide disponibili |
| GET | `/challenges/available` | login | Tutte le sfide (JSON) |
| POST | `/challenges/create` | director | Crea sfida |
| POST | `/<id>/add_challenge` | manager | Aggiungi sfida al turno |
| POST | `/<id>/remove_challenge` | manager | Rimuovi sfida |
| GET | `/amalfi/classification/<id>/<round>` | login | Classifica Amalfi |
| GET | `/api/strategy_constraints/<strategy>` | admin | Vincoli strategia (JSON) |

### Match Trio

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| POST | `/trio/<id>/add_rack` | manager | Aggiungi rack trio |
| POST | `/trio/<id>/remove_rack` | manager | Rimuovi rack trio |
| POST | `/trio/<id>/confirm` | manager | Conferma risultato trio |
| POST | `/trio/<id>/forfeit` | manager | Forfeit trio |
| POST | `/trio/<id>/set_result` | manager | Imposta risultato trio |
| POST | `/trio/<id>/reset` | manager | Reset match trio |

---

## Blueprint: `admin/user` (registrato su `/admin`)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/users` | admin | Lista utenti |
| GET | `/user/<id>` | admin | Dettaglio utente |
| GET | `/director_requests` | admin | Richieste director pending |
| POST | `/director_requests/<id>/approve` | admin | Approva richiesta |
| POST | `/director_requests/<id>/reject` | admin | Rifiuta richiesta |
| POST | `/director_requests/<id>/process` | admin | Processa richiesta |
| POST | `/user/<id>/promote_director` | admin | Promuovi a director |
| POST | `/user/<id>/demote_director` | admin | Rimuovi ruolo director |
| POST | `/user/<id>/toggle_gamification_override` | admin | Toggle override gamification |
| POST | `/user/<id>/set-password` | admin | Imposta password utente |

---

## Blueprint: `admin/venue` (registrato su `/admin`)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/venues` | login | Lista sale (role-adaptive) |
| GET | `/venues/<id>` | login | Dettaglio sala |
| GET, POST | `/venues/new` | admin | Crea sala |
| GET, POST | `/venues/<id>/edit` | venue_manager | Modifica sala |
| POST | `/venues/<id>/delete` | admin | Elimina sala |
| POST | `/venues/<id>/activate` | admin | Attiva sala |
| POST | `/venues/<id>/toggle` | admin | Toggle attivo/verificato |
| POST | `/venues/<id>/verify` | venue_manager | Verifica sala |
| POST | `/venues/<id>/table_numbers` | venue_manager | Aggiorna numeri tavoli |
| POST | `/venues/<id>/photo` | venue_manager | Upload foto sala |
| GET | `/venues/names` | admin | Nomi sale (JSON) |
| GET | `/manager-requests` | admin | Richieste venue manager |
| POST | `/manager-requests/<id>/process` | admin | Processa richiesta |
| POST | `/<id>/assign-manager` | admin | Assegna venue manager |
| POST | `/assignments/<id>/revoke` | admin | Revoca assegnazione |

---

## Blueprint: `admin/kpi` (prefisso: `/admin/kpi`)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/` | admin | Dashboard KPI |
| GET | `/api/overview` | admin | Metriche panoramica (JSON) |
| GET | `/api/chart-data` | admin | Dati grafici (JSON) |
| GET | `/api/feature-usage` | admin | Uso feature (JSON) |
| GET | `/api/check-alerts` | admin | Alert attività (JSON) |
| POST | `/api/check-milestones` | admin | Controlla milestone (JSON) |

---

## Blueprint: `challenge` (prefisso: `/challenges`)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/` | login | Catalogo sfide |
| GET, POST | `/create` | director | Crea sfida |
| GET | `/<id>` | login | Dettaglio sfida |
| GET, POST | `/<id>/edit` | director | Modifica sfida |
| POST | `/<id>/delete` | director | Elimina sfida |
| GET, POST | `/<id>/attempt` | login | Inizia tentativo |
| GET | `/attempt/<id>` | login | Dettaglio tentativo |
| POST | `/attempt/<id>/complete` | login | Completa tentativo |
| POST | `/<id>/favorite` | login | Toggle preferito |
| GET | `/<id>/statistics` | director | Statistiche sfida |
| POST | `/x-replacement/<gara_id>/<round>` | login | Crea sfida X replacement |
| POST | `/x-replacement/<attempt_id>/complete` | login | Completa X replacement |

---

## Blueprint: `rating` (prefisso: `/rating`)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/` | login | Dashboard rating |
| GET | `/category` | login | Categoria giocatore |
| GET | `/ratings` | login | Tutti i rating |
| POST | `/ratings/update` | login | Aggiorna rating |
| GET | `/handicap/calculator` | login | Calcolatore handicap |
| POST | `/handicap/calculate` | login | Calcola handicap (JSON) |
| GET | `/manage` | director | Gestisci rating |
| POST | `/category/assign` | director | Assegna categoria |
| POST | `/ratings/<id>/verify` | director | Verifica rating |
| GET | `/admin/rules` | admin | Gestisci regole handicap |
| POST | `/admin/rules/create` | admin | Crea regola handicap |
| GET | `/admin/statistics` | admin | Statistiche rating |
| GET | `/leaderboard` | qualsiasi | Classifica pubblica |
| GET | `/api/user/<id>/category` | login | Categoria utente (JSON) |
| GET | `/api/handicap/<p1>/<p2>` | login | Handicap tra giocatori (JSON) |

---

## Blueprint: `individual_match` (prefisso: `/match`)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/` | login | Dashboard match individuali |
| GET | `/matches` | player/director | Lista match |
| GET | `/matches/<id>` | player/director | Dettaglio match |
| POST | `/matches/<id>/start` | player/director | Avvia match |
| POST | `/matches/<id>/racks/add` | player/director | Aggiungi rack |
| POST | `/matches/<id>/racks/remove` | player/director | Rimuovi rack (undo) |
| POST | `/matches/<id>/confirm` | player/director | Conferma risultato |
| POST | `/matches/<id>/complete` | player/director | Completa match |
| POST | `/matches/<id>/cancel` | player/director | Annulla match |
| POST | `/matches/<id>/forfeit` | player/director | Forfeit match |
| POST | `/matches/<id>/reject` | player/director | Rifiuta risultato |
| GET | `/matches/<id>/rematch` | player/director | Rematch |
| POST | `/matches/<id>/update-times` | player/director | Aggiorna orari |
| GET | `/proposals` | player/director | Proposte match |
| GET | `/proposals/<id>` | player/director | Dettaglio proposta |
| GET, POST | `/proposals/create` | player/director | Crea proposta |
| POST | `/proposals/<id>/accept` | player/director | Accetta proposta |
| POST | `/proposals/<id>/decline` | player/director | Rifiuta proposta |
| POST | `/proposals/<id>/cancel` | player/director | Annulla proposta |
| GET | `/availability` | player/director | Calendario disponibilità |
| POST | `/availability` | player/director | Aggiorna disponibilità |
| GET | `/players/search` | player/director | Cerca avversari |
| GET | `/players/opponents` | player/director | Lista avversari |
| GET | `/statistics` | player/director | Statistiche match |
| GET | `/admin/overview` | director | Overview amministrativa |

---

## Blueprint: `player` (prefisso: `/player`)

### Profilo e Account

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/profile` | player | Profilo utente |
| GET | `/profile/<id>` | qualsiasi | Profilo pubblico |
| GET, POST | `/profile/edit` | login | Modifica profilo |
| POST | `/profile/change_password` | login | Cambio password |
| POST | `/profile/verify-email` | login | Richiedi verifica email |
| GET | `/profile/<id>/export/csv` | player | Export profilo CSV |
| GET, POST | `/delete_account` | player | Eliminazione account |
| POST | `/gdpr-export/request` | player | Richiesta export GDPR |
| GET | `/gdpr-export/download/<filename>` | player | Download export GDPR |

### Gare e Match

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| POST | `/gara/<id>/inscribe` | player | Iscriviti a gara |
| POST | `/gara/<id>/unsubscribe` | player | Disiscriviti da gara |
| GET | `/history` | player | Storico match/gare |
| POST | `/match/<id>/racks/add` | match_player | Aggiungi rack |
| POST | `/match/<id>/racks/remove` | match_player | Rimuovi rack |
| POST | `/match/<id>/confirm` | match_player | Conferma risultato |
| POST | `/match/<id>/reject` | match_player | Rifiuta risultato |
| POST | `/match/<id>/forfeit` | match_player | Forfeit match |
| POST | `/match/<id>/trio/*` | trio_player | Operazioni trio (add_rack, remove, confirm, forfeit) |

### Notifiche e Privacy

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/notifications` | login | Notifiche utente |
| POST | `/notifications/<id>/mark_read` | login | Segna come letta |
| POST | `/notifications/mark_all_read` | login | Segna tutte lette |
| POST | `/notifications/delete_selected` | login | Elimina selezionate |
| GET | `/privacy-settings` | login | Impostazioni privacy |
| POST | `/privacy-settings` | login | Aggiorna privacy |
| POST | `/hide/*` e `/show/*` | player | Nascondi/mostra campionati, iscrizioni, match |

### Proposte e Disponibilità

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/match-proposals` | player | Le mie proposte |
| POST | `/match-proposals/create` | player | Crea proposta |
| POST | `/match-proposals/<id>/accept` | player | Accetta |
| POST | `/match-proposals/<id>/reject` | player | Rifiuta |
| GET | `/availability` | player | Impostazioni disponibilità |
| GET | `/availability/discover` | player | Scopri giocatori vicini |
| GET | `/api/nearby-gare` | login | Gare vicine (JSON) |

---

## Blueprint: `gamification` (prefisso: `/gamification`)

### Utente

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/dashboard` | login | Dashboard gamification |
| GET | `/achievements` | login | I miei achievement |
| GET | `/leaderboards` | qualsiasi | Classifiche XP |
| GET | `/api/level-progress` | login | Progresso livello (JSON) |

### Admin

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/admin` | admin | Dashboard admin gamification |
| GET | `/admin/quests` | admin | Gestisci quest |
| GET, POST | `/admin/quests/create` | admin | Crea quest |
| POST | `/admin/quests/<id>/activate` | admin | Attiva quest |
| POST | `/admin/quests/<id>/delete` | admin | Elimina quest |
| POST | `/admin/quests/<id>/expire` | admin | Scadenza quest |
| GET | `/admin/achievements` | admin | Gestisci achievement |
| GET, POST | `/admin/achievements/create` | admin | Crea achievement |
| GET | `/admin/config` | admin | Configurazione gamification |
| GET | `/admin/config/xp` | admin | Configurazione XP |
| POST | `/admin/config/xp/update` | admin | Aggiorna tassi XP |
| GET | `/admin/config/levels` | admin | Configurazione livelli |
| POST | `/admin/config/levels/*` | admin | Gestione unlock livelli |
| GET | `/admin/config/streaks` | admin | Configurazione streak |
| POST | `/admin/config/streaks/*` | admin | Gestione milestone streak |
| GET | `/admin/features` | admin | Feature flags |
| GET, POST | `/admin/features/create` | admin | Crea feature |
| GET | `/admin/features/<code>` | admin | Dettaglio feature |
| POST | `/admin/features/<code>/update` | admin | Aggiorna feature |

---

## Blueprint: `sse` (prefisso: `/sse`)

### SSE Streaming

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/trio/<id>` | login | Stream SSE match trio |
| GET | `/gara/<id>` | login | Stream SSE gara |
| GET | `/user/<id>` | login | Stream SSE eventi utente |
| GET | `/individual_match/<id>` | login | Stream SSE match individuale |

### Polling (raccomandato)

| Metodo | Path | Auth | Descrizione |
|--------|------|------|-------------|
| GET | `/poll/trio/<id>` | login | Polling match trio |
| GET | `/poll/gara/<id>` | login | Polling gara |
| GET | `/poll/user/<id>` | login | Polling eventi utente |
| GET | `/poll/individual_match/<id>` | login | Polling match individuale |
| GET | `/poll/match/<id>` | login | Polling match torneo |

---

## Autenticazione e Autorizzazione

### Decoratori Usati

| Decoratore | Descrizione |
|-----------|-------------|
| `@login_required` | Utente autenticato |
| `@admin_required` | Ruolo admin |
| `@director_required` | Ruolo director |
| `@director_or_admin_required` | Admin o director |
| `@campionato_manager_required` | Gestisce campionato specifico |
| `@gara_manager_required` | Gestisce gara specifica |
| `@match_player_required` | Giocatore del match |
| `@trio_player_required` | Partecipante trio |
| `@venue_manager_required` | Gestisce sala |

### Rate Limiting

| Endpoint | Limite |
|----------|--------|
| `/auth/login` (POST) | 10 richieste/minuto |
| `/auth/register` (POST) | 5 richieste/minuto |
| `/auth/forgot-password` (POST) | 3 richieste/minuto |

---

## Statistiche Finali

| Metrica | Valore |
|---------|--------|
| **Endpoint totali** | 275 |
| **Blueprint principali** | 10 |
| **Sotto-blueprint** | 8 |
| **GET endpoint** | ~140 |
| **POST endpoint** | ~120 |
| **Endpoint autenticati** | ~230 |
| **Endpoint pubblici** | ~45 |
| **Endpoint JSON/API** | ~25 |
