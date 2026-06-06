# ADR-031 — Modello di gating della gamification: loop base aperto, responsabilità a metriche+ruolo, livelli come feedback

**Data**: 2026-06-05
**Stato**: Proposed (in affinamento dei dettagli)
**Decisori**: Paolo Coppola

## Contesto

Revisione del sistema di gamification (richiesta del 2026-06-05). L'analisi di
codice e documentazione ha rilevato che il sistema, pur ricco (XP, livelli,
achievement, streak, quest, motore ABAC), è **stratificato, con doppioni e non
calibrato**. In particolare:

1. **Due motori di unlock in conflitto**:
   - Legacy basato sul livello — `models/gamification/xp_config.py::LEVEL_UNLOCKS`
     (es. `match_proposals` a L5, `tournament_creation` a L10) con
     `is_feature_unlocked()` / `get_next_unlock()`.
   - ABAC (quello realmente usato da `current_user.can_access(...)`) —
     `models/gamification/unlock_engine.py` + tabella `feature_config`
     (es. `create_match_direct`, `create_gara`, `do_challenge`).
   I due descrivono regole diverse e incoerenti per le stesse capacità, con
   codici doppioni (`match_proposals` vs `create_match_direct`,
   `tournament_creation` vs `create_gara`).

2. **Curva di livello troppo ripida rispetto ai gate**: `100 * level^1.5` →
   L5 = 1.118 XP ≈ 22+ vittorie. Nessuno "sblocco" nei primi minuti/settimana.

3. **Dipendenze circolari sul neoiscritto**: `do_challenge` (drill) richiede
   `L5 OPPURE 1 drill in torneo`; `create_match_direct` richiede `5 match + 1
   score`. Le due attività pensate per il giorno 1 (drill solitari e match
   individuali) sono di fatto **chiuse** proprio all'inizio.

4. **Nessun onboarding**: solo toast di benvenuto e nudge al login. Manca la
   raccolta di zona/interessi che orienterebbe il percorso e alimenterebbe i
   trigger futuri.

5. **Visibilità `gamification.*` ai soli `director`**: in produzione le pagine
   `gamification.*` sono mappate a `{"director"}` in `utils/feature_flags.py`,
   quindi un **player non vede la propria dashboard** XP/achievement pur avendo
   il badge in navbar. **Non è (necessariamente) un bug**: è il *maturity gate*
   di ADR-028 (deny-by-default) che fa il suo lavoro — la gamification non è
   ancora stata promossa ai player in produzione. Promuoverla ai player è
   l'ultimo step del rollout, da fare quando il redesign è stabile, non un fix
   urgente.

### Tre layer ortogonali di gating (premessa)

Il sistema distingue — e va tenuto concettualmente pulito — tre livelli
indipendenti:

| Layer | Domanda | Chi decide | Dove |
|-------|---------|------------|------|
| **L0 — Maturità** | la feature è pronta/stabile per essere visibile in prod a quel ruolo? | sviluppatore, per deploy | ADR-028 `ENDPOINT_ROLES` (deny-by-default) |
| **L1 — Autorizzazione** | questo *ruolo* può eseguire l'azione una volta raggiunta? | regole di ruolo | decoratori `@login_required`, `@director_required`… |
| **L2 — Progressione** | *questo utente* ha sbloccato la feature via gamification? | gamification | ABAC `can_access()` / `UnlockEngine` |

I due gate sono **già accoppiati**: `models/gamification/feature_endpoint_map.py`
+ `nudge_service.py` consultano `is_endpoint_visible(endpoint, user)` prima di
emettere nudge/unlock, così la progressione (L2) **non pubblicizza mai** una
feature non ancora promossa (L0). Conseguenza progettuale: "non pronta per
nessuno" (L0) e "non ancora sbloccata da te" (L2) sono **due empty-state
diversi** da comunicare diversamente (nascondere del tutto vs "ti manca poco").

Obiettivi dichiarati dello stakeholder (in ordine, multi-selezione):
**filtrare i permessi seri**, **creare abitudine/ritorno**, **guidare la
scoperta delle funzioni**. *Non* lo status come fine. Il neoiscritto deve poter
**proporre match individuali** e **fare drill** dal giorno 1.

## Decisione

### 1. Architettura a due piani

- **Loop base (sempre aperto, dopo l'onboarding)**: fare drill da solo,
  proporre match individuali, iscriversi alle gare, vedere
  profili/statistiche/leaderboard.
- **Responsabilità (gate su metriche d'attività + ruolo/approvazione, MAI sul
  livello)**: organizzare gare, creare campionati, creare drill per altri,
  gestire sedi (venue manager).

### 2. Livelli/XP come feedback, non come barriera

I livelli **non gattano funzioni**. Servono come segnale di competenza e
riconoscimento (numero che sale, leaderboard, badge). Quando una funzione si
sblocca *per metrica*, la si presenta come momento celebrativo ("Hai completato
3 drill → ora puoi proporli alla community!"), così l'utente percepisce uno
sblocco senza che il livello sia un muro. Coerente con SDT (evitare
over-justification) e con l'obiettivo "non lo status come fine".

### 3. Un solo motore di gating: ABAC (codice **e** console admin)

Si mantiene il motore ABAC (`UnlockEngine` + `feature_config`). Si **eliminano**
il dizionario legacy `LEVEL_UNLOCKS` e i codici doppioni
(`match_proposals`, `tournament_creation`, `priority_invites`,
`custom_badge_display`, `venue_suggestion`, `challenge_creation`,
`director_fast_track`, `legend_status` nella misura in cui duplicano regole
ABAC). Le condizioni di tipo `LEVEL` restano disponibili nel motore ma non sono
più la leva primaria per le responsabilità.

La de-duplicazione **non è solo di codice**: a livello admin coesistono due
console di unlock — `/admin/config/levels/unlock/*` (legacy, modello
`LevelUnlock`, basata sul livello) e `/admin/features/*` (ABAC). Si **ritira o
riconverte** la prima, consolidando **tutto il tuning degli unlock su
`/admin/features`** (che ha già la preview d'impatto). Restano valide e utili le
altre console di `routes/gamification/config.py`: tuning dei tassi XP, della
curva di livello e delle milestone streak (coerenti con "livelli = feedback").

### 7. Layer admin/tuning e coorte di beta

- **Console di tuning unica per gli unlock**: `/admin/features` con preview
  d'impatto è il luogo per tarare le soglie della mappa di progressione sui dati
  reali (community piccola → partire basse). Le console XP-rate / curva /
  milestone restano per la calibrazione del feedback.
- **Quest dormienti**: non esiste seed di quest (solo `achievement_seeds.py`);
  le quest esistono solo se create da admin. Decisione: seedare un set minimo di
  quest di default **oppure** tenere la UI quest dietro maturity-gate (L0)
  finché non viene popolata, per non mostrare una sezione vuota.
- **Achievement non sbloccabili / progressi non cablati** (verificato in
  `achievement_service.py::_check_requirements`):
  - **Stub veri** (ritornano `False` incondizionato): `win_streak` (riga 279),
    `category_reached` (304). Non scattano mai → implementare o nascondere.
  - **Progressivi ma a rischio**: `tournament_podium`, `tournament_wins`,
    `unique_opponents`, `strategies_tried`, `perfect_challenges`,
    `match_proposals_created`, `match_proposals_accepted` funzionano solo se un
    event handler incrementa `current_progress`; se nessuno lo fa, l'achievement
    *sembra valido ma non avanza mai*. Serve un audit di quali progressi sono
    effettivamente cablati agli eventi.
- **Coorte di beta interna**: gli admin sono esclusi dalla gamification (niente
  XP/achievement/streak), i director no. Con `gamification.* = {"director"}` i
  **director** possono sia vedere sia guadagnare → sono la coorte naturale per
  validare il redesign in produzione *prima* della promozione ai player (L0).

### 4. Onboarding portante come soft-gate anti-abuso

Un onboarding minimo (zona d'interesse + tipo di attività: drill / match /
tornei / organizzare) diventa **prerequisito leggero** per il loop social
(proporre match). È al tempo stesso l'investimento (Hook model) che alimenta i
nudge geolocalizzati futuri. Questo sostituisce gate basati sul grind come
barriera anti-spam.

### 5. Empty-state geografico come bivio, non vuoto

Quando non ci sono gare nella zona dell'utente, l'interfaccia offre: (a)
allenati con un drill, (b) proponi un match nella tua provincia, (c) allarga il
raggio alle province limitrofe, (d) **segnala interesse** → l'interesse
aggregato per zona diventa un segnale per i director su dove conviene
organizzare (feature nuova).

### 6. Calibrazione dei segnali (anti-invasività)

Ridurre mascotte "Chalky" e animazioni pesanti/confetti; mantenere un **feedback
sobrio ma evidente** su XP/level-up (es. badge in navbar che pulsa), toast solo
per i momenti che contano (level-up, sblocco funzione, milestone streak), **max
1 messaggio gamification per sessione**, micro-guadagni XP accorpati/silenziati.

## Alternative Considerate

### Alternativa 1: Livelli come gate, curva ricalibrata (RPG classico)

**Descrizione**: mantenere "raggiungi LN per sbloccare X" abbassando la curva.

- **Pro**: modello mentale semplice; senso di progressione netto.
- **Contro**: reintroduce grind e dipendenze circolari; XP diventa portante →
  rischio over-justification (SDT); calibrazione della curva fragile; non
  risolve il caos dei due motori se non se ne sopprime uno comunque.

### Alternativa 2: Mix non disciplinato (status quo)

**Descrizione**: lasciare convivere livelli e ABAC come oggi.

- **Pro**: nessun lavoro di pulizia.
- **Contro**: è la causa del problema attuale — regole incoerenti, codici
  doppioni, comportamento imprevedibile.

### Alternativa 3: Anti-abuso senza onboarding (solo email verificata o rate limit)

**Descrizione**: aprire tutto subito, contenere lo spam con limiti di rate.

- **Pro**: frizione minima.
- **Contro**: perde l'investimento dell'onboarding (trigger futuri) e i dati di
  zona/interessi che servono all'empty-state e ai nudge. Lo stakeholder ha
  scelto esplicitamente l'onboarding come soft-gate.

## Conseguenze

### Positive

- Neoiscritto operativo dal giorno 1 (drill + match) con early win.
- Un solo motore di gating, regole coerenti e leggibili.
- Livelli/XP non bloccano nessuno → calibrazione a basso rischio.
- Onboarding genera dati (zona/interessi) riutilizzabili da nudge ed empty-state.
- Responsabilità "serie" restano protette da esperienza reale + approvazione.

### Negative / Costi

- Lavoro di pulizia: rimozione legacy; **consolidamento delle due surface di
  proposte match** — `routes/player/proposals.py` (creata 2025-12-29, ferma dal
  2026-02-07, linkata dalle dashboard) e `routes/individual_match/proposals.py`
  (creata 2026-02-07, più recente, linkata dalla navbar). **Non sono due
  backend**: entrambe usano l'unico `models/individual_match/` — è duplicazione
  di route+template (con drift: metodi service diversi,
  `create_direct/open_proposal`+`reject_proposal` vs
  `create_proposal`+`reject_invitation`). Il consolidamento = ritirare una
  surface (presumibilmente la più vecchia `player.match-proposals`),
  reindirizzare i link e allineare i metodi; **non** fondere domini. Inoltre:
  achievement stub veri (`win_streak`, `category_reached`) da implementare o
  nascondere, + audit dei progressi achievement non cablati agli eventi.
- L'onboarding diventa un percorso obbligato leggero: va progettato per non
  essere frizione (skippabile-ma-sollecitato).

### Rischi

- Soglie metriche mal tarate su una community piccola → meglio partire basse.
- "Sblocco celebrato per metrica" può confondere se non c'è un punto unico che
  decide quando mostrarlo (serve un hook su variazione di eleggibilità).

## Note Implementative

Decisione **non ancora in implementazione**. Dettagli risolti il 2026-06-05
(vedi `docs/reference/GAMIFICATION_V3.md`):

- **Onboarding**: brevissimo e obbligatorio (zona + interessi); per gli **utenti
  esistenti** (sistema già in produzione) si innesca **al primo login** via flag
  `User.onboarding_completed` (default `False`, backfill su tutti gli account).
- **Anti-invasività**: eventi celebrativi → **solo toast**; notifica persistente
  **solo se azionabile** (invito a match, gara in zona). Feedback sobrio sul
  level-up = micro-animazione del badge in navbar (**da costruire**: oggi non
  esiste).
- **Creare drill per altri**: ingresso a **metrica pura** (N drill completati),
  con **pubblicazione progressiva a engagement**: 3 slot iniziali,
  `cap = 3 + (# tuoi drill con ≥1 completamento esterno)`; senza engagement si
  resta a 3 e per crearne uno nuovo se ne ritira uno vecchio. "Si crea solo
  finché si ingaggia" → qualità auto-regolata, niente moderazione manuale.

- **Modello geografico** (community internazionale, Italia+Europa): si passa da
  province italiane a **prossimità per coordinate + raggio**, country-agnostic e
  **identico per utenti e sale**. Dataset città **GeoNames `cities500`** bundlato
  offline (zero dipendenze runtime); coordinate = fonte di verità, città =
  etichetta; `province` legacy. Merita un **ADR dedicato**. Dettaglio in
  `GAMIFICATION_V3.md` §10-bis.

- **Leaderboard & confronto sociale**: lo status non è il fine → **riformulazione
  locale/contributo** (non rimozione totale). Classifiche sportive di
  gara/campionato intoccate; leaderboard XP globale assoluto ritirato dalla UI
  principale; sostituito da classifiche **locali/geografiche** (modello a leghe
  à la Duolingo, aggancio al modello geo) e basate sul **contributo/engagement**
  (non XP grezzi); loop quotidiano su progresso **auto-referenziale**. Base:
  Hanus & Fox 2015, Mekler et al. 2017, SDT/CET, Festinger. Dettaglio in
  `GAMIFICATION_V3.md` §11-bis.

- **Segnale-domanda → organizzatori**: i giocatori esprimono richieste di gara
  geolocalizzate; quando la domanda *attiva* in una **zona del director** (cerchio
  a **raggio regolabile**, default ~30 km, Haversine) raggiunge **≥6** (fronte di
  salita), il director riceve una **notifica azionabile**; idem alla promozione
  player→director se la domanda esiste già. Richieste con **scadenza ~60 gg** +
  **auto-refresh sull'attività + riconferma**; consumate quando la gara è creata
  (e i giocatori notificati). Chiude il loop "crea l'offerta dove c'è domanda".
  Dettaglio in `GAMIFICATION_V3.md` §10-ter.

- **Quest & Achievement** (principio: mai mostrare contenuto non ottenibile/non
  attivo). *Achievement*: seeding **già agganciato** all'avvio (`app.py:282-290`,
  *correzione 2026-06-05: non "mai chiamato in prod"*); **disattivare**
  (`is_active=False`, non `is_hidden` che mostra solo "???") i 2 stub (`win_streak`,
  `category_reached`) e gli 8 progress-based non cablati — via migrazione `UPDATE`
  per i DB esistenti; cablare agli eventi i progress-based economici (Fase 2).
  *Quest*: status **calcolato dalle date** (niente cron) + **seed minimo** di
  quest personali ricorrenti, dietro maturity-gate. Dettaglio in
  `GAMIFICATION_V3.md` §11-ter.

- **Feedback badge navbar**: il badge livello+XP esiste già ma è statico → si
  rende **vivo** con un **anello di progresso** (feedback auto-referenziale di
  competenza) + *pulse* su XP e *glow*+toast su level-up. **Scala di intensità**:
  la maggioranza degli eventi resta sul badge silenzioso, il toast (e la
  mascotte) solo ai momenti forti → chiude il problema toast+notifica. Rispetto di
  `prefers-reduced-motion`. Dettaglio in `GAMIFICATION_V3.md` §11-quater.

Con questo il **design è completo**. Restano solo tarature (soglie numeriche,
grafica onboarding, raggio default, classifiche locali leghe-vs-raggio, set quest
seed / achievement da cablare) e la pianificazione dell'implementazione a fasi.

File coinvolti (riferimento, non ancora modificati):
- `models/gamification/xp_config.py` — rimozione `LEVEL_UNLOCKS`/helper legacy.
- `models/gamification/unlock_engine.py`, `feature_models.py` — motore ABAC unico.
- `migrations/20260126_populate_gamification_rules.py` — ricalibrare regole.
- `utils/feature_flags.py` — fix visibilità `gamification.*` per `player`.
- `routes/individual_match/` + `routes/player/proposals.py` — consolidamento
  surface (ritiro della più vecchia, redirect dei link dashboard, allineamento
  metodi service); backend `models/individual_match/` unico, non toccato.
- `routes/auth.py` — innesto onboarding post-registrazione.

## Audit sottosistemi (2026-06-05, verificato sul codice)

- **Leaderboard** (`leaderboard_service.py`): reale e cablato — 5 tipi calcolati
  da `UserLevel`/`StreakTracker`/`PlayerRating`, cache con refresh on-demand.
  ~~Micro-bug: `STREAK_LONGEST` non setta `calculated_at`.~~ **Risolto in Fase 1**
  (`STREAK_LONGEST` non impostava né `score` né `calculated_at`: poiché
  `score` è `NOT NULL`, la classifica falliva del tutto al refresh; ora allineata
  agli altri `_calculate_*`).
- **Achievement non ottenibili — RISOLTO in Fase 2 (re-engineering metric-driven)**:
  la causa radice era `_check_requirements` con due meccanismi incoerenti
  (contatore incrementale fragile vs query reali). Oltre ai 12 disattivati in
  Fase 1, erano di fatto non ottenibili anche `champion`/`podium_finish`/
  `tournament_dominator` e perfino `tournament_debut`/`tournament_regular`.
  Reingegnerizzata l'idoneità su modello unico (`AchievementMetrics`, fonte di
  verità per ogni metrica "conta N"); resi ottenibili e cablati champion/podium/
  dominator (ledger XP), diverse_competitor/community_pillar (avversari unici) e
  social_butterfly/popular_player (proposte). I 4 social riattivati con migrazione
  `20260606`. Restano disattivati 8 senza sorgente dati (serie vittorie,
  categoria giocatore, drill/strategie). Vedi `GAMIFICATION_V3_HANDOFF.md`.
- **Quest**: registrazione progresso cablata end-to-end (event handlers →
  `record_activity_for_quests` → auto-join/incremento/XP/evento), MA **nessun
  seed** e `update_quest_statuses()` **mai invocato** (niente cron/route) → le
  quest non si attivano/scadono automaticamente; sistema **dormiente** salvo
  azione manuale admin. Serve uno scheduler o una transizione di stato lazy.
- **Config runtime** (`config_service.py` + `routes/gamification/config.py`):
  curva livelli e level-unlock **cablati** (letti a runtime con fallback ai
  default); **tassi XP NO-OP** — gli event handler usano `XP_RATES` hardcoded da
  `xp_config.py` invece di `ConfigService.get_xp_rate()`, quindi l'editor
  `/admin/config/xp` non ha effetto sugli award. Da cablare o rimuovere
  l'editor.
- **Sistema legacy level-unlock vivo**: `LevelService.award_xp` consulta
  `ConfigService.get_all_level_unlocks_dict()` per popolare gli sblocchi nel
  `LevelUpEvent`. Rimuoverlo (Decisione §3) impatta anche il **contenuto della
  celebrazione di level-up**, non solo il gating → prevedere sostituto coerente
  col "trucco" (celebrare sblocchi-per-metrica).
- **Invasività = doppio canale** (`frontend_bridge.py` + `notification_handlers.py`):
  4 eventi su 5 (LevelUp, Achievement, StreakMilestone, QuestCompleted) emettono
  **sia toast sia notifica persistente**, senza dedup né rate-limit; una partita
  può generare ~3 toast + ~3 notifiche. XP è protetto (solo toast, soppresso se
  ≤0); StreakBroken volutamente muto. Intervento mirato ad alto impatto per
  l'obiettivo "non invasiva".
- **Feedback sobrio non esiste ancora**: in `gamification.js` il feedback *è* il
  toast con mascotte "Chalky" + confetti. La scelta "giù mascotte, tieni un
  feedback evidente (badge che pulsa)" richiede di **costruire** la micro-
  animazione del badge come sostituto, non solo di rimuovere.

## Riferimenti

- `docs/reference/GAMIFICATION_V3.md` — documento di design esteso.
- `docs/reference/GAMIFICATION_V2.md` — sistema precedente (invisible/signal-based).
- `docs/adr/ADR-019-gamification-abac-migration.md` — migrazione a ABAC.
- `docs/adr/ADR-028-production-endpoint-allowlist.md` — allowlist endpoint.
- Letteratura: Fogg Behavior Model (B=MAP); Eyal, *Hooked* (Trigger-Action-Reward-Investment);
  Ryan & Deci, Self-Determination Theory; principi di onboarding/time-to-value.
