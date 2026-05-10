# Sessione test manuale — 2026-05-10

## 🧪 Da testare

### Gara con matchmaking Random
- [ ] Dopo aver finito il test Amalfi (gara 20), creare una nuova gara con `matchmaking_strategy=random` e ripetere i test analoghi
- Random crea **tutti i turni** insieme allo start (vs Amalfi che ne crea uno alla volta) → comportamento diverso da verificare

### Forfait × Gestione dispari (combinazioni)
- [ ] Costruire **tabella esaustiva** di tutte le combinazioni `forfait_management` × `odd_handling` e testare ciascuna cella
- Output atteso: matrice con esito (OK / bug / da chiarire)

### Amalfi — opzioni primo turno
- [ ] Testare le opzioni del primo turno **diverse da "casuale"** (non ho conferma che funzionino)
- Decisione: o le validiamo, oppure le nascondiamo in produzione finché non sono testate
- Vedi anche sezione 🚧 sotto

### In corso
- ✅ Gara id=20, "gara prova 4 turni" (4 turni, Amalfi, 9-ball, esatti 5 rack) — **completed** dopo SSR
- 🆕 Gara id=21, "test gara 4 turni con trio" (4 turni, Amalfi, 8-ball, esatti 4 rack, trio per dispari) — **status=setup**

### 📋 Dati gara id=21 (dal DB locale, nuovo test)
| Campo | Valore | Note |
|---|---|---|
| `name` | "test gara 4 turni con trio" | |
| `campionato_id` | NULL | standalone |
| `rounds_count` | 4 | |
| `matchmaking_strategy` | `amalfi` | |
| `first_round_policy` | `random` | |
| `distance` | 4 | |
| `is_race_to` | **0** | → "esatti 4 rack" ✓ |
| `is_multi_set` | 0 | ma `match_distance=2` ⚠️ default ombra (vedi gara 20) |
| `discipline` | `8_ball` | "palla 8" ✓ |
| `odd_number_policy` | `trio` | ✓ test specifico per trio con dispari |
| `withdraw_policy` | `Forfeit` | |
| `classification_system` | `WINS` | |
| `min_participants` | 6 | |
| `status` | `setup` | non ancora avviata |

**Override per turno (`round_configuration`) — confermati salvati server-side ✓**:
- Turno 1: `10_ball`, distance=6, `is_race_to=1` → 10-ball race to 6
- Turno 2: `9_ball`, distance=5, `is_race_to=0` → 9-ball esatti 5 rack
- Turno 3 e 4: nessun record → fallback ai default gara (8-ball, esatti 4 rack)

**Iscritti: 11 (numero dispari!) → `trio` attivo**:
BRUNO, CRISTIAN, EGLE, EMILIO, MAX P, Mario Rossi, PICCHIO, PIETRO, Paolo, SAMUEL, SERGIO
- Con `odd_number_policy=trio`, ci si aspetta un match trio (3 giocatori) invece di bye
- Path meno testato di matchmaking: trio + Amalfi (algoritmo per coppie) — verificare chi finisce nel trio

### 📋 Dati gara id=20 (dal DB locale)
| Campo | Valore | Note |
|---|---|---|
| `name` | "gara prova 4 turni" | |
| `rounds_count` | 4 | |
| `matchmaking_strategy` | `amalfi` | |
| `first_round_policy` | `random` | ✓ come scelto |
| `distance` | 5 | |
| `is_race_to` | **0** | → "esatti 5 rack" (si giocano tutti i rack) ✓ |
| `is_multi_set` | 0 | ma `match_distance=2`, `is_race_to_sets=1` ⚠️ valori popolati anche se non multi-set — verificare se è un bug o solo "default ombra" |
| `odd_number_policy` | `trio` | da testare con varie combinazioni |
| `withdraw_policy` | `Forfeit` | da testare con varie combinazioni |
| `min_participants` | 6 | |
| `max_participants` | NULL | |
| `discipline` | `9_ball` | |
| `entry_fee` | 10.0 | |
| `status` | `setup` | non ancora avviata |
| `iscritti` | 0 | |
| `round_configuration` | nessun override | tutti i 4 turni useranno la config gara (Distance VO fallback — ADR-027) |

---

## 🚧 Da nascondere in produzione (non ancora testato a sufficienza)
- [ ] **Match multi-set**: opzione UI da nascondere in prod finché non è testata (i campi `is_multi_set` / `match_distance` esistono già nel modello)
- [ ] **Amalfi — primo turno, opzioni ≠ "casuale"**: nascondere in prod oppure testare → poi decidere

## 🐛 Bug trovati

### B6 — 🚨 Errore aggiungendo rack /admin/match/173 (BLOCCANTE) ✅ FIXATO
- **Cosa**: Paolo (director) clicca "+" → "Errore durante l'aggiornamento"
- **Causa reale (svelata dallo screenshot console)**: 404 NOT FOUND su POST. Il fetch JS riceve HTML del 404 → `response.json()` fallisce con `SyntaxError: Unexpected token '<'` → catch → messaggio generico
- **Causa root**: il server gira in **modalità produzione** (DEBUG_MODE=false) → middleware ADR-028 attivo → `admin.match.add_rack_result` mancante dall'allowlist → deny-by-default 404
- **Fix**: aggiunti all'allowlist (`utils/feature_flags.py`) **8 endpoint admin.match.* di scoring** mancanti, tutti per ruolo `director`:
  - `add_rack_result`, `remove_rack_admin`, `set_match_result_direct`, `validate_match`, `validate_rack_admin`, `reset_match`, `record_challenge_attempt`, `record_challenge_attempts`
- **Fix collaterale (preventiva, non causa root)**: in `templates/match_detail.html` sostituito `csrfToken()` (function lookup di meta tag) con `const csrfToken = {{ csrf_token()|tojson }}` — pattern robusto già usato in `_round_management.html`
- **🚨 Per applicare il fix devi RIAVVIARE il server**: in prod mode Werkzeug non fa auto-reload. Ctrl-C nel terminale del server, poi `python app.py`. Poi hard refresh (Cmd+Shift+R) nel browser
- **🔍 Follow-up scoperti**:
  - **B6a**: il tuo server gira con `DEBUG_MODE=false` — verificare se è intenzionale (testing prod-like in locale?) o accidentale (env shell, default cambiato). In dev pure il default dovrebbe essere true
  - **B6b**: audit completo di TUTTI gli endpoint mancanti dall'allowlist, non solo admin.match. Il test `tests/new/unit/test_endpoint_coverage.py` dovrebbe beccarli (verificare se passa)
  - **B6c** (UX): il fetch JS dovrebbe controllare `response.ok` prima di `response.json()` per dare un messaggio di errore più utile (status code esplicito invece di "Errore durante l'aggiornamento" generico)

### B8 — Player Emilio: "Gioca Partita" → 404 admin/match/172 ✅ FIXATO
- **Cosa**: Emilio (player) dalla dashboard clicca "Gioca Partita" → `/admin/match/172` → 404
- **Causa root**: stesso pattern di B6 (server in prod mode → ADR-028 attivo). L'endpoint `admin.match.match_detail` è una **vista unificata** progettata per essere usata da admin, director E player (vedi commento `routes/admin/match/detail.py:27-32`), ma era nell'allowlist solo per `{"director"}`
- **Fix**: estesa allowlist a `{"player", "director"}` in `utils/feature_flags.py`. La page stessa fa il routing per ruolo (`user_can_manage`/`is_player_in_match`) e fa `abort(403)` se l'utente non è coinvolto (riga 86-87)
- **Verificato**:
  - Emilio (player2 di match 172) GET /admin/match/172 → 200 ✓
  - Emilio NON in match 173 GET /admin/match/173 → 403 ✓ (correctly denied)
- **🚨 Per applicare**: come B6, **riavvia il server** (no auto-reload in prod mode)

### B13 — Avanzamento round bloccato da match in stato `validated` ✅ FIXATO
- **Cosa**: tutti i match del turno 1 mostrati come "Completata" in UI, ma click "Avvia Turno 2" → "Completa prima tutte le partite del turno 1!"
- **Causa root**: `m172` (SAMUEL vs EMILIO) ha `status=validated` (transizione COMPLETED→VALIDATED dopo conferma admin). I check di "round finished" cercano solo `status == COMPLETED`, così trattano `validated` come "non finito". `VALIDATED` è in realtà uno stato post-COMPLETED, *più avanzato*, quindi dovrebbe contare come finito (vedi commento `models/status_enum.py:94`)
- **NON è colpa del cleanup**: m172 era già `validated` prima dei miei test (visto nello stato iniziale del DB). Bug preesistente nel codice di check
- **Fix applicato in 4 punti**: ora i check accettano sia COMPLETED che VALIDATED come "match finito":
  - `routes/admin/competition/rounds.py:455-461` (amalfi_classification "round completed?")
  - `routes/admin/competition/rounds.py:546-551` (amalfi_start_round prev round check)
  - `routes/admin/competition/rounds.py:643-648` (start_round_generic prev round check)
  - `routes/admin/competition/detail.py:265-272` (gara_detail "is_round_completed?")
- **Follow-up scoperti** (NON fixati, sono di natura diversa: stats/visualizzazione):
  - **B13a**: `Match.is_completed()` (`models/match/models.py:144`) ritorna False per validated. Decidere se aggiornare la semantica del metodo o creare `is_finished()` accanto
  - **B13b**: `models/user/stats_service.py`, `routes/player/profile.py`, `routes/player/exports.py`, `models/player/history_service.py` filtrano per `status == COMPLETED` (con VALIDATED escluso). Questo significa che match validati NON contano nelle statistiche player → **bug latente sulle stats** (decidere se è intenzionale)
- **🚨 Per applicare**: come gli altri, **riavvia il server**

### B12 — assign_table su match in playing (anomalo) → "player già impegnato" (self-match) ✅ FIXATO
- **Cosa**: assegnando un tavolo a un match già in `playing` (stato anomalo, es. dopo un reset incompleto) il check `_is_player_busy` trova **il match stesso** come "altro match playing" → blocca con messaggio fuorviante "Paolo è già impegnato in un'altra partita"
- **Causa root**: `models/match/table_assignment_service.py::_is_player_busy` cercava match playing nella gara senza escludere il match corrente
- **Fix**: aggiunto parametro `exclude_match_id` a `_is_player_busy` (default None per back-compat); aggiornati tutti e 3 i call sites a passare `match.id` (defensive, non strettamente necessario per i flussi normali ma evita regressioni future)
- **🚨 Per applicare**: come B6/B8, **riavvia il server**
- **Causa scatenante in questa sessione**: il mio cleanup precedente ha lasciato m173 in stato `playing` senza tavolo né rack. Ora ho riportato m173 a `pending` (stato corretto)
- **Test di regressione candidato**: assign_table su match in playing senza tavolo non deve trovare se stesso

### B20 — 🚨 SSR rileva parimerito sbagliati (ignora `classification_system`) ✅ FIXATO
- **Cosa**: la fase SSR (spareggi) rilevava parimerito basandosi solo su `rack_difference`, ignorando il sistema di classificazione configurato sulla gara (WINS / RACK / POSITION)
- **Esempio del bug**: in gara 20 (`classification_system=WINS`), la classifica reale è EMILIO(3w,+8) > CRISTIAN(2w,+8) > Paolo(2w,+4) ≡ EGLE(2w,+4). Il vero parimerito è Paolo+EGLE in pos 3. Pre-fix il servizio raggruppava per rack_diff e identificava "EMILIO+CRISTIAN su +8" come parimerito (sbagliato: hanno wins diversi e sono pos 1 e 2)
- **Fix**: `models/competition/spareggio_service.py`:
  - Estratto helper `_group_by_classification(gara)` che carica le `RoundClassification` con ORDER BY appropriato e raggruppa per chiave classifica:
    - `WINS` (default) e `POSITION`: tuple `(matches_won, rack_difference)`
    - `RACK`: solo `rack_difference` (comportamento legacy)
  - Refactor: sia `detect_tiebreakers` che `get_all_ssr_groups` ora usano l'helper (zero duplicazione)
- **Verificato in DB**:
  - Pre-fix: `tiebreaker_groups = [pos 1 rack_totali=8 (EMILIO,CRISTIAN)]` ❌
  - Post-fix: `tiebreaker_groups = [pos 3 rack_totali=4 (Paolo,EGLE)]` ✓
- **🚨 Per applicare**: come gli altri, **riavvia il server**
- **Nota tecnica**: il campo `rack_totali` nel `TiebreakerGroup` (interfaccia con il template) è preservato come "rack_difference comune del gruppo" anche per WINS — per non rompere la UI esistente. Se il template volesse anche mostrare il numero di vittorie comune, serve una piccola estensione del TypedDict

### B19 — 🚨 Avvio SSR → 404 (allowlist incompleta) ✅ FIXATO
- **Cosa**: a fine turno 4, click "Avvia spareggi" → "Errore durante l'avvio della fase SSR". Console: `POST /admin/gara/20/start_ssr 404 NOT FOUND` + `JSON.parse: unexpected character '<'` (HTML del 404)
- **Causa root**: stesso pattern di B6/B8 (server in prod mode + ADR-028 attivo). `admin.competition.start_ssr` mancante dall'allowlist
- **Audit completo eseguito**: trovati **20 endpoint admin.competition.* mancanti** dall'allowlist. Tutti aggiunti come `{"director"}`:
  - **SSR/spareggi**: `start_ssr`, `save_ssr_group`, `save_ssr_scores`
  - **Round management**: `amalfi_start_round`, `bulk_reset_round_matches`, `cancel_round_advanced`, `reset_match_advanced`
  - **Director assignment**: `add_director`, `remove_director`
  - **Gara CRUD**: `delete_gara`, `soft_delete_gara`
  - **Challenge** (per gare Random): `add/remove_challenge_to_gara`, `create_new_challenge`, `get_available_challenges*`, `get_gara_challenges`, `get_gara_challenge_classification`
  - **Trio match**: `trio_reset`, `trio_set_result`
- **Verificato**: POST `/admin/gara/20/start_ssr` (in prod mode simulato) ora ritorna 200 con JSON valido (lista players + ssr_score) ✓
- **🚨 Per applicare**: come gli altri, **riavvia il server**
- **Follow-up scoperti** — altri endpoint admin.* missing dall'allowlist (NON bloccano questa sessione, da decidere ruoli):
  - **`admin.campionato.*`** (11 endpoint, prevalentemente playoff): probabilmente `{"director"}` per gestione campionato
  - **`admin.user.*`** (8 endpoint, gestione ruoli/director requests): probabilmente admin-only (lasciare fuori dall'allowlist)
  - **`admin.venue.*`** (15 endpoint, venue management): mix — `venue_detail`/`venues_list` forse director, gli altri admin
  - **`admin.kpi.*`** (6 endpoint, statistiche piattaforma): admin-only ✓ (lasciare fuori)
- **Lezione**: questo bug (e B6/B8) sono evidenza che il test `tests/new/unit/test_endpoint_coverage.py` o non esiste o non sta più funzionando. Vale la pena verificare e fixarlo per prevenire futuri 404 in prod

### B33 — 🚨 SyntaxError "missing } after function body" su TUTTE le pagine ✅ FIXATO
- **Cosa**: console error `Uncaught SyntaxError: missing } after function body` con `note: { opened at line N, column 17` su qualunque pagina (visto su `/admin/match/194`, `/admin/match/198`, `/admin/gara/21`, ...). I numeri di riga cambiano con la pagina ma il bug è lo stesso
- **Severità**: alto. Il SyntaxError fa fallire il parsing dell'inline script → tutto il codice dopo nello stesso block non viene eseguito → side-effects che vediamo come "page slow", click che non rispondono, ecc.
- **Causa root**: `templates/base.html:600-621` (script "Polling for Notification Badge Real-time Updates")
  - L'IIFE `(function() { ... })()` non era mai chiusa. Il codice arrivava fino a `.start();` (linea 620) e poi `</script>` (linea 621). Mancava il `})();` finale per chiudere la function expression e invocarla
  - Il template è incluso da TUTTE le pagine (gated solo da `{% if current_user.is_authenticated %}`) → ogni pagina autenticata mostrava lo stesso errore
- **Diagnosi guidata dall'utente**: clicco sul link nella console → Firefox jumpa a "subito dopo `<!-- Polling for Notification Badge Real-time Updates -->`" → trovato il sito esatto del bug
- **Fix applicata** (`templates/base.html:621`):
  ```html
          }).start();
      })();          ← AGGIUNTO: chiude e invoca l'IIFE
      </script>
  ```
- **Verifica**: rendering della pagina mostra ora `).start();\n})();\n</script>` come previsto. Bilanciamento bracce ripristinato
- **Lezione**: il SyntaxError di Firefox riportato a riga assoluta del DOM era fuorviante. Il vero hint è venuto dal "click jumps to ..." (DevTools naviga al sito esatto). Lezione di debugging: quando i numeri di riga sembrano inconsistenti (cambiano per pagina diversa), chiedere all'utente "clicca sul link nell'errore — dove ti porta?". Il codebase è troppo grande per cercare a tentoni
- **TODO**: i bug B30/B31 erano in parte oscurati da questo. Probabilmente entrambi erano già fixati ma il SyntaxError parsing-failure spegneva script che avrebbero funzionato. Da verificare al test successivo

### B32 — Reset trio match: assegnare tavolo libero automaticamente (estensione di B17)
- **Cosa**: quando il director resetta un trio match, se c'è un tavolo disponibile in gara va assegnato automaticamente (analogo a B17 per i match regular)
- **Path attuale** (`models/match/trio_scoring_service.py:305-349`):
  - Cancella tutti i `TrioRack`, resetta flag/scores
  - **Preserva** `match.table_assignment` se già presente: status → `PLAYING`
  - Se non c'era tavolo: status → `PENDING` (e lì rimane finché un director non assegna manualmente)
  - Manca il "se c'è un tavolo libero in gara, prendilo"
- **Comportamento atteso**: dopo `reset()`, se `match.table_assignment` è ancora None, chiamare `TableAssignmentService.assign_available_tables(trio.match.gara_id)` (stesso helper proposto in B17)
- **Files coinvolti**:
  - `models/match/trio_scoring_service.py:305-349` (`TrioScoringService.reset`) — aggiungere chiamata a `assign_available_tables` in fondo
  - **Già esistente**: `TableAssignmentService.assign_available_tables(gara_id)` in `models/match/table_assignment_service.py:247`
- **Edge case**: lo stesso `assign_available_tables` deve gestire correttamente il match trio (3 giocatori) → verificare in `_is_player_busy` che non escluda erroneamente uno dei 3 (vedi B12 dove avevamo già aggiunto `exclude_match_id`)
- **Lezione di coerenza**: B17 (match regular) e B32 (trio) descrivono lo stesso requisito su due path paralleli. Quando si implementa B17, applicare la stessa fix qui in modo consistente — meglio in una passata sola

### B31 — 🚨 Trio "Imposta Risultato": dichiara pareggio anche con vincitore chiaro ✅ FIXATO
- **Cosa**: trio match 194, scores inseriti SAMUEL=2, Mario Rossi=3, SERGIO=1 → UI dice "Pareggio!" invece di "Vincitore: Mario Rossi"
- **Severità**: bloccante per il flusso di scoring trio via "Imposta Risultato"
- **Causa root**: conflitto di design tra input e algoritmo
  - Il trio usa metodo **Condorcet/Schulze** (`models/match/trio_schulze.py`) — vincitore = chi batte tutti gli altri in scontri DIRETTI a coppie (head-to-head)
  - Il path "Imposta Risultato" (`TrioScoringService.set_result_direct` in `models/match/trio_scoring_service.py:170-285`) crea **rack sintetici** distribuendo i totali con un'euristica greedy ("chi ha più vincite ancora da assegnare vince il prossimo rack")
  - Esempio con 2-3-1: la distribuzione greedy nei 6 rack del round-robin rende Mario 2-0 vs SERGIO ma 1-1 vs SAMUEL → Condorcet non vede vincitore (Mario non batte tutti) → "Pareggio"
  - L'utente che inserisce totali si aspetta semantica intuitiva "vince chi ne ha più", non la ricostruzione greedy + algoritmo head-to-head
- **Fix applicata** (`models/match/trio_scoring_service.py:267-285`):
  - Dopo aver creato i rack sintetici, prima di Schulze: verificare se c'è un **massimo totale unico**
  - Se sì → quel giocatore è il vincitore (rispetta intent dell'input)
  - Solo se i totali sono in pareggio → fallback a Schulze (legittimo: con totali pari conta head-to-head)
  ```python
  totals = {trio.player1_id: player1_racks, ...}
  max_racks = max(totals.values())
  top_players = [pid for pid, r in totals.items() if r == max_racks]
  if len(top_players) == 1:
      trio.winner_id = top_players[0]
  else:
      trio.winner_id = determine_trio_winner(...)  # Schulze fallback
  ```
- **Note importanti**:
  - Il rack-by-rack flow (player aggiunge ogni rack giocato) **continua a usare Schulze** correttamente: in quel path i rack riflettono la storia reale, head-to-head ha senso
  - Il match 194 era in stato `pending` con 0-0 al momento dell'analisi: la submission precedente era fallita per B30 (csrfToken). Lo screenshot mostrava UI stantia. Dopo restart server e rifix, l'utente dovrà reinserire 2-3-1 — il fix farà il suo lavoro
- **Lezione architetturale**: input semantici diversi richiedono algoritmi di winner-detection diversi. Mescolare "input totali" con "algoritmo head-to-head" è fonte di sorprese. La scelta dell'algoritmo deve seguire la scelta del path di input

### B30 — 🚨 Trio submit: `csrfToken is not a function` (regressione di B6) ✅ FIXATO
- **Cosa**: Paolo (director) prova a inserire risultato trio rapido (match 194, turno 2 8-ball gara 21) → console error `TypeError: csrfToken is not a function` + secondo errore `SyntaxError: missing }` a riga 727 (cascata)
- **BLOCCANTE**: il pulsante "Imposta Risultato" non funziona, impossibile registrare il risultato del trio
- **Causa root (regressione di B6)**:
  - `templates/base.html:54` definisce `window.csrfToken = function() { ... }` come **funzione globale** (legge il meta tag)
  - ~50 template usano `csrfToken()` come funzione, pattern globale storico
  - B6 (defensive fix) ha aggiunto `const csrfToken = {{ csrf_token()|tojson }};` in `match_detail.html:191` → const al module-level **shadowa** la funzione globale via TDZ binding nel global declarative environment
  - In match_detail.html avevo convertito tutti i `csrfToken()` → `csrfToken` (per usare la const)
  - Ma il componente incluso `_match_admin_controls.html` continuava a chiamare `csrfToken()` → `csrfToken` è ora la stringa, non la funzione → TypeError
  - Stesso problema in `_match_challenge_input.html` (per gare con challenge)
- **Fix applicata (revert difensiva di B6)**:
  - Rimosso `const csrfToken = ...` da `match_detail.html:188-191`
  - Convertito tutti i `csrfToken` → `csrfToken()` in match_detail.html (17 occorrenze)
  - Lasciato invariato `_match_admin_controls.html` e `_match_challenge_input.html` (già usavano `csrfToken()`)
  - Verificato: `_round_management.html:171` ha il const ma è dentro un IIFE `(function() { ... })()` → scope locale, non shadowa il globale → safe
- **Lezione architetturale**:
  - Il pattern globale `window.csrfToken = function()` di base.html è già robusto
  - `const` a script-level scope shadowa proprietà di window via TDZ — gotcha non ovvio. Mai dichiarare `const csrfToken` in qualsiasi template renderizzato in pagine con altri script; usare nomi diversi se serve una const, oppure rispettare il pattern globale
  - **Mio errore**: la "defensive fix" di B6 ha introdotto questa regressione. Ho appreso: prima di duplicare un pattern già fornito globalmente, verificare se è davvero rotto, non aggiungere "for good measure"
- **Files toccati nella fix**:
  - `templates/match_detail.html:188-191` (rimosso const), 17 sostituzioni `csrfToken` → `csrfToken()`
  - `templates/components/_match_admin_controls.html` — non modificato (era OK)
  - `templates/components/_match_challenge_input.html` — non modificato (era OK)
- **Bonus i18n**: convertita stringa italiana `'Richiesta già in corso, ignorata'` (console.log developer-facing) → `'Request already in progress, ignored'` per coerenza con altri log inglesi nel file
- **TODO**: il SyntaxError a riga 727 nella console era probabilmente residuo di parsing in cascata dal csrfToken — da verificare al prossimo restart server

### B29 — 🚨 Modal "Risultato Rapido" usa config gara invece di config turno (BLOCCANTE per quel path)
- **Cosa**: in admin/gara, il modal "Imposta Risultato Rapido" su un match del turno 1 (override 10-ball race-to-6):
  - Mostra "Esattamente 4 rack" (default gara) invece di "Race to 6"
  - **Blocca l'input** a max=4 (`max="{{ gara.distance }}"` sui campi `<input type="number">`) → impossibile inserire 5 o 6
- **Conferma utente**: "la ui non mi permette di inserire valori superiori a 4. se vado in admin/match, invece, la ui riconosce correttamente al 6 e mi permette di inserire il risultato"
- **Workaround disponibile**: `/admin/match/<id>` (usa `_match_admin_controls.html` con `match.effective_distance`) — ma il bug rende inutilizzabile il modal rapido per i match con override
- **Severità rivista**: prima ho scritto "UI-only" perché il backend rifiuta input sbagliati. Sbagliato: il backend non viene mai raggiunto perché l'input HTML blocca prima. Quindi è funzionalmente bloccante per il path "imposta risultato rapido" sui match con override per turno
- **Causa root**: `templates/gara_detail.html:530-600` (modal `quickResultModal`) è **renderizzato una sola volta** server-side leggendo `gara.distance_config`, `gara.is_race_to`, `gara.distance` (linee 544-548, 576, 580, 586, 590, 594, 598). Lo stesso modal viene riutilizzato per ogni match cliccato → testo sempre fermo sui valori della gara, ignorando override per turno
- **Backend invece OK**:
  - `templates/components/_match_admin_controls.html:61-62, 84-89` usa correttamente `match.distance_config` e `match.effective_distance` (ADR-027 compliant)
  - `routes/admin/match/...set_match_result_direct` valida tramite `Match.distance_config` → rifiuta input sbagliati
- **Fix proposto (UI-only)**:
  1. Quando l'utente clicca "Imposta Rapido" su un match, popolare via JS i campi del modal (testo modalità, max input) usando attributi `data-*` letti dal trigger
  2. Sorgente dati: ogni "trigger row" del match nella gara_detail dovrebbe già esporre `match.effective_distance` e `match.distance_config.is_race_to_racks`. Vedi `_match_admin_controls.html:61-62` come pattern esistente
  3. Aggiornare in `submitQuickResult()` o nella funzione che apre il modal: leggere i `data-*` del button cliccato e settare:
     - Testo "Modalità: ... " in `#quickResultNormalInfo`
     - `max` di `#quickPlayer1Score`/`#quickPlayer2Score`
- **Files coinvolti**:
  - `templates/gara_detail.html:530-600` (modal HTML, sostituire valori statici con placeholder JS)
  - `templates/gara_detail.html:1410-1460` (logica JS che apre il modal — già setta i player labels, va estesa per distance/race_to)
  - Eventuali "row trigger" che aprono il modal: assicurarsi che esponga `data-effective-distance` e `data-is-race-to`
- **Estensione**: stesso pattern probabilmente nel modal trio (`#quickResultTrioInfo` linee 553-570) — il `trio_max_racks` deriva sempre da `gara.distance`. Per i turni con override la logica trio dovrebbe anch'essa adattarsi
- **Lezione architetturale**: ADR-027 richiede audit anche dei **testi statici** nei template, non solo della logica di scoring. I modal condivisi tra match diversi sono particolarmente a rischio: render-once + reuse-many = staleness garantita

### B28 — Trio confirm: incoerenza tra match_detail e gara_detail per director-player
- **Cosa**: in un match trio dove Paolo è giocatore E director della gara, il pulsante "Valida il risultato" su `/admin/match/<id>` non cambia lo stato; da `/admin/gara/<id>` invece la stessa azione funziona e lo stato passa a "completata"
- **Non è bug di allowlist**: entrambi gli endpoint coinvolti sono in `ENDPOINT_ROLES`. È un'**incoerenza di design** tra le due pagine
- **Causa root**: due endpoint diversi per "conferma trio":
  - `player.confirm_trio_result` (`POST /player/match/<id>/trio/confirm`): chiama `TrioMatchService.confirm_trio_result_by_player()` → richiede che **TUTTI E 3** i giocatori confermino prima di completare. La conferma di Paolo da sola non basta, servono anche BRUNO+PICCHIO
  - `admin.competition.trio_confirm` (`POST /admin/gara/trio/<id>/confirm`): chiama `TrioMatchService.confirm_trio_result()` → **one-shot**, completa subito (azione di director)
- **`templates/match_detail.html:261-265`** ha un dual-path con commento esplicito:
  ```jinja2
  {% if user_is_player %}
      const trioEndpoint = `/player/match/{{ match.id }}/trio/confirm`;
  {% elif user_can_manage %}
      const trioEndpoint = `/admin/gara/trio/{{ match.trio_match.id }}/confirm`;
  {% endif %}
  // Comment: "Player endpoint has priority (fairness: directors who are players use player flow)"
  ```
  → quando l'utente è **sia player sia director** (caso di Paolo), `user_is_player=True` → usa endpoint player → la sua conferma da sola non basta → lo stato non cambia
- **Da `/admin/gara/<id>`** invece il pulsante punta direttamente al path admin (`trio_confirm`) bypassando il "fairness intent" del match_detail → un click chiude tutto
- **Il "fairness" del match_detail è solo apparente**: il director-player che vuole forzare la chiusura senza aspettare gli altri due trova facilmente la scorciatoia su admin/gara
- **Reframing (osservazione utente)**: "valida risultato dentro admin/match non considera che se a validare è il director allora deve validare completamente"
  - Cioè: la priorità player-first nel match_detail è un **errore di ordine**, non un design intenzionale. Il ruolo `director` ha semantica amministrativa (validare chiude la partita); quando l'utente cumula i ruoli, l'azione "valida" deve invocare il path admin (one-shot) perché stai esercitando il ruolo amministrativo, non quello di giocatore
  - Il commento `"Player endpoint has priority (fairness)"` nel template confonde due cose diverse:
    - **Conferma del proprio risultato come giocatore** (atto privato, deve passare dal flusso 3-of-3)
    - **Validazione del match come director** (atto pubblico/gestionale, è il proposito stesso del ruolo director)
  - Trattarli come la stessa azione "compressa in un bottone con priorità player" rompe la semantica del ruolo director per chi cumula i ruoli
- **Tre possibili linee d'azione (in ordine di preferenza secondo questa lettura)**:
  1. **Pro-director (raccomandata)**: invertire la priorità in `match_detail.html:261-265` → `{% if user_can_manage %} admin path {% elif user_is_player %} player path {% endif %}`. Allinea match_detail con gara_detail e con la semantica del ruolo. Il director-player che vuole agire "come giocatore" deve farlo da una pagina senza permessi admin (es. dashboard player) — coerente con il principio "il ruolo più alto vince per azioni amministrative"
  2. **UI esplicita (più trasparente, più verbosa)**: due bottoni distinti per il director-player ("Conferma come giocatore" / "Valida come director") con motivazione visibile. Costo: spazio UI + complessità
  3. **Pro-fairness (status quo + chiusura del backdoor)**: estendere il "fairness" anche a gara_detail → un director che è anche giocatore non può mai usare il path admin one-shot. Più rigoroso ma rende impossibile chiudere match abbandonati dagli altri 2
- **Implicazione su altri casi simili**: è probabile che lo stesso pattern di priorità sia replicato per altre azioni (forfeit, reset trio). Da auditare insieme
- **Files coinvolti**:
  - `templates/match_detail.html:259-300` (logica dual-path con priorità player)
  - `routes/player/matches.py:67-91` (endpoint player con 3-of-3)
  - `routes/admin/competition/matches.py:54-66` (endpoint admin one-shot)
  - `models/match/trio_match_service.py` — `confirm_trio_result` vs `confirm_trio_result_by_player`
- **Note**: l'attuale implementazione lascia anche il rischio che il director-player non capisca **perché** il pulsante non funziona (nessun feedback visibile sul fatto che servono altre 2 conferme)

### B27 — Storico campionati: filtri assenti + posizione classifica spesso vuota
- **Cosa**: in `/player/history?tab=campionati` (a) non ci sono filtri (search/stato), (b) le schede dovrebbero mostrare la posizione del giocatore in classifica generale ma sospetto sia spesso vuota
- **(a) Filtri — decisione di design da rivedere**:
  - `templates/components/_history_campionati_tab.html:3` ha il commento esplicito `<!-- No filters for campionati (simpler view) -->`
  - Quindi **scelta deliberata**, non bug tecnico. Probabilmente datata da quando i campionati erano sempre pochi
  - **Proposta**: aggiungere almeno filtro "Attivi/Conclusi" (la prop `campionato.is_active` è già usata per il badge), eventualmente search per nome quando il volume cresce. Allineare allo stile di `_history_filters.html` già usato per matches/gare
  - Il sospetto dell'utente "forse dipende dal fatto che ci sono solo due campionati" è corretto: con 2 campionati non si nota il gap, ma con 20+ diventa scomodo
- **(b) Posizione classifica — feature presente ma fragile**:
  - `templates/components/_history_campionati_tab.html:57-79` ha già la logica (medaglia top 3 + "N° Classifica Generale")
  - Ma legge `campionato.classifications` filtrato per `cls.user_id == current_user.id`: se quel record `Classification` non è popolato, **niente posizione**
  - Possibili cause:
    - Campionato senza classifica generale calcolata (es. campionato non ancora completato, o flag `final_playoffs`/`challenge_mode` che cambia il flusso)
    - Utente iscritto a una sola gara del campionato → forse non viene calcolata una posizione aggregata
    - Trigger di calcolo non chiamato dopo termine ultima gara
  - **Verifica suggerita**: query DB locale per i campionati visibili nello storico:
    ```sql
    SELECT c.id, c.name, COUNT(cl.id) as classifications
    FROM campionato c LEFT JOIN classification cl ON cl.campionato_id = c.id
    GROUP BY c.id;
    ```
    Se `classifications=0` per campionati conclusi → manca il trigger di popolamento
- **Files coinvolti**:
  - `templates/components/_history_campionati_tab.html:3` (filtri da aggiungere)
  - `templates/components/_history_campionati_tab.html:57-79` (logica già presente)
  - `templates/components/_history_filters.html` (pattern di riferimento per i filtri)
  - `models/classification/services.py` (probabile sede del trigger di calcolo classifica generale campionato)
- **Estensione**: stessa lacuna probabile per i campionati "challenge_mode" — la classifica challenge è separata e potrebbe non popolare `Classification`

### B26 — Storico gare: schede senza posizione finale in classifica
- **Cosa**: nello storico delle gare, le schede delle singole gare non mostrano (o non sempre mostrano) la posizione finale del giocatore in classifica
- **Due possibili viste in causa**:
  1. **`/player/history?tab=gare` → `_history_gare_tab.html:90-114`**: la logica per la posizione finale **c'è già** (medaglia per top 3, "N° Posto" altrimenti), ma è gated da:
     - `gara.status == 'completed'` (esclude `awaiting_ssr`, `playing`, ecc.)
     - `rc.round_number == gara.current_round` (deve esistere una `RoundClassification` per il "current_round" della gara)
     - `if user_final_position` truthy
     - **Sospetto bug**: gare standalone terminate senza pieno completamento (es. SSR che lascia `awaiting_ssr`, o `current_round` non sincronizzato col round in cui esiste la classification) → posizione invisibile anche se i dati sarebbero ricavabili. Da verificare per gara 20 dopo SSR
  2. **`/player/profile` → `_player_inscriptions.html`**: mostra le iscrizioni come `<li>` (campionato + standalone), **manca completamente** qualsiasi info sulla posizione finale. Solo data + status badge. Se il commento dell'utente parla di "schede" del profilo, qui va aggiunta proprio la feature
- **Fix proposto**:
  - Verificare quale dei due casi è quello osservato (chiedere all'utente o ispezionare lo screenshot mentale)
  - Caso 1 (history): rilassare il filtro per includere SSR completato; possibile cercare la max `round_number` tra le `round_classifications` invece di affidarsi a `current_round`
  - Caso 2 (profilo): replicare il pattern di `_history_gare_tab.html:91-113` dentro `_player_inscriptions.html`, magari come piccolo badge accanto al nome della gara
- **Files coinvolti**:
  - `templates/components/_history_gare_tab.html:90-114` (logica esistente, possibile bug)
  - `templates/components/_player_inscriptions.html` (logica mancante)
  - `models/classification/models.py` — `RoundClassification.calculate_classification_after_round` (popolamento)
- **Estensione utile**: stessa info dovrebbe comparire anche nella **dashboard** del giocatore per le gare appena finite (vedi anche B22 "criterio coerente")

### B25 — Profilo: storico partite recenti esclude le gare singole
- **Cosa**: nel profilo del giocatore (`/player/profile`), nel box "Storico Partite Recenti" non compaiono i match delle gare standalone (es. gara 20 appena giocata da Paolo)
- **Causa probabile (ordering, non query)**:
  - `routes/player/profile.py:50-64` la query usa già `outerjoin(Campionato)` quindi le gare standalone SONO incluse a livello DB
  - MA l'ordering è: `Campionato.created_at.desc().nullslast(), Gara.date.desc(), Match.round_number.desc()`
  - `nullslast()` come **prima chiave** spinge le gare standalone (campionato_id NULL) IN FONDO, indipendentemente dalla loro data
  - Poi a riga 87-89: `[m for m in matches if m.status == COMPLETED][:10]` → se ci sono 10+ match di campionato, le gare standalone vengono troncate via
- **Files coinvolti**:
  - `routes/player/profile.py:50-64` (query da correggere)
  - `routes/player/profile.py:87-89` (slice `[:10]`)
  - `templates/components/_player_recent_matches.html` (template, già OK — gestisce `match.gara.campionato is None`)
- **Fix proposto**: ordinare per `Match.created_at.desc()` (o `Gara.date.desc()`) come **prima chiave**, lasciando il campionato come tie-break secondario. Così le partite recenti — campionato o standalone — emergono in modo equo
- **Verifica suggerita**: query veloce sul DB locale per confermare:
  ```sql
  SELECT COUNT(*) FROM match m JOIN gara g ON m.gara_id=g.id
  WHERE (m.player1_id=<paolo_id> OR m.player2_id=<paolo_id>)
    AND m.status='completed' AND g.campionato_id IS NULL;
  ```
  Se >0 ma non compare in profilo → conferma il bug di ordering
- **Estensione**: stessa logica probabilmente anche in `dashboard.dashboard` e `admin.user.user_detail` se usano lo stesso pattern. Da verificare insieme

### B24 — Auto-cancellazione notifiche non funziona (metodo orfano)
- **Cosa**: l'auto-cancellazione delle notifiche secondo `NotificationPreference.auto_delete_days` non avviene mai
- **Causa root**: `NotificationService.auto_delete_by_user_preferences()` (`models/notification/services.py:382`) è implementato correttamente ma **non è invocato da nessun trigger**. Grep conferma: zero caller nel codebase non-test
- **Anche `expire_old_notifications()` e `cleanup_old_notifications()`** stessa situazione (vedi `models/notification/CLAUDE.md` "Do not forget cleanup - Run periodically" — è documentato che vanno chiamati ma non lo fa nessuno)
- **Soluzione (proposta dall'utente, sensata)**: chiamare `auto_delete_by_user_preferences()` all'accesso a `/player/notifications` (`routes/player/notifications.py:46`). Pro: trigger naturale, just-in-time. Contro: latency aggiunta sulla page load se ci sono molte notifiche da cancellare
- **Soluzioni alternative o complementari**:
  - **Cron/scheduled task** giornaliero (analogo a `auto_deploy.py` già presente in CLAUDE.md). Più efficiente per volumi alti, ma richiede infrastruttura
  - **`@before_request` hook** sul blueprint player (probabilistico, es. 1 chiamata su 100, per amortizzare il costo)
  - **Combinazione**: trigger on access + cron come fallback
- **Files coinvolti**:
  - `routes/player/notifications.py:46` (route da modificare se si va con la soluzione user)
  - `models/notification/services.py:382` (metodo già pronto)
- **Note**:
  - Lo stesso pattern "metodo implementato + mai chiamato" potrebbe valere per altri cleanup nel codebase. Audit `cleanup_*` / `expire_*` consigliato
  - Se si va con "trigger on access": chiamare il metodo PRIMA di caricare la lista notifiche, così l'utente vede già lo stato pulito

### B23 — Notifica level-up: pulsante "Visualizza progressi" → 404
- **Cosa**: notifica "Congratulazioni hai raggiunto il livello 11" mostra pulsante "Visualizza progressi" che porta a 404 (probabilmente endpoint gamification non in allowlist per il ruolo dell'utente)
- **Atteso**: **se l'endpoint target non è visibile per l'utente, il pulsante deve essere nascosto** (no promesse rotte)
- **Pattern già esistente nel codebase** (vedi `feature_endpoint_map.feature_visible_to_user`): è già usato per nudge/unlock in `frontend_bridge.py:222,248` per non promuovere feature non raggiungibili. **Non è stato applicato anche al level-up**
- **Files probabili**:
  - `models/notification/...` (template della notifica level-up con il pulsante)
  - `models/gamification/notification_handlers.py` (compone il messaggio + link)
  - `templates/notifications/...` (rendering del pulsante)
- **Fix duplice**:
  1. Aggiungere `gamification.dashboard` (o l'endpoint specifico per "progressi") all'allowlist se è davvero accessibile a player/director
  2. Anche dopo il fix #1: il template della notifica deve usare `feature_visible('endpoint.name')` per nascondere il pulsante quando l'endpoint non è visibile (defense-in-depth — vale per future regressioni o utenti con ruoli non standard)
- **Memoria correlata** ([feedback_gamification_aligned_with_allowlist](memory)): "Nudge/unlock toast filtrati da `feature_endpoint_map.feature_visible_to_user`; non promuovere endpoint nascosti." — vale ANCHE per le notifiche level-up
- **Audit**: probabilmente lo stesso problema esiste per altre notifiche gamification (achievement unlocked → "Vedi achievement", quest completed → "Vedi quest", ecc.). Verificare tutti i pulsanti delle notifications gamification

### B22 — Lista gare in dashboard: serve criterio coerente + storia recente
- **Cosa**: la dashboard giocatore non mostra le gare appena terminate. Più in generale, manca un **criterio globale e coerente** su quali gare visualizzare nelle viste sintetiche (dashboard guest/player/director vs pagina completa)
- **Criterio richiesto** (per dashboard sintetiche, guest e player):
  - **In preparazione** (`status=setup`): mostra **solo se `gara.date > oggi`** (a guest/player). Admin e director della gara: sempre.
  - **Iscrizioni aperte** (`status=inscription`): **sempre**
  - **In corso** (`status=playing` / `awaiting_ssr`): **sempre**
  - **Terminate** (`status=completed`): **ultime 2** (per data discendente)
  - Pulsante "Vedi tutte" → **pagina dedicata** con paginazione, ordinamento, ricerca
- **Logica differenziata per ruolo**:
  - **Guest**: criterio sopra applicato a tutte le gare pubbliche
  - **Player**: criterio applicato + filtro "solo gare alle quali sono iscritto" (oppure due sezioni separate: "Le mie gare" + "Altre gare")
  - **Director della gara**: vede sempre tutte le gare che gestisce (incluse quelle in setup con data passata)
  - **Admin**: vede tutto, sempre
- **Files coinvolti**:
  - **Dashboard player**: `templates/components/_separated_dashboard_content.html`, `routes/player/dashboard.py` (o equivalente)
  - **Dashboard guest/home pubblica**: `templates/index.html` (probabilmente), `routes/main/...`
  - **Pagina lista completa**: già esiste `main.public_garas_list` (`/garas`)? Verificare se ha già paginazione/ricerca, oppure va estesa
- **Filtraggio centralizzato**: probabilmente conviene un helper unico (es. `models/competition/dashboard_query.py` o `GaraService.get_dashboard_garas(role, user_id, limit_completed=2)`) che applichi il criterio in modo uniforme. Oggi probabilmente la logica è duplicata in più route/template
- **Terminologia**: "partite" qui = **gare** (competizioni intere). I match individuali (partite all'interno di una gara) sono altra cosa. Da chiarire nei prossimi annotamenti

### B21 — Toast gamification poco esplicativi (XP, level-up, achievement)
- **Cosa**: i toast gamification non spiegano **cosa è successo** né **perché** l'utente riceve XP/livello/achievement
- **Atteso**: messaggi narrativi e self-contained, leggibili senza dover ricostruire il contesto (es. "+50 XP per aver vinto la partita contro EGLE" invece di "+50 XP — Partita #173")
- **Esempi concreti dal codice attuale** (`models/gamification/frontend_bridge.py`):
  - **XP** (riga 134-148): reason = `"Partita #173"` o `"Torneo #20"` → opaco. Migliore: `"per aver vinto la partita contro EGLE"` / `"per esserti iscritto alla gara N"` / `"per aver completato il match"`
  - **Level-up** (riga 151-160): titolo = `f"Livello {new_level}"` senza spiegazione. Migliore: aggiungere subtitle tipo `"Hai accumulato N XP totali"` o `"Ora puoi sbloccare X"`
  - **Achievement** (riga 163-174): mostra nome + difficulty ma `description` è generica `f"+{xp} XP - {category}"`. Migliore: usare la descrizione semantica dell'achievement (`achievement.description` dal DB, già disponibile)
  - **Streak** (riga 177-187): solo `count` + `type`, senza testo. Migliore: `"Hai giocato X settimane consecutive!"`
  - **Quest** (riga 200-209): description hardcoded `"Quest completata!"` → ripetere il nome quest e magari il reward sarebbe utile
- **Files coinvolti**:
  - `models/gamification/frontend_bridge.py` (testi sorgente)
  - `static/js/gamification.js` (renderer toast)
  - i18n: tutti i nuovi testi devono essere wrappati in `_()` per tradurre IT/EN
- **Correlato**: B10 (toast "view other profiles" poco chiaro) e B4 (toast "streak perso" da eliminare/tradurre) — sono tutti aspetti della stessa direzione: rendere i toast gamification narrativi e azionabili

### B18 — Dashboard player: scheda partita ignora override disciplina per turno (ADR-027)
- **Cosa**: ultimo turno gara 20 ha override `RoundConfiguration` (8-ball, 4 rack). La scheda partita nella dashboard player mostra **correttamente i 4 rack** (override distance applicato) **MA mostra "9-ball" come disciplina** (default gara invece dell'override 8-ball)
- **Causa**: `templates/components/_separated_dashboard_content.html:119` usa `match.gara.discipline` direttamente, ignorando l'override per turno. Pattern bacato:
  ```jinja
  {{ match.gara.discipline|replace('_',' ')|title }}  ← ignora override
  ```
- **Fix**: usare `match.discipline or match.gara.discipline`, oppure ancora meglio `match.effective_discipline` (che già implementa il fallback secondo ADR-027)
- **Pattern corretto** (esempio già esistente in `templates/components/_match_header.html:7`):
  ```jinja
  {{ (match.discipline or match.gara.discipline)|replace('_',' ')|title }}
  ```
- **Sospetto pattern globale**: ho fatto grep e ho trovato **almeno 5 template** che usano `gara.discipline` direttamente invece di `match.discipline or gara.discipline`:
  - `_separated_dashboard_content.html:119` ← questo bug
  - `_my_inscriptions_dashboard.html:13`
  - `_available_proofs.html:12`
  - `_director_my_inscriptions.html:11`
  - `_history_gare_tab.html:87`
  - `_campionato_garas.html:34`
  Alcuni di questi sono "lista gare" (non per match singolo) → ok usare gara. Ma quelli che mostrano un match specifico devono usare `match.effective_discipline`. Audit completo da fare
- **Correlato a B3** (discipline non normalizzate): quando si fixa, conviene **anche** introdurre il filtro Jinja `|discipline_display` per evitare di ripetere `replace('_', ' ')|title` ovunque

### B17 — Reset partita: se c'è un tavolo libero, assegnarlo automaticamente
- **Cosa**: quando il director/admin resetta una partita, attualmente il match torna a `pending` senza tavolo (anche se c'è un tavolo libero in gara). Il director deve poi assegnarlo manualmente
- **Atteso**: dopo il reset, se c'è un tavolo libero (non occupato da altro match playing), va **assegnato automaticamente** al match resettato → match passa direttamente da `pending` a `playing`
- **Files coinvolti**:
  - `models/match/rack_service.py::reset_match_complete` (entry point) → in fondo, chiamare `TableAssignmentService.assign_available_tables(match.gara_id)`
  - `models/match/match_service.py::reset_to_pending` (variante) → stessa logica
  - **Già esistente**: `TableAssignmentService.assign_available_tables(gara_id)` in `models/match/table_assignment_service.py:247` fa esattamente questo — assegna tavoli liberi ai match pending dell'intera gara
- **Edge case da gestire**:
  - Se il reset avviene su match già completato di un round precedente (e gara è in round successivo), forse non si vuole riassegnare → solo se match è del round corrente
  - Se il match resettato fa parte di un trio, la logica trio_match potrebbe richiedere considerazione speciale

### B16 — Ordine turni in admin/gara → "Partite": dipende da stato gara
- **Cosa**: nella sezione "Partite" di admin/gara, i turni dovrebbero essere ordinati in funzione dello stato della gara
- **Atteso**:
  - Gara in corso (status `playing` / `inscription` / `setup`) → turni dal **più recente al più vecchio** (turno corrente in alto, utile al director che lavora sul corrente)
  - Gara completata (status `completed`) → ordine **cronologico** (primo in alto, utile per consultazione storica)
- **Files coinvolti**:
  - **Mobile**: `templates/components/_match_cards_mobile.html:16,35,46` — ora `for round_num in range(1, gara.rounds_count + 1)` (ascendente). Per i 2 loop su `active_rounds` e `completed_rounds`, applicare `reverse()` quando gara non è completata
  - **Desktop**: vedere come è renderizzato in `templates/gara_detail.html` (probabilmente inline, non in un partial dedicato — i `_match_table*.html` non esistono)
- **Pattern Jinja**: `{% for round_num in (active_rounds|reverse if gara.status != 'completed' else active_rounds) %}` o equivalente con variabile pre-calcolata nel route

### B15 — "Imposta Rapido" modal: input fuori soglia → modal si chiude in silenzio
- **Cosa**: nel modal di "Imposta Rapido" (admin/director), inserendo più rack del massimo consentito (es. 6 rack su gara race-to-5), il modal si chiude **senza messaggio di errore**. L'utente non capisce che è successo
- **Atteso (preferito)**: validazione JavaScript live nel modal — quando si cambia un campo rack, l'altro viene **limitato dinamicamente** in base alla modalità:
  - **race-to N**: somma max dei rack è N + (N-1) = 2N-1, e nessuno dei due può superare N
  - **exact N**: somma esatta è N, quindi p1 + p2 == N (l'altro campo è derivato/limitato)
  - usare `<input type="number">` con `min`/`max` aggiornati dinamicamente al cambio
- **Atteso (alternativo, fallback)**: messaggio di errore visibile nel modal **che non deve chiudersi** finché l'utente non corregge o annulla esplicitamente
- **Files coinvolti**:
  - Modal: `templates/components/_match_admin_controls.html:59` (form `set_match_result_direct`)
  - Backend (già valida): `routes/admin/match/scoring.py::set_match_result_direct` → `ScoringService._validate_score_limits` solleva `ValueError` con messaggio chiaro, ma il modal non lo mostra
- **Bug aggiuntivo (correlato)**: il messaggio di errore del backend **viene perso** dal flusso form-submit → redirect, senza un toast/flash visibile. Potrebbe essere il vero problema da cui parte: il backend valida e rifiuta, ma il client non riceve/mostra niente. Da verificare se il modal usa fetch AJAX o form submit standard
- **Caso speculare (sotto-soglia)**: stesso problema anche con valori **inferiori** al risultato finale (es. 2-1 in race-to-5 → match non finito). Il modal si chiude in silenzio. Due opzioni di design da scegliere:
  - **(a)** errore esplicito "Risultato incompleto: ti mancano X rack" + modal non si chiude
  - **(b)** accettare come **risultato parziale** → match resta `playing` con score parziale (utile se il director vuole pre-popolare il punteggio mentre il match è in corso)
  - Decisione utente: una delle due, ma non chiusura silenziosa

### B14 — Classifica admin gara non rispetta `classification_system` scelto
- **Cosa**: nella vista admin/gara, la classifica mostra **solo "differenza rack"** sia in mobile che (forse) in desktop, indipendentemente dal sistema di classificazione configurato
- **Atteso**: se `classification_system=WINS` (default per Amalfi/Random/Round-Robin), la classifica mostra **vittorie + diff rack**. Se `RACK`, solo rack. Se `POSITION`, posizioni
- **Sistemi disponibili** (da `migrations/add_classification_system_field.py`):
  - `WINS`: ordina per vittorie, poi diff rack (default per la maggior parte delle strategie)
  - `RACK`: ordina per diff rack
  - `POSITION`: per posizioni
- **Scope**: la fix vale **sia per mobile che per desktop** (l'utente l'ha esplicitato)
- **Files probabili**:
  - `templates/gara_detail.html` (sezione classifica)
  - eventuali partial/include per il leaderboard
  - service layer che popola i dati: `models/classification/services.py`
- **Nota**: il campo `gara.classification_system` esiste già nel DB (vedi migration `add_classification_system_field.py`); è solo la **visualizzazione** a non leggerlo correttamente

### B11 — Flash "account non verificato" poco chiaro, manca link
- **Cosa**: messaggio post-login `"Attenzione: il tuo account non è ancora verificato. Controlla la tua email."` è troppo vago
- **Atteso**: spiegazione più chiara (cosa NON funziona finché non verifichi?) + link "Reinvia email di verifica" inline nel flash
- **Endpoint per re-invio**: già esiste `player.request_verification_email` (visto in allowlist `feature_flags.py:65`)
- **File**: `routes/auth.py:45` (string hardcoded; manca anche `_()` → non è i18n)
- **Note correlate**: stesso problema anche in `routes/auth.py:79` (flash post-registrazione `"Registrazione completata! Controlla la tua email per verificare l'account."` — anch'esso non i18n)

### B10 — Toast "View other profiles" poco chiaro
- **Cosa**: il toast "view other profiles" non si capisce
- **Atteso**: messaggio più chiaro + eventuale link diretto alla pagina dei profili
- **Files probabili**: `models/gamification/frontend_bridge.py` (handle_nudge_event/handle_feature_unlock_event), `static/js/gamification.js` (renderer toast nudge/unlock)
- **Nota**: dato che ora TUTTI i toast gamification sono centrati hero (B1), un link cliccabile dentro il toast sarebbe più ergonomico

### B9 — Pagina admin gara non aggiorna i punteggi automaticamente
- **Cosa**: Paolo (director) sulla pagina `/admin/gara/20` non vede i punteggi aggiornarsi quando cambiano (es. quando un player aggiunge un rack su altro tab/dispositivo)
- **Verificato lato server (tutto OK)**:
  - `/sse/poll/gara/20?since=...` → 200 ✓
  - `emit_gara_event` chiamato correttamente in `scoring.py:48` quando si aggiunge un rack ✓
  - Test simulato: polling riceve evento `match_updated` con dati corretti dopo POST add_rack ✓
  - `polling.js` incluso in `base.html`, `Polling.reloadOnEvents` chiamato in `gara_detail.html:1810` ✓
  - `sse.poll_gara` è in `INFRASTRUCTURE_ALLOWLIST` (sempre visibile)
- **Probabilmente browser-side** (come ipotizzato dall'utente): cache JS vecchia, errore JS in console che blocca il polling, o sessione stale post-restart server
- **Da fare per diagnosticare**:
  1. Hard refresh (Cmd+Shift+R) e riprova
  2. Aprire console e verificare se ci sono errori JS prima del messaggio `[Polling] match_updated, reloading...`
  3. Verificare nel Network tab che `/sse/poll/gara/20?since=...` venga chiamato ogni 3 secondi
- **Se persiste dopo hard refresh**: probabile errore JS specifico — chiedere all'utente uno screenshot della console come per B6

### B7 — Match detail: ora con secondi/decimali non arrotondata
- **Cosa**: in `/admin/match/173`, sezione "Info partita" → "Tempi", il formato dell'ora mostra secondi (probabilmente con decimali/microsecondi) non arrotondati
- **Atteso**: formato pulito tipo `HH:MM` o al massimo `HH:MM:SS`
- **Files probabili**: filtri Jinja `|datetime_local` / `|date_local` o template `templates/match_detail.html` (sezione "Info partita")

### B5 — Guest: gara "terminata" listata insieme alle attive
- **Cosa**: come guest, nella sezione "Standalone competitions" è visibile una gara già **terminata**, mescolata a quelle attive (setup/inscription/playing)
- **Atteso**: gare completate dovrebbero essere visualizzate in modo distinto (es. sezione separata "Gare passate", oppure badge "Terminata" + ordinamento in fondo, oppure non visibili affatto se non rilevanti)
- **Da decidere**: vogliamo mostrare lo storico al guest? Se sì, in che forma?
- **Endpoint coinvolto**: probabilmente `main.public_garas_list` (vedi `ENDPOINT_ROLES` in `utils/feature_flags.py`, è `{"anonimo", "player", "director"}`)
- **Files da guardare**: route `routes/main/...` e template lista pubblica gare

### B4 — Toast "Hai perso uno streak" duplicato + da eliminare?
- **Cosa**: a fine match il toast "Hai perso uno streak di 2 settimane!" è apparso **due volte**
- **Causa duplicazione (confermata leggendo `event_handlers.py:190-202`)**: per ogni player a fine match si chiama `StreakService.record_activity` due volte:
  - una per `WEEKLY_MATCH`
  - una per `WEEKLY_ACTIVITY`
  Se entrambi gli streak sono rotti, viene emesso `StreakBrokenEvent` due volte → 2 toast.
- **Decisione utente**: il toast "streak perso" probabilmente va **eliminato del tutto** — non c'è azione possibile da fare in risposta. Senza un'azione (es. "usa un freeze"), il messaggio non è azionabile.
- **Tradurre "streak" → italiano** (richiesta correlata) nel toast milestone (`StreakMilestoneEvent` → "streak" event in `frontend_bridge.py:177`). Termini possibili: "serie", "sequenza", "filotto" (gergo biliardo)
- **Punti di intervento**:
  - Eliminazione toast: rimuovere `handle_streak_broken` in `models/gamification/frontend_bridge.py:190-198` (oppure rimuovere la registrazione handler riga 77-81)
  - Traduzione: stringhe hardcoded in `frontend_bridge.py` da spostare in `_()` + verificare anche `gamification.js` per stringhe lato client
- **Da decidere quando si fixa**: meglio rimuovere il bridge handler (toast) ma **lasciare** l'evento `StreakBrokenEvent` emesso dal service (potrebbe essere usato per analytics/notifications future)

### B3 — Discipline non normalizzate né i18n (problema globale)
- **Cosa**: i nomi delle discipline appaiono in formati inconsistenti e non tradotti, in più punti dell'app:
  - Dropdown: "9 ball" / "8-Ball" (formattazione mista)
  - **Card guest**: descrizione mostra raw `9_ball` (con underscore!) — istanza scoperta nella lista gare guest (B5)
- **Atteso**: nomi unici (un solo formato) + tradotti in italiano via `_()`
- **Scope**: ovunque nei template (probabilmente tutti i posti che usano `discipline_choices` da `Discipline.get_choices()`, ma anche posti che mostrano `gara.discipline` raw senza filtro)
- **Soluzione tipo**: usare costanti centrali (Discipline enum) con `display_name` tradotto via `_()`. Rimuovere ogni `.replace("_", " ").title()` ad-hoc nei template
- **Files coinvolti** (da verificare):
  - `models/status_enum.py::Discipline.display_name` (sorgente)
  - `templates/components/_round_management.html` (usa `.replace("_", " ").title()` riga 18, 20, 60)
  - `templates/admin/gara_create_standalone.html`
  - `templates/components/_new_gara_modal.html`
  - `templates/components/_gara_edit_form.html`
  - `routes/admin/competition/detail.py`, `routes/admin/competition/crud.py`, `routes/admin/campionato.py` (passano `discipline_choices=Discipline.get_choices()`)

### B2 — 🚨 Errore 400 salvataggio config turno (CSRF mancante) ✅ FIXATO
*(I round-config endpoint sono già in allowlist ✓ — il fix B2 era effettivamente CSRF, non ADR-028.)*


- **Cosa**: salvataggio override per turno → "Errore 400"
- **Causa**: il fetch JS in `templates/components/_round_management.html` non mandava `X-CSRFToken` header. CSRF è abilitato in dev/prod (disabilitato solo in TestingConfig). L'`@app.errorhandler(CSRFError)` rendeva HTML 400 → la `resp.json()` falliva → utente vedeva "Errore 400" generico
- **Fix**: aggiunto `X-CSRFToken` header su POST/DELETE in `_round_management.html` (3 fetch)
- **Da verificare manualmente**: ricarica gara id=20, modifica config turno 2 (8-ball, 4 rack) → deve salvare
- **🔍 Follow-up scoperti**:
  - **B2a**: Audit di TUTTI i fetch nei template per X-CSRFToken mancante (probabilmente non è l'unico)
  - **B2b**: `errorhandler(CSRFError)` in `app.py:307` ritorna sempre HTML — dovrebbe ritornare JSON per AJAX (come fa già `errorhandler(500)`)
  - **B2c**: I test integration non beccano questo tipo di bug perché TESTING disabilita CSRF. Pensare a 1-2 E2E test che girino con CSRF attivo per le route AJAX critiche
  - **B2d** (UX nice-to-have): feedback "Turno N salvato" troppo discreto (`text-muted`, 1.5s, in fondo a destra). Migliorare visibilità in futuro
- **DB verificato**: `round_configuration` ha 2 righe (turno 2, turno 4): discipline=8_ball, distance=4, is_race_to=0 ✓

### B1 — 🎯 TUTTI i toast gamification non centrati ✅ FIXATO
- **Cosa**: tutti i toast della gamification appaiono in alto a destra invece che al centro
- **Causa**: in `static/css/gamification.css` solo `.welcome/.nudge/.unlock` erano "hero" (centrati). Gli altri (`xp-gain`, `level-up`, `achievement`, `streak`, `streak-lost`, `quest`) usavano il container `top:80px;right:20px` con `toastSlideIn` da destra
- **Fix**: promosso il centramento alla classe base `.gamification-toast`. Rimossi i blocchi ridondanti (variants specifici + media query mobile). Aggiornato anche `level-up` che faceva override esplicito di `animation: toastSlideIn` → `toastCenterIn`
- **Files modificati**: `static/css/gamification.css` (3 sezioni)
- **Da verificare manualmente**: ricarica la pagina, completa un'azione che dia XP/streak/achievement → toast deve apparire centrato sullo schermo

## ✅ Bug fixati nel batch finale 2026-05-10

Tutti i bug annotati sono stati implementati. Riepilogo dei fix per file:

- **B25** Profilo storico include gare standalone — `routes/player/profile.py` (ordering by Match.created_at)
- **B18** Dashboard usa effective discipline — `_separated_dashboard_content.html`, `_current_matches_dashboard.html`, `_match_info.html`
- **B26** Storico gare posizione SSR — `_history_gare_tab.html` (max round_number); `_player_inscriptions.html` (nuovo macro position_badge)
- **B27** Storico campionati filtri — `_history_filters.html` (campionato_status), `_history_campionati_tab.html`, `history_service.py` (filtro is_active)
- **B17 + B32** Reset auto-assign tavolo — `RackService.reset_match_complete` (param auto_assign_table), `TrioScoringService.reset`; `TableAssignmentService` chiama con `auto_assign_table=False` quando rimuove esplicitamente
- **B16** Ordine turni in admin/gara — `_match_cards_mobile.html`, `_gara_matches.html` (reverse se gara non completata)
- **B14** Classifica rispetta classification_system — `_detailed_classification.html`, `_classification_mobile.html` (badge wins se non RACK)
- **B15** Modal Imposta Rapido validazione live — `gara_detail.html` `validateQuickResultLive()` + alert inline
- **B29** Modal Risultato Rapido legge config turno — `gara_detail.html` (placeholder JS, data-modal-distance), caller passa `match.effective_distance` + `effective_is_race_to`
- **B28** Trio confirm director-first — `match_detail.html` (priorità invertita: user_can_manage prima)
- **B7** Ora arrotondata HH:MM — `utils/jinja.py` `format_time_local` gestisce datetime
- **B5** Guest gare attive vs concluse — `routes/main.py`, `templates/public/garas_list.html`
- **B11** Flash account non verificato — `routes/auth.py` (Markup + link reinvio + i18n)
- **B22** Dashboard SETUP date passate nascoste — `models/dashboard/query_builders.py`
- **B24** Auto-cancellazione notifiche — `routes/player/notifications.py` chiama `auto_delete_by_user_preferences(user_id)`; `services.py` accetta user_id opzionale
- **B23** Notifica level-up gated — `utils/feature_flags.py` (gamification.* in allowlist), `app.py` `url_visible()` helper, `templates/player/notifications.html`
- **B21** Toast gamification narrativi — `models/gamification/frontend_bridge.py` (XP reason, level-up subtitle, achievement description da DB)
- **B10** Toast view other profiles — `frontend_bridge.py._NUDGE_COPY` mappa code→{name,description} narrative
- **B4** Toast streak perso eliminato — non registrato l'handler in `frontend_bridge.py`
- **B3** Filtro `|discipline_display` — `utils/jinja.py` `format_discipline`, registrato in `status_ui.py`, applicato in 22+ template

**Test:** 908 unit + 246 integration passano. Pyright 0 errors.

---

**Note di sessione:**
- Branch: `main`
- Ultimi commit rilevanti:
  - `5ba67b1` docs: refresh BMad snapshots
  - `846e83b` docs: restructure docs/
  - `a1e01bd` feat: rework guest home + i18n + rename brand
  - `29e51db` fix: gamification toasts allowlist (ADR-028)
  - `035849e` docs: ADR-028 follow-up
