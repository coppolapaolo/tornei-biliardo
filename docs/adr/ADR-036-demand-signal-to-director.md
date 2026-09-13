# ADR-036 — Segnale-domanda → director (richieste geolocalizzate)

- **Status**: Accepted (core v1; open items documentati)
- **Data**: 2026-06-06
- **Decisore**: Paolo Coppola
- **Correlati**: GAMIFICATION_V3 §10-ter (design), ADR-034 (geo/prossimità),
  ADR-033 (availability per sala), ADR-028 (allowlist endpoint), §11 (policy
  notifiche: azionabile → persistente)

## Problema

L'empty-state geografico (§10) ha una leva inespressa: *"vorrei una gara nella
mia zona"*. Quella domanda, aggregata per area, è un trigger azionabile per i
director ("crea l'offerta dove c'è domanda"). Serve un modello che: (1) raccolga
le richieste geolocalizzate dei giocatori, (2) notifichi i director quando nella
loro zona la domanda supera una soglia, (3) chiuda il loop consumando le
richieste quando il director apre una gara vicina.

Il design §10-ter è anteriore ad ADR-034, che ha stabilito **nessuna coordinata
utente persistita** (GPS effimero + fallback `home_city` centroide). Va
riconciliato.

## User story

> Come **giocatore** senza gare vicine, voglio segnalare che vorrei una gara
> nella mia zona; come **director**, voglio essere avvisato quando c'è
> abbastanza domanda intorno a me da giustificare l'organizzazione di una gara.

## Decisioni (dall'intervista)

### 1. Posizione della richiesta — GPS effimero → fallback home_city, persistita SUL record
Alla creazione, la posizione è risolta da: **GPS del browser** se concesso,
altrimenti **centroide di `home_city`** (ADR-034, network-free). Le coordinate
risolte sono salvate **sul record `DemandSignal`** — non sull'utente. È un dato
**esplicito e per-richiesta** (il giocatore *dichiara* "voglio giocare qui"),
non un tracciamento passivo: coerente col principio ADR-034 (zero coordinate
utente persistite; la superficie di posizione resta su sale e ora su richieste
esplicite).

### 2. Zona del director — centroide home_city + raggio regolabile
La zona è un cerchio attorno alla **home del director** (centroide delle sale
della sua `home_city`), con **raggio regolabile** (`User.signal_radius_km`,
default **30 km**, clamp ADR-034). Director senza `home_city` risolvibile → zona
non calcolabile → nessuna notifica (graceful).

### 3. Soglia & trigger (core v1)
- Modello `DemandSignal`: `user_id`, `latitude`, `longitude`, `city` (label
  opzionale), `created_at`, `expires_at` (~**60 giorni**), `status`
  (`active`/`consumed`/`expired`/`cancelled`), `consumed_by_gara_id`.
- **Fronte di salita ≥6**: alla creazione di una richiesta, per ogni director la
  cui zona copre il punto, si conta `attive_nel_raggio`. Si notifica **solo al
  crossing** (count passa esattamente a `DEMAND_THRESHOLD=6`), non in continuo
  finché ≥6. **Cooldown** anti-nag (`signal_notified_at` su User,
  `DEMAND_COOLDOWN_DAYS=7`). Notifica **persistente azionabile** (§11) con
  `action_url` alla creazione gara.
- **Consumo**: alla creazione di una gara con sala dotata di coordinate (handler
  su `CompetitionCreatedEvent`), le richieste attive entro il raggio della sala
  vengono marcate `consumed` e i giocatori ricevono la notifica azionabile
  *"gara aperta vicino a te"*. Idempotente; errori isolati (EventBus).
- Conteggio sempre su richieste **attive e non scadute** (`expires_at` futuro).

### 4. Visibilità (ADR-028) — maturity-gated come il resto
L'endpoint di creazione (`demand.create_signal`) è in `ENDPOINT_ROLES` con
`{"director"}` (admin bypassa): in prod raggiungibile da admin/director per la
validazione beta, **non dai player**, coerente con proposte/gamification. La
notifica ai director funziona comunque (i director esistono in prod). La
promozione ai player avverrà col maturity-gate quando l'area è validata. In
dev/test l'allowlist è pass-through.

## Alternative considerate
- **Solo centroide home_city** (no GPS): più semplice ma granularità città e
  richiede home_city. Scartata: il GPS effimero dà precisione senza persistere
  coord utente.
- **Tutto §10-ter in un colpo** (re-eval su promozione player→director,
  segnale-admin per zone senza director, auto-refresh + prompt scadenza):
  scartata per ampiezza/superfici da validare. Vedi Open Items.

## Conseguenze

### Positive
- Chiude il loop domanda→offerta sopra il modello geo ADR-034, riusandolo.
- Notifiche azionabili coerenti con la policy §11 (persistenti, non toast).
- Coordinate solo su sale + richieste esplicite: superficie privacy minima.

### Negative / costi
- Due colonne su User (`signal_radius_km`, `signal_notified_at`) e una nuova
  tabella `demand_signal`.
- Granularità del fallback = città (quando manca il GPS).

### Rischi
- **Nesting transazionale**: il consumo gira come handler dentro la transazione
  di `create_gara` (savepoint). Mitigato: handler idempotente + isolamento
  per-handler dell'EventBus (un fallimento non rompe la creazione gara).
  *(nota 2026-09-13: fino a questa data l'isolamento non reggeva — un handler
  decorato che falliva annullava l'intera sessione, creazione della gara
  compresa, e l'EventBus proseguiva come se niente fosse. Corretto da ADR-061.)*
- **home_city non geocodificata**: se nessuna sala della città ha coordinate, la
  zona del director non è calcolabile → nessuna notifica (accettato).

## Open Items (rimandati, design in §10-ter)
1. ~~**Re-eval alla promozione** player→director~~ — **FATTO**:
   `evaluate_zone_for_new_director` chiamato da `process_director_request` e
   `promote_to_director` (errori isolati); se zona già ≥ soglia → notifica
   una-tantum (cooldown).
2. ~~**Segnale-admin** per zone senza director~~ — **FATTO**:
   `_maybe_notify_admins_no_director` su crossing soglia quando nessun director
   copre il punto (`NotificationType.DEMAND_ZONE_NO_DIRECTOR`).
3. **Auto-refresh + prompt di riconferma + scadenza** — **FATTO**:
   - `User.last_active_at` (migrazione `20260607_user_last_active`) aggiornato
     da un hook `before_request` *throttled* (`utils.activity.touch_user_activity`,
     1/ora/utente; skip nei test). È il tracciamento di attività che mancava.
   - `process_expiring_signals(within_days=7, active_within_days=30)`: per i
     segnali in scadenza, **auto-refresh** se il proprietario è attivo (entro 30
     gg), altrimenti **prompt di riconferma** una-tantum (`reminded_at`,
     `NotificationType.DEMAND_SIGNAL_EXPIRING`).
   - `expire_due_signals` (→ EXPIRED), `refresh_signal` (riconferma manuale,
     route `POST /demand/signal/<id>/refresh`), `send_expiry_reminders`
     (prompt-only primitivo). Script `scripts/daily_jobs.py` (job `demand`)
     (auto-refresh + prompt + expiry).
4. **Tarature**: soglia (6), raggio default (30 km), cooldown (7 gg), scadenza
   (60 gg), finestra promemoria (7 gg), finestra "attivo" (30 gg), throttle
   attività (60 min) — costanti documentate, affinare sui dati reali.

## Note implementative
- `models/demand/` (`models.py` `DemandSignal`, `service.py`
  `DemandSignalService`, `event_handlers.py` consumo su
  `CompetitionCreatedEvent`).
- `User.signal_radius_km` (default 30), `User.signal_notified_at` (cooldown).
  Migrazione `20260607_demand_signal`.
- `NotificationType.DEMAND_THRESHOLD_REACHED` (director, azionabile),
  `DEMAND_GARA_NEARBY` (player).
- Routes: blueprint `demand`, `POST /demand/signal`. `ENDPOINT_ROLES`
  `{"director"}`.
- Geo: riuso `utils/geo` (bounding-box + haversine) e
  `AvailabilityService.city_centroid_for`.

## Riferimenti
- `docs/reference/GAMIFICATION_V3.md` §10, §10-ter, §11
- ADR-034, ADR-033, ADR-028
- File: `models/demand/*`, `models/user/models.py`, `routes/demand.py`,
  `models/notification/models.py`
