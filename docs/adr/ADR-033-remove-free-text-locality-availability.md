# ADR-033 — Rimozione della disponibilità "località" a testo libero (`PlayerAvailability`)

- **Status**: Accepted
- **Data**: 2026-06-06
- **Decisore**: Paolo Coppola
- **Segue**: ADR-032 (consolidamento superficie disponibilità)

## Contesto

ADR-032 ha unificato la superficie di disponibilità sul blueprint
`individual_match` con `AvailabilityService` come unica fonte di verità, ma ha
**rinviato** la deprecazione completa di `PlayerAvailability` — il modello
legacy basato su `location` (stringa a testo libero) — perché ancora consumato
da `ProposalService` e da dati storici.

Convivevano quindi due modelli di disponibilità:

- `PlayerAvailability` — località a **testo libero** (`location: str`), nessun
  vincolo referenziale verso una sala reale.
- `UserLocationAvailability` — disponibilità per **sala** (`billiard_hall_id`
  FK verso `BilliardHall`), modello canonico.

La doppia superficie raddoppiava il codice (form, route, query, notifiche),
permetteva disponibilità verso luoghi inesistenti/typo ("Bar Sport" vs "bar
sport"), e rendeva la discovery e l'eligibility delle proposte aperte
ambigue (match per stringa vs match per FK).

## Decisione

**Rimuovere completamente `PlayerAvailability`.** La disponibilità diventa
**solo per sala** (`UserLocationAvailability` / `BilliardHall`).

1. **Dati**: migrazione `20260606_drop_player_availability` — ogni record
   `player_availability` viene mappato a `user_location_availability` quando la
   stringa `location` corrisponde (case-insensitive, trimmed) al `name` di una
   `BilliardHall`; i record senza sala corrispondente vengono **scartati**
   (perdita accettata: erano luoghi non censiti). Poi `DROP TABLE
   player_availability`. Idempotente: se la tabella non esiste è un no-op.

2. **Modello/Service**: eliminati `PlayerAvailability`,
   `AvailabilityService.set_player_availability`,
   `get_available_players_at_location`, `remove_player_availability`.
   `get_user_availability_preferences` ritorna solo `venues`.

3. **Eligibility proposte aperte** (`ProposalService.get_user_proposals`):
   non più per stringhe da `PlayerAvailability`, ma per **sale disponibili**
   (`UserLocationAvailability.billiard_hall_id`) unite alle sale/località dove
   l'utente ha **già giocato** (`IndividualMatch`). Se l'utente non ha né
   disponibilità né storico, vede tutte le proposte aperte (comportamento
   invariato).

4. **Notifiche proposte aperte**: per sala → giocatori disponibili in sala;
   per località a testo libero (le proposte mantengono il campo `location`) →
   giocatori che hanno **giocato** in quella località. La logica
   played-at-location è estratta in
   `AvailabilityService.get_players_who_played_at_location`, riusata anche da
   `notify_players_of_availability` (che resta, è `PlayerAvailability`-free).

5. **UI**: rimossi dalla pagina `availability.html` il form "Aggiungi una
   località" e la lista delle località; `discover_players.html` perde il filtro
   per località (discovery solo per sala). La creazione proposta conserva il
   campo `location` libero (campo separato su `MatchProposal`), non toccato qui.

6. **Admin overview**: "Località attive" → "Sale attive"
   (`UserLocationAvailability` + `BilliardHall`).

## Conseguenze

### Positive
- Una sola superficie di disponibilità, referenzialmente integra (FK a sala).
- Discovery ed eligibility coerenti e prive di ambiguità tra stringa e FK.
- Meno codice, niente più record verso luoghi inesistenti.

### Negative / Rischi
- **Perdita dati**: le disponibilità verso località non censite come
  `BilliardHall` non sono migrabili e vengono scartate. Accettata
  esplicitamente: erano dati a testo libero non azionabili dalla discovery.
- Gli utenti ora possono dichiararsi disponibili **solo per sale registrate**.
  Mitigazione naturale verso il modello geografico (ADR futuro): le sale hanno
  già `latitude/longitude`.

## Note implementative
- Migrazione: `migrations/20260606_drop_player_availability.py`.
- Service: `models/individual_match/availability_service.py`.
- Eligibility/notifiche: `models/individual_match/proposal_service.py`.
- Statistiche/admin: `models/individual_match/statistics_service.py`.
- Template: `templates/individual_match/availability.html`,
  `discover_players.html`, `admin_overview.html`.
- Test: `tests/new/integration/test_individual_match_availability_routes.py`
  (riscritti su sala), `test_gare_usecase_7_player_availability.py` (già su
  sala — rimosso solo l'import inutilizzato).
