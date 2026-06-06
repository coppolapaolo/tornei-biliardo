# ADR-032 — Consolidamento della superficie di disponibilità sul blueprint individual_match

**Data**: 2026-06-06
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Il dominio "disponibilità giocatore" (use case 7) era implementato da **due
sistemi paralleli e parzialmente sovrapposti**, residuo del dedup delle proposte
(#3):

1. **Legacy — 5 route su `player_bp`** in `routes/player/proposals.py`
   (`availability_preferences`, `set_location_availability`,
   `set_venue_availability`, `discover_available_players`,
   `request_availability_match`), basate su `AvailabilityService`. Coprivano sia
   la disponibilità per **località** (stringa, `PlayerAvailability`) sia quella
   per **sala** (FK, `UserLocationAvailability`), più discovery e richiesta
   match.

2. **Canonica — `individual_match.manage_availability`** in
   `routes/individual_match/views.py`, basata su
   `IndividualMatchService.get_user_availability/update_user_availability` e sul
   solo modello `PlayerAvailability`.

Problemi rilevati analizzando il codice:

- Le 2 GET legacy renderizzavano template **mai esistiti**
  (`player/availability_preferences.html`, `player/discover_players.html`) → in
  produzione ogni accesso era un **500**; il sistema legacy era di fatto morto
  end-to-end (oltre a essere admin-only per ADR-028, non listato in
  `ENDPOINT_ROLES`).
- Ironia dei modelli: `PlayerAvailability` è **esplicitamente deprecato** nel suo
  docstring a favore di `UserLocationAvailability` (FK sala). Eppure la UI
  canonica usava il modello deprecato, mentre la capacità "per sala" + discovery
  viveva solo nelle route legacy rotte.
- `AvailabilityService` **non** è morto: `ProposalService.create_open_proposal`
  ne consuma `get_available_players_at_venue/location` per notificare i giocatori
  delle proposte aperte. Quindi entrambe le disponibilità (sala e località)
  alimentano funzionalità reali.
- Duplicazione anche a livello servizio: `IndividualMatchService` aveva una
  propria coppia write-side (`update_user_availability`, `set_player_availability`,
  `get_player_availability`, `get_eligible_players_for_location`) su
  `PlayerAvailability`, con l'unico chiamante vivo nella route canonica
  (`update_user_availability` faceva inoltre **append senza dedup**).

## Decisione

Unificare la disponibilità su **un'unica superficie nel blueprint
`individual_match`**, con **`AvailabilityService` come unica fonte di verità**
per disponibilità (località + sala) e discovery:

1. Le route vivono in `routes/individual_match/availability.py` e usano
   `AvailabilityService`. La GET conserva il nome endpoint
   `individual_match.manage_availability` (per non rompere `dashboard.html`,
   `_nearby_gare.html`, `feature_endpoint_map.py`).
2. La UI canonica gestisce **sia sala (primaria, `UserLocationAvailability`) sia
   località (legacy, `PlayerAvailability`)** + discovery + richiesta match.
3. I duplicati write-side su `IndividualMatchService` sono rimossi; il "salva"
   passa per `AvailabilityService.set_*` (semantica di **replace**, niente più
   append-duplicati).
4. Il pulsante "rimuovi" ha ora un backend reale
   (`AvailabilityService.remove_player_availability/remove_venue_availability`,
   con controllo di ownership → 404 se non proprietario).
5. Le 5 route legacy e `routes/player/proposals.py` sono eliminate;
   `_nearby_gare.html` è ripuntato sull'endpoint canonico.

Visibilità in produzione (ADR-028): gli endpoint restano **non listati in
`ENDPOINT_ROLES`** → admin/director-only, coerente con lo stato attuale di
`manage_availability`. La promozione ai player è una scelta di rollout separata
(maturity gate), non parte di questo ADR.

`PlayerAvailability` resta in uso (consumato da `ProposalService` e dalle
proposte) ma è confermato **legacy**: `UserLocationAvailability` (FK sala) è il
modello primario della superficie.

## Alternative Considerate

### Alternativa 1: Spostamento verbatim delle 5 route

**Descrizione**: spostare le route legacy nel blueprint rinominando gli endpoint,
creando i 2 template mancanti.

- **Pro**: recupera la feature così com'era; cambiamento meccanico.
- **Contro**: relocherebbe due sistemi paralleli mantenendo la duplicazione di
  servizio; lascia `PlayerAvailability` come superficie primaria contro la sua
  stessa deprecazione; più codice da mantenere.

### Alternativa 2: Eliminare e basta le route legacy

**Descrizione**: cancellare le 5 route morte e ripuntare il link, senza portare
sala/discovery nella UI canonica.

- **Pro**: minimo, bassissimo rischio.
- **Contro**: perde silenziosamente la disponibilità per sala e la discovery
  (uniche vie d'accesso erano route rotte) — una capacità che `ProposalService`
  consuma comunque a monte. Lascia la UI canonica sul solo modello deprecato.

## Conseguenze

### Positive

- Un'unica superficie e un unico servizio per la disponibilità: meno codice,
  niente doppio canale, fonte di verità coerente con `ProposalService`.
- La disponibilità per sala (modello canonico) e la discovery sono finalmente
  raggiungibili da UI funzionante.
- Corretti due difetti latenti: append-duplicati nel salvataggio e "rimuovi"
  senza backend.

### Negative

- `PlayerAvailability` (deprecato) resta vivo finché `ProposalService` e i dati
  storici lo richiedono: la deprecazione completa è rinviata.

### Rischi

- La UI mostra ora due tipi di record (sala/località) con modelli diversi: la
  futura migrazione dati località→sala dovrà gestire entrambi. Mitigato: i due
  flussi sono separati e testati end-to-end.

## Note Implementative

- Route: `routes/individual_match/availability.py` (RoleRequirement +
  AvailabilityService); registrate in `routes/individual_match/__init__.py`.
- Servizio: `AvailabilityService` (SSoT) +
  `remove_player_availability`/`remove_venue_availability`.
- Template: `templates/individual_match/availability.html` (riscritto) e
  `templates/individual_match/discover_players.html` (nuovo), i18n.
- Test: `tests/new/integration/test_individual_match_availability_routes.py`
  (set/remove/discover/request, ownership 404, legacy rimosse). I test di
  servizio UC7 (`test_gare_usecase_7_player_availability.py`) restano validi.

## Riferimenti

- ADR-028 (allowlist endpoint in produzione), ADR-031 (gating gamification)
- File correlati: `routes/individual_match/availability.py`,
  `models/individual_match/availability_service.py`,
  `models/individual_match/availability_models.py` (deprecazione
  `PlayerAvailability`), `models/location/models.py` (`UserLocationAvailability`)
