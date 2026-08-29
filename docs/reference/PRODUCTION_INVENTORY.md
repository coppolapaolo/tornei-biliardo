# Inventario Completo delle Funzionalità — Tornei Biliardo

**Data creazione**: 2026-05-09
**Scopo**: documento di lavoro per decidere una **production allowlist** (deny-by-default) — vedi ADR-028 (in pausa).
**Stato**: snapshot; va aggiornato quando nuove route entrano nel codebase.
**Ultima verifica contro `app.url_map`**: 2026-08-15 — path, nomi di endpoint e
decoratori riallineati. La sezione ADMIN/COMPETITION è stata riscritta riga per
riga ed è l'unica garantita **completa**; le altre restano lacunose (~60 route
esistenti non ancora documentate, soprattutto campionato, venue, match admin e
gamification API). Presidiato da
`tests/new/unit/test_production_inventory_accuracy.py`: il test non pretende
completezza, ma fallisce se una riga cita un endpoint o un path che non
esistono — è così che `round_management` è finito in `ENDPOINT_ROLES` e da lì in
produzione.

## Come usare questo documento

Questo file enumera **tutto** ciò che oggi è raggiungibile nell'app Flask:

- **Sezione 1**: ogni route HTTP raggruppata per area, con decoratori e descrizione.
- **Sezione 2**: voci di menu/navbar/dropdown visibili nell'UI.
- **Sezione 3**: gerarchia di permessi (anonimo / player / director / admin).
- **Sezione 4**: indizi concreti di feature work-in-progress trovati nel codice.

Per costruire la production allowlist, scorri ogni area in Sezione 1 e marca esplicitamente le route che vuoi visibili in produzione. Default: **non in allowlist = 404 in prod**.

> **Note tecniche**: Flask 5.x con Flask-Login, SQLAlchemy, e sistema ABAC (Attribute-Based Access Control) per gamification V2.

---

## Sezione 1: Inventario Route per Area Funzionale

### Autenticazione (AUTH)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/auth/login` | GET, POST | `auth.login` | `@limiter.limit("10/minute")` | UI page | Pagina di login con autenticazione username/password |
| `/auth/register` | GET, POST | `auth.register` | `@limiter.limit("5/minute")` | UI page | Pagina di registrazione con verifica email richiesta |
| `/auth/logout` | GET, POST | `auth.logout` | `@login_required` | Redirect/action | Effettua logout e reindirizza alla home |
| `/auth/verify-email/<token>` | GET | `auth.verify_email` | None | Redirect/action | Verifica email tramite token inviato |
| `/auth/forgot-password` | GET, POST | `auth.forgot_password` | `@limiter.limit("3/minute")` | UI page | Richiesta reset password |
| `/auth/reset-password/<token>` | GET, POST | `auth.reset_password` | None | UI page | Reset password con token valido |

**Endpoint root:** `/auth`

---

### Dashboard (DASHBOARD)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/dashboard` | GET | `dashboard.dashboard` | `@login_required` | UI page | Dashboard univoco che instrada ad admin/director/player basato su ruolo |

**Endpoint root:** `/dashboard`

---

### Campionati e Gare (ADMIN/COMPETITION)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/campionato/wizard` | GET | `admin.campionato.wizard_start` | `@director_or_admin_required` | UI page | Step 1 wizard creazione campionato (configurazione base) |
| `/admin/campionato/wizard/step2` | POST | `admin.campionato.wizard_step2` | `@director_or_admin_required` | UI page | Step 2 wizard (configurazione gare default) |
| `/admin/gara/<int:gara_id>` | GET | `admin.competition.gara_detail` | *(nessuno: controlli sul ruolo inline)* | UI page | Dettaglio gara (view unificata per admin/director/player/anonimo) |
| `/admin/gara/<int:gara_id>/tabellone` | GET | `admin.competition.gara_bracket` | *(nessuno: pagina pubblica)* | UI page | Tabellone della gara in sola lettura (solo formule a eliminazione) |
| `/admin/gara/create_standalone` | GET, POST | `admin.competition.create_gara_standalone` | `@director_or_admin_required` | UI page + action | Crea gara standalone |
| `/admin/gara/create` | POST | `admin.competition.create_gara` | `@login_required` (permessi sul campionato verificati inline) | action | Crea gara entro campionato (POST via wizard) |
| `/admin/gara/<int:gara_id>/edit` | GET, POST | `admin.competition.edit_gara` | `@gara_manager_required` | UI page + action | Modifica configurazione gara |
| `/admin/gara/<int:gara_id>/tables-config` | POST | `admin.competition.update_tables_config` | `@gara_manager_required` | JSON action | Aggiorna numero/nomi dei tavoli |
| `/admin/gara/<int:gara_id>/delete` | POST | `admin.competition.delete_gara` | `@gara_manager_required` | action | Elimina gara (hard delete) |
| `/admin/gara/<int:gara_id>/soft-delete` | POST | `admin.competition.soft_delete_gara` | `@admin_required` | action | Soft delete gara |
| `/admin/gara/<int:gara_id>/cancel` | POST | `admin.competition.cancel_gara` | `@gara_manager_required` | action | Annulla gara in corso |
| `/admin/gara/api/strategy_constraints/<strategy>` | GET | `admin.competition.get_strategy_constraints` | `@admin_required` | JSON API | Configurazione constraints per strategia matchmaking |

**Inscriptions:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/gara/<int:gara_id>/open_inscriptions` | POST | `admin.competition.open_inscriptions` | `@gara_manager_required` | action | Apre iscrizioni |
| `/admin/gara/<int:gara_id>/modify_inscription_dates` | POST | `admin.competition.modify_inscription_dates` | `@gara_manager_required` | action | Modifica date inizio/fine iscrizioni |
| `/admin/gara/<int:gara_id>/close_inscriptions` | POST | `admin.competition.close_inscriptions` | `@gara_manager_required` | action | Chiude iscrizioni |
| `/admin/gara/<int:gara_id>/admin_inscribe` | POST | `admin.competition.admin_inscribe_user` | `@gara_manager_required` | action | Iscrive player manualmente |
| `/admin/gara/<int:gara_id>/admin_uninscribe/<int:user_id>` | POST | `admin.competition.admin_uninscribe_user` | `@gara_manager_required` | action | Disiscrive player manualmente |
| `/admin/gara/<int:gara_id>/add_director` | POST | `admin.competition.add_director` | `@gara_manager_required` | action | Aggiunge co-director a gara |
| `/admin/gara/<int:gara_id>/remove_director` | POST | `admin.competition.remove_director` | `@gara_manager_required` | action | Rimuove co-director |

**Squadre (separazione compagni nel sorteggio, ADR-039):**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/gara/<int:gara_id>/squadre/create` | POST | `admin.competition.create_squadra` | `@gara_manager_required` | JSON action | Crea squadra nella gara |
| `/admin/gara/<int:gara_id>/squadre/<int:squadra_id>/rename` | POST | `admin.competition.rename_squadra` | `@gara_manager_required` | JSON action | Rinomina squadra |
| `/admin/gara/<int:gara_id>/squadre/<int:squadra_id>/merge` | POST | `admin.competition.merge_squadra` | `@gara_manager_required` | JSON action | Fonde due squadre |
| `/admin/gara/<int:gara_id>/squadre/<int:squadra_id>/toggle` | POST | `admin.competition.toggle_squadra` | `@gara_manager_required` | JSON action | Attiva/disattiva squadra |
| `/admin/gara/<int:gara_id>/inscription/<int:inscription_id>/squadra` | POST | `admin.competition.set_inscription_squadra` | `@login_required` (giocatore titolare **o** direttore: distinzione nel service) | action | Assegna un iscritto a una squadra |
| `/admin/gara/<int:gara_id>/inscription/<int:inscription_id>/categoria` | POST | `admin.competition.set_inscription_categoria` | `@gara_manager_required` | JSON action | Assegna la categoria di un iscritto **dal nome**, creandola se manca (ADR-049) |
| `/admin/gara/<int:gara_id>/categorie/<int:categoria_id>/rename` | POST | `admin.competition.rename_categoria` | `@gara_manager_required` | action | Rinomina una categoria |
| `/admin/gara/<int:gara_id>/categorie/<int:categoria_id>/toggle` | POST | `admin.competition.toggle_categoria` | `@gara_manager_required` | action | Attiva/disattiva una categoria |
| `/admin/gara/<int:gara_id>/categorie/<int:categoria_id>/delete` | POST | `admin.competition.delete_categoria` | `@gara_manager_required` | action | Elimina una categoria non assegnata a nessuno |

**Rounds Management:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/gara/<int:gara_id>/start_first_round` | POST | `admin.competition.start_first_round` | `@gara_manager_required` | action | Avvia primo turno, genera match |
| `/admin/gara/<int:gara_id>/cancel_first_round` | POST | `admin.competition.cancel_first_round` | `@gara_manager_required` | action | Annulla primo turno (resetta gara) |
| `/admin/gara/<int:gara_id>/cancel_current_round` | POST | `admin.competition.cancel_current_round` | `@gara_manager_required` | action | Annulla turno corrente |
| `/admin/gara/<int:gara_id>/terminate` | POST | `admin.competition.terminate_gara` | `@gara_manager_required` | action | Termina gara definitivamente |
| `/admin/gara/<int:gara_id>/start_ssr` | POST | `admin.competition.start_ssr` | `@gara_manager_required` | action | Avvia SSR (Spareggio/Tiebreaker) round |
| `/admin/gara/<int:gara_id>/cancel_ssr` | POST | `admin.competition.cancel_ssr` | `@gara_manager_required` | action | Annulla SSR e riporta la gara a `playing` |
| `/admin/gara/<int:gara_id>/save_ssr_group` | POST | `admin.competition.save_ssr_group` | `@gara_manager_required` | action | Salva configurazione gruppo SSR |
| `/admin/gara/<int:gara_id>/save_ssr_scores` | POST | `admin.competition.save_ssr_scores` | `@gara_manager_required` | action | Salva risultati SSR |
| `/admin/gara/amalfi/classification/<int:gara_id>/<int:round_number>` | GET | `admin.competition.amalfi_classification` | `@gara_manager_required` | JSON API | Ritorna classificazione Amalfi per round |
| `/admin/gara/<int:gara_id>/amalfi/start_round/<int:round_number>` | POST | `admin.competition.amalfi_start_round` | `@gara_manager_required` | action | Avvia turno Amalfi con gli accoppiamenti confermati |
| `/admin/gara/<int:gara_id>/start_round/<int:round_number>` | POST | `admin.competition.start_round_generic` | `@gara_manager_required` | action | Avvia turno specifico |
| `/admin/gara/<int:gara_id>/round_status` | GET | `admin.competition.get_round_status` | `@gara_manager_required` | JSON API | Stato corrente turno |
| `/admin/gara/<int:gara_id>/match/<int:match_id>/reset_advanced` | POST | `admin.competition.reset_match_advanced` | `@gara_manager_required` | JSON action | Azzera una singola partita già iniziata |
| `/admin/gara/<int:gara_id>/round/<int:round_number>/cancel` | POST | `admin.competition.cancel_round_advanced` | `@gara_manager_required` | JSON action | Annulla un turno specifico |
| `/admin/gara/<int:gara_id>/round/<int:round_number>/bulk_reset` | POST | `admin.competition.bulk_reset_round_matches` | `@gara_manager_required` | JSON action | Azzera tutte le partite del turno |
| `/admin/gara/<int:gara_id>/round/<int:round_number>/prova-x/<int:user_id>/valida` | POST | `admin.competition.validate_x_replacement` | `@gara_manager_required` | form | Registra e convalida la prova giocata al posto della X: è da qui che il punteggio entra in classifica |
| `/admin/gara/<int:gara_id>/round/<int:round_number>/prova-x/<int:user_id>/azzera` | POST | `admin.competition.reset_x_replacement` | `@gara_manager_required` | form | Azzera la prova: il turno torna a valere zero |
| `/admin/gara/<int:gara_id>/round-config` | GET | `admin.competition.list_round_configs` | `@gara_manager_required` | JSON API | Elenca gli override di configurazione per turno |
| `/admin/gara/<int:gara_id>/round-config/<int:round_number>` | POST | `admin.competition.upsert_round_config` | `@gara_manager_required` | JSON action | Salva l'override del turno (ADR-027) |
| `/admin/gara/<int:gara_id>/round-config/<int:round_number>` | DELETE | `admin.competition.delete_round_config` | `@gara_manager_required` | JSON action | Rimuove l'override del turno |
| `/admin/gara/<int:gara_id>/match/<int:match_id>/modification_check` | GET | `admin.competition.check_match_modification` | `@gara_manager_required` | JSON API | Verifica se match è modificabile |

**Challenges in Gara:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/gara/<int:gara_id>/challenges` | GET | `admin.competition.get_gara_challenges` | `@gara_manager_required` | JSON API | Lista challenges associate a gara |
| `/admin/gara/<int:gara_id>/add_challenge` | POST | `admin.competition.add_challenge_to_gara` | `@gara_manager_required` | JSON action | Aggiunge challenge a gara |
| `/admin/gara/<int:gara_id>/remove_challenge` | POST | `admin.competition.remove_challenge_from_gara` | `@gara_manager_required` | JSON action | Rimuove challenge da gara |
| `/admin/gara/<int:gara_id>/challenges/available` | GET | `admin.competition.get_available_challenges_for_gara` | `@gara_manager_required` | JSON API | Lista challenges disponibili per gara |
| `/admin/gara/challenges/available` | GET | `admin.competition.get_available_challenges` | `@admin_required` | JSON API | Tutte challenges disponibili (admin) |
| `/admin/gara/challenges/create` | POST | `admin.competition.create_new_challenge` | `@admin_required` | JSON action | Crea challenge direttamente da gara |
| `/admin/gara/<int:gara_id>/challenge_classification` | GET | `admin.competition.get_gara_challenge_classification` | `@gara_manager_required` | JSON API | Classificazione per challenge |

**Match Scoring (Trio & Multi-Set):**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/match/<int:match_id>` | GET | `admin.match.match_detail` | `@match_manager_required` | UI page | Dettaglio match con scoring |
| `/admin/match/<int:match_id>/update-times` | POST | `admin.match.update_match_times` | `@match_manager_required` | action | Modifica orari match |
| `/admin/match/<int:match_id>/assign-table` | POST | `admin.match.assign_table` | `@match_manager_required` | action | Assegna tavolo |
| `/admin/match/<int:match_id>/start-next-set` | POST | `admin.match.start_next_set` | `@match_manager_required` | action | Avvia set successivo (multi-set) |
| `/admin/match/<int:match_id>/set/add_rack` | POST | `admin.match.add_set_rack` | `@match_manager_required` | action | Aggiunge rack a set |
| `/admin/match/<int:match_id>/set/remove_rack` | POST | `admin.match.remove_set_rack` | `@match_manager_required` | action | Rimuove rack da set |
| `/admin/gara/trio/<int:trio_id>/add_rack` | POST | `admin.competition.trio_add_rack` | `@trio_manager_required` | action | Aggiunge rack a trio match |
| `/admin/gara/trio/<int:trio_id>/remove_rack` | POST | `admin.competition.trio_remove_rack` | `@trio_manager_required` | action | Rimuove rack da trio |
| `/admin/gara/trio/<int:trio_id>/confirm` | POST | `admin.competition.trio_confirm` | `@trio_manager_required` | action | Conferma risultato trio |
| `/admin/gara/trio/<int:trio_id>/forfeit` | POST | `admin.competition.trio_forfeit` | `@trio_manager_required` | action | Registra forfeit trio |
| `/admin/gara/trio/<int:trio_id>/reset` | POST | `admin.competition.trio_reset` | `@trio_manager_required` | action | Reset completo trio |
| `/admin/gara/trio/<int:trio_id>/set_result` | POST | `admin.competition.trio_set_result` | `@trio_manager_required` | action | Imposta risultato manualmente |
| `/admin/match/record_challenge_attempt` | POST | `admin.match.record_challenge_attempt` | `@match_manager_required` | action | Registra tentativo challenge |
| `/admin/match/record_challenge_attempts` | POST | `admin.match.record_challenge_attempts` | `@match_manager_required` | action | Registra multiple challenge attempts |

**Endpoint root:** `/admin/gara` (blueprint `admin.competition`), `/admin/match`

---

### Admin - Campionati (ADMIN/CAMPIONATO)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/campionato/create` | POST | `admin.campionato.create_campionato` | `@director_or_admin_required` | action | Crea campionato (legacy, wizard preferito) |
| (vedi wizard sopra) | - | - | - | - | - |

**Endpoint root:** `/admin/campionato`

---

### Admin - Utenti (ADMIN/USER)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/users` | GET | `admin.user.users_list` | `@admin_required` | UI page | Lista di tutti gli utenti con statistiche |
| `/admin/user/<int:user_id>` | GET | `admin.user.user_detail` | `@admin_required` | UI page | Dettaglio utente, inscriptions, matches, stats |
| `/admin/director_requests` | GET | `admin.user.director_requests` | `@admin_required` | UI page | Lista richieste di promozione a director |
| `/admin/director_requests/<int:req_id>/approve` | POST | `admin.user.approve_director_request` | `@admin_required` | action | Approva promozione a director |
| `/admin/director_requests/<int:req_id>/reject` | POST | `admin.user.reject_director_request` | `@admin_required` | action | Rifiuta promozione a director |
| `/admin/director_requests/<int:req_id>/process` | POST | `admin.user.process_director_request` | `@admin_required` | action | Processa richiesta (fallback) |
| `/admin/user/<int:user_id>/demote_director` | POST | `admin.user.demote_director` | `@admin_required` | action | Revoca ruolo director |
| `/admin/user/<int:user_id>/promote_director` | POST | `admin.user.promote_director` | `@admin_required` | action | Promuove a director |
| `/admin/user/<int:user_id>/toggle_gamification_override` | POST | `admin.user.toggle_gamification_override` | `@admin_required` | action | Attiva/disattiva gamification override |

**Endpoint root:** `/admin/user`

---

### Admin - Venue (ADMIN/VENUE)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/venues` | GET | `admin.venue.venues_list` | `@login_required` | UI page | Lista pubbliche sale biliardo |
| `/admin/venues/<int:venue_id>` | GET | `admin.venue.venue_detail` | `@login_required` | UI page | Dettaglio sala |
| `/admin/manager-requests` | GET | `admin.venue.venue_manager_requests` | `@admin_required` | UI page | Richieste di gestione sala |
| `/admin/manager-requests/<int:request_id>/process` | POST | `admin.venue.process_venue_manager_request` | `@admin_required` | action | Approva o rifiuta la richiesta di gestione sala |
| (vedi player routes per venue manager requests) | - | - | - | - | - |

**Endpoint root:** `/admin/venues`, `/admin/manager-requests` (blueprint `admin.venue`)

---

### Admin - KPI

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/admin/kpi/` | GET | `admin.kpi.index` | `@admin_required` | UI page | Dashboard KPI e metriche di sistema |
| `/admin/kpi/api/overview` | GET | `admin.kpi.api_overview` | `@admin_required` | JSON API | Metriche di sintesi per la dashboard |
| `/admin/kpi/api/chart-data` | GET | `admin.kpi.api_chart_data` | `@admin_required` | JSON API | Serie storiche per i grafici |
| `/admin/kpi/api/feature-usage` | GET | `admin.kpi.api_feature_usage` | `@admin_required` | JSON API | Utilizzo delle feature |
| `/admin/kpi/api/check-alerts` | GET | `admin.kpi.api_check_alerts` | `@admin_required` | JSON API | Alert attivi sulle metriche |
| `/admin/kpi/api/check-milestones` | POST | `admin.kpi.api_check_milestones` | `@admin_required` | JSON action | Verifica il raggiungimento dei milestone |

**Endpoint root:** `/admin/kpi`

---

### Challenge (CHALLENGE)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/challenges/` | GET | `challenge.challenge_catalog` | `@login_required` | UI page | Catalogo challenges per player |
| `/challenges/create` | GET, POST | `challenge.create_challenge` | `@director_required` | UI page + action | Crea nuova challenge (directors) |
| `/challenges/<int:challenge_id>` | GET | `challenge.challenge_detail` | `@login_required` | UI page | Dettaglio challenge |
| `/challenges/<int:challenge_id>/edit` | GET, POST | `challenge.edit_challenge` | `@director_required` | UI page + action | Modifica challenge |
| `/challenges/<int:challenge_id>/delete` | POST | `challenge.delete_challenge` | `@director_required` | action | Soft delete challenge |
| `/challenges/builder` | GET, POST | `challenge.diagram_builder` | `@director_required` + `@feature_required('use_drill_builder')` | UI page + action | Disegna un drill invece di fotografarlo: salva immagine **e** scena |
| `/challenges/<int:challenge_id>/builder` | GET, POST | `challenge.edit_diagram` | `@director_required` + `@feature_required('use_drill_builder')` | UI page + action | Riapre il disegno di un drill costruito (solo se ha una scena) |
| `/challenges/<int:challenge_id>/train` | GET, POST | `challenge.training_session` | `@login_required` | UI page + action | Allenamento: registra una prova dopo l'altra sulla stessa schermata |
| `/challenges/<int:challenge_id>/attempt` | GET, POST | `challenge.start_attempt` | `@login_required` | UI page + action | Inizia tentativo challenge (percorso gara: drill al posto del bye) |
| `/challenges/attempt/<int:attempt_id>` | GET | `challenge.attempt_detail` | `@login_required` | UI page | Dettaglio tentativo |
| `/challenges/attempt/<int:attempt_id>/complete` | POST | `challenge.complete_attempt` | `@login_required` | action | Completa tentativo challenge |
| `/challenges/<int:challenge_id>/favorite` | POST | `challenge.toggle_favorite` | `@login_required` | action | Aggiungi/rimuovi dai preferiti |
| `/challenges/<int:challenge_id>/statistics` | GET | `challenge.challenge_statistics` | `@director_required` | UI page | Statistiche di una challenge |
| `/challenges/x-replacement/<int:gara_id>/<int:round_number>` | POST | `challenge.create_x_replacement` | `@login_required` | action | Crea tentativo X-replacement |
| `/challenges/x-replacement/<int:attempt_id>/complete` | POST | `challenge.complete_x_replacement` | `@login_required` | action | Completa X-replacement |

**Endpoint root:** `/challenges` (blueprint `challenge`)

**Visibilità in produzione (ADR-028)**: il blueprint è stato classificato in
`ENDPOINT_ROLES` il 2026-08-16 — fino ad allora nessuna sua route compariva
nella matrice, quindi per deny-by-default l'intero catalogo dei drill era
**admin-only** (voce di menu assente, 404 per URL diretto). Ora: allenamento
(catalogo, dettaglio, `train`, tentativo, preferiti, X-replacement) a
`{"player", "director"}`; autorialità e statistiche (`create`, `edit`,
`delete`, `statistics`, tutte `@director_required`) a `{"director"}`. Il gate
di progressione `can_access('do_challenge')` resta ortogonale e invariato.

---

### Rating & Handicap (RATING) — rimosso

Il blueprint `/rating` **non esiste più** (ADR-049, 2026-08-19). Erano quindici
endpoint su categorie globali per utente e regole di handicap, tutti
irraggiungibili: la cartella `templates/rating/` non è mai stata creata, quindi
ogni view cadeva nell'except e finiva in un flash + redirect, e nessuna entry
in `ENDPOINT_ROLES` li rendeva visibili in produzione.

Le categorie oggi vivono nella competizione (`models/categoria/`) e si
gestiscono dalla schermata della gara, sotto `admin.competition.*`. L'unica
cosa che il rating decide da solo è **quali partite entrano nell'Elo**:
`models/rating/eligibility.py`.

---

### Gamification (GAMIFICATION)

**Dashboard & User Routes:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/gamification/test` | GET | `gamification.test_gamification` | (only if DEBUG_MODE) | UI page | Test page mascotte gamification |
| `/gamification/dashboard` | GET | `gamification.dashboard` | `@login_required` | UI page | Dashboard gamification: XP, livello, achievements, quests |
| `/gamification/leaderboards` | GET | `gamification.leaderboards` | None (public) | UI page | Leaderboard pubblico XP, livelli, streaks |
| `/gamification/achievements` | GET | `gamification.achievements` | None (public) | UI page | Showcase achievements sbloccati |
| `/gamification/quests` | GET | `gamification.quests` | `@login_required` | UI page | Quests attive e completate |
| `/gamification/streaks` | GET | `gamification.streaks` | `@login_required` | UI page | Tracking streaks |

**Admin Routes:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/gamification/admin` | GET | `gamification.admin_dashboard` | `@admin_required` | UI page | Admin dashboard gamification |
| `/gamification/admin/quests` | GET | `gamification.admin_quests` | `@admin_required` | UI page | Gestione quests |
| `/gamification/admin/quests/create` | GET, POST | `gamification.admin_create_quest` | `@admin_required` | UI page + action | Crea quest |
| `/gamification/admin/quests/<int:quest_id>/activate` | POST | `gamification.admin_activate_quest` | `@admin_required` | action | Attiva quest |
| `/gamification/admin/quests/<int:quest_id>/expire` | POST | `gamification.admin_expire_quest` | `@admin_required` | action | Scade quest |
| `/gamification/admin/quests/<int:quest_id>/delete` | POST | `gamification.admin_delete_quest` | `@admin_required` | action | Elimina quest |
| `/gamification/admin/achievements` | GET | `gamification.admin_achievements` | `@admin_required` | UI page | Gestione achievements |
| `/gamification/admin/achievements/create` | GET, POST | `gamification.admin_create_achievement` | `@admin_required` | UI page + action | Crea achievement |
| `/gamification/admin/achievements/<int:achievement_id>/toggle_hidden` | POST | `gamification.admin_toggle_achievement_hidden` | `@admin_required` | action | Nascondi/mostra achievement |
| `/gamification/admin/xp` | GET | `gamification.admin_xp_management` | `@admin_required` | UI page | Gestione XP |
| `/gamification/admin/xp/grant` | POST | `gamification.admin_grant_xp` | `@admin_required` | action | Assegna XP manualmente |
| `/gamification/admin/xp/reset/<int:user_id>` | POST | `gamification.admin_reset_user_level` | `@admin_required` | action | Reset XP player |
| `/gamification/admin/streaks` | GET | `gamification.admin_streaks` | `@admin_required` | UI page | Gestione streaks |
| `/gamification/admin/streaks/grant_freeze` | POST | `gamification.admin_grant_freeze` | `@admin_required` | action | Assegna freeze streak |
| `/gamification/admin/api/user_search` | GET | `gamification.admin_api_user_search` | `@admin_required` | JSON API | Ricerca player per admin |

**Config Routes:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/gamification/admin/config` | GET | `gamification.admin_config_dashboard` | `@admin_required` | UI page | Dashboard configurazione gamification |
| `/gamification/admin/config/xp` | GET | `gamification.admin_xp_config` | `@admin_required` | UI page | Config XP rates |
| `/gamification/admin/config/xp/update` | POST | `gamification.admin_update_xp_config` | `@admin_required` | action | Aggiorna XP config |
| `/gamification/admin/config/levels` | GET | `gamification.admin_level_curve_config` | `@admin_required` | UI page | Config level progression |
| `/gamification/admin/config/levels/update_curve` | POST | `gamification.admin_update_level_curve` | `@admin_required` | action | Aggiorna curva livelli |
| `/gamification/admin/config/levels/unlock/add` | POST | `gamification.admin_add_level_unlock` | `@admin_required` | action | Aggiunge unlock feature |
| `/gamification/admin/config/levels/unlock/<int:unlock_id>/edit` | POST | `gamification.admin_edit_level_unlock` | `@admin_required` | action | Modifica unlock |
| `/gamification/admin/config/levels/unlock/<int:unlock_id>/delete` | POST | `gamification.admin_delete_level_unlock` | `@admin_required` | action | Elimina unlock |
| `/gamification/admin/config/streaks` | GET | `gamification.admin_streak_config` | `@admin_required` | UI page | Config streaks |
| `/gamification/admin/config/streaks/update` | POST | `gamification.admin_update_streak_config` | `@admin_required` | action | Aggiorna config streaks |
| `/gamification/admin/config/streaks/milestone/add` | POST | `gamification.admin_add_streak_milestone` | `@admin_required` | action | Aggiunge milestone |
| `/gamification/admin/config/streaks/milestone/<int:milestone_id>/edit` | POST | `gamification.admin_edit_streak_milestone` | `@admin_required` | action | Modifica milestone |
| `/gamification/admin/config/streaks/milestone/<int:milestone_id>/delete` | POST | `gamification.admin_delete_streak_milestone` | `@admin_required` | action | Elimina milestone |

**Features (ABAC):**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/gamification/admin/features` | GET | `gamification.admin_features` | `@admin_required` | UI page | Gestione feature flags ABAC |
| `/gamification/admin/features/<code>` | GET | `gamification.admin_feature_detail` | `@admin_required` | UI page | Dettaglio feature |
| `/gamification/admin/features/<code>/update` | POST | `gamification.admin_update_feature` | `@admin_required` | action | Modifica feature ABAC rules |
| `/gamification/admin/features/<code>/preview` | GET | `gamification.admin_feature_preview` | `@admin_required` | UI page | Preview chi ha accesso feature |
| `/gamification/admin/features/create` | GET, POST | `gamification.admin_create_feature` | `@admin_required` | UI page + action | Crea feature flag |

**Endpoint root:** `/gamification`

---

### Individual Match (INDIVIDUAL_MATCH)

**Dashboard & Management:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/match/` | GET | `individual_match.dashboard` | `@player_or_director_required` | UI page | Dashboard match individuali |
| `/match/statistics` | GET | `individual_match.user_statistics` | `@player_or_director_required` | UI page | Statistiche match individuali |
| `/match/availability` | GET, POST | `individual_match.manage_availability` | `@player_or_director_required` | UI page + action | Gestione disponibilità per proposte |
| `/match/admin/overview` | GET | `individual_match.admin_overview` | `@admin_required` | UI page | Admin overview tutti match |

**Matches:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/match/matches` | GET | `individual_match.match_list` | `@player_or_director_required` | UI page | Lista match individuali dell'utente |
| `/match/matches/<int:match_id>` | GET | `individual_match.match_detail` | `@login_required` | UI page | Dettaglio match individuale |
| `/match/matches/<int:match_id>/start` | POST | `individual_match.start_match` | `@login_required` | action | Avvia match |
| `/match/matches/<int:match_id>/racks/add` | POST | `individual_match.add_rack` | `@login_required` | action | Aggiunge rack |
| `/match/matches/<int:match_id>/racks/remove` | POST | `individual_match.remove_rack` | `@login_required` | action | Rimuove rack |
| `/match/matches/<int:match_id>/confirm` | POST | `individual_match.confirm_result` | `@login_required` | action | Conferma risultato |
| `/match/matches/<int:match_id>/reject` | POST | `individual_match.reject_result` | `@login_required` | action | Rifiuta risultato |
| `/match/matches/<int:match_id>/complete` | POST | `individual_match.complete_match` | `@login_required` | action | Completa match |
| `/match/matches/<int:match_id>/cancel` | POST | `individual_match.cancel_match` | `@login_required` | action | Annulla match |
| `/match/matches/<int:match_id>/update-times` | POST | `individual_match.update_match_times` | `@login_required` | action | Modifica orari |
| `/match/matches/<int:match_id>/forfeit` | POST | `individual_match.forfeit_match` | `@login_required` | action | Registra forfeit |
| `/match/matches/<int:match_id>/tpa` | GET | `individual_match.tpa_referto` | `@player_or_director_required` | UI page | Referto TPA: si compila o si guarda (ADR-044) |
| `/match/matches/<int:match_id>/tpa/open` | POST | `individual_match.tpa_open` | `@player_or_director_required` + `@feature_required('tpa_scoresheet')` | action | Prende il referto — **unica** route col gate gamification |
| `/match/matches/<int:match_id>/tpa/press` | POST | `individual_match.tpa_press` | `@player_or_director_required` | action (JSON) | Un tocco sul tastierino; scrive solo il compilatore |
| `/match/matches/<int:match_id>/tpa/undo` | POST | `individual_match.tpa_undo` | `@player_or_director_required` | action (JSON) | Annulla l'ultimo tocco |
| `/match/matches/<int:match_id>/tpa/state` | GET | `individual_match.tpa_state` | `@player_or_director_required` | API JSON | Stato del referto, per chi lo guarda in sola lettura |
| `/match/matches/<int:match_id>/tpa/close` | POST | `individual_match.tpa_close` | `@player_or_director_required` | action | Chiude il referto |
| `/match/matches/<int:match_id>/rematch` | GET | `individual_match.rematch` | `@login_required` | UI page | Proponi rematch |

**Proposals:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/match/proposals` | GET | `individual_match.proposal_list` | `@player_or_director_required` | UI page | Lista proposte match |
| `/match/proposals/<int:proposal_id>` | GET | `individual_match.proposal_detail` | `@login_required` | UI page | Dettaglio proposta |
| `/match/players/search` | GET | `individual_match.search_players` | `@player_or_director_required` | JSON API | Ricerca player per proposte |
| `/match/players/opponents` | GET | `individual_match.get_opponents` | `@player_or_director_required` | JSON API | Lista opponent suggeriti |
| `/match/proposals/create` | GET, POST | `individual_match.create_proposal` | `@player_or_director_required` | UI page + action | Crea proposta match |
| `/match/proposals/<int:proposal_id>/accept` | POST | `individual_match.accept_proposal` | `@login_required` | action | Accetta proposta |
| `/match/proposals/<int:proposal_id>/decline` | POST | `individual_match.decline_proposal` | `@login_required` | action | Rifiuta proposta |
| `/match/proposals/<int:proposal_id>/cancel` | POST | `individual_match.cancel_proposal` | `@login_required` | action | Annulla proposta inviata |

**Endpoint root:** `/match` (blueprint `individual_match`)

---

### Player Profile & Account (PLAYER)

**Profile:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/player/profile` | GET | `player.profile` | `@login_required` | UI page | Profilo personale con stats |
| `/player/profile/<int:user_id>` | GET | `player.view_profile` | `@login_required` | UI page | Profilo pubblico altro player |
| `/player/profile/edit` | GET, POST | `player.edit_profile` | `@login_required` | UI page + action | Modifica profilo |
| `/player/profile/verify-email` | POST | `player.request_verification_email` | `@login_required` | action | Richiedi re-verifica email |
| `/player/profile/change_password` | POST | `player.change_password` | `@login_required` | action | Cambio password |
| `/player/request_director` | POST | `player.request_director` | `@login_required` | action | Richiedi promozione director |

**Account & Privacy:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/player/delete_account` | GET, POST | `player.delete_account` | `@login_required` | UI page + action | Richiesta eliminazione account |
| `/player/privacy-settings` | GET, POST | `player.privacy_settings` | `@login_required` | UI page + action | Configurazione privacy |
| `/player/hide/match/<int:match_id>` | POST | `player.hide_match` | `@login_required` | action | Nascondi match dalla classifica |
| `/player/show/match/<int:match_id>` | POST | `player.show_match` | `@login_required` | action | Mostra match |
| `/player/hide/inscription/<int:inscription_id>` | POST | `player.hide_inscription` | `@login_required` | action | Nascondi iscrizione |
| `/player/show/inscription/<int:inscription_id>` | POST | `player.show_inscription` | `@login_required` | action | Mostra iscrizione |
| `/player/hide/campionato/<int:campionato_id>` | POST | `player.hide_campionato` | `@login_required` | action | Nascondi campionato |
| `/player/show/campionato/<int:campionato_id>` | POST | `player.show_campionato` | `@login_required` | action | Mostra campionato |

**Export (GDPR):**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/player/profile/<int:user_id>/export/csv` | GET | `player.export_profile_csv` | `@login_required` | Download | Export CSV dati player |
| `/player/gdpr-export/request` | POST | `player.request_gdpr_export` | `@login_required` | action | Richiedi export GDPR completo |
| `/player/gdpr-export/download/<filename>` | GET | `player.download_gdpr_export` | `@login_required` | Download | Download export GDPR |

**Competitions:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/player/` | GET | `player.dashboard` | `@login_required` | UI page | Lista gare disponibili per iscrizione |
| `/player/gara/<int:gara_id>` | GET | `player.gara_detail` | `@login_required` | UI page | Dettaglio gara per player |
| `/player/gara/<int:gara_id>/inscribe` | POST | `player.inscribe_to_gara` | `@login_required` | action | Iscrivi player a gara |
| `/player/gara/<int:gara_id>/unsubscribe` | POST | `player.unsubscribe_from_gara` | `@login_required` | action | Disiscriviti da gara |
| `/player/history` | GET | `player.history` | `@login_required` | UI page | Storico gare partecipate |

**Matches (in Gara):**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/player/match/<int:match_id>/trio/add_rack` | POST | `player.add_trio_rack` | `@login_required` | action | Aggiunge rack a trio match |
| `/player/match/<int:match_id>/trio/remove_rack` | POST | `player.remove_trio_rack` | `@login_required` | action | Rimuove rack trio |
| `/player/match/<int:match_id>/trio/confirm` | POST | `player.confirm_trio_result` | `@login_required` | action | Conferma trio |
| `/player/match/<int:match_id>/trio/forfeit` | POST | `player.forfeit_trio` | `@login_required` | action | Forfeit trio |
| `/player/match/<int:match_id>/racks/add` | POST | `player.add_rack_simplified` | `@login_required` | action | Aggiunge rack standard |
| `/player/match/<int:match_id>/racks/remove` | POST | `player.remove_rack_simplified` | `@login_required` | action | Rimuove rack |
| `/player/match/<int:match_id>/confirm` | POST | `player.confirm_match_result` | `@login_required` | action | Conferma match result |
| `/player/match/<int:match_id>/reject` | POST | `player.reject_match_result` | `@login_required` | action | Rifiuta risultato match |
| `/player/match/<int:match_id>/forfeit` | POST | `player.forfeit_match` | `@login_required` | action | Forfeit match |

**Playoff:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/player/playoff/invitation/<int:qualification_id>` | GET | `player.playoff_invitation` | `@login_required` | UI page | Visualizza invito playoff |
| `/player/playoff/confirm/<int:qualification_id>` | POST | `player.playoff_confirm` | `@login_required` | action | Accetta playoff |
| `/player/playoff/decline/<int:qualification_id>` | POST | `player.playoff_decline` | `@login_required` | action | Rifiuta playoff |

**Notifications & Venue Manager:**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/player/notifications` | GET | `player.notifications` | `@login_required` | UI page | Lista notifiche |
| `/player/notifications/<int:notification_id>/mark_read` | POST | `player.mark_notification_read` | `@login_required` | action | Segna notifica come letta |
| `/player/notifications/mark_all_read` | POST | `player.mark_all_notifications_read` | `@login_required` | action | Segna tutte lette |
| `/player/notifications/delete_selected` | POST | `player.delete_selected_notifications` | `@login_required` | action | Elimina notifiche selezionate |
| `/player/notifications/update_auto_delete` | POST | `player.update_auto_delete` | `@login_required` | action | Config auto-delete notifiche |
| `/player/request_venue_manager` | POST | `player.request_venue_manager` | `@login_required` | action | Richiedi ruolo gestore sala |
| `/player/cancel_venue_manager_request/<int:request_id>` | POST | `player.cancel_venue_manager_request` | `@login_required` | action | Annulla richiesta |
| `/player/my_venue_requests` | GET | `player.my_venue_requests` | `@login_required` | UI page | Mie richieste gestore sala |

**Challenges (in Gara):**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/player/challenge/<int:gara_challenge_id>` | GET | `player.challenge_detail` | `@login_required` | UI page | Dettaglio challenge in gara |
| `/player/challenge/<int:gara_challenge_id>/attempt` | POST | `player.record_challenge_attempt` | `@login_required` | action | Inizia tentativo challenge in gara |

**Geo (Location Services):**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/player/api/nearby-gare` | GET | `player.api_nearby_gare` | `@login_required` | JSON API | Gare vicino location player |
| `/player/api/my-provinces` | GET | `player.api_my_provinces` | `@login_required` | JSON API | Province di interesse player |

**Endpoint root:** `/player`

---

### Main & Public (MAIN)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/` | GET | `main.index` | None (public) | UI page | Homepage pubblica / reindirizza a dashboard se autenticato |
| `/campionatos` | GET | `main.public_campionatos_list` | None (public) | UI page | Lista pubblica campionati attivi |
| `/campionato/<int:campionato_id>/public` | GET | `main.campionato_detail_public` | None (public) | UI page | Dettaglio campionato pubblico |
| `/garas` | GET | `main.public_garas_list` | None (public) | UI page | Lista gare standalone pubbliche |
| `/gara/<int:gara_id>` | GET | `main.gara_detail_public` | None (public) | UI page | Dettaglio gara (redirect a unified view) |
| `/public/gara/<int:gara_id>` | GET | `main.gara_detail_public` | None (public) | UI page | Dettaglio gara (deprecated, redirects) |
| `/g/<token>` | GET | `main.gara_invite` | None (public) | Redirect | Link pubblico di iscrizione a una gara (issue #61): iscrive l'utente autenticato e reindirizza al dettaglio gara; l'anonimo passa da login/registrazione |

**Debug Routes (only if DEBUG_MODE):**

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/reset` | GET | `main.reset_database` | (DEBUG_MODE only) | UI page | Pagina reset database con snapshot management |
| `/reset/confirm` | POST | `main.reset_database_confirm` | (DEBUG_MODE only) | action | Conferma reset |
| `/reset/save` | POST | `main.save_reset_snapshot` | (DEBUG_MODE only) | action | Salva snapshot stato corrente |
| `/reset/delete/<snapshot_id>` | POST | `main.delete_reset_snapshot` | (DEBUG_MODE only) | action | Elimina snapshot |
| `/debug/login/<username>` | GET | `main.quick_login` | (DEBUG_MODE only) | Redirect | Login rapido per debug (qualunque username) |
| `/debug/create_player` | GET | `main.debug_create_player` | (DEBUG_MODE only) | Redirect | Crea player "playerN" automaticamente |
| `/debug/fill_gara/<int:gara_id>` | GET | `main.debug_fill_gara` | (DEBUG_MODE only) | Redirect | Iscrivi tutti player* mario pino a gara |
| `/debug/complete_current_round/<int:gara_id>` | GET | `main.debug_complete_current_round` | (DEBUG_MODE only) | Redirect | Completa match turno con risultati random |

**Endpoint root:** `/` (main), `/`

---

### Real-time Updates (SSE / Polling)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/sse/trio/<int:trio_id>` | GET | `sse.trio_stream` | `@login_required` | SSE stream | Real-time trio match updates |
| `/sse/gara/<int:gara_id>` | GET | `sse.gara_stream` | `@login_required` | SSE stream | Real-time gara (competition) updates |
| `/sse/user/<int:user_id>` | GET | `sse.user_stream` | `@login_required` | SSE stream | Real-time user-specific updates (XP, achievements) |
| `/sse/individual_match/<int:match_id>` | GET | `sse.individual_match_stream` | `@login_required` | SSE stream | Real-time individual match updates |
| `/sse/poll/trio/<int:trio_id>` | GET | `sse.poll_trio` | `@login_required` | JSON API (polling) | Poll trio updates (recommended over SSE) |
| `/sse/poll/gara/<int:gara_id>` | GET | `sse.poll_gara` | `@login_required` | JSON API (polling) | Poll gara updates |
| `/sse/poll/user/<int:user_id>` | GET | `sse.poll_user` | `@login_required` | JSON API (polling) | Poll user updates (security: own user only) |
| `/sse/poll/individual_match/<int:match_id>` | GET | `sse.poll_individual_match` | `@login_required` | JSON API (polling) | Poll individual match updates |
| `/sse/poll/match/<int:match_id>` | GET | `sse.poll_match` | `@login_required` | JSON API (polling) | Poll gara match (tournament match) updates |

**Endpoint root:** `/sse`

---

### i18n (Internationalization)

| Path HTTP | Metodo | Endpoint | Decoratori | Tipo | Descrizione |
|-----------|--------|----------|-----------|------|-------------|
| `/i18n/set_language/<language>` | GET | `i18n.set_language` | None | Redirect | Imposta lingua (it/en) in session |

**Endpoint root:** `/i18n`

---

## Sezione 2: Voci di Menu e Link Visibili nell'UI

### Navbar Principale (templates/base.html)

**Sezione Left (authenticated users):**

1. **Dashboard** - `url_for('dashboard.dashboard')` - Sempre visibile per utenti autenticati
2. **Sale Biliardo** - `url_for('admin.venue.venues_list')` - Sempre visibile per utenti autenticati (directory pubblica)
3. **Challenge** - `url_for('challenge.challenge_catalog')` - Visibile solo se `current_user.can_access('do_challenge')` (feature flag ABAC)
4. **Match Individuali** - `url_for('individual_match.dashboard')` - Visibile solo se `current_user.can_access('create_match_direct')` (feature flag ABAC)

**Admin-Only Section (if `current_user.is_admin`):**

5. **Admin Gamification** - `url_for('gamification.admin_dashboard')`
6. **Utenti** - `url_for('admin.user.users_list')`
7. **KPI** - `url_for('admin.kpi.index')`

**Debug Section (if `debug_info.debug_mode`):**

8. **Reset DB** - `url_for('main.reset_database')` - Badge rosso WARNING

---

### Language Selector Dropdown

- **Italiano** - `url_for('i18n.set_language', language='it')`
- **English** - `url_for('i18n.set_language', language='en')`

---

### Profile Dropdown (Authenticated Users)

**Main Section:**

1. **Notifiche** - `url_for('player.notifications')` - Con badge count notifiche non lette
2. **Le mie Richieste Gestore** (se non admin) - `url_for('player.my_venue_requests')`
3. **Dashboard** - `url_for('dashboard.dashboard')`

**Profile Section (if `can_view_profile`):**

4. **Il mio Profilo** - `url_for('player.profile')`

**Admin Management (if `show_admin_management`):**

5. **Utenti** - `url_for('admin.user.users_list')`
6. **Sale Biliardo** - `url_for('admin.venue.venues_list')`
7. **Challenge** - `url_for('challenge.challenge_catalog')`
8. **Richieste Gestore Sala** - `url_for('admin.venue.venue_manager_requests')`
9. **Richieste Director** - `url_for('admin.user.director_requests')`

**Account Actions (if `can_delete_account`):**

10. **Elimina Account** - `url_for('player.delete_account')` - Badge rosso danger

**Logout:**

11. **Logout** - `url_for('auth.logout')`

---

### Gamification Badge (Navbar, sempre visibile se non admin)

- **XP Badge** - Clicca per andare a `url_for('gamification.dashboard')`
- Mostra Livello e XP corrente

---

### Debug Footer (if `debug_info.debug_mode`)

**Database:**
- `Reset DB` - `url_for('main.reset_database')`
- `Save Reset` - apre modale `#saveResetModal` (form nome/descrizione → POST `main.save_reset_snapshot`)

**Quick Login** (lista dinamica da `debug_info.quick_login_users`):
- Popolata da `utils.database_utils.get_quick_login_users(limit=16, max_directors=4)`
- Ordine: admin → director (max 4) → player, fino a 16 totali
- Colore bottone per ruolo: admin = `btn-danger`, director = `btn-warning`, player = `btn-primary`

**Test Fixtures:**
- `+ Player` - `url_for('main.debug_create_player')`
- `Fill Gara` - `url_for('main.debug_fill_gara', gara_id=gara.id)` (solo su `admin.competition.gara_detail`)
- `Complete Round` - `url_for('main.debug_complete_current_round', gara_id=gara.id)` (solo su `admin.competition.gara_detail`). ADR-027 compliant: usa `match.effective_*` / `match.distance_config`, salta `is_bye` e `is_trio`.

---

## Sezione 3: Gerarchia di Permessi

### Ruoli Definiti (models/user/role_enum.py)

```python
ADMIN = "admin"
DIRECTOR = "director"
PLAYER = "player"
```

---

### Permessi per Ruolo

#### Anonimo (non autenticato)

**Accesso pubblico (senza login):**
- Visualizza homepage pubblica `/`
- Visualizza lista pubblica campionati `/campionatos`
- Visualizza dettaglio campionato pubblico `/campionato/<id>/public`
- Visualizza lista pubblica gare `/garas`
- Visualizza dettaglio gara pubblico `/gara/<id>`
- Visualizza leaderboard pubblico `/rating/leaderboard`
- Visualizza achievements/quests pubblici `/gamification/achievements`

**Azioni bloccate:**
- Iscrizione gare
- Creazione match individuali
- Accesso a challenge
- Qualunque azione di modifica

---

#### Player (giocatore)

**Eredita:** Accesso pubblico + il seguente

**Dashboard:**
- Accede a `/dashboard` (dashboard player)

**Gare e Campionati:**
- Visualizza gare disponibili per iscrizione
- Iscrizione/discrizione gare
- Accede a dettagli gara come iscritto
- Inserimento risultati match (solo propri match)
- Visualizza classifica gara

**Match Individuali (se feature `create_match_direct` abilitata):**
- Accede dashboard match individuali
- Crea/accetta/rifiuta proposte match
- Gestisce disponibilità per matchmaking
- Aggiunge rack e conferma risultati match propri
- Visualizza statistiche match individuali

**Challenge (se feature `do_challenge` abilitata):**
- Visualizza catalogo challenges
- Inizia/completa tentativi challenge
- Visualizza statistiche challenge

**Profilo:**
- Visualizza profilo proprio
- Modifica profilo (email, password, bio)
- Accede a `/player/profile`
- Richiede promozione a director
- Configura privacy settings
- Richiede ruolo gestore sala

**Notifiche:**
- Visualizza notifiche proprie
- Marca come lette
- Elimina notifiche

**Export:**
- Export CSV dati proprio
- Richiesta export GDPR completo

**Rating:**
- Visualizza proprio rating/categoria
- Auto-segnala rating (richiede verifica)
- Accede calcolatore handicap

**Playoff:**
- Visualizza inviti playoff
- Accetta/rifiuta playoff

---

#### Director (direttore di torneo)

**Eredita:** Accesso Player + il seguente

**Campionati:**
- Accede `/dashboard` (dashboard director)
- Crea campionati (tramite wizard) - se feature `create_campionato` abilitata
- Modifica campionati assegnati
- Gestisce gare in campionati assegnati

**Gare (se assegnato):**
- Visualizza dettaglio gara come manager
- Modifica configurazione gara
- Apre/chiude iscrizioni
- Iscrizione/discrizione manuale player
- Genera match per turni
- Assegna tavoli
- Inserisce risultati match
- Gestisce challenges nella gara
- Visualizza classifiche

**Gestione Diretti:**
- NON può competere nelle gare che gestisce (bloccato)
- Può essere sia player che director in diverse gare

**Challenges:**
- Crea/modifica/elimina challenges proprie
- Visualizza statistiche challenges

**Rating:**
- Gestisce rating players
- Assegna categorie
- Verifica rating auto-segnalati

**Match Individuali:**
- Visualizza dashboard match individuali
- Crea proposte match

**Accesso limitato ADMIN:**
- NON accede a admin panel full
- NON gestisce utenti
- NON resetta database

---

#### Admin

**Eredita:** Tutte le azioni di Player + Director + il seguente

**Admin Panel Completo:**
- Accede `/dashboard` (dashboard admin)
- Visualizza tutte statistiche e metriche

**Utenti:**
- Visualizza lista utenti con stats
- Visualizza dettaglio utente
- Promuove/retrocede director
- Processa richieste promozione director
- Rimuove account (soft delete)
- Assegna/revoca ruoli
- Gestisce venue manager requests

**Campionati:**
- Crea/modifica/elimina campionati
- Gestisce TUTTE le gare (non solo assegnate)

**Gare:**
- Accesso completo CRUD
- Annulla turni
- Resetta match
- Imposta risultati manualmente
- Soft/hard delete gare

**Database:**
- Accede reset database (DEBUG_MODE only)
- Salva/carica snapshot stati database

**Gamification:**
- Accede admin gamification dashboard
- Gestisce quests, achievements, XP
- Configura level progression
- Configura streak system
- Gestisce feature flags ABAC
- Assegna XP/freeze manualmente
- Reset XP players

**Rating:**
- Visualizza statistiche rating system
- Gestisce regole handicap

**Venue:**
- Gestisce venue manager requests

**KPI:**
- Accede dashboard KPI completo

**Esclusioni Gamification:**
- NON participa a gamification (non ha XP, livello)
- NON accede dashboard gamification personale (reindirizzamento)

---

### Decoratori Implementati (models/user/role_decorators.py)

```python
@login_required              # Richiede autenticazione
@admin_required              # Solo admin (abort 403)
@director_required           # Solo director/admin (flash + redirect)
@director_or_admin_required  # Director o admin (abort 403)
@player_or_director_required # Player o director, NO admin (abort 403)
@authenticated_required      # Generico authenticated (abort 401)
```

Plus custom decorators:
- `@campionato_manager_required` - Gestore specifico campionato
- `@gara_manager_required` - Gestore specifico gara
- `@match_manager_required` - Gestore specifico match

---

### Permission Check System (models/user/permissions.py)

**PermissionChecker static methods:**
- `can_manage_campionato(user, campionato_id)` - Admin o DirectorAssignment
- `can_manage_competition(user, gara_id)` - Admin o DirectorAssignment gara/campionato
- `can_inscribe_to_competition(user, gara_id)` - Non admin, non gara che gestisce
- `can_insert_match_results(user, match_id)` - Admin, director gara, o player nel match
- `can_create_campionato(user)` - ABAC check (director/admin/legend level/veteran metrics)
- Etc.

---

## Sezione 4: Feature Evidentemente Incomplete

### Indicatori di Work-in-Progress

#### 1. **Gamification Test Page** (`/gamification/test`)

**Location:** `/routes/gamification/dashboard.py:28-34`

```python
@gamification_bp.route("/test")
def test_gamification():
    """Test page for gamification mascot integration - debug only."""
    from config import Config
    if not Config.DEBUG_MODE:
        abort(404)
    return render_template("test_gamification.html")
```

**Indizio WIP:** Route esplicitamente denominata "test", solo in DEBUG_MODE, renderizza template "test_gamification.html" che potrebbe non essere completo.

---

#### 2. **SSE vs. Polling Architecture Transition**

**Location:** `/routes/sse.py:1-17`

```
Docstring: """Real-time updates via polling (replaced SSE to avoid worker blocking).
...
Migration from SSE to Polling (Feb 2026):
    SSE connections were blocking uWSGI workers indefinitely, causing
    severe performance issues with only 3 workers on PythonAnywhere.
    Polling with 3s interval provides near-real-time updates without blocking.
"""
```

**Indizio WIP:** Migrazione da SSE a polling non completata. Mantiene endpoint SSE (streaming) per backward compatibility ma raccomanda polling. Questo suggests still-in-flight refactor.

---

#### 3. **Challenge X-Replacement Dual Pattern**

**Location:** `/routes/challenge.py:325-408`

```python
# Due pattern coesistenti:
# - Nuovo: GaraByeChallenge model
# - Deprecato: gara_id field diretto su ChallengeAttempt

bye_challenge = GaraByeChallenge.query.filter_by(
    challenge_attempt_id=attempt_id
).first()

is_x_replacement = bye_challenge is not None or attempt.gara_id is not None
```

**Indizio WIP:** Due sistemi per tracciare X-replacement challenges. Commento nel codice: "new pattern (GaraByeChallenge) and deprecated field (gara_id)". Suggests refactoring incompleto.

---

#### 4. **Unified Gara Detail View (Guest/Director/Admin)**

**Location:** `/routes/main.py:159-167`

```python
@main_bp.route("/gara/<int:gara_id>")
@main_bp.route("/public/gara/<int:gara_id>")
def gara_detail_public(gara_id):
    """
    DEPRECATED: Redirect to unified gara_detail view.
    La vista unificata in admin.competition.gara_detail si adatta
    automaticamente in base ai permessi dell'utente (anche per guest).
    """
    return redirect(url_for('admin.competition.gara_detail', gara_id=gara_id))
```

**Indizio WIP:** Route che reindirizza a route unificata. Suggests refactoring di consolidamento views che non è completato (mantiene route legacy per compatibilità).

---

#### 5. **Round Configuration - Multiple Endpoints with Long Decorators**

**Location:** `/routes/admin/competition/rounds.py` (multiple entries)

```python
@competition_bp.route("...")  # Lungo string, troncato output grep
@competition_bp.route(
    "<int:gara_id>/classification/<int:round_number>/edit_round_results", 
    methods=["POST"]
)
```

**Indizio WIP:** Nombreuses route con decorator multiline non riuscite a essere captate da grep. Suggests possibile incomplete or overly-complex routing setup.

---

#### 6. **Playoff/SSR (Spareggio) Implementation**

**Location:** `/models/playoff/` directory + `/routes/admin/competition/rounds.py`

Model exists (`/models/playoff/models.py`, `/models/playoff/services.py`) with:
- 29 methods in models
- 30 methods in services

But routes sono sparce:
- `/admin/gara/<gara_id>/start_ssr` - POST
- `/admin/gara/<gara_id>/save_ssr_group` - POST
- `/admin/gara/<gara_id>/save_ssr_scores` - POST

**Indizio WIP:** Modelli e servizi playoff ben sviluppati, ma routing e UI per gestire playoff possono essere incomplete o sparse in various competition admin views.

---

#### 7. **Round Overrides Full Migration**

**Location:** `/migrations/20260509_round_overrides_full.py`

```python
# Migration file naming suggests recent addition (May 2026)
```

**Indizio WIP:** Migration file dalla data odierna (`20260509_round_overrides_full.py`) suggests recente implementazione di feature "round overrides". Feature è ancora "hot" e potrebbe avere edge cases non gestiti.

---

#### 8. **Classification/Tiebreaker Strategy Registry**

**Location:** `/models/classification/registry.py` + multiple strategy files

**Indizio WIP:** 
- Classificazione system supporta multiple strategie (Amalfi, Random, etc.)
- Registry pattern suggests extensible-but-incomplete design
- Tiebreaker resolver con 14 metodi (`/models/tiebreaker/services.py`)
- Route `/admin/gara/amalfi/classification/<gara_id>/<round_number>` è Amalfi-specific, suggesting possibile altre strategie con routing ancora da completare

---

#### 9. **Individual Match - Trio vs. Standard Mismatch**

**Location:** `/routes/individual_match/` + `/routes/player/matches.py`

**Indizio WIP:**
- Endpoint `/player/match/<match_id>/trio/...` per trio matches
- Endpoint `/match/matches/<match_id>/...` per standard individual matches
- Due sistemi match tipo (Trio dal `Match` model, IndividualMatch modello separato)
- Possibile inconsistenza tra quale tipo di match usa quale endpoint

---

#### 10. **Playoff Invitation UI Incomplete**

**Location:** `/routes/player/playoff.py`

```python
@player_bp.route("/playoff/invitation/<int:qualification_id>")
@player_bp.route("/playoff/confirm/<int:qualification_id>", methods=["POST"])
@player_bp.route("/playoff/decline/<int:qualification_id>", methods=["POST"])
```

**Indizio WIP:**
- Route esiste per visualizzare/confermare/rifiutare playoff
- Logica sottostante probabilmente in `models/playoff/services.py`
- Ma template rendering (`player/playoff_invitation.html`) può non esistere o essere stub
- No intermediate acceptance flow visible (es. confermazione venue/orario)

---

#### 11. **GDPR Export Implementation**

**Location:** `/routes/player/exports.py`

```python
@player_bp.route("/gdpr-export/request", methods=["POST"])
@player_bp.route("/gdpr-export/download/<filename>")
```

**Indizio WIP:**
- Route exists for GDPR export request + download
- Suggests background job per generare export (non visibile nei routes)
- Logica di cleanup/expiry download links probabilmente incomplete
- File storage mechanism non documentata in routes

---

#### 12. **Feature Flags (ABAC) vs. Role-Based Permissions Mixing**

**Location:** `/models/user/permissions.py:275-281`

```python
@staticmethod
def can_create_campionato(user) -> bool:
    # Use ABAC system (Gamification V2)
    # This evaluates: Role (Director/Admin) OR Level (Legend) OR Metrics (Veteran)
    if hasattr(user, "can_access"):
         return user.can_access("create_campionato")
    # Fallback if method missing
    return user.is_admin or user.is_director
```

**Indizio WIP:**
- Dual system: fallback role-based + nuovo ABAC gamification system
- Hasattr check suggests transizione non completa (legacy fallback)
- Possibile inconsistenze se ABAC config non inizializzata

---

### Riassunto Indicatori WIP

| Feature | Indizio | Gravità |
|---------|---------|---------|
| Gamification Test Page | Route test-only con DEBUG_MODE check | Bassa (test internal) |
| SSE→Polling Migration | Mantenere SSE per compat, raccomanda polling | Media (arch transition) |
| X-Replacement Challenges | Due pattern coesistenti (old + new model) | Media (refactor incomplete) |
| Unified Gara View | Route legacy reindirizza a unificata | Bassa (shim, backwards compat) |
| Round Configuration | Decorator multiline, routing sparse | Alta (complexity, possible gaps) |
| Playoff/SSR | Model ricco ma UI/routing sparse | Media (feature working but scattered) |
| Round Overrides | Migration data odierna (20260509) | Alta (brand new, untested) |
| Classification Strategies | Registry pattern, Amalfi-only routes visible | Media (extensible but incomplete) |
| Trio vs. Individual Match | Due sistemi match, routing inconsistente | Alta (user confusion risk) |
| Playoff Invitation | Route exists, template possibile incomplete | Media (core UX incomplete) |
| GDPR Export | Background job logic non visibile | Media (async logic hidden) |
| ABAC vs. Role-Based Mix | Fallback legacy system + new ABAC | Alta (permission logic fragile) |

---

**Report completato.** Totale route catalogate: **~250+ endpoint** organizzati in **12 aree funzionali**, con **12 indizi di feature WIP** identificati. L'app è in buono stato di maturità generale, con refactoring architetturali in corso (SSE→polling, ABAC gamification, unified views) e feature recenti in stabilizzazione (round overrides, playoff).