# ADR-035 — Onboarding obbligatorio (una volta) + backfill esistenti

- **Status**: Accepted
- **Data**: 2026-06-06
- **Decisore**: Paolo Coppola
- **Correlati**: GAMIFICATION_V3 §7 (design originale), ADR-033 (availability
  solo per sala), ADR-034 (modello geo/prossimità), ADR-028 (allowlist endpoint
  in prod), ADR-031 (gating gamification)

## Problema

Il design V3 (§7) prevede un **onboarding portante**, brevissimo e
**obbligatorio una volta sola**, che (1) raccoglie *dove* l'utente vuole giocare
e *cosa* gli interessa, (2) semina i trigger geo/empty-state, (3) fa da
touchpoint di benvenuto. La piattaforma è **già in produzione**: gli utenti
esistenti non hanno mai visto un onboarding, quindi va innescato anche per loro
al **primo login** (backfill).

Il design §7 è però **anteriore** ad ADR-033/034, che hanno sostituito il
modello "province testo-libero" con **sale (`BilliardHall`)** per
eligibility/discovery e **`User.home_city`** (opt-in) come fallback di
prossimità. L'onboarding va quindi **riconciliato** su quel modello, non sul
vecchio "seleziona province".

## User story

> Come **nuovo utente** (o utente esistente al primo accesso post-rilascio),
> voglio un passaggio iniziale brevissimo in cui dico **dove** gioco e **cosa**
> mi interessa, così la piattaforma mi propone subito qualcosa di rilevante e io
> non resto davanti a una home vuota.

## Decisioni (dall'intervista)

### 1. Forma — pagina dedicata `/onboarding`, non modale
Route `GET/POST /onboarding` (blueprint `onboarding`). L'obbligatorietà è
imposta **server-side** da un hook `before_request` che reindirizza a
`/onboarding` ogni utente autenticato **non-admin** con
`onboarding_completed=False`. Più testabile e robusto di un modale JS
(non bypassabile, niente chiusura accidentale). Al completamento → redirect a
`dashboard.dashboard`.

**Esenzioni dal redirect**: gli endpoint dell'onboarding stesso, `auth.logout`,
gli static, l'infrastruttura SSE/polling (riuso di `INFRASTRUCTURE_ALLOWLIST`),
e l'`i18n.set_language` (cambio lingua deve restare possibile nella pagina).
Gli **admin sono esenti** (utenti interni, niente friction); il loro flag resta
`False` ma non vengono mai reindirizzati.

### 2. Step "Dove" — `home_city` + selezione sale (riconciliato ADR-033/034)
- **`home_city`** (testo libero, colonna già esistente): alimenta il **centroide
  geo** come fallback di prossimità (ADR-034). Opt-in.
- **Selezione di una o più sale** (`UserLocationAvailability` via
  `AvailabilityService.set_venue_availability`): è ciò che, post-ADR-033,
  alimenta **eligibility delle proposte aperte e discovery**. Semina anche i
  trigger geo utili al "segnale-domanda → director".

Entrambi **opzionali** (la geolocalizzazione è opt-in per ADR-034): l'onboarding
è obbligatorio come **passaggio**, ma i dati al suo interno non sono forzati.
Completare la pagina = onboarding fatto.

### 3. Step "Cosa ti interessa" — incluso, salvato su `User`
Multi-scelta tra `drill` / `match` / `tornei`, salvata in una nuova colonna
`User.onboarding_interests` (CSV di token da un set chiuso). Usata per
personalizzare l'atterraggio (early win) e tarare nudge futuri. In beta le
feature relative sono comunque admin/director-only (ADR-028), quindi gli
interessi oggi guidano solo la copy/landing; il valore cresce alla promozione
player.

### 4. Backfill — flag default `False` + migrazione
`User.onboarding_completed: bool` (default `False`, NOT NULL). Migrazione
idempotente `20260607_onboarding`: aggiunge le due colonne; **tutti gli account
esistenti** restano a `False` → eseguono l'onboarding al primo login
successivo. I nuovi utenti partono `False` e lo eseguono dopo la registrazione
(al primo login, dato che non c'è auto-login alla registrazione).

### 5. Soft-gate proposte — deferito al maturity-gate (ADR-028)
Il design lega "completare l'onboarding" allo sblocco delle proposte. In beta le
proposte sono già admin/director-only (ADR-028), quindi il gate funzionale è
ridondante ora. L'onboarding **setta il flag e raccoglie i dati**; quando le
proposte verranno promosse ai player (maturity-gate), il flag
`onboarding_completed` sarà la condizione naturale di sblocco. Nessun gate
player-facing aggiunto adesso (oltre al redirect stesso).

## Alternative considerate

### Alternativa: modale sulla prima dashboard
Overlay non dismissibile. **Scartata**: dipende dal JS (bypassabile, fragile),
più difficile da testare lato server, e l'enforcement resterebbe comunque
server-side — la pagina dedicata è più semplice e onesta.

### Alternativa: step "Dove" = province (come §7 originale)
**Scartata**: le province non sono più il modello dominante dopo ADR-033/034.
Selezionare sale + `home_city` è coerente con eligibility/discovery attuali.

### Alternativa: omettere gli interessi nel beta
Valida ma scartata su scelta esplicita: il costo è una colonna e tre checkbox,
e avere il dato da subito evita una seconda migrazione/seconda visita.

## Conseguenze

### Positive
- Touchpoint di benvenuto coerente; semina dati geo (home_city + sale) utili al
  Task B (segnale-domanda) e alla discovery ADR-034.
- Enforcement server-side, testabile, deny-by-default.
- Riconciliazione esplicita del design §7 col modello ADR-033/034.

### Negative / costi
- Una colonna extra (`onboarding_interests`) il cui valore è limitato finché le
  feature restano admin-only in beta.
- Friction iniziale al primo login per gli utenti esistenti (mitigata: campi
  opzionali, pagina brevissima).

### Rischi
- **Redirect loop** se l'allowset di esenzioni è incompleto → coperto da test
  che verificano gli endpoint esenti (onboarding, logout, static, i18n, SSE).
- **Allowlist ADR-028**: i nuovi endpoint vanno aggiunti a `ENDPOINT_ROLES`
  (`{"player","director"}`) altrimenti 404 in prod → coperto dal test di
  coverage degli endpoint.

## Note implementative

- **Modello**: `models/user/models.py` — `onboarding_completed` (Boolean,
  default False, NOT NULL) + `onboarding_interests` (String, nullable, CSV) con
  property `interests_list`.
- **Migrazione**: `migrations/20260607_onboarding.py` (idempotente, aggiunge le
  colonne se assenti). Nota: NOT NULL con default applicato via SQLite
  `ADD COLUMN ... DEFAULT 0`.
- **Service**: `models/user/onboarding_service.py` —
  `OnboardingService.complete_onboarding(user_id, home_city, venue_ids,
  interests)` `@transactional`: setta `home_city`, crea le availability sala
  (riuso `AvailabilityService.set_venue_availability`), salva interessi, setta
  il flag.
- **Routes**: `routes/onboarding.py` (blueprint `onboarding`), `GET/POST
  /onboarding`, `@login_required`. Aggiunto a `ENDPOINT_ROLES`.
- **Enforcement**: `before_request` in `app.py` (`enforce_onboarding`), dopo
  l'allowlist, con allowset di esenzioni.
- **Template**: `templates/onboarding.html`.

## Riferimenti

- `docs/reference/GAMIFICATION_V3.md` §7
- ADR-033, ADR-034, ADR-028, ADR-031
- File: `models/user/models.py`, `routes/onboarding.py`,
  `models/user/onboarding_service.py`, `app.py`, `utils/feature_flags.py`
