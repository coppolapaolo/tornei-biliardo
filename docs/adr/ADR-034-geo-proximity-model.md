# ADR-034 — Modello geografico / di prossimità per discovery e proposte

- **Status**: Accepted (design) — implementazione separata, vedi "Piano"
- **Data**: 2026-06-06
- **Decisore**: Paolo Coppola
- **Correlati**: ADR-032 (consolidamento availability), ADR-033 (availability
  solo per sala), ADR-028 (allowlist endpoint in prod)

## Problema

Dopo ADR-033 la discovery dei giocatori e l'eligibility delle proposte aperte
sono **per sala** (`BilliardHall`). Manca però un modo per rispondere alla
domanda naturale del giocatore: *"chi/cosa c'è vicino a me?"*. Le sale hanno già
i campi `latitude`/`longitude` (spesso NULL), inutilizzati.

## User story

> Come **giocatore**, voglio trovare **sale** e **proposte di match aperte**
> **vicino alla mia posizione** entro un raggio, per organizzare partite comode
> senza scorrere elenchi globali.

## Decisioni (dall'intervista)

### 1. Posizione dell'utente — GPS effimero + fallback città profilo
- **Primario**: Geolocation API del browser al momento della ricerca. Le
  coordinate viaggiano nella richiesta e sono usate **solo per la query**.
- **Fallback** (permesso negato/non disponibile): una **città "home"**
  dichiarata dall'utente nel profilo (livello città, opt-in).

### 2. Privacy — nessuna memorizzazione della posizione
- Le coordinate GPS catturate **non vengono mai persistite** (né per utente né
  per ricerca): sono effimere per-request.
- L'unico dato salvato è la **città home auto-dichiarata** (stringa a livello
  città, opt-in): un *preference*, non una posizione rilevata. Nessuna
  lat/long utente in DB.
- **Conseguenza chiave**: poiché "giocatori vicino a me" è **fuori scope** (vedi
  §3), non serve alcuna coordinata del giocatore. La superficie GDPR resta
  minima (coordinate solo sulle sale, dato pubblico/di business).

> *Riconciliazione esplicita*: Q1 (fallback profilo) e Q2 (nessuna
> memorizzazione) convivono perché il fallback è una **città** auto-dichiarata,
> non una posizione rilevata. Se anche la città in profilo fosse indesiderata,
> ripiegare sull'input città per-ricerca (effimero).

### 3. Ambito — sale e proposte aperte (NON giocatori)
- **Sale vicino a me**: `BilliardHall` ordinate/filtrate per distanza; con esse i
  giocatori disponibili in quelle sale (riuso `get_available_players_at_venue`).
- **Proposte aperte vicino a me**: ordinate/filtrate per distanza della loro
  sala (`MatchProposal.billiard_hall_id` → coord sala).
- **NON** "giocatori vicino a me" (niente coordinate giocatore).
- La prossimità è un **overlay di ordinamento/filtro**, **non** sostituisce
  l'eligibility di ADR-033: quali proposte un utente può vedere/accettare resta
  governato da sala-disponibile/storico-giocato; la prossimità riordina/filtra
  ciò che è già eligibile (o, per la pura discovery sale, l'elenco sale attive).

### 4. Coordinate sala — inserimento manuale
- Le coord si inseriscono a mano nella scheda sala (admin / venue manager).
- Sale **senza coordinate** sono **escluse dal ranking di distanza** e mostrate a
  parte ("sale senza posizione"), mai silenziosamente nascoste.
- **Nessuna dipendenza di rete** (no geocoding esterno). Il fallback città può
  derivare un'origine approssimata dal **centroide delle coord note delle sale
  in quella città** — prossimità senza rete; se nessuna sala in città ha coord,
  fallback a match testuale per città.

## Criteri di accettazione

- [ ] AC1: con permesso GPS, la discovery sale mostra le sale entro `radius_km`
      ordinate per distanza crescente, con etichetta distanza.
- [ ] AC2: con permesso GPS, la discovery proposte aperte ordina/filtra le
      proposte eligibili per distanza della sala.
- [ ] AC3: senza GPS ma con città home, l'origine è il centroide delle sale di
      quella città (o match per città se nessuna coord) — nessuna chiamata di rete.
- [ ] AC4: nessuna coordinata utente è scritta in DB in alcun flusso.
- [ ] AC5: sale senza coord non spariscono: compaiono in una sezione separata.
- [ ] AC6: `radius_km` ha un default sensato ed è regolabile dall'utente.
- [ ] AC7: l'eligibility ADR-033 delle proposte è invariata (la prossimità
      filtra/riordina, non amplia né restringe i diritti di accesso).

## User journey (sale vicino a me)

1. Giocatore su `/match/availability/discover`.
2. Clicca "📍 Vicino a me" → il browser chiede il permesso di posizione.
3a. Permesso concesso → lista sale entro raggio, ordinate per distanza ("a 3,2 km").
3b. Permesso negato → usa città home del profilo; se assente, invita a impostarla
    o a scegliere una sala/città.
4. Per ogni sala, i giocatori disponibili; bottone "richiedi match" come oggi.

## Edge cases

| Scenario | Comportamento |
|----------|---------------|
| GPS negato e nessuna città home | Messaggio + link a impostare città/usare filtro sala |
| Sala senza lat/long | Esclusa dal ranking, mostrata in "sale senza posizione" |
| Nessuna sala entro raggio | Stato vuoto + suggerimento di aumentare il raggio |
| Città home senza sale con coord | Fallback a match testuale per città (nessuna distanza) |
| Coordinate fuori range / malformate | Ignorate; si ripiega su fallback |
| Raggio enorme | Cap massimo (es. 200 km) per limitare il working set |

## Impatto tecnico

- **Dati**:
  - `User.home_city` (VARCHAR nullable, opt-in) — migrazione additiva.
  - `BilliardHall.latitude/longitude` già esistenti: nessuna nuova colonna; UI
    admin per compilarle. Indice opzionale su `(latitude, longitude)` per il
    pre-filtro bounding-box (migrazione).
- **Query (SQLite, no PostGIS)**: pre-filtro **bounding-box** (`lat BETWEEN ±Δ`,
  `lng BETWEEN ±Δ` con Δ derivato dal raggio) per ridurre le righe, poi
  **haversine in Python** per distanza precisa e ordinamento. Helper in
  `utils/geo.py` (`haversine_km`, `bounding_box`, `city_centroid`).
- **Service**: estendere `AvailabilityService` con
  `get_venues_near(lat, lng, radius_km)` e l'ordinamento proposte per distanza
  (in `ProposalService`/discovery), senza toccare l'eligibility ADR-033.
- **Route/UI**: `discover_players` accetta `near=lat,lng&radius_km=`; bottone
  "Vicino a me" (JS `navigator.geolocation`); scheda sala admin con campi
  lat/long. i18n per le nuove stringhe.
- **ADR-028**: gli endpoint discovery sono già su `individual_match`; nessun
  nuovo endpoint pubblico oltre ai parametri. Decidere visibilità se si aggiunge
  un endpoint dedicato.

## Integrazione

- **Notifiche**: invariate (la prossimità è lato lettura/discovery).
- **Gamification**: nessun impatto diretto; "Local Hero"/`manage_availability`
  restano per sala.
- **i18n**: sì, nuove stringhe (IT primario, EN fallback).
- **Mobile futura**: la Geolocation API è web-standard; il modello effimero si
  presta bene anche a un client mobile.

## Conseguenze

### Positive
- Discovery e proposte finalmente "locali" senza infrastruttura GIS né rete.
- Privacy forte: nessuna posizione utente persistita.
- Riuso dei campi coord sala già presenti.

### Negative / Rischi
- Qualità dipende dal **popolamento manuale** delle coord sala (mitigazione:
  sezione "senza posizione" + UI admin comoda).
- Haversine in Python non scala a milioni di righe (irrilevante a questa scala;
  il bounding-box + indice tiene il working set piccolo).
- Il fallback per centroide-città è approssimato (accettabile per un fallback).

## Domande aperte

- [ ] `radius_km` default: 25 km? e cap massimo 200 km? (assunto in AC6/edge)
- [ ] La città home va nel profilo utente ora, o si parte col solo GPS +
      input città per-ricerca (zero nuove colonne)?
- [ ] L'ordinamento per distanza è default quando la posizione è nota, o
      opt-in via toggle?

## Piano di implementazione (fasi, dopo questo ADR)

1. `utils/geo.py` (haversine, bounding-box, centroid) + unit test puri.
2. Migrazione `User.home_city` (se confermata) + UI admin coord sala + migrazione
   indice coord.
3. `AvailabilityService.get_venues_near(...)` + ordinamento proposte per distanza
   (eligibility ADR-033 invariata) + test.
4. `discover_players` con `near`/`radius_km` + bottone "Vicino a me" (JS) +
   stato "sale senza posizione" + i18n.
5. (Eventuale) endpoint/parametro per proposte aperte ordinate per distanza.
