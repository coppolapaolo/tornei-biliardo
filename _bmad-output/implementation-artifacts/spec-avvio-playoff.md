---
title: 'Avvio Playoff — qualificazione, conferma e creazione gara'
type: 'feature'
created: '2026-04-06'
status: 'done'
context:
  - 'CLAUDE.md (Campionato domain, @transactional, utc_now, enum .value)'
  - 'models/playoff/CLAUDE.md'
  - 'docs/SPECIFICHE.md (playoff lifecycle)'
baseline_commit: '46baeee'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Il bottone "Avvia Playoff" nella pagina campionato detail è disabilitato con tooltip "Funzionalità in arrivo". I modelli playoff (PlayoffConfiguration, PlayoffQualification, PlayoffTournament) e il PlayoffService esistono ma non sono integrati: `PlayoffTournament.start_registration()` lancia `NotImplementedError`, non c'è route per avviare i playoff, e il flusso qualificazione→conferma→gara non è collegato.

**Approach:** Implementare il flusso completo: (0) prima dell'avvio, admin può modificare/aggiungere/rimuovere le PlayoffConfiguration create dal wizard, (1) route POST per avvio playoff che genera le qualificazioni dalla classifica del campionato, (2) pagina giocatore per conferma/rifiuto qualificazione con deadline, (3) gestione manuale admin: aggiungere/rimuovere giocatori dalle qualificazioni, (4) route admin per creare la gara playoff e iscrivere automaticamente i confermati. Il passo 0 è disponibile su campionato TERMINATED pre-avvio; i passi 2-4 sono attivabili dopo avvio.

## Boundaries & Constraints

**Always:**
- Le PlayoffConfiguration vengono create dal wizard campionato ma sono modificabili dall'admin finché i playoff non sono avviati
- Admin può: modificare config esistenti (name, positions_from/to, max_participants, min_garas_played, parametri gara), aggiungere nuove config, disattivare config (is_active=False). Dopo l'avvio playoff, le config sono bloccate
- Parametri gara nella config: aggiungere colonne `discipline`, `distance`, `rounds_count`, `strategy_type`, `odd_number_policy` a PlayoffConfiguration (migrazione). Default NULL = eredita dalla prima gara completata del campionato. Se l'admin li sovrascrive, usare i valori espliciti
- La gara playoff ha iscrizioni bloccate: nasce in status `PLAYING` (skip SETUP/INSCRIPTION), solo i confermati vengono iscritti automaticamente via `InscriptionService.inscribe_user()`. Nessun giocatore può auto-iscriversi. Il flag `Gara.playoff_config_id` (già esistente) identifica la gara come playoff
- Usare `Classification` model (già persistito) per determinare le posizioni, non `calculate_general_classification()` (che è un calcolo live)
- `PlayoffConfiguration.positions_from` / `positions_to` definiscono il range di posizioni qualificanti (già presente nel model)
- Se `positions_from`/`positions_to` sono NULL, fallback su `evaluate_qualifications()` esistente (usa `qualification_criteria` JSON)
- `@transactional(domain="playoff")` su tutti i metodi service che modificano stato
- Creare la gara playoff con `GaraService.create_gara()` passando `playoff_config_id` via kwargs + parametri gara dalla config (o defaults dal campionato)
- Iscrivere i giocatori confermati con `InscriptionService.inscribe_user()`
- `campionato_manager_required` decorator per tutte le route admin playoff
- Deadline di risposta: se `PlayoffConfiguration.response_deadline` è None, default 7 giorni da avvio
- Giocatori qualificati con `min_garas_played` insufficiente vengono esclusi (già implementato in `_meets_minimum_requirements`)
- Notifiche via `NotificationFactory` per inviti e rimpiazzi
- Admin/director può aggiungere manualmente un giocatore: crea `PlayoffQualification` con status CONFIRMED, `qualification_reason` = "Aggiunto manualmente da {admin_username}"
- Admin/director può rimuovere un giocatore: soft-remove settando status → DECLINED con `qualification_reason` aggiornato a "Rimosso da {admin_username}"
- L'aggiunta manuale non è vincolata da `positions_from/to` né da `min_garas_played` — l'admin ha override totale
- Solo giocatori iscritti al campionato (con almeno 1 Inscription in una gara del campionato) possono essere aggiunti manualmente; NON utenti arbitrari
- Status `PlayoffTournament`: setup → registration → playing → completed
- Transizione campionato: rimane `TERMINATED` fino a playoff `completed`, poi diventa `COMPLETED`

**Ask First:**
- Se il numero di confermati è < `max_participants`, creare comunque la gara o attendere?
- Email notification oltre alla notifica in-app?

**Never:**
- NON modificare lo schema di `PlayoffConfiguration` model (campi e relazioni esistenti bastano)
- NON creare un nuovo Blueprint separato per playoff — usare `routes/admin/campionato.py`
- NON toccare la logica di `terminate_campionato()`
- NON implementare la transizione TERMINATED→COMPLETED (viene a playoff conclusi, fuori scope)

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Modifica config pre-avvio | Admin cambia Elite da pos 1-6 a pos 1-8, max_participants=8 | Config aggiornata, preview classifica mostra 8 giocatori | N/A |
| Config parametri gara default | Config con discipline=NULL, distance=NULL | Al momento creazione gara: eredita dalla prima gara completata del campionato | N/A |
| Config parametri gara override | Admin setta discipline=palla_8, distance=3 nella config | Gara playoff creata con palla_8, race to 3 (ignora defaults campionato) | N/A |
| Aggiunta nuova config | Admin aggiunge "Playoff Consolazione" pos 9-16 | Nuova PlayoffConfiguration creata, visibile in sezione Playoff | N/A |
| Disattiva config | Admin disattiva Academy | config.is_active=False, non appare più nell'avvio | N/A |
| Modifica config dopo avvio | Playoff già avviati, admin prova a modificare | Blocco con flash error "Non modificabile dopo avvio playoff" | Flash error |
| Positions overlap | Admin crea config pos 1-8 quando Elite pos 1-6 esiste | Permesso (overlap è responsabilità admin, no validazione automatica) | N/A |
| Avvio playoff happy path | Campionato TERMINATED, 1 config Elite (pos 1-6), 8 giocatori in classifica, min_garas=3 tutti ok | 6 PlayoffQualification PENDING create, response_deadline settato, notifiche inviate | N/A |
| Config con positions_from/to NULL | Config con qualification_criteria JSON | Usa `evaluate_qualifications()` per determinare qualificati | N/A |
| Giocatore non raggiunge min_garas | Pos 3 ha giocato solo 2 gare su min_garas=3 | Escluso, prossimo in classifica (pos 7) invitato come rimpiazzo | N/A |
| Nessun giocatore in classifica | Campionato terminato senza gare completate (tutte soft-deleted) | 0 qualificazioni, flash warning "Nessun giocatore qualificato" | Flash warning, no error |
| Conferma qualificazione | Giocatore con PENDING conferma | Status → CONFIRMED, responded_at settato | N/A |
| Rifiuto qualificazione | Giocatore con PENDING rifiuta | Status → DECLINED, primo escluso riceve invito rimpiazzo | Se nessun rimpiazzo disponibile, nessuna azione |
| Deadline scaduta con pending | response_deadline passato, 2 giocatori PENDING | PENDING → EXPIRED, rimpiazzi invitati se disponibili | N/A |
| Creazione gara playoff | Admin clicca "Crea Gara Playoff", 5 confermati su 6 | Gara creata con playoff_config_id in status PLAYING, 5 iscrizioni automatiche, iscrizione libera bloccata | N/A |
| Giocatore tenta iscriversi a gara playoff | Gara con playoff_config_id settato, giocatore non qualificato | Iscrizione rifiutata: "Gara playoff — iscrizione riservata ai qualificati" | Flash error |
| Avvio su campionato non terminato | Campionato IN_PROGRESS | 403 / flash error | "Il campionato deve essere terminato" |
| Playoff già avviati | Config con qualificazioni già generate | No-op, flash info "Playoff già avviati" | N/A |
| Doppia conferma | Giocatore già CONFIRMED riconferma | No-op o flash info | N/A |
| Config con gara già creata | Admin reclicca "Crea Gara" | Redirect a gara esistente | N/A |
| Admin aggiunge giocatore | Admin seleziona giocatore del campionato non in lista | PlayoffQualification CONFIRMED creata, reason "Aggiunto manualmente" | N/A |
| Admin aggiunge giocatore già qualificato | Giocatore già ha PlayoffQualification per questa config | No-op, flash info "Giocatore già presente" | Flash info |
| Admin aggiunge utente non del campionato | User senza Inscription in gare del campionato | Rifiutato con flash error | "Il giocatore non ha partecipato al campionato" |
| Admin rimuove giocatore PENDING | Admin rimuove giocatore con status PENDING | Status → DECLINED, reason aggiornato | N/A |
| Admin rimuove giocatore CONFIRMED | Admin rimuove giocatore CONFIRMED | Status → DECLINED, reason aggiornato | N/A |
| Admin rimuove dopo gara creata | Config ha già gara playoff creata | Blocco: non si possono modificare qualificazioni dopo creazione gara | Flash error |

</frozen-after-approval>

## Code Map

- `models/playoff/services.py` -- PlayoffService: aggiungere `update_configuration()`, `add_configuration()`, `deactivate_configuration()`, `start_playoff()`, `create_playoff_gara()`, `admin_add_player()`, `admin_remove_player()`, fix `start_playoff_registration()`
- `models/playoff/models.py` -- PlayoffTournament: fix `start_registration()` (rimuovere NotImplementedError)
- `models/campionato/tournament_service.py` -- aggiungere `start_playoff()` facade che delega a PlayoffService
- `routes/admin/campionato.py` -- POST `/<id>/playoff/config/<config_id>/edit`, POST `/<id>/playoff/config/add`, POST `/<id>/playoff/config/<config_id>/deactivate`, POST `/<id>/start-playoff`, POST `/<id>/create-playoff-gara/<config_id>`, POST `/<id>/playoff/<config_id>/add-player`, POST `/<id>/playoff/<config_id>/remove-player`
- `routes/player/notifications.py` -- route per conferma/rifiuto qualificazione (o pagina dedicata playoff)
- `templates/admin/campionato_detail.html` -- attivare bottone, sezione stato playoff con config, qualificazioni, bottoni azione
- `templates/player/playoff_invitation.html` -- pagina conferma/rifiuto per giocatore (nuovo)
- `models/notification/services.py` -- notifica invito playoff
- `tests/new/unit/test_avvio_playoff.py` -- tutti scenari I/O Matrix
- `tests/new/integration/test_avvio_playoff_route.py` -- route + permessi + flusso completo

## Tasks & Acceptance

**Execution:**
- [x] `migrations/20260406_playoff_config_gara_params.py` -- ADD COLUMN `discipline VARCHAR(50) NULL`, `distance INTEGER NULL`, `rounds_count INTEGER NULL`, `strategy_type VARCHAR(50) NULL`, `odd_number_policy VARCHAR(20) NULL` a `playoff_configuration`
- [x] `models/playoff/models.py` -- aggiungere colonne `discipline`, `distance`, `rounds_count`, `strategy_type`, `odd_number_policy` a PlayoffConfiguration; aggiungere metodo `get_gara_params(campionato)` che ritorna dict con valori espliciti o defaults dal campionato
- [x] `models/playoff/services.py` -- aggiungere `PlayoffService.update_configuration(config_id, **fields)`: modifica tutti i campi config (qualificazione + parametri gara); blocca se playoff avviati (qualificazioni esistono)
- [x] `models/playoff/services.py` -- aggiungere `PlayoffService.add_configuration(campionato_id, name, positions_from, positions_to, max_participants, min_garas_played=None)`: crea nuova PlayoffConfiguration; blocca se playoff avviati
- [x] `models/playoff/services.py` -- aggiungere `PlayoffService.deactivate_configuration(config_id)`: setta is_active=False; blocca se playoff avviati
- [x] `models/playoff/services.py` -- aggiungere `PlayoffService.start_playoff(campionato_id)`: per ogni config attiva, genera qualificazioni da Classification, setta response_deadline, invia notifiche
- [x] `models/playoff/services.py` -- aggiungere `PlayoffService.create_playoff_gara(configuration_id)`: crea Gara con `GaraService.create_gara()` + `playoff_config_id`, iscrive tutti i CONFIRMED con `InscriptionService.inscribe_user()`, aggiorna PlayoffTournament
- [x] `models/playoff/services.py` -- aggiungere `PlayoffService.admin_add_player(configuration_id, user_id, admin_username)`: valida che user ha partecipato al campionato, crea PlayoffQualification CONFIRMED; se già esiste, no-op
- [x] `models/playoff/services.py` -- aggiungere `PlayoffService.admin_remove_player(qualification_id, admin_username)`: setta status DECLINED con reason "Rimosso da {admin}"; blocca se gara playoff già creata
- [x] `models/playoff/models.py` -- fix `PlayoffTournament.start_registration()`: rimuovere NotImplementedError, implementare logica con InscriptionService
- [x] `models/campionato/tournament_service.py` -- aggiungere `start_playoff(campionato_id)` facade
- [x] `routes/admin/campionato.py` -- POST `/<id>/playoff/config/<config_id>/edit`: form modifica config (name, positions_from/to, max_participants, min_garas_played), chiama `update_configuration`
- [x] `routes/admin/campionato.py` -- POST `/<id>/playoff/config/add`: form nuova config, chiama `add_configuration`
- [x] `routes/admin/campionato.py` -- POST `/<id>/playoff/config/<config_id>/deactivate`: chiama `deactivate_configuration`, redirect con flash
- [x] `routes/admin/campionato.py` -- POST `/<id>/start-playoff`: validazione (TERMINATED, has configs attive, non già avviato), chiama service, redirect con flash
- [x] `routes/admin/campionato.py` -- POST `/<id>/create-playoff-gara/<config_id>`: validazione, chiama `create_playoff_gara`, redirect a gara
- [x] `routes/admin/campionato.py` -- POST `/<id>/playoff/<config_id>/add-player`: form con select giocatore, chiama `admin_add_player`
- [x] `routes/admin/campionato.py` -- POST `/<id>/playoff/<config_id>/remove-player`: chiama `admin_remove_player`, redirect con flash
- [x] `routes/admin/campionato.py` -- aggiornare `campionato_detail` context: passare playoff_status con qualificazioni per config + lista giocatori campionato disponibili per aggiunta manuale
- [x] `routes/player/` -- route GET/POST per conferma/rifiuto qualificazione del giocatore
- [x] `templates/admin/campionato_detail.html` -- sezione Playoff con due stati: (A) pre-avvio: lista config editabili (form inline o modal per edit), bottone aggiungi config, bottone "Avvia Playoff"; (B) post-avvio: stato per config (qualificati/confermati/pending/rifiutati), lista giocatori con bottone rimuovi, form aggiunta manuale, bottone "Crea Gara Playoff"
- [x] `templates/player/playoff_invitation.html` -- pagina con dettagli qualificazione, bottoni conferma/rifiuta
- [x] `models/notification/services.py` -- tipo notifica PLAYOFF_INVITATION con link a pagina conferma
- [x] `tests/new/unit/test_avvio_playoff.py` -- test per tutti scenari I/O Matrix (happy path, rimpiazzi, edge cases)
- [x] `tests/new/integration/test_avvio_playoff_route.py` -- test route: permessi, avvio, conferma/rifiuto, creazione gara
- [x] `models/competition/inscription_service.py` -- in `inscribe_user()`, se gara.is_playoff raise ValueError("Gara playoff — iscrizione riservata ai qualificati") a meno che non sia chiamato internamente dal PlayoffService (aggiungere parametro `_bypass_playoff_check=False`)
- [x] Traduzioni: `pybabel extract && pybabel update && pybabel compile`

**Acceptance Criteria:**
- Given campionato TERMINATED con playoff Elite (pos 1-6), when admin modifica config a pos 1-8 e distance=3, then config aggiornata con nuovo range e parametri gara
- Given campionato TERMINATED, when admin aggiunge nuova config "Consolazione" pos 9-16, then PlayoffConfiguration creata e visibile
- Given gara playoff creata (playoff_config_id settato), when giocatore non qualificato tenta iscrizione, then rifiutata con errore
- Given campionato TERMINATED con playoff Elite (pos 1-6), when admin clicca "Avvia Playoff", then 6 PlayoffQualification PENDING create e giocatori notificati
- Given giocatore qualificato con invito PENDING, when conferma, then status → CONFIRMED e conteggio aggiornato in admin view
- Given giocatore rifiuta, when rifiuto, then status → DECLINED e primo escluso (pos 7) riceve invito rimpiazzo
- Given tutti i qualificati hanno risposto (5 CONFIRMED, 1 DECLINED), when admin clicca "Crea Gara Playoff", then Gara creata con playoff_config_id e 5 iscrizioni automatiche
- Given campionato non TERMINATED, when POST start-playoff, then 403 / flash error
- Given playoff già avviati, when POST start-playoff, then no-op con flash info
- Given playoff avviati per config Elite, when admin aggiunge giocatore del campionato non in lista, then PlayoffQualification CONFIRMED creata con reason "Aggiunto manualmente"
- Given playoff avviati, when admin rimuove giocatore CONFIRMED, then status → DECLINED con reason "Rimosso da {admin}"
- Given config con gara playoff già creata, when admin tenta aggiunta/rimozione, then flash error "Non modificabile dopo creazione gara"
- Given admin tenta aggiungere utente senza partecipazione al campionato, then flash error "Il giocatore non ha partecipato al campionato"
- `pytest tests/new/ -n 4` → tutti verdi; `pyright` → 0 errori

## Design Notes

**Perché Classification e non calculate_general_classification():** La `Classification` table è già persistita e aggiornata al completamento di ogni gara. Usarla evita ricalcoli costosi e garantisce consistenza — la classifica "congelata" al momento della terminazione è quella che conta per i playoff.

**Configurazione pre-avvio:** Le PlayoffConfiguration vengono create dal wizard campionato con valori default, ma l'admin può modificarle, aggiungerne di nuove, o disattivarne prima di cliccare "Avvia Playoff". L'avvio "congela" le config e genera gli inviti. Questo separa due momenti: la definizione della struttura playoff (modificabile) e l'esecuzione (irreversibile).

**Flusso a 3 fasi post-avvio:** (1) Avvio = genera inviti, (2) Raccolta risposte = giocatori confermano/rifiutano + admin gestisce manualmente, (3) Creazione gara = admin decide quando creare. Questo design dà flessibilità: l'admin può attendere la deadline, forzare la creazione prima, o gestire casi particolari.

**Gara playoff come gara normale:** La gara playoff è una Gara standard con `playoff_config_id` settato. Questo riusa tutta l'infrastruttura esistente (matchmaking, scoring, rounds) senza codice speciale.

## Verification

**Commands:**
- `pytest tests/new/unit/test_avvio_playoff.py -v -n auto` -- expected: tutti i test I/O Matrix passano
- `pytest tests/new/integration/test_avvio_playoff_route.py -v -n 4` -- expected: tutti i test route passano
- `pyright` -- expected: 0 errori

## Suggested Review Order

**Modelli e migrazione**

- Nuove colonne gara params + `get_gara_params()` con fallback campionato + `has_qualifications()` guard
  [`models.py:87`](../../models/playoff/models.py#L87)

- Migrazione idempotente per le 5 nuove colonne
  [`20260406_playoff_config_gara_params.py:1`](../../migrations/20260406_playoff_config_gara_params.py#L1)

- `start_registration()` semplificata — solo status change, iscrizioni delegate al service
  [`models.py:430`](../../models/playoff/models.py#L430)

**Service layer (cuore della feature)**

- `start_playoff()` — genera qualificazioni dalla Classification, gestisce rimpiazzi per min_garas, notifica
  [`services.py:447`](../../models/playoff/services.py#L447)

- `create_playoff_gara()` — crea Gara con params ereditati/override, iscrive confermati, aggiorna PlayoffTournament
  [`services.py:564`](../../models/playoff/services.py#L564)

- Config management: `update_configuration`, `add_configuration`, `deactivate_configuration` — bloccati post-avvio
  [`services.py:370`](../../models/playoff/services.py#L370)

- `admin_add_player` / `admin_remove_player` — override manuale con audit trail
  [`services.py:632`](../../models/playoff/services.py#L632)

**Guard iscrizioni playoff**

- `_bypass_playoff_check` in `inscribe_user` — blocca auto-iscrizione su gare playoff
  [`inscription_service.py:73`](../../models/competition/inscription_service.py#L73)

**Routes**

- 8 nuove route admin: start, create gara, config CRUD, player add/remove
  [`campionato.py:665`](../../routes/admin/campionato.py#L665)

- Context arricchito in `campionato_detail`: playoff_status + campionato_players
  [`campionato.py:428`](../../routes/admin/campionato.py#L428)

- 3 route player: invitation view, confirm, decline
  [`playoff.py:1`](../../routes/player/playoff.py#L1)

**Templates**

- Sezione Playoff con 2 stati: pre-avvio (config editabili) e post-avvio (qualificazioni + gestione)
  [`campionato_detail.html:58`](../../templates/admin/campionato_detail.html#L58)

- Pagina invito playoff per il giocatore
  [`playoff_invitation.html:1`](../../templates/player/playoff_invitation.html#L1)

**Test**

- 27 unit test: config management, start, confirm/decline, admin add/remove, create gara, guard, get_gara_params
  [`test_avvio_playoff.py:1`](../../tests/new/unit/test_avvio_playoff.py#L1)

- 10 integration test: route permissions, full flow, config CRUD
  [`test_avvio_playoff_route.py:1`](../../tests/new/integration/test_avvio_playoff_route.py#L1)
