# Gamification V3 — Design di revisione

**Data**: 2026-06-05
**Stato**: Proposed (decisioni prese; implementazione da pianificare)
**Decisore**: Paolo Coppola
**ADR collegato**: [ADR-031](../adr/ADR-031-gamification-gating-model.md)

Documento di design della revisione del sistema di gamification. Sostituisce
l'impostazione descritta in `GAMIFICATION_V2.md` dove in conflitto. Nessuna
modifica di codice è ancora stata fatta: questo è il "capire bene" condiviso da
cui partirà l'implementazione.

---

## 1. Problema

Il sistema è ricco ma **stratificato, con doppioni e non calibrato**. Sintomi
verificati sul codice (vedi §10 e l'audit nell'ADR-031):

- **Due motori di unlock in conflitto** (legacy per livello — *ancora vivo* — e
  ABAC) con codici doppioni.
- **Curva di livello lentissima** (L5 ≈ 1.118 XP ≈ 22+ vittorie) e **dipendenze
  circolari** che chiudono al neoiscritto proprio drill e match individuali.
- **Nessun onboarding**: niente raccolta di zona/interessi.
- **Invasività**: 4 eventi su 5 generano *sia* toast *sia* notifica persistente,
  senza dedup; mascotte ovunque.
- **Pezzi abbozzati**: editor tassi XP no-op, quest dormienti, achievement stub,
  due surface di proposte match divergenti.

## 2. Obiettivi (dallo stakeholder)

In ordine: **filtrare i permessi seri**, **creare abitudine/ritorno**,
**guidare la scoperta delle funzioni**. *Non* lo status come fine. Il neoiscritto
deve poter **fare drill** e **proporre match individuali** dal giorno 1.

## 3. Principi guida (letteratura)

- **Fogg (B=MAP)**: per il neoiscritto si abbassa l'*Abilità*, non si alza la
  motivazione → loop base aperto, prima azione banale.
- **Hook (Eyal)**: l'onboarding (zona+interessi) è l'*Investimento* che alimenta
  i *Trigger* futuri (nudge geolocalizzati).
- **SDT (Ryan & Deci)**: Autonomia (scegli il percorso), Competenza (XP =
  feedback, non barriera → evita over-justification), Relazione (trovare con chi
  giocare vicino).
- **Time-to-Value**: early win nella prima sessione; funzioni bloccate mostrate
  come *traguardi*, mai muri; empty-state = bivio, mai vicolo cieco.

## 4. Tre layer ortogonali di gating

| Layer | Domanda | Chi decide | Dove |
|-------|---------|------------|------|
| **L0 — Maturità** | la feature è pronta/stabile per essere visibile in prod a quel ruolo? | sviluppatore, per deploy | ADR-028 `ENDPOINT_ROLES` (deny-by-default) |
| **L1 — Autorizzazione** | questo *ruolo* può eseguire l'azione? | regole di ruolo | decoratori `@login_required`, `@director_required`… |
| **L2 — Progressione** | *questo utente* ha sbloccato la feature via gamification? | gamification | ABAC `can_access()` / `UnlockEngine` |

Sono **già accoppiati**: `feature_endpoint_map.py` + `nudge_service.py`
consultano `is_endpoint_visible()` prima di emettere nudge/unlock, così L2 non
pubblicizza mai una feature non promossa (L0). **"Non pronta per nessuno" (L0)**
e **"non ancora sbloccata da te" (L2)** sono due empty-state diversi, da
comunicare diversamente (nascondere del tutto vs "ti manca poco").

## 5. Architettura a due piani (L2)

### Piano 1 — Loop base (sempre aperto, dopo l'onboarding)
Fare drill da solo, proporre match individuali, iscriversi alle gare, vedere
profili/statistiche/leaderboard. Anti-abuso = **completamento onboarding**
(soft-gate, §7).

### Piano 2 — Responsabilità (gate su metriche + ruolo/approvazione, mai su livello)
Organizzare gare, creare campionati, creare drill per altri, gestire sedi.

### Livelli/XP = feedback, non barriera
I livelli **non gattano funzioni**: segnalano progresso e riconoscimento
(numero che sale, leaderboard, badge). Il "**trucco**": quando una funzione si
sblocca *per metrica*, la si presenta come momento celebrativo ("Hai completato
3 drill → ora puoi proporli alla community!"), così l'utente percepisce uno
sblocco senza che il livello sia un muro.

## 6. Un solo motore di gating: ABAC

Si mantiene `UnlockEngine` + `feature_config`. Si **eliminano** il dizionario
legacy `LEVEL_UNLOCKS` e i codici doppioni, **e** si ritira/riconverte la console
admin `/admin/config/levels/unlock/*` consolidando il tuning degli unlock su
`/admin/features` (che ha già la preview d'impatto). Nota: il legacy è *vivo*
(`award_xp` lo legge per popolare gli sblocchi nel `LevelUpEvent`) → prevedere un
sostituto coerente col "trucco" per il contenuto della celebrazione di livello.

## 7. Onboarding portante

**Forma**: brevissimo (1-2 schermate) e **obbligatorio una volta sola**.
1. **Dove** vuoi giocare? → seleziona una/più province → *salvate* (alimentano
   i nudge geo e l'empty-state).
2. **Cosa** ti interessa? → drill / match individuali / tornei (multi-scelta).
3. Atterraggio su una **prima azione su misura** (early win) in base alla scelta.

Completare l'onboarding **sblocca le proposte di match** (soft-gate anti-abuso)
e semina i trigger futuri.

**Utenti esistenti (il sistema è già in produzione)**: l'onboarding va
innescato **al primo login** per chi è già registrato. Implementazione:
campo `onboarding_completed: bool` su `User`, default `False`; migrazione che lo
imposta `False` per tutti gli account esistenti → ognuno lo esegue al login
successivo. I nuovi utenti lo eseguono dopo la registrazione.

## 8. Mappa di progressione proposta (tunabile a runtime via `/admin/features`)

| Funzione | Oggi | Proposta | Razionale |
|---|---|---|---|
| Drill solitari | L5 *opp.* 1 drill in torneo (circolare) | **Aperto post-onboarding** | Early win senza dipendenze |
| Proporre match diretto | 5 match + 1 score (circolare) | **Aperto post-onboarding** | Loop social dal giorno 1 |
| Proporre match alla community | 15 match | **3 match individuali giocati** | Soglia bassa ma non zero |
| Richiedere ruolo director | L3 + 1 torneo | **Partecipato a ≥2 gare** (poi approvazione) | Esperienza reale, non grind XP |
| Creare gara | ruolo director | **invariato** | Già corretto |
| Creare campionato | director + 3 gare org. *opp.* L50 | **director + ≥2 gare organizzate** | Toglie la scorciatoia-livello |
| Creare drill per altri | L30 (legacy) | **§9 (slot a engagement)** | Apertura + qualità auto-regolata |
| Gestire sede (venue) | L5 + 50 match in sede | **presenza reale in sede** | Metrica geografica, non livello |

> I numeri sono punti di partenza, da tarare sui dati reali (community piccola →
> soglie basse all'inizio). La console `/admin/features` con preview d'impatto è
> il luogo per la calibrazione.

## 9. Creare drill per altri — slot a engagement

**Ingresso (metrica pura)**: chi ha completato **N drill** (proposta: N=10,
tunabile) sblocca la creazione di drill.

**Pubblicazione progressiva (auto-regolazione qualità/anti-spam)**:
- Ogni creatore parte con **3 slot** di drill pubblicati.
- **Per superare i 3**, almeno un proprio drill dev'essere stato **completato da
  un altro utente** (segnale di engagement).
- Formalizzazione: `cap_effettivo = 3 + (numero di tuoi drill con ≥1
  completamento da parte di un altro utente)`.
- Se nessuno dei tuoi drill ingaggia, resti a 3: per pubblicarne uno nuovo devi
  **ritirarne uno vecchio**.

**Principio**: *si crea solo finché si ingaggia*. Premia chi produce contenuti
utili, svuota i drill morti, evita lo spam di contenuti, senza bisogno di
moderazione manuale.

## 10. Empty-state geografico (il neoiscritto senza gare vicine)

"Nessuna gara nella tua zona" diventa un **bivio**, non un vuoto:
1. **Allenati** con un drill adesso.
2. **Proponi** un match ai giocatori della tua provincia.
3. **Allarga il raggio** (province limitrofe) automaticamente.
4. **Segnala domanda → organizzatori**: "avvisami se apre una gara qui";
   l'interesse **aggregato per zona** diventa un segnale che mostra ai director
   *dove* conviene organizzare (feature nuova: crea l'offerta dove c'è domanda).

## 10-bis. Modello geografico (selezione luogo, internazionale)

La community è internazionale (**Italia in particolare, Europa in generale**).
La geografia attuale è **Italia-only** (`BilliardHall.province` = codice
provincia italiana, `country` default "Italy", `GeoMatchingService` interamente
provincia-based; `latitude`/`longitude` presenti ma **inutilizzati**). Va
sostituita con un modello **per prossimità**, country-agnostic, **identico per
utenti e per sale**.

### Principio
Coordinate (lat/lng) = **fonte di verità**; discovery per **raggio** (default
~30–50 km, regolabile) sostituisce l'uguaglianza-provincia. `city` + `country`
restano come **etichetta** leggibile e per il raggruppamento del segnale-domanda
(§10.4). `province` degradato a campo legacy di display per le sale italiane
esistenti.

### Dataset città: GeoNames, offline
[GeoNames](https://www.geonames.org) (licenza **CC BY 4.0**, gazetteer mondiale)
pubblica dump di città con coordinate. Si **bundla `cities500`** (~185k righe,
pop>500 *oppure* sedi amministrative fino a PPLA4) in una tabella `cities`
locale → **zero dipendenze a runtime**, nessun problema di whitelist.
- Per **Italia+Europa** è la scelta giusta: in Italia i **comuni** sono inclusi
  anche se piccoli (sedi amministrative PPLA3/PPLA4); in Europa copre i centri
  >500 ab. Attribuzione GeoNames in footer.
- 185k righe con indice = banali per SQLite.

### Selezione (utenti e sale, stesso flusso)
- **Geolocalizzazione browser** ("usa la mia posizione") → lat/lng dal device →
  città più vicina dalla tabella locale (Haversine). Zero dipendenze.
- **Ricerca città** (autocomplete) offline sulla tabella `cities`.
- Creazione **sala**: scegli la città (eredita coordinate) + coordinata precisa
  opzionale del gestore.
- **Robustezza ai buchi**: se un luogo non è nel dataset, le coordinate
  (geolocalizzazione o punto manuale) bastano comunque per la discovery; si
  mostra la città nota più vicina come etichetta. **Mai un blocco.**

### Nominatim (online) — opzionale, futuro
Solo se servirà la precisione a livello di **indirizzo/via** per le sale;
dipende dalla whitelist di produzione e dai limiti d'uso (≈1 req/s +
attribuzione). Non necessario per la granularità città.

### Impatto tecnico
- Accoppiamento attuale piccolo: `models/location/geo_service.py`,
  `routes/player/geo.py`.
- Nuova tabella `cities` (seed da GeoNames `cities500`).
  `BilliardHall`/`UserLocationAvailability` ancorate a `city`+coordinate;
  `province` legacy.
- `GeoMatchingService` riscritto per **raggio** (bounding-box + Haversine su
  SQLite, niente PostGIS).
- Migrazione dati: geocodificare le sale italiane esistenti da città/provincia a
  lat/lng (via tabella `cities`).
- Merita probabilmente un **ADR dedicato** ("modello geografico per prossimità").

## 10-ter. Segnale-domanda → organizzatori ("crea l'offerta dove c'è domanda")

Chiude la leva #4 dell'empty-state (§10): la domanda inespressa dei giocatori
diventa un trigger azionabile per i director. Riusa la geografia (§10-bis) e la
policy notifiche (§11: azionabile → **notifica persistente**).

**Richiesta**: un giocatore esprime "vorrei una gara nella mia zona". Campi:
giocatore, coordinate, `created_at`, `expires_at`.

**Zona del director**: cerchio attorno alla home del director, **raggio
regolabile dal director** (default **~30 km**). Conteggio = richieste *attive*
con distanza Haversine ≤ raggio (linea d'aria dalle lat/lng GeoNames).

**Soglia & trigger** (notifica persistente, azionabile):
- **Fronte di salita** a **≥6** richieste attive nella zona (notifica al passaggio
  5→6, *non* in continuo finché ≥6). Soglia configurabile.
- **Player → director**: alla promozione si valuta la sua zona; se già ≥6,
  notifica una-tantum → chiude il loop domanda→offerta.
- **Cambio home/raggio** del director → rivaluta.
- **Cooldown** per director/zona dopo una notifica (anti-nag).

**Scadenza & refresh**: `expires_at` ~**60 giorni**; **auto-refresh** se il
giocatore è attivo sulla piattaforma **+ prompt di riconferma** prima della
scadenza. Scaduta → esce silenziosamente dal conteggio.

**Chiusura del cerchio**: quando il director crea la gara, le richieste
corrispondenti vengono **consumate** (non rifanno scattare la soglia) e i
giocatori ricevono la notifica azionabile "gara aperta vicino a te → iscriviti".

**Zona senza director**: la domanda si accumula come **segnale per l'admin**
(dove reclutare/promuovere un director) e resta in attesa del trigger
player→director.

## 11. Calibrazione dei segnali (anti-invasività)

- **Doppio canale → policy**: eventi celebrativi (XP, level-up, achievement,
  streak, quest) = **solo toast** transitorio. La **notifica persistente** resta
  solo per cose **azionabili / che puoi perderti** (nuovo invito a match, gara
  nella tua zona). Risolve alla radice la ridondanza toast+notifica (oggi su 4
  eventi).
- **Giù mascotte/animazioni pesanti** (Chalky, confetti): solo per i momenti
  forti, non per ogni evento.
- **Tieni un feedback evidente ma sobrio** su XP/level-up: es. **badge in navbar
  che pulsa/anima**. *Da costruire*: oggi il feedback è il toast con mascotte, la
  micro-animazione del badge non esiste ancora → va creata come sostituto.
- **Max 1 messaggio gamification per sessione**, mai sovrapposti; micro-guadagni
  XP accorpati/silenziati.

## 11-bis. Leaderboard & confronto sociale (riformulazione locale/contributo)

Lo status **non è il fine**: si **riformula** il confronto sociale, non lo si
elimina. Base in letteratura: [Hanus & Fox (2015)](https://www.semanticscholar.org/paper/Assessing-the-effects-of-gamification-in-the-A-on-Hanus-Fox/dff76a9862467d426113ec530f83942016ae3a97)
(longitudinale: leaderboard *globale status-based* ↓ motivazione intrinseca,
soddisfazione, voti); [Mekler et al. (2017)](https://www.sciencedirect.com/science/article/abs/pii/S0747563215301229)
(punti/livelli/leaderboard = *progress indicator*, non muovono la motivazione
intrinseca); SDT/CET (over-justification); Festinger (il confronto con
*simili-vicini* motiva, quello con lontani demoralizza); modello a leghe di
Duolingo.

Regole decise:
1. **Classifiche sportive (gara/campionato): intoccate** — competizione
   legittima di dominio, non gamification vanity.
2. **Leaderboard XP globale assoluto: rimosso dalla UI principale** — è un
   secondo strato di status ridondante, in tensione con gli obiettivi e col
   "problema del 50.000° posto".
3. **Sostituito da confronto locale + contributo**:
   - **Locale/geografico**: "classifica della tua zona" (aggancio al modello
     geo §10-bis), rilevante e *vincibile*; eventualmente a **leghe** di simili
     (modello Duolingo) per evitare la coda lunga che si disimpegna.
   - **Contributo/pro-sociale**: metrica = *engagement generato* (drill
     completati da altri, gare organizzate, persone aiutate), **non XP grezzi**
     → status virtuoso, agganciato al sistema drill a engagement (§9).
   - **Opt-in/contestuale**: ranking mostrato dove la competizione è attesa, non
     nel loop quotidiano.
4. **Default del loop quotidiano = progresso auto-referenziale** (il *tuo*
   streak/livello/record personale), non ranking sugli altri → nutre la
   Competenza-SDT **senza** il confronto sociale corrosivo.

Impatto tecnico: `LeaderboardService` (oggi global/XP) va riorientato — aggiungere
scope **geografico** (filtro per raggio/zona riusando il nuovo
`GeoMatchingService`) e una metrica **contributo**; ritirare il board XP globale
come default. Sinergia con §9 (drill) e §10-bis (geo): la stessa nozione di
engagement e la stessa geografia alimentano sia gli slot drill sia le classifiche.

## 12. Debito tecnico / pulizia (da ADR-031, verificato)

- **BUG/maturity**: `gamification.*` è `{"director"}` in `feature_flags.py`: è il
  maturity-gate, non un bug. Promuovere ai player è l'ultimo step del rollout.
- **Editor tassi XP no-op**: gli handler usano `XP_RATES` hardcoded → cablare
  `ConfigService.get_xp_rate()` o rimuovere l'editor `/admin/config/xp`.
- **Quest dormienti**: nessun seed + `update_quest_statuses()` mai invocato →
  aggiungere scheduler/transizione lazy, e seedare un set minimo *oppure* tenere
  la UI quest dietro maturity-gate finché non popolata.
- **Achievement**: stub veri `win_streak`/`category_reached` (sempre `False`) da
  implementare o nascondere; audit dei progressi non cablati agli eventi.
- **Proposte match**: due surface route+template (`routes/player/proposals.py` —
  vecchia, ferma — e `routes/individual_match/proposals.py` — recente) su **un
  solo backend** `models/individual_match/`. Consolidare ritirando la più
  vecchia, redirigere i link delle dashboard, allineare i metodi del service.
- **Leaderboard**: ok; micro-bug `STREAK_LONGEST` senza `calculated_at`.

## 13. Rollout per fasi (dietro maturity gate L0)

1. **Pulizia a basso rischio** (non visibile agli utenti): rimozione legacy +
   dedup proposte + cablare/rimuovere editor XP + fix stub/quest. Fix
   `STREAK_LONGEST`.
2. **Redesign unlock** (ABAC unica console, mappa §8) + livelli-come-feedback +
   micro-animazione badge + policy toast/notifica §11. Tutto **director-only**
   (L0): i director sono la coorte di beta (vedono la gamification *e* guadagnano
   XP; gli admin sono esclusi dagli XP).
3. **Onboarding** (§7) + backfill utenti esistenti al primo login.
4. **Empty-state geografico** (§10) incl. segnale-domanda → organizzatori.
5. **Promozione ai player a blocchi** in `ENDPOINT_ROLES` quando ogni area è
   stabile (prima dashboard/achievement/streak, poi drill, poi match individuali).

## 14. Punti ancora da tarare

- Soglie numeriche §8/§9 sui dati reali.
- Grafica esatta dell'onboarding (modale vs pagina; come gestire lo skip dei soli
  campi non essenziali).
- Segnale-domanda (§10-ter, design fatto): restano da tarare soglia (≥6),
  default raggio (~30 km), finestra scadenza (~60 gg), durata cooldown.
- Raggio di default per la discovery (~30–50 km) e se renderlo per-utente.
- Modello geografico (§10-bis): da formalizzare in un ADR dedicato prima
  dell'implementazione (schema `cities`, migrazione sale italiane, riscrittura
  `GeoMatchingService`).
- Classifiche locali (§11-bis): design preciso — **a leghe** (gruppi di simili,
  promozione/retrocessione) vs **raggio fisso**; quali metriche di contributo
  esporre; cosa resta opt-in.
