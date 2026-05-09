# ADR-027 Round-Level Configuration: Persistenza ed Enforcement

**Data**: 2026-05-09
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Il template `templates/components/_round_management.html` esponeva una UI
"Configurazione per Turno" che permetteva al director, in stato `setup`, di
sovrascrivere disciplina e distanza per ogni singolo turno della gara. La nota
in fondo al pannello recitava:

> "Le configurazioni vengono salvate e applicate automaticamente quando ogni
> turno viene avviato."

In realtà il backend ignorava completamente questi valori:

1. Il JS della UI salvava la configurazione **solo in `localStorage` del
   browser** (riga `localStorage.setItem(...)`); nessuna chiamata fetch
   verso il server.
2. Il modello `RoundConfiguration` esisteva (`models/competition/round_configuration.py`),
   ma `grep RoundConfiguration routes/` restituiva zero risultati: nessun
   endpoint lo popolava. Il record in DB era sempre vuoto.
3. `RoundCreationService._create_round_impl` leggeva `RoundConfiguration` per
   l'override di `distance` e `discipline`, ma non leggeva `is_race_to`,
   `is_multi_set`, `match_distance`, `is_race_to_sets`. Quindi anche se la
   persistenza avesse funzionato, l'override della modalità (race-to vs
   esatto) sarebbe stato silentemente perso.
4. Lo scoring layer (`models/match/scoring_service.py`,
   `models/match/rack_service.py`, `models/classification/score_aggregator.py`,
   `models/match/models.py::is_at_distance`) leggeva direttamente
   `match.gara.distance` / `match.gara.is_race_to` invece di
   `match.distance_config`. Il VO `Distance` esisteva ma 7 call site lo
   bypassavano.

Sintomo in produzione (gara dell'utente, maggio 2026):

> "Creo gara standalone, 4 turni, palla 9, 5 rack esatti, amalfi. Modifico
> turno 2 e 4 a palla 8 con 4 rack esatti. Apro iscrizioni, avvio gara con
> 10 giocatori. L'interfaccia chiede 5 rack ma il backend chiude i match a
> 4. Tutti i match risultano 'Completata' ma l'avvio del turno 2 dà
> 'Completa prima tutte le partite del turno 1'."

La discrepanza nasceva dall'inconsistenza tra (a) i valori usati per chiudere
i match (presi via `match.match_distance`, popolato dal round-creation con la
gara) e (b) i valori usati per validare il completamento del round (presi
via altri path che usavano `match.gara.distance`). Quando il backfill
implicito fra le due strade si rompe, si ottengono match "completi" che il
sistema non riconosce come tali.

## Decisione

Tre cambiamenti coordinati:

### 1. Persistenza server-side via API

Aggiunti tre endpoint in `routes/admin/competition/rounds.py`:

- `GET /admin/gara/<id>/round-config` — lista override + defaults della gara
- `POST /admin/gara/<id>/round-config/<n>` — upsert (JSON body)
- `DELETE /admin/gara/<id>/round-config/<n>` — rimuovi override

Vincoli:

- Auth: `@gara_manager_required` (director della gara o admin)
- Stato: solo `setup`. Fuori da setup → 409 Conflict
- Round number nel range `[1, gara.rounds_count]`

Il template `_round_management.html` chiama gli endpoint via `fetch` su
`change`, e cancella il `localStorage` legacy delle installazioni precedenti
per pulizia.

### 2. Schema esteso per esprimere ogni override

Migration `migrations/20260509_round_overrides_full.py`:

- Aggiunge a `match`: `is_race_to`, `is_race_to_sets` (Boolean nullable)
- Aggiunge a `round_configuration`: `is_race_to`, `is_multi_set`,
  `match_distance`, `is_race_to_sets`
- Migra `round_configuration.best_of` (deprecated) → `is_race_to`
- Backfill: per i match single-set legacy con `match_distance=1`/NULL, li
  uniforma a `gara.distance`. Risolve la "legacy heuristic" in
  `Distance.from_match`.

Convenzione: NULL su un override significa "eredita dal default della gara".
Le property `Match.effective_*` (`effective_distance`, `effective_is_race_to`,
`effective_is_race_to_sets`) materializzano il fallback in un solo punto.

### 3. `Distance` VO usato ovunque per il scoring

Tutti i call site che leggevano `match.gara.distance` o `match.gara.is_race_to`
sono stati riscritti per usare `match.distance_config` o le property
`effective_*`. I siti coinvolti:

- `models/match/scoring_service.py`: `_should_clear_winner`,
  `_validate_score_limits`, `_validate_rack_addition`, `_calculate_result`
- `models/match/rack_service.py`: `remove_rack_with_score_update`
- `models/match/models.py`: `Match.is_at_distance`, `TrioMatch.trio_config`
- `models/classification/score_aggregator.py`: `_process_trio_match`
- `models/player/history_service.py`: trio rack accounting

`Distance.from_match` legge tutto da `match.effective_*`, eliminando la
heuristic ugly basata su `match_distance > 1`.

### 4. Round creation propaga TUTTI gli override

Nuovo helper `resolve_round_overrides(gara, round_number)` in
`models/competition/round_creation.py` centralizza la risoluzione
RoundConfiguration → kwargs. `_create_round_impl` (per amalfi/round-robin),
`RoundService.start_first_round` (per random multi-round) e
`create_matches_from_pairings` ne usano lo stesso output, evitando
duplicazione e drift.

## Alternative Considerate

### Alternativa 1: Rimuovere la UI "Configurazione per Turno"

**Descrizione**: Cancellare il template, il modello `RoundConfiguration`, e i
ref in `_create_round_impl`. Lasciare solo configurazione gara-level.

- **Pro**: drasticamente semplice. Riduce surface area
- **Contro**: rimuove una feature che il director ragionevolmente si aspetta
  (cambiare disciplina/distanza tra turni di un campionato in fasi diverse).
  L'utente l'ha chiesta e usata in produzione

### Alternativa 2: Salvare solo distanza, non modalità (race-to/exact)

**Descrizione**: Estendere RoundConfiguration solo con `match_distance` e
discipline (già fatto), lasciare `is_race_to` solo gara-level.

- **Pro**: schema minimal
- **Contro**: cambiare modalità per turno è proprio il caso del bug originale.
  L'utente voleva 5 rack esatti su turno 1 e 4 rack esatti su turno 2.
  Senza override di `is_race_to`, questo non si esprime

### Alternativa 3: Sostituire `match.match_distance` polisemico con due colonne separate

**Descrizione**: Aggiungere `match.racks_distance` (single-set) e mantenere
`match.match_distance` solo per multi-set count di set. Più pulito
semanticamente.

- **Pro**: schema più parlante
- **Contro**: cambia molti test e siti consumer. Lo schema migrato in
  produzione era ancora coerente; il backfill della migration risolve la
  heuristic ugly senza dover rinominare campi. Rinviato a refactor futuro

## Conseguenze

### Positive

- La UI mantiene la promessa: gli override per turno hanno effetto reale
- `Distance` VO è effettivamente usato come single source of truth
- Schema additivo, retrocompatibile: NULL = "nessun override" è lessicalmente
  esplicito
- Nessun caso d'uso precedente è impattato: tutti i match esistenti senza
  override continuano a funzionare con la distanza della gara
- Backfill automatico unifica i match legacy con `match_distance=1`

### Negative

- 4 nuove colonne nullable su 2 tabelle. Costo storage trascurabile
- Manteniamo temporaneamente `RoundConfiguration.best_of` come dead column
  per compat schema (la migration ne ha già travasato i valori)

### Rischi

- I match già giocati in produzione sotto il bug rimangono inconsistenti.
  Il fix non fa retrofit di partite esistenti: il director deve
  manualmente resettare/cancellare la gara compromessa
- Se un altro layer (es. notification, gamification) leggeva
  `match.gara.distance` direttamente, può esserci ancora drift. Mitigato
  dal grep esaustivo fatto in fase di refactor

## Note Implementative

### Pattern: NULL = eredita

```python
# Match column
is_race_to = db.Column(db.Boolean, nullable=True)

# Risoluzione centralizzata via property
@property
def effective_is_race_to(self) -> bool:
    if self.is_race_to is not None:
        return self.is_race_to
    return self.gara.is_race_to if self.gara else True
```

Solo le property `effective_*` (e `Distance.from_match`, fallback nel VO)
sono autorizzate a leggere direttamente da `self.gara`. Tutto il resto del
codice deve usare `match.distance_config` o `match.effective_*`.

### Endpoint contract

```
POST /admin/gara/123/round-config/2
Content-Type: application/json
Body:
{
  "discipline": "palla_8",
  "distance": 4,
  "is_race_to": false,
  "is_multi_set": false,
  "match_distance": null,
  "is_race_to_sets": null
}

200 OK
{ "success": true, "config": { "round_number": 2, ... } }

409 Conflict (gara non in setup)
{ "success": false, "error": "..." }
```

### Test di regressione

`tests/new/integration/test_round_overrides_adr027.py`:

- `test_round_creation_propagates_override_to_match`: setup gara exact-5,
  override turno 2 a exact-4, verifica che match round 1 ha
  `match_distance=5` e match round 2 ha `match_distance=4`
- `test_scoring_respects_round_override`: il match con override exact-4
  accetta 2-2 (totale 4) come complete, rifiuta 3-2 (totale 5)
- `test_post_blocked_outside_setup`: ritorna 409 dopo apertura iscrizioni
- + GET / POST / DELETE happy path

## Riferimenti

- Migration: `migrations/20260509_round_overrides_full.py`
- Test: `tests/new/integration/test_round_overrides_adr027.py`
- Endpoint: `routes/admin/competition/rounds.py` (in fondo)
- Helper: `models/competition/round_creation.py::resolve_round_overrides`
- Property: `models/match/models.py::Match.effective_*`
