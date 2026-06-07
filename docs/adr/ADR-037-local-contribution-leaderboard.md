# ADR-037 — Leaderboard locale + contributo (riformulazione §11-bis)

- **Status**: Accepted (v1; leghe e tarature come open items)
- **Data**: 2026-06-06
- **Decisore**: Paolo Coppola
- **Correlati**: GAMIFICATION_V3 §11-bis (design), ADR-034 (geo/prossimità),
  ADR-031 (gating gamification = feedback), ADR-028 (allowlist endpoint),
  §9 (drill a engagement)

## Problema

Il leaderboard attuale (`LeaderboardService`) è **globale e XP-centrico**
(XP_ALL_TIME, LEVEL_HIGHEST, STREAK, ELO) — un secondo strato di status
ridondante che la letteratura (Hanus & Fox 2015; Festinger) indica come
**corrosivo** per la motivazione intrinseca (confronto con lontani demoralizza;
"problema del 50.000° posto"). Il §11-bis chiede di **ritirarlo dalla UI** e
sostituirlo con (1) un confronto **locale** (vincibile, tra simili-vicini) e
(2) una metrica di **contributo** pro-sociale (status virtuoso).

Riconciliazione con ADR-034: **non esistono coordinate del giocatore
persistite**. La "zona" di un giocatore va derivata dall'unico dato di posizione
opt-in: `home_city`.

## User story

> Come **giocatore**, voglio vedere come me la cavo *nella mia zona* (rilevante e
> raggiungibile) e chi *contribuisce di più* alla community, invece di una
> classifica XP globale dove sono il 50.000°.

## Decisioni (dall'intervista)

### 1. Zona = `home_city` (+ città vicine via centroide)
La classifica locale confronta i giocatori che **condividono la `home_city`**
del visitatore, espandibile alle **città vicine** il cui centroide-sale (ADR-034)
è entro un raggio (default 30 km). Nessuna coordinata giocatore persistita;
livello città. **Leghe (Duolingo)** rimandate (open item).
Punteggio locale = `UserLevel.total_xp` (XP reso *vincibile* dalla località —
progress indicator, non vanity globale).

### 2. Contributo = composito pro-sociale
`contribution_score = drills_engaged + gare_organized + proposals_accepted`,
dove:
- **drills_engaged**: tentativi *completati da altri utenti* su drill di cui
  l'utente è autore (`Challenge.created_by_id`) — aggancio al sistema §9.
- **gare_organized**: gare di cui l'utente è responsabile (`Gara.director_id`).
- **proposals_accepted**: proposte **aperte** create dall'utente e **accettate**.

Premia *l'engagement generato*, non gli XP grezzi (§11-bis). Pesi uguali in v1
(taratura = open item). Board di contributo **community-wide** (il contributo è
intrinsecamente sociale; pool piccolo).

### 3. UI: ritiro del board XP globale
La pagina `gamification.leaderboards` mostra **due tab**: *La tua zona* e
*Contributo*. I board globali (XP_ALL_TIME, LEVEL_HIGHEST, STREAK, ELO) sono
**ritirati dalla UI**. `LeaderboardService` resta nel codice (non rimosso) ma
non più esposto come default. Il loop quotidiano resta **progresso
auto-referenziale** (badge navbar, dashboard personale — già esistenti).

### 4. Calcolo on-demand, niente nuova tabella
La classifica locale è **per-visitatore** (ogni `home_city` è un board diverso):
non si materializza nella cache globale `leaderboard_entry`. Si calcola
**on-demand** (community piccola). Idem contributo in v1. Nessuna migrazione.

### 5. Visibilità (ADR-028) — invariata
`gamification.leaderboards` resta `{"director"}` (maturity-gated come oggi);
promozione ai player col maturity-gate quando validato.

## Alternative considerate
- **Per sale condivise** (UserLocationAvailability): granularità sala; scartata
  in favore di `home_city` (più semplice, sempre presente come opt-in).
- **Leghe a coorti**: più ingaggiante ma molto più grande (assegnazione coorti,
  cicli, promo/retro, storage). Rimandata (open item).
- **Tenere il board XP globale**: reintroduce lo status ridondante che il design
  vuole rimuovere. Scartata.

## Conseguenze
### Positive
- Confronto rilevante e vincibile; status virtuoso dal contributo; rimosso lo
  strato XP corrosivo. Riusa geo ADR-034 e il modello drill §9.
- Nessuna migrazione né coordinate giocatore (privacy minima).
### Negative / costi
- Calcolo on-demand O(utenti/città) — accettabile per community piccola; se
  cresce, materializzare/cachare (open item).
- Dipende da `home_city` impostata: chi non l'ha non vede il board locale (gli
  mostriamo un invito a impostarla).
### Rischi
- Città scritte in modo incoerente ("Napoli"/"napoli") → match case-insensitive
  via trim/lower. Città senza centroide → niente espansione (solo match esatto).

## Open Items
1. **Leghe** a coorti di simili (promozione/retrocessione settimanale) —
   **RIMANDATO**: ha valore solo con abbastanza utenti per coorte; nel beta
   piccolo darebbe coorti da 1-2 persone (controproducente). Da riprendere
   quando la community cresce.
2. **Tarature** — **FATTO** (costanti documentate): pesi del contributo
   centralizzati in `CONTRIBUTION_WEIGHTS` (default peso 1), raggio espansione
   città in `LOCAL_ZONE_RADIUS_KM`. Facili da affinare; nessun pannello runtime.
3. **Performance**: materializzare/cachare (come `LeaderboardEntry`) se la
   community cresce — *ancora aperto* (premature ora).
4. ~~**gare_organized** via `DirectorAssignment`~~ — **FATTO**.

## Note implementative
- `models/gamification/community_leaderboard_service.py`
  (`CommunityLeaderboardService`): `get_local_leaderboard`,
  `compute_contribution`, `get_contribution_leaderboard`. Riuso `utils.geo` +
  `AvailabilityService.city_centroid_for`.
- Route `gamification.leaderboards` riorientata; template
  `gamification/leaderboards.html` → tab Zona + Contributo.

## Riferimenti
- `docs/reference/GAMIFICATION_V3.md` §11-bis, §9
- ADR-034, ADR-031, ADR-028
- File: `models/gamification/community_leaderboard_service.py`,
  `routes/gamification/dashboard.py`, `templates/gamification/leaderboards.html`
