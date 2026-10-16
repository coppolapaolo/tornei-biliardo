# Rating Domain

## Purpose

Rating Elo dei giocatori, calcolato a **rack** e aggiornato a partita conclusa.

**Core Responsibilities:**
- Tre pool di rating, uno per vista di certificazione (ADR-083)
- Registro dei delta applicati a ogni partita
- Regola unica su quali partite contano (`RatingEligibility`, ADR-049)
- Ricalcolo completo dei pool

Le **categorie** dei giocatori non vivono qui: sono per competizione, su
`Inscription.categoria_id`, in `models/categoria/` (ADR-049).

---

## Quick Reference

```python
from models.rating.models import RatingSystem, PlayerRating, MatchRatingHistory
from models.rating.calculation_service import RatingCalculationService
from models.rating.eligibility import RatingEligibility

# Conta per l'ELO? None = si'; altrimenti un RatingExclusion col motivo
motivo = RatingEligibility.exclusion_reason(match)

# In un ciclo: costruisci l'indice delle categorie una volta sola
index = RatingEligibility.build_index(matches)
motivo = RatingEligibility.exclusion_reason(match, index=index)

# Aggiornamento (di solito lo fa l'handler dell'evento, non il chiamante)
RatingCalculationService.process_match_result(match)
RatingCalculationService.process_individual_match_result(individual_match)
```

---

## Pool di rating (`RatingSystem`)

| Sistema | Partite | Uso |
|---|---|---|
| `ELO` | solo match di torneo — vista *Tornei* | competitivo; sincronizzato su `User.elo_rating` |
| `ELO_GLOBAL` | tornei + sfide confermate da entrambi — vista *Confermate* | solo display |
| `ELO_ALL` | anche le sfide firmate da uno solo — vista *Tutte* (ADR-083) | solo display |
| `INTERNAL` | — | rating interno di club |

Un match di torneo aggiorna i tre pool; una sfida individuale mai `ELO`.
Quali sfide entrano lo decide `models/certificazione.py`
(`sfida_conta_per_elo`: niente forfait, niente pareggi). Tutti i `process_*`
sono **idempotenti per pool**: se esiste gia' una riga di `MatchRatingHistory`
per quella partita e quel sistema, non fanno niente.

`ELO_GLOBAL` lo muove l'evento della seconda firma. `ELO_ALL` lo segue
l'ascoltatore di sessione `elo_tutte.py`: una sfida entra alla prima firma, ed
esce — con un ricalcolo da zero del solo pool, perche' l'ELO dipende
dall'ordine — quando perde le firme o finisce in forfait.

Chi cambia i fatti sotto l'ELO (unione di account, riassegnazione, categorie
corrette) chiama `recalculate_all_pools()`, mai un pool solo.

---

## Models

- **`PlayerRating`**: `user_id`, `rating_system`, `rating_value`, `confidence`,
  `robustness` (rack giocati, non partite), `last_updated`, `external_id`,
  `verified`.
- **`MatchRatingHistory`**: un delta per (partita, giocatore, sistema) —
  `match_id` o `individual_match_id`, `old_rating`, `new_rating`, `delta`,
  `robustness_increment`.

---

## Il motore (`rack_engine.py`, ADR-052)

`ΔR = k · (vinti − attesi)` sui **rack**, non sull'esito: un 7–0 e un 7–6
muovono i rating in modo diverso. Scala di FargoRate (100 punti), partenza
`rack_engine.PARTENZA`. Il motore non conosce il database: lo usa
`RatingCalculationService`.

---

## Quali partite contano (`eligibility.py`, ADR-049)

`RatingEligibility.exclusion_reason` restituisce il **motivo**
(`RatingExclusion`: `WALKOVER`, `HANDICAP_CATEGORY_MISSING`,
`HANDICAP_DIFFERENT_CATEGORY`, `PROVA`) o `None`. Con l'handicap l'ELO si
muove solo fra giocatori della **stessa categoria**; l'handicap da solo non
esclude. `counts_for_rating` e' la forma booleana.

Handler (`RatingEventHandlers`), ricalcoli e `scripts/diagnose_elo.py` passano
tutti da qui: `process_match_result` **non** rilegge la regola, quindi chi lo
chiama deve aver gia' escluso le partite che non contano.

---

## Do Not

- **Do not decide ELO eligibility with your own `if`** (es. `effective_has_handicap`) - Use `RatingEligibility`
- **Do not look for categories here or on `User`** - They live on `Inscription.categoria_id` (`models/categoria/`)
- **Do not call `db.session.commit()`** - `RatingCalculationService` does not commit: the caller owns the transaction (`@transactional`)
- **Do not recompute a single pool after changing the facts** - `recalculate_all_pools()`: the others would stay behind
- **Do not decide which individual matches count with your own filter** - `models/certificazione.py` (ADR-083)

---

## Cross-References

- **Categorie**: `models/categoria/`
- **Events**: `RatingEventHandlers` in `event_handlers.py` (`MatchCompletedEvent`, `IndividualMatchCompletedEvent`)
- **ADR**: `docs/adr/ADR-049-same-category-restores-elo-in-handicap-events.md`, `docs/adr/ADR-052-rating-model-decided-by-measurement.md`
