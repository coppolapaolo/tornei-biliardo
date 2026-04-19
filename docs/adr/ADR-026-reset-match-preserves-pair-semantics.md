# ADR-026 Reset Match Preserves Pair Semantics

**Data**: 2026-04-19
**Stato**: Accepted — Supersedes in part [ADR-002](ADR-002-fix-anti-rematch-encounter-cleanup.md) (la parte `reset_match_complete`; la parte `cancel_round` di ADR-002 resta valida)
**Decisori**: Paolo Coppola (product owner), interview + code review sessione 2026-04-19

---

## Contesto

Durante la review adversariale della strategia **Random Anti-Rematch** (2026-04-19, commit `38fc050`) era stato segnalato il gap **G3**:

> *"Reset match in gara Random non libera il pair anti-rematch. `RackService.reset_match_complete` elimina `PlayerEncounter` ma mantiene il `Match` → Random vede ancora il pair come incontrato."*

L'handoff `_bmad-output/handoffs/random-next-steps.md` proponeva tre opzioni correttive: (a) eliminare il `Match` al reset, (b) aggiungere una colonna `Match.is_reset`, (c) rigenerare automaticamente i round successivi.

Un'indagine più attenta, condotta tramite interview con il product owner, ha capovolto il quadro: **G3 non è un bug**. Il comportamento di Random (pair preservato via `Match.query`) è semanticamente corretto. Il difetto è nel lato opposto del data source ibrido: la cancellazione di `PlayerEncounter` al reset, formalizzata da [ADR-002](ADR-002-fix-anti-rematch-encounter-cleanup.md).

### Semantica del `reset_match_complete` confermata

Il **product owner ha confermato** che l'intent del director quando esegue il reset è **esclusivamente** la correzione di uno score inserito erroneamente:

> *"Il vero intento del director con reset è solo correzione punteggio. I pair vengono annullati solo quando si annulla il turno o l'avvio del match."*

Conseguenza: **il pair di un match resettato deve restare contrassegnato come "incontrato"** in tutti i data source utilizzati dall'anti-rematch, perché gli stessi due giocatori torneranno a giocare lo stesso match.

### Fatti verificati che rendono la cleanup attuale superflua e dannosa

1. **`PlayerEncounter.record_encounter` è idempotente** ([models/classification/models.py:501-509](../../models/classification/models.py)): se l'encounter esiste già, ritorna l'esistente senza creare duplicati. Il ri-complete del match non causa né crash né violazione del `UNIQUE` constraint, anche senza cleanup preventiva.

2. **`AdvancedRoundManager.cancel_round` ha una cleanup autonoma** ([round_manager.py:221-223](../../models/competition/round_manager.py)) che chiama direttamente `PlayerEncounter.delete_round_encounters(gara_id, round_number)`. Il flow cancel non dipende in alcun modo dalla cleanup dentro `reset_match_complete`.

3. **`cancel_round` blocca l'esecuzione se esistono match con risultati parziali** ([round_manager.py:196-206](../../models/competition/round_manager.py)): il director deve resettare i match prima di cancellare il round. Anche se il reset smette di pulire encounter, il successivo `cancel_round` li eliminerà comunque tramite la propria cleanup.

4. **`Gara.can_start_new_round` blocca l'avanzamento di round in presenza di match non completati** ([models/competition/models.py:319-337](../../models/competition/models.py)): il reset riporta il match a `PENDING`/`PLAYING`, quindi nessun round successivo può partire nell'intervallo tra reset e ri-completamento. Lo scenario "Amalfi genera round N+1 con encounter stale" è impossibile.

5. **Random crea tutti i round all-startup** e non rigenera i round futuri dopo operazioni sul round corrente. Lo scenario "Random rigenera e vede encounter stale" è parimenti impossibile.

6. **La cleanup attuale è inesistente per i trio match**: per un trio match, `reset_match_complete` (rack_service.py:117-120) delega a `TrioScoringService.reset` e **ritorna early**, bypassando completamente il blocco `delete_encounter` (righe 127-135). Tuttavia il flow di completamento trio registra 3 encounter (le 3 coppie del trio) via `PlayerEncounterService.record_match_encounters`. Risultato: con il codice attuale, per trio **0 di 3 encounter vengono cancellati al reset** — comportamento de facto coerente con la semantica corretta (preservare pair), ma ottenuto per omissione più che per design. Con il fix questo diventa esplicito e uniforme.

### Bug latente in `cancel_round` esposto dal fix (scope esteso)

Durante l'implementazione è emerso che `AdvancedRoundManager.cancel_round`
aveva una precondition errata: bloccava il cancel se un match del round aveva
`player1_score is not None or player2_score is not None`. Dopo `reset_match_complete`,
gli score vengono azzerati a `0` (non `None`), quindi `0 is not None == True`
→ cancel_round fallisce silenziosamente dopo ogni reset.

Il test di regressione `test_encounter_cleanup_on_round_cancel` passava
**accidentalmente** perché la cleanup di `PlayerEncounter` nel reset
(quella rimossa da questo ADR) faceva il lavoro che `cancel_round` non
riusciva a compiere: gli encounter risultavano già eliminati quando il
test verificava l'assertion finale. Il test non controllava il valore di
ritorno di `cancel_round`, quindi il fallimento silenzioso non veniva
intercettato.

Rimuovendo la cleanup nel reset (decisione principale di questo ADR),
il bug latente emerge: `cancel_round` fallisce sempre dopo reset, e
gli encounter non vengono più rimossi.

**Fix in scope esteso:** la precondition "match ha risultati parziali"
diventa `(score or 0) > 0`. Questa versione tratta sia `None` sia `0`
come "nessun risultato": `None` per match mai giocati, `0` per match
resettati (ADR-026). Score > 0 significa "almeno un rack vinto" — questo
è il vero indicatore di "risultato parziale".

### Finestra di inconsistenza aperta dalla cleanup attuale

Tra il momento del reset e il ri-completamento del match (il tempo che il director impiega a reinserire lo score corretto), i due data source si disallineano:

- `Match.query`: il match con il pair `(A, B)` esiste ancora (status `PENDING`/`PLAYING`) → pair "incontrato" ✓
- `PlayerEncounter.have_played(A, B)`: ritorna `False` → pair "mai incontrato" ✗

Questa finestra non causa un bug osservabile nelle strategie correnti (per i motivi 4 e 5 di cui sopra), ma costituisce un'inconsistenza dello stato del sistema che viola il principio "single source of truth" e rende fragile ogni futuro consumer dell'anti-rematch.

---

## Decisione

1. **Rimuovere** la chiamata a `PlayerEncounter.delete_encounter` da `RackService.reset_match_complete` (righe 127-135 di [models/match/rack_service.py](../../models/match/rack_service.py)), incluso il commento inline che la giustifica.

2. **Rimuovere** il metodo `PlayerEncounter.delete_encounter` dalla classe in [models/classification/models.py](../../models/classification/models.py) (righe 521-546). Dopo la modifica al reset, il metodo diventa dead code: nessun altro caller lo invoca.

3. **Invertire l'assertion** del test `test_encounter_cleanup_on_match_reset` ([tests/new/unit/test_anti_rematch_regression.py:549-655](../../tests/new/unit/test_anti_rematch_regression.py)). Rinominare in `test_contract_reset_preserves_encounter` per segnalare che enforza un **contratto** (comportamento atteso by design), non un bug fix di regressione.

4. **Mantenere invariata** la cleanup dentro `AdvancedRoundManager.cancel_round` ([round_manager.py:221-223](../../models/competition/round_manager.py)) che usa `PlayerEncounter.delete_round_encounters`. La semantica di `cancel_round` è diversa e per quel flow la cleanup è corretta e necessaria.

5. **Chiudere il gap G3** nell'handoff `_bmad-output/handoffs/random-next-steps.md` come misdiagnosi risolta.

6. **Annotare ADR-002** come "superseded in part" da questo ADR, limitatamente alla decisione su `reset_match_complete`.

7. **Fixare la precondition di `AdvancedRoundManager.cancel_round`** (scope esteso emerso in implementazione): cambiare il check da `m.player1_score is not None or m.player2_score is not None` a `(m.player1_score or 0) > 0 or (m.player2_score or 0) > 0`. Solo score > 0 costituisce "risultato parziale"; sia `None` sia `0` rappresentano "nessun risultato" (`None` = mai giocato, `0` = resettato). Senza questo fix, `cancel_round` fallirebbe sempre dopo un reset — il bug era mascherato dalla cleanup di `PlayerEncounter` nel reset, che faceva da workaround silente.

---

## Alternative Considerate

### Alternativa (a): Eliminare il `Match` al reset

**Descrizione**: trasformare `reset_match_complete` in `delete Match` con cascade su tabelle figlie, più migrazione del FK `tiebreaker.match_id` (attualmente senza cascade) a `ON DELETE SET NULL` o `CASCADE`.

- **Pro**:
  - Elimina davvero il data source fantasma: un solo contratto ("match esiste ⟺ pair pertinente")
  - Allinea la semantica di reset a quella di `cancel_round`
- **Contro**:
  - **Rompe la semantica attuale del reset** (correzione score, pair preservato) trasformando il reset in un'operazione di annullamento — contrario all'intent confermato dal product owner
  - Richiede migrazione schema del FK `tiebreaker.match_id`
  - Perdita audit trail senza mitigazione via domain event
  - Il director che voleva correggere uno score si ritrova senza il match da rigiocare

**Scartata**: in contrasto diretto con l'intent del reset.

### Alternativa (b): Flag `Match.is_reset`

**Descrizione**: aggiungere colonna booleana a `Match` e far filtrare Random su `is_reset=False`, senza toccare la cleanup di `PlayerEncounter`.

- **Pro**:
  - Minima invasività apparente, 1 solo consumer da modificare
- **Contro**:
  - **Codifica nello schema un'operazione ("reset") senza toccare la causa del bug** (asimmetria dei data source)
  - Aggiunge debito permanente: ogni futuro consumer di `Match.query` per logica anti-rematch dovrà ricordarsi del flag (stesso anti-pattern di `is_deleted` denunciato in `CLAUDE.md`)
  - Non risolve l'incompletezza trio né la finestra di inconsistenza

**Scartata**: pezza semantica, non risolve la causa radice.

### Alternativa (c): Rigenerare automaticamente i round successivi al reset

**Descrizione**: trasformare il reset in un rollback cascade che elimina e rigenera tutti i round successivi.

- **Pro**:
  - Semanticamente forte ("reset = rollback completo")
- **Contro**:
  - UX complessa (dialog di conferma obbligatorio)
  - Il director che voleva solo correggere uno score perde tutti gli abbinamenti già visti
  - Transazione complessa con cascade potenzialmente ampio
  - Contrario all'intent del reset confermato

**Scartata**: UX pesante per risolvere un'inconsistenza di dati.

### Alternativa (d) - scelta: Rimuovere la cleanup da `reset_match_complete`

**Descrizione**: il reset non tocca `PlayerEncounter`. L'encounter viene cancellato solo da `cancel_round` (via cleanup autonoma preesistente).

- **Pro**:
  - Allinea entrambi i data source alla semantica confermata (pair preservato)
  - Rimuove codice (dead code elimination), non aggiunge
  - Risolve collateralmente l'incompletezza trio
  - Chiude la finestra di inconsistenza
  - Zero migrazioni schema
- **Contro**:
  - Richiede inversione di un test di regressione esistente
  - ADR-002 va annotato come parzialmente superato

**Scelta**: l'unica opzione che risolve la causa radice (asimmetria semantica tra reset e cancel codificata in ADR-002) anziché gestirne i sintomi.

---

## Conseguenze

### Positive

- **Un solo contratto per l'anti-rematch dopo reset**: entrambi i data source (`Match.query` e `PlayerEncounter`) concordano che il pair resta "incontrato"
- **Eliminazione di dead code**: 3 righe di chiamata + 26 righe di metodo rimossi
- **Comportamento trio allineato esplicitamente**: il reset trio, che già preservava gli encounter per omissione (early-return bypassava il blocco cleanup), ora ha lo stesso contratto semantico del reset 2-player — entrambi preservano by design
- **Finestra di inconsistenza chiusa**: nessun intervallo in cui i data source divergono
- **`cancel_round` funziona davvero**: la precondition corretta (score > 0 = risultato parziale) permette di cancellare round con match resettati, eliminando un bug latente nascosto per mesi dietro il workaround della cleanup nel reset
- **Documentazione operazioni di lifecycle** (vedi "Operations glossary" sotto) estraibile in `CLAUDE.md` — un punto di riferimento canonico che mancava e la cui assenza è la causa prima di questa confusione
- **Test con naming più onesto**: `test_contract_*` segnala un contratto user-facing, distinto dai `test_regression_*` che proteggono contro ricomparsa di bug

### Negative

- **ADR-002 va annotato come superseded in part**: il lettore di ADR-002 deve essere indirizzato a questo ADR per la parte `reset_match_complete`
- **Test invertito** `test_encounter_cleanup_on_match_reset` → `test_contract_reset_preserves_encounter`: il commit che applica la decisione cambia l'intent del test, non solo l'implementazione

### Rischi (verificati nulli)

Ciascuno di questi rischi è stato verificato tramite codice e ispezione:

- ✅ **Ri-complete crash per duplicato**: non avviene, `record_encounter` è idempotente (classification/models.py:501-509)
- ✅ **cancel_round perde la cleanup**: non avviene, `cancel_round` ha la propria (round_manager.py:221-223)
- ✅ **Amalfi vede encounter stale e ri-paira il pair**: non avviene, `can_start_new_round` blocca l'avvio del round successivo (models.py:319-337)
- ✅ **Random rigenera round con encounter stale**: non avviene, Random crea round all-startup e non rigenera
- ✅ **`bulk_reset_round_matches` ha un flow peculiare**: verificato, delega a `reset_match_with_validation` → `RackService.reset_match_complete`. Dopo la modifica continua a funzionare (il cancel_round seguente o il ri-complete gestiscono lo stato)

---

## Previous Assumption Debunked

Questa sezione documenta esplicitamente come e perché [ADR-002](ADR-002-fix-anti-rematch-encounter-cleanup.md) sia arrivato alla conclusione sbagliata sul reset, in modo che il pattern sia riconoscibile in futuro.

### L'errore di ADR-002

ADR-002 (2025-12-28) ha codificato come "comportamento atteso":

> *"Se un match viene resettato o un round cancellato, i giocatori devono poter essere nuovamente abbinati."*

Questa affermazione **unifica reset_match e cancel_round** sotto la stessa categoria ("operazioni che liberano il pair"), assumendo che entrambe abbiano la medesima semantica di annullamento. L'assunzione non è stata validata con il product owner: l'ADR non cita alcuna user story né discute l'intent del director nei due flow.

### Perché l'errore è passato inosservato

1. **Nessun glossario delle operazioni di lifecycle**: non esisteva (e non esiste tuttora, fino a questo ADR) una definizione canonica di "reset" vs "cancel" vs "bulk reset". Il lettore dell'ADR non aveva un riferimento per contestare l'unificazione.

2. **Il test di regressione ha cristallizzato l'errore**: una volta scritto `test_encounter_cleanup_on_match_reset` con l'assertion sbagliata, il comportamento enforced da quel test è diventato "la verità" per tutti gli sviluppatori successivi. I test enforzano specs: una spec sbagliata produce test sbagliati che poi difendono lo sbaglio.

3. **L'handoff della review Random ha ereditato l'asserzione**: il gap G3 è stato formulato come "Random non libera il pair = bug" senza notare che la premessa ("il pair DEVE essere liberato al reset") veniva direttamente da ADR-002 ed era mai stata verificata. Gli handoff mescolavano **fatti osservati** e **asserzioni ereditate** senza distinguerli.

4. **Il data source ibrido ha amplificato la confusione**: quando la review 2026-04-19 ha scoperto che Random doveva leggere da `Match.query` per ragioni di tempistica (round creati all-startup), la discrepanza tra "reset pulisce encounter" e "reset non pulisce Match" è apparsa come un bug **di Random**, non come un bug **di ADR-002**. Il colpevole sbagliato.

### Lezioni per future ADR

- Ogni ADR che introduce un comportamento user-facing deve citare **l'user story** che lo motiva e l'intent confermato con il product owner. ADR-002 non lo faceva.
- Quando due operazioni appaiono "simili" e vengono trattate uniformemente, validare che siano **davvero** la stessa operazione semanticamente. In questo caso bastava un'interview mirata.
- I test di regressione che enforzano un **contratto** (comportamento atteso) vanno nominati diversamente dai test che enforzano **un bug fix**. Un naming come `test_contract_<operation>_<property>` vs `test_regression_<bug_id>` rende i primi candidati a rivalutazione quando il contratto cambia.
- Gli handoff dovrebbero separare **fatti verificati** da **asserzioni ereditate**, costringendo il contributore successivo a validare le seconde prima di agire.

---

## Operations Glossary

Definizioni canoniche delle operazioni di lifecycle dei match. **Questa sezione è candidata all'estrazione in `CLAUDE.md` come riferimento principale**: ogni futuro ADR o spec che parla di queste operazioni deve linkare qui invece di ridefinirle.

### `reset_match_complete` (single-match reset)

**Intent del director**: *"Ho inserito uno score sbagliato, voglio correggerlo rigiocando gli stessi rack con gli stessi giocatori."*

**Semantica**:
- Il `Match` esiste prima e dopo il reset (stesso `id`, `round_number`, `player1_id`, `player2_id`)
- Gli `Rack` (e eventuali `Set` multi-set) vengono eliminati
- Per i trio match, delega a `TrioScoringService.reset` che azzera i `TrioRack` e lo stato trio
- Scores azzerati, `winner_id` → None, conferme bilaterali azzerate
- Status torna a `PLAYING` (se ha tavolo assegnato) o `PENDING` (altrimenti)
- **`PlayerEncounter` PRESERVATO** (dopo questo ADR): il pair resta "incontrato" by design, i due giocatori sono ancora accoppiati per quel match
- Forfeit flag su `Inscription` azzerati per consentire il rigioco

**Blocchi operativi**:
- `RoundLockStatus.LOCKED` se la strategia supporta round locking e un round successivo è attivo (`can_modify_match` via `reset_match_with_validation`)
- Non può resettare un match bye (`raise ValueError("Non puoi resettare una partita bye!")`)
- **Gara con tiebreaker attivo** (stato != `CANCELLED`): lo SSR certifica implicitamente i risultati della gara, quindi `can_modify_match` blocca il reset finché il director non annulla lo spareggio. Scope del blocco: tutti i match della gara (non solo dei giocatori in parità). Nessun override admin. Spec: `_bmad-output/implementation-artifacts/spec-reset-blocked-by-tiebreaker.md`. Residuo originario in ADR-026 §Operations Glossary ("Tiebreaker rows sopravvivono al reset") risolto riqualificando il framing: non si cancellano o rigenerano tiebreaker al reset — si impedisce il reset.

**Caller**: `RackService.reset_match_complete` → invocato da `routes/admin/match/scoring.py:reset_match`, da `routes/admin/competition/rounds.py:reset_match_advanced`, e da `AdvancedRoundManager.reset_match_with_validation` (che aggiunge validazione lock + aggiornamento classifiche + progressione round).

### `bulk_reset_round_matches` (bulk reset)

**Intent del director**: *"Voglio resettare in massa tutti i match di un turno ancora in gara, tipicamente per poi annullare il turno."*

**Semantica**:
- Delega a `AdvancedRoundManager.reset_match_with_validation` per ciascun match completato del round
- **Ogni singolo match reset** segue la semantica di `reset_match_complete` (pair preservato)
- Errori parziali vengono raccolti e riportati (rollback del savepoint per-match, continuazione sugli altri)
- Aggiorna la progressione del round dopo il reset massivo

**Caller**: `AdvancedRoundManager.bulk_reset_round_matches` → tipicamente invocato come precondizione per `cancel_round` (che richiede match senza risultati parziali).

### `cancel_round` (round cancellation)

**Intent del director**: *"Voglio annullare l'intero turno. I pair potrebbero essere ri-generati diversamente al prossimo avvio."*

**Semantica**:
- **Precondizione**: nessun match del round può avere risultati parziali (deve essere stato fatto `bulk_reset_round_matches` prima, se necessario)
- **Solo round corrente o successivi** possono essere cancellati
- Tutti i `Match` del round vengono **eliminati** (`db.session.delete`)
- Tutti gli `Rack` associati vengono eliminati (bulk `.delete()`)
- Le `RoundClassification` del round vengono eliminate
- **Tutti i `PlayerEncounter` del round vengono eliminati** via `PlayerEncounter.delete_round_encounters(gara_id, round_number)` — **questa cleanup resta valida e necessaria** perché, a differenza del reset, il cancel libera davvero i pair che possono essere ri-abbinati diversamente al prossimo avvio del round
- `gara.current_round` decrementato (torna a `INSCRIPTION` se era il primo round)

**Caller**: `AdvancedRoundManager.cancel_round` → `routes/admin/competition/rounds.py:cancel_round_advanced`.

### Tabella riassuntiva

| Operazione | `Match` | `Rack` | `PlayerEncounter` | Pair semantics |
|---|---|---|---|---|
| `reset_match_complete` | preservato | eliminato | **preservato** | stessi due rigiocano |
| `bulk_reset_round_matches` | preservato (tutti) | eliminato (tutti) | **preservato** (tutti) | stessi pair del round rigiocano |
| `cancel_round` | **eliminato** | eliminato | **eliminato** | pair liberati, ri-generabili |

---

## G3 — Closure Note

Il gap **G3** tracciato in `_bmad-output/handoffs/random-next-steps.md` come *"Reset match in gara Random non libera il pair anti-rematch"* è dichiarato **misdiagnosi**. Il comportamento di Random (pair preservato via `Match.query` dopo reset) non è un bug ma l'implementazione semanticamente corretta del contratto del reset.

L'handoff va aggiornato per segnalare che il lavoro residuo non è su Random ma sul lato `PlayerEncounter` del data source ibrido, e che la correzione è fatta da questo ADR (implementazione via `bmad-quick-dev`).

---

## Note Implementative

File da modificare nell'implementazione che seguirà questo ADR:

1. **`models/match/rack_service.py`** (righe 127-135): rimuovere il blocco di chiamata `delete_encounter` e il commento inline `"Delete PlayerEncounter to maintain anti-rematch consistency"` — anche il docstring della funzione alle righe 102-104 va aggiornato (rimuovere il paragrafo `"IMPORTANT: Also deletes the PlayerEncounter..."`).

2. **`models/classification/models.py`** (righe 521-546): rimuovere il metodo `PlayerEncounter.delete_encounter` (dead code).

3. **`tests/new/unit/test_anti_rematch_regression.py`** (righe 549-655): rinominare il test in `test_contract_reset_preserves_encounter`, invertire l'assertion finale (da `assert not PlayerEncounter.have_played(...)` a `assert PlayerEncounter.have_played(...)`), aggiornare docstring per riflettere il contratto atteso. Il docstring dovrebbe linkare a questo ADR.

4. **`docs/adr/ADR-002-fix-anti-rematch-encounter-cleanup.md`**: aggiungere banner "**Stato**: Accepted (superseded in part by [ADR-026](ADR-026-reset-match-preserves-pair-semantics.md) per la parte `reset_match_complete`; la parte `cancel_round` resta valida)".

5. **`_bmad-output/handoffs/random-next-steps.md`**: marcare G3 come `resolved (misdiagnosis)` con link a questo ADR.

6. **`_bmad-output/implementation-artifacts/spec-random-anti-rematch.md`**: rimuovere la nota "Limitation documentata: reset match + Random" (righe 192-196 circa) — non è più una limitazione perché il comportamento descritto è quello corretto.

7. **`CLAUDE.md`** o **`models/competition/CLAUDE.md`**: estrarre la sezione "Operations glossary" di questo ADR come riferimento canonico, con link di ritorno all'ADR per il razionale.

8. **`models/competition/round_manager.py`** (scope esteso): aggiornare la precondition di `cancel_round` (righe ~195-200) da `m.player1_score is not None or m.player2_score is not None` a `(m.player1_score or 0) > 0 or (m.player2_score or 0) > 0`. Aggiungere commento inline che cita ADR-026 e la motivazione (None = mai giocato, 0 = resettato, >0 = risultato parziale).

### Esempio della modifica a `rack_service.py`

```python
# PRIMA (righe 127-135 da rimuovere):
# Delete PlayerEncounter to maintain anti-rematch consistency
# This ensures players can be paired again after match reset
if match.player2_id:  # Only for non-bye matches
    from models.classification.models import PlayerEncounter
    PlayerEncounter.delete_encounter(
        gara_id=match.gara_id,
        player1_id=match.player1_id,
        player2_id=match.player2_id
    )

# DOPO: nessun blocco. L'encounter resta come registrato
# al completamento originale (see ADR-026).
```

---

## Riferimenti

- [ADR-002 Fix Anti-Rematch Encounter Cleanup](ADR-002-fix-anti-rematch-encounter-cleanup.md) — superseded in part da questo ADR
- Commit `38fc050` — review adversariale Random Anti-Rematch (2026-04-19)
- Commit `2b6feb4` — fix G2 parity waitlist in Random (2026-04-19)
- Handoff: `_bmad-output/handoffs/random-next-steps.md`
- Spec: `_bmad-output/implementation-artifacts/spec-random-anti-rematch.md`
- File correlati:
  - `models/match/rack_service.py` (implementazione `reset_match_complete`)
  - `models/classification/models.py` (classe `PlayerEncounter`, metodi `record_encounter`/`delete_encounter`/`delete_round_encounters`)
  - `models/competition/round_manager.py` (`cancel_round`, `reset_match_with_validation`, `bulk_reset_round_matches`)
  - `models/matchmaking/strategies/random_anti_rematch.py` (consumer `Match.query` per `previous_pairs`)
  - `tests/new/unit/test_anti_rematch_regression.py` (test di contratto/regressione)
