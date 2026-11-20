# Classification Domain

## Purpose

Ranking and classification system for tournaments at multiple scopes: round, gara, and campionato.

**Core Responsibilities:**
- Round-by-round classification for matchmaking (Amalfi algorithm)
- Final gara rankings
- Aggregated campionato standings
- Anti-rematch tracking via PlayerEncounter
- Tiebreaker resolution

---

## Quick Reference

```python
from models.classification.models import (
    Classification, RoundClassification, GaraClassification, PlayerEncounter
)
from models.classification.services import (
    ClassificationService, RoundClassificationService,
    StrategyBasedClassificationService
)

# Scrive la copia della classifica generale nelle righe Classification (ADR-073)
ClassificationService.update_campionato_classification(campionato_id)

# Calculate and save round classification (for matchmaking)
RoundClassificationService.calculate_and_save_round_classification(gara_id, round_number)

# Strategy-based classification (recommended for new code)
service = StrategyBasedClassificationService()
result = service.calculate_round_classification(gara, round_number)
# Returns: ClassificationResult with PlayerScore list

# Check anti-rematch
played = PlayerEncounter.have_played(gara_id, player1_id, player2_id)
```

---

## Models

### Classification
Campionato-level standings across all gare.

**Fields:** `campionato_id`, `user_id`, `position`, `total_matches_won`, `total_point_difference`, `gare_played`

### RoundClassification
Per-round standings within a gara. Used by matchmaking for pairing.

**Fields:** `gara_id`, `round_number`, `user_id`, `position`, `matches_won`, `racks_won`, `rack_difference`, `previous_position`

### GaraClassification
Final rankings for a completed gara. Includes SSR tiebreaker scores.

**Fields:** `gara_id`, `user_id`, `position`, `matches_won`, `racks_won`, `racks_lost`, `rack_difference`, `spot_shot_wins`

### PlayerEncounter
Tracks player matchups for anti-rematch logic.

**Fields:** `gara_id`, `player1_id`, `player2_id`, `round_number`

---

## Strategy Pattern

Classification uses strategy pattern in `strategies/` subdirectory:

| Strategy | Scope | Usage |
|----------|-------|-------|
| `amalfi_round` | Round | Amalfi per-round classification |
| `amalfi_gara` | Gara | Amalfi final standings |
| `random_round` | Round | Random strategy classification |
| `random_gara` | Gara | Random final standings |
| `position_round` | Round | Gare a tabellone, classifica parziale |
| `position_gara` | Gara | Gare a tabellone, bande di pari merito |
| `points_round` | Round | Classifica a punti (POINTS), turno |
| `points_gara` | Gara | Classifica a punti (POINTS), finale |

### Sistema POINTS (classifica a punti, ADR-078 emendamento)

Si ordina **solo sui punti**, poi la catena (default = quella WINS). I punti
di vittoria/pareggio/sconfitta (default 3/1/0) stanno sulla gara
(`points_win/draw/loss`), proposti dal campionato (`default_points_*`), e si
leggono **solo** da `punti.py`. `ScoreAggregator` conta i pareggi
(`matches_drawn`) e somma i punti (`_esito`) solo nelle gare a punti: la X
vale una vittoria, il trio senza vincitore dà il pareggio a chi è in testa e
la sconfitta al terzo. Le righe di classifica tengono `points` (NULL con gli
altri sistemi); la classifica generale somma `total_points` pesati, copiati
in `Classification.total_position_points`.

### Sistema POSITION (gare a tabellone)

La posizione **si legge dal tabellone**, non si conta dalle vittorie: chi esce
allo stesso turno condivide la banda e quindi la posizione (due semifinalisti
entrambi 3°, quattro quartifinalisti tutti 5°). Il calcolo sta in
`bracket_standings.py` ed è usato da tre chiamanti — le due strategie e
`SpareggioService.apply_final_positions`, che è il percorso di produzione.

**Lo spareggio è spento per POSITION** (`SpareggioService.tiebreakers_apply_to`):
i pari merito sono l'esito voluto, non un'ambiguità da sciogliere. È una
divergenza deliberata dalla convenzione di `gara_strategies.py:36-46`, dove i
pari merito *devono* far scattare lo spot shot rally.

I punti di campionato stanno in `position_points.py`, con i valori della spec
come default e una tabella sovrascrivibile su `Campionato.position_points`. È
l'unica tabella: le altre due (10/7/5/4 della pagina, 1000/800/500 di una
strategia mai usata) sono state tolte con la classifica generale unica
(ADR-073).

```python
from models.classification.registry import get_classification_registry

registry = get_classification_registry()
strategy = registry.get("amalfi_round")
result = strategy.calculate(scores, previous_classification)  # scores: List[PlayerScore]
```

---

## Services

### Classifica generale del campionato: un calcolo solo (ADR-073)
- `TournamentStatisticsService.classifica_generale(campionato_id)` — **l'unico**
  posto in cui si calcola: somma le classifiche finali delle gare concluse
  (`SPECIFICHE.md` riga 292), pesate, con SSR e punti per piazzamento. La
  legge la pagina via `calculate_general_classification`.
- `ClassificationService.update_campionato_classification(campionato_id)` —
  ne scrive la **copia** nelle righe `Classification` (profilo, export, inviti
  ai playoff). Non è in cache: una funzione che scrive non si mette in cache.

Non esistono più strategie di campionato, né un aggregatore di campionato sulle
partite: una regola nuova della classifica generale si scrive in
`classifica_generale`, e basta.

### RoundClassificationService
- `calculate_and_save_round_classification(gara_id, round_number)` - For matchmaking
- `get_round_standings(gara_id, round_number)` - Query existing

### StrategyBasedClassificationService (Recommended)
- `calculate_round_classification(gara, round_number)` - Strategy-based
- `calculate_gara_classification(gara)` - Final gara standings
- Uses `ScoreAggregator` and `TiebreakerResolver`

---

## Tiebreaker Resolution: la catena (ADR-078)

Un motore solo, `ordinamento.py` (puro): criterio principale del sistema,
poi la **catena** applicata a gruppi. Le catene e gli scontri si leggono dalla
gara o dal campionato in `catene.py`. Tre classifiche, tre catene:

- **turno** (`round_strategies.py`): WINS differenza → posizione precedente →
  sorteggio; RACK posizione precedente → sorteggio. Ordine sempre completo.
  Lo SSR non c'è: si gioca a gara finita.
- **gara** (`SpareggioService.apply_final_positions` → `_fasce`, e
  `gara_strategies.py` per i ricalcoli): WINS differenza → SSR fino al N°;
  RACK SSR fino al N°. Chi resta pari condivide la posizione.
- **campionato** (`TournamentStatisticsService._sort_and_rank_players`):
  differenza (WINS) → SSR somma → posizione dopo la gara precedente →
  sorteggio. Ordine sempre completo.

Le catene **si configurano**: `Gara.catena_turno` / `Gara.catena_gara`
(NULL = come il campionato), proposte da `Campionato.default_catena_*`, più
`Campionato.catena_generale`. Liste JSON (`testo_della_catena`), lette **solo**
da `catene.py`. Lo spareggio è il criterio `ssr:N` della catena di gara: chi
chiede «fin dove?» usa `SpareggioService.ssr_fino_al(gara)`. La catena di turno
a gara avviata vale dal turno successivo: `catena_di_turno(gara, turno)` la
legge dalla storia. L'editor sta in `editor_catena.py` +
`components/_catena_spareggi.html`.

Il sorteggio è un hash del seme (`draw_seed` della gara, id del campionato):
mai l'id del giocatore. POSITION non passa dal motore (ADR-040).

**Posizione che decide e posizione mostrata** (2026-10-11, ADR-078
emendamento). `position` è l'ordine col sorteggio: decide abbinamenti,
inviti, punti. Chi è separato **solo** dal sorteggio è a pari merito e si
mostra alla posizione più alta: `shown_position` / `shown_group_position` /
`shown_previous_position` sulle righe, `posizione_mostrata(riga)` per
leggerle (ripiega su `position` sulle righe di prima). Una definizione sola,
`ordinamento.posizioni_mostrate`. Chi **mostra** una posizione legge quella
mostrata; chi **decide** legge `position`.

## Do Not

- **Do not use legacy static methods** - Prefer `StrategyBasedClassificationService`
- **Do not forget to calculate after round completion** - Matchmaking needs updated classification
- **Do not query PlayerEncounter without gara_id** - Always scope to gara
- **Do not call `db.session.commit()`** - Services use `@transactional`
- **Do not sort a WINS/RACK classification with your own key** - Use `ordinamento.ordina` (ADR-078)
- **Do not compute the campionato standings anywhere else** - `classifica_generale` is the only source; rows are its copy (ADR-073)

---

## Cross-References

- **Matchmaking**: [../matchmaking/CLAUDE.md](../matchmaking/CLAUDE.md) - Uses RoundClassification for pairing
- **Competition**: [../competition/CLAUDE.md](../competition/CLAUDE.md) - Gara completion triggers classification
- **Campionato**: [../campionato/](../campionato/) - Aggregated Classification

---

## Errori già commessi

Errori capitati davvero in questo dominio, con la strada giusta e il presidio che li tiene fermi.

| Errore | Strada giusta |
|--------|---------------|
| `campionato_type` per decidere **come si ordina** una classifica | `campionato.classification_system` (`ClassificationSystem`, ADR-047): il tipo dice come si formano le partite, il sistema su cosa si ordina. Sono scelte indipendenti e coincidono abbastanza spesso da rendere il bug invisibile per mesi (issue #89) |
| Sommare `rack_difference` e chiamarlo "triangoli totali" | `racks_won` è il totale, `rack_difference` la differenza (migration 20260728). Un totale negativo in classifica è la firma esatta di questo scambio |
| Dare per scontato che `rack_difference` in **produzione** sia sempre una differenza | Su ~400 righe storiche contiene ancora un totale: i dati non sono stati riparati **per scelta** (gare già premiate, nessuna schermata li legge con quel significato — ADR-047, sezione dedicata). Chi ci costruisce sopra qualcosa di nuovo — spareggio, statistica, export — lo trova |
| Sommare le partite di un campionato in un unico mucchio per fare la classifica | L'aggregazione è **per gara**, poi somma pesata su `Gara.classification_weight` (ADR-053): una gara può valere il doppio delle altre, e quella di playoff può valere **zero** quando è lei a decidere la classifica finale. Con tutti i pesi a 1 il risultato è quello di sempre |
| Ordinare una classifica a vittorie o a rack con un `sorted()` e una chiave scritta lì | Passa dal motore della catena (`ordinamento.ordina`, ADR-078): lo scontro diretto vale fra i soli pari e lo SSR solo fino al suo posto, e nessuna chiave lo esprime. Chi è pari per lo spareggio lo dice `SpareggioService._fasce`, una volta sola |
| Calcolare la classifica generale del campionato fuori da `classifica_generale` | Si calcola in **un posto solo**, `TournamentStatisticsService.classifica_generale` (ADR-073): somma le classifiche finali delle gare concluse, come dice `SPECIFICHE.md`, «Classifica». La pagina la legge via `calculate_general_classification`, le righe `Classification` (profilo, export, inviti ai playoff) ne sono la **copia** scritta da `update_campionato_classification`. Fino al 24/09/2026 le righe rifacevano i conti dalle partite con regole loro, e tre regole su tre sono vissute in un percorso solo: peso e playoff (#335), la zona playoff (#433), la X che negli inviti non contava — nel campionato 5 l'ottavo posto è andato al nono (#550). Presidio: `test_classifica_generale_una_sola.py` |
| Leggere le righe `Classification` per disegnare qualcosa **sopra la classifica in pagina** (zona playoff, evidenze) | Le righe sono ferme all'ultimo evento che le ha ricalcolate, la pagina calcola al volo: fino al 14/09/2026 la barra dei playoff segnava il 14º e saltava il 4º perché le righe erano ferme alla gara 1. Ciò che si disegna sulla classifica in pagina si calcola da quella (`models/playoff/zona.py`, `righe_della_classifica_in_pagina`); le righe le leggono solo profilo, export e `start_playoff`, che le ricalcola prima |
