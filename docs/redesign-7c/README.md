# Handoff — Redesign "7c" · Tornei Biliardo

Repo di destinazione: `coppolapaolo/tornei-biliardo`, branch `main`. Flask + Jinja2 + Bootstrap 5.

## Cosa contiene questo pacchetto

1. **`files/`** — file **pronti al commit** nel repo reale. Sono Jinja/CSS/JS veri, scritti sui template esistenti: logica, variabili `vm.*`, `url_for`, blocchi, macro e commenti tecnici (issue #61, #62, #68, B5, B14, B23, ADR-018…) sono preservati. È cambiato il livello visivo e, dove serviva, la struttura di layout. Copiali al percorso corrispondente del repo sovrascrivendo l'esistente.
2. **`Redesign Mobile.dc.html`** e **`Design System 7c.md`** — **riferimento di design**, non codice da spedire. Servono per le schermate non ancora convertite.

**Fidelity: hi-fi.** Colori, tipografia, spaziature e raggi sono definitivi e codificati in `tokens-7c.css`. Le schermate mancanti vanno riprodotte riusando le classi `.c7-*`, senza inventare valori nuovi.

## Architettura (leggere prima di toccare qualsiasi template)

Approccio **bottom-up, non per-template**:

- `static/css/tokens-7c.css` — solo `:root`, nessuna regola.
- `static/css/theme-7c.css` — override di Bootstrap + classi `.c7-*`. Caricato **dopo** bootstrap, `variables.css` e `main.css`.
- `templates/base.html` — guscio 7c: Manrope/JetBrains Mono, header, nav mobile, container toast Chalky, blocco alert.

Conseguenza: la grande maggioranza dei 179 template eredita lo stile **senza toccarne il markup** (`.card`, `.btn`, `.table`, `.badge`, `.form-control`, `.modal`, `.nav-tabs`, `.alert`, `.progress` sono tutti ridefiniti). Serve lavoro per-template solo dove cambia il *layout* o dove il markup contiene stili/colori hardcoded.

**Regola operativa per Claude Code: non riscrivere un template prima di averlo aperto nel browser.** Se il tema lo copre già, lascialo stare. Intervieni quando trovi: layout sbagliato, `style="..."` con colori fuori palette, `<style>` inline con gradienti, copy in inglese, o "Bye" al posto di "X a tavolino".

## Stato del lavoro

### Convertito e pronto al commit (in `files/`)

**Fondamenta**
`static/css/tokens-7c.css` · `static/css/theme-7c.css` · `static/js/gamification.js` (toast `.c7-chalky`, API invariata) · `static/img/chalk1-10.png` · `templates/base.html` · `components/_user_menu.html` · `components/_form_macros.html`

**Dashboard e liste unificate**
`_unified_dashboard_header.html` · `_separated_dashboard_content.html` · `_director_dashboard_content.html` · `_player_dashboard_content.html` · `_admin_dashboard_content.html` (invariato, solo include) · `_unified_cards.html` · `_dashboard_empty_state.html` · `_nearby_gare.html`

**Gara**
`_gara_header.html` · `_gara_info.html` · `_gara_management.html` · `_gara_inscriptions.html` · `_round_management.html` · `_gara_matches.html` · `_match_cards_mobile.html` · `_match_card.html` · `_match_result_row.html` · `_classification_mobile.html` · `_detailed_classification.html` · `_guest_info.html`

**Partita e segnapunti**
`_match_header.html` · `_unified_match_score.html` · `_unified_rack_input.html` (segnapunti da tavolo, multi-set e set unico) · `_unified_rack_history.html`

**Creazione e modifica**
`_gara_edit_form.html` · `admin/gara_edit.html` · `admin/campionato_wizard_step1.html` · `admin/campionato_wizard_step2.html` · `_campionato_create_modal.html` · `_distance_configurator.html` (stepper + anteprima in parole) · `_soft_delete_modal.html`

**Home pubblica**
`index.html` · `_index_registration_info.html` · `_index_live.html` · `_index_open_inscriptions.html` · `_index_upcoming.html` · `_index_archive.html` · `public/garas_list.html` · `public/campionatos_list.html`

**Accesso, profilo, area personale**
`login.html` · `register.html` · `player/profile.html` · `player/history.html` · `player/notifications.html` · `player/privacy_settings.html` · `player/delete_account.html` · `player/_change_password_modal.html` · `player/playoff_invitation.html`

**Challenge e progressi**
`challenge/catalog.html` · `challenge/_challenge_card.html` · `challenge/_challenge_grid.html` · `gamification/leaderboards.html`

**Sale e amministrazione**
`player/venues.html` · `player/my_venue_requests.html` · `admin/director_requests.html`

**Errori**
`errors/400.html` · `errors/404.html` · `errors/429.html` · `errors/500.html`

> **Nessuno di questi file è stato eseguito.** Il primo passo è copiarli, avviare l'app e verificare pagina per pagina.

### Da verificare (probabilmente già coperti dal tema)

Aprili e intervieni solo se qualcosa non torna:

`admin/kpi.html` · `admin/users_list.html` · `admin/venues_list.html` · `admin/venue_form.html` · `admin/venue_detail.html` · `admin/venue_manager_requests.html` · `admin/campionato_detail.html` · `admin/gara_create_standalone.html` · `admin/gara_challenge_classification.html` · `admin/amalfi_classification.html` · `individual_match/*` (10 file) · `components/_history_*` (5 file) · `components/_campionato_*` (7 file) · `components/_player_*` (statistiche, rating, iscrizioni, partite recenti) · `components/_challenge_management_modal.html` · `components/_gara_tables_config.html` · `components/_gara_public_link.html` · `components/_directors_management.html` · `components/_ssr_section.html` · `auth/forgot_password.html` · `auth/reset_password.html` · `reset.html` · `onboarding.html` · `privacy.html` · `no_campionato.html` · `public/campionato_detail.html` · `public/invite_not_found.html` · `player/profile_edit.html` · `player/venue_detail.html` · `player/challenge_detail.html`

### Da rifare a mano (layout o stili hardcoded)

1. **`gara_detail.html` (85 KB) e `match_detail.html` (30 KB)** — i componenti che includono sono già 7c, ma il *guscio* di pagina (colonne, testate, blocchi JS, modali di risultato rapido e assegnazione tavolo) va portato su `.c7-cols` / `.c7-head` / `.c7-actionbar`. Sono i due file più delicati: procedere a piccoli passi, verificando ogni sezione nel browser.
2. **`gamification/dashboard.html`, `achievements.html`, `quests.html`, `streaks.html`** — XP e livelli, streak con freeze e traguardi, achievement per categoria/difficoltà, quest. Il prototipo mostra il modello: barra XP piena larghezza, achievement come griglia di tessere, streak con calendario compatto. Attenzione: contengono `<style>` inline con gradienti da rimuovere.
3. **`gamification/admin/*` (14 file)** — pannelli di configurazione. Bassa priorità, molto lavoro, poco impatto: convertire per ultimi.
4. **`challenge/create.html`, `challenge/start_attempt.html`, `challenge/_challenge_detail.html`, `player/challenge_attempt_detail.html`, `player/gara_challenge_detail.html`** — flusso di tentativo (foto, tentativi a punteggio o riuscita/fallita).
5. **`components/_new_gara_modal.html`** e gli altri modali del direttore di gara non ancora aperti.
6. **Pulizia finale**: rimuovere da `main.css` e `variables.css` le regole superate dal tema. Solo alla fine, a verifica completata.

## Design token (fonte di verità: `files/static/css/tokens-7c.css`)

Superfici `--c7-bg #E4E8E7` (fondo pagina, **mai bianco puro**), `--c7-card #F5F7F6`, `--c7-sunken #ECEEED` (disabilitato / ereditato / concluso).
Inchiostro `--c7-ink #1B2124`, `--c7-ink-soft #3D474A`, `--c7-ink-muted #6B7679`, `--c7-ink-faint #9AA3A6`, `--c7-on-ink #F2F5F4`.
Linee `--c7-line #D3D8D7`, `--c7-line-soft #E4E8E7`.
Accento `--c7-accent #2C4A52`, `--c7-accent-bright #8FCDE8`, `--c7-accent-dim #A9C4C7`, `--c7-accent-tint #DDE9EE`.
Semantici: ok `#2C8A6B` su `#E4EDE9` · errore `#B23B3B` su `#F3E2E0` · attenzione `#8A6A1F` su `#F0E9D8` · info = accento.
Tipografia Manrope (UI, pesi 600/700/800) + JetBrains Mono (numeri e punteggi).
Raggi: pill 999 · card 22 · card-lg 26 · campo 18 · controllo 14 · chip 12.
Spaziature: gutter 18 (mobile) / 28 (desktop) · pad card 16/20 · gap 12/16.
Misure: touch 48 · campo 58 · bottone 56 · sidebar 244 · nav mobile 76.
Ombre **solo** su toast e overlay: le card si distinguono per superficie, non per ombra.

## Classi `.c7-*` più usate

`c7-app` `c7-main` `c7-content` `c7-head` (+`__back` `__title` `__sub`) `c7-actionbar` · `c7-side` `c7-mobilenav` · `c7-card` (+`--accent` `--locked` `--ok` `--warn` `--err` `--info`) `c7-grid` `c7-stack` `c7-cols` `c7-kpis` `c7-live` · `c7-pill` `c7-state` (+`--ok` `--err` `--warn` `--info` `--accent` `--muted`) · `c7-num` `c7-num-lg` `c7-num-xl` `c7-label` `c7-kicker` · `c7-choice` `c7-stepper` · `c7-table-wrap` `c7-cell-actions` `c7-row--attention` `c7-row--done` · `c7-flash` (+ toni) `c7-band` · `c7-chalky` (+`--level` `--rare` `--lost`) · `c7-empty` · `c7-avatar` `c7-divider` `c7-sep` `c7-crumbs` `c7-iconbtn`.

## Regole non negoziabili

- Nessun bianco puro, nessuna ombra sulle card, nessun gradiente.
- Numeri e punteggi sempre in JetBrains Mono (`.c7-num*`), tabulari.
- Target tattile mai sotto 48px.
- Stato "ereditato / bloccato / concluso" = superficie `--c7-sunken`, mai il grigio disabilitato di Bootstrap.
- Rosso pieno solo per il pallino live e le icone dei flash: le azioni distruttive usano fondo tenue `--c7-err-bg`.
- Le opzioni poche e importanti sono `.c7-choice` (card selezionabili), non `<select>`.
- I numeri piccoli e frequenti sono `.c7-stepper`, non `input[type=number]`.

## Terminologia (rispettarla in ogni copy)

campionato ≠ gara ≠ match · **"X a tavolino"**, mai *bye* · **"direttore di gara"**, mai *director* · turno, mai *round* nel testo visibile · iscrizione · sala biliardo · "conclusa" per una gara finita, "da giocare" per una partita in attesa.

## Toast Chalky

Container separato in `base.html`, mappa evento→immagine nella config di `gamification.js`, markup `.c7-chalky`, 10 pose in `static/img/`. L'API pubblica di `gamification.js` non è cambiata: i chiamanti esistenti (incluso `models/gamification/frontend_bridge.py`) funzionano senza modifiche.

## Ordine di lavoro consigliato

1. Copia `files/` nel repo, avvia l'app.
2. Giro completo delle pagine, annota cosa è rotto: è il passo che riduce tutti i successivi.
3. `gara_detail.html` e `match_detail.html` (punto 1 di "da rifare a mano").
4. Gamification giocatore.
5. Flusso challenge.
6. Pannelli admin di gamification.
7. Pulizia di `main.css` / `variables.css`.
