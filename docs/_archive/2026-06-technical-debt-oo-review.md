# Technical Debt & OO Design Review — 2026-06-05

> Analisi metodica della code base per valutare debito tecnico e aderenza ai
> principi di buona programmazione orientata agli oggetti (SOLID, GRASP, DRY,
> Law of Demeter). Ogni finding è **verificato sul codice** (non solo sulla
> documentazione) con riferimenti `file:line`.
>
> Severità: 🔴 **HIGH** (debito strutturale / rischio bug) · 🟡 **MEDIUM**
> (smell consolidato, refactor consigliato) · 🟢 **LOW** (nit incrementale).

## Metodo
- 531 file Python; ~55k LOC in `models/`, ~73k LOC totali (escl. test/migrations).
- Codegraph MCP non disponibile in questo ambiente → analisi via grep/read +
  4 sub-agent paralleli (service layer, domain models, strategie, routes).
- Riferimenti: `docs/reference/ARCHITECTURE.md`, ADR-001..030, `models/CLAUDE.md`.
- Tutte le affermazioni degli agent sono state ri-verificate sul codice; le
  rettifiche sono annotate (vedi *Falsi positivi corretti* in fondo).

---

## Nota sull'architettura monolitica (chiarimento)

"Monolite" qui è **descrittivo, non un difetto**. Per questo contesto — singolo
maintainer, deploy unico su PythonAnywhere, SQLite, dominio fortemente coeso
(tornei) — un **monolite modulare** è la scelta architetturale *corretta*:
microservizi introdurrebbero rete, transazioni distribuite, overhead di deploy e
complessità ingiustificati. La codebase è già di fatto un monolite *modulare*
(bounded context separati sotto `models/`), che è esattamente il pattern giusto.
**Nessuna delle raccomandazioni di questo documento richiede di cambiare lo stile
architetturale**: sono interventi *dentro* il monolite (coesione, duplicazione,
dead code), non una spinta verso microservizi. L'unico margine di miglioramento
architetturale reale è rendere più netti i confini tra i moduli (ridurre gli
import incrociati tra servizi, F8.4) — ma resta un monolite.

## Sintesi esecutiva

Il progetto è, nel complesso, **ben architettato come monolite modulare Flask**:
DDD con bounded context chiari, Strategy/Factory reali (non if-elif), event bus
pulito, VO `Distance`/`Score`, convenzione `@transactional` rispettata (nessun
`db.session.commit()` manuale nei servizi). La documentazione (ADR, CLAUDE.md)
è ricca e per lo più allineata al codice.

Il debito tecnico non è diffuso ma **concentrato in pochi cluster ad alto
impatto**. I tre più importanti:

1. **Infrastruttura "enterprise" non collegata all'app** (~1500–2000 LOC *non
   referenziate dal codice di produzione*): `DomainOrchestrator`, il monitoring di
   `QueryOptimizer`, le metriche/isolation-level/read-only di `TransactionManager`,
   la base `DomainService` (3 servizi su 79). ⚠️ "non usato" è un *fatto*;
   "abbandonato" è un *intento da confermare col maintainer* (vedi §1, correzione
   terminologica). Costo di manutenzione senza valore a runtime, ma la scelta
   pausa-vs-scarto è tua.
2. **Astrazione transazionale "che perde"** (debito *gestito*, non da
   rifattorizzare): la correttezza dipende dal sapere "decora solo il metodo più
   interno". ⚠️ Dopo aver letto ADR-012/025 ho **ritirato** la proposta di
   riscrivere il manager: il core è load-bearing e protetto da test (vedi §2).
   L'unico intervento sicuro è togliere i decoratori *ridondanti* sui facade.
3. **Nessuna tassonomia di eccezioni di dominio**: 458 `raise ValueError`
   grezzi, 1 sola eccezione custom. I layer superiori non possono distinguere
   validazione / not-found / conflitto / permessi.

Più 1 **bug reale** ad alta confidenza (`is_active is True`) e una serie di
smell OO classici (god-class, fat controller, duplicazione di algoritmi,
primitive obsession sugli stati).

### Tabella di priorità (consigliata, non sovraingegnerizzata)

| # | Intervento | Severità | Sforzo | Payoff |
|---|-----------|----------|--------|--------|
| A | Fix bug `is_active is True` (+ test) | 🔴 | XS | Alto |
| B | Togliere `@transactional` ridondante sui facade di pura delega (F2.2/F2.3) — **non** toccare il core del manager | 🟡 | S | Medio |
| C | Infra non usata in prod (orchestrator, query-monitoring, DomainService): **confermare con maintainer** se pausa o scarto, poi rimuovere | 🟡 | S | Alto se rimossa (−~1.5k LOC) |
| D | `BaseModel`/`UtilityMixin`: rimuovere la duplicazione (entrambi quasi inutilizzati in prod) | 🟡 | XS | Medio |
| E | Mini-gerarchia eccezioni di dominio | 🟡 | S | Medio |
| F | Predicati di stato sugli enum (`is_finished()`…) | 🟡 | S | Medio |
| G | Estrarre view-model service dai fat controller | 🟡 | M | Medio |
| H | Deduplicare algoritmi (matching nx, trio, tie-break, stats) | 🟡 | M | Medio |

> **Nota su B:** la versione originale di questa riga ("rendere `@transactional`
> rientrante") è stata **ritirata** dopo aver letto ADR-012/025 — vedi §2. Il core
> transazionale è load-bearing e protetto da test; si interviene solo sui
> decoratori ridondanti.

---

## 1. Infrastruttura non usata in produzione (cluster) — ⚠️ intento da confermare col maintainer

> **CORREZIONE TERMINOLOGICA (2026-06-05).** Obiezione corretta del maintainer:
> *"non trovo più commit recenti" ≠ "abbandonato"*. Codice è davvero abbandonato
> solo se (a) **esplicitamente** dichiarato tale, oppure (b) **incompatibile** con
> scelte successive. La mancanza di attività recente può essere lavoro *messo in
> pausa, deprioritizzato o dimenticato*. Quindi riformulo: distinguo il **fatto
> osservabile** ("non referenziato dal codice di produzione", che posso provare)
> dall'**intento** ("abbandonato", che NON posso provare dagli artefatti). La
> decisione su cosa farne resta del maintainer; io fornisco fatti + livello di
> evidenza.

| Componente | Fatto osservabile | Evidenza sull'intento | Classificazione onesta |
|-----------|-------------------|----------------------|------------------------|
| `DomainOrchestrator` / `MatchmakingOrchestrator` | Usati solo da test legacy; `setup_complete_campionato` chiama `TournamentService` in modo statico → si romperebbe | Handoff 2026-02 (TASK 4.1) li chiama "codice morto" e cancella il task | **Più vicino ad (a)**: un maintainer li ha *osservati* morti, ma non è una decisione formale di non costruire mai l'orchestrazione. Resta riprendibile. |
| `models/scoring/` (ScoringPolicy Classic/Fargo/Elo) | Non referenziato dal codice di produzione; la classifica live passa per `classification/strategies` + registry | ADR-013 ha ridisegnato la classifica con un **meccanismo parallelo**, ma **non dice** di rimuovere `scoring/` | **(b) parziale**: *reso ridondante in pratica*, non strettamente "incompatibile". Non posso affermare che sia stato deciso di buttarlo. |
| `QueryOptimizer`/`QueryAnalyzer` monitoring | Nessun consumatore in prod (solo test legacy) | Nessuna dichiarazione, nessuna incompatibilità | **Né (a) né (b)**: solo *non usato*, intento ignoto → potrebbe essere lavoro in pausa. |
| `DomainService` base | 3 servizi su 79 | Nessuna | **Né (a) né (b)**: adozione incompleta, intento ignoto. |

> **Implicazione pratica:** per la riga 1 (orchestrators) e 2 (`scoring/`) la
> rimozione è ragionevole ma va **confermata da te** (sai se era "pausa" o "scarto");
> per le righe 3-4 la raccomandazione corretta **non è "elimina"** ma *"decidi tu se
> è pausa o scarto"*. Non spaccio un'inferenza per un fatto.

Pattern ricorrente: componenti "enterprise" costruiti in anticipo e **non
collegati all'app in esecuzione**. Verificato che `app.py` non inizializza
nessuno di questi.

> **STORIA REALE GITHUB (verificata via MCP, 2026-06-05).** La history locale è un
> singolo commit di import; quella vera è su GitHub. Riscontro:
> - `models/orchestration/service.py` — ultimo commit *sostanziale* `901eab9`
>   (**2025-08-24**, "feat: …Add advanced MatchmakingOrchestrator… Phase 3 backend
>   architecture"). Dopo, solo il refactor bulk `utc_now()` (2026-02) lo ha
>   toccato di striscio. **~10 mesi senza lavoro reale** → abbandonato, non
>   "appena iniziato".
> - `models/scoring/strategies.py` — due commit, entrambi **2025-08-25**
>   (`0bd86024` lo cabla a `ClassificationService`; `18ba16c4` "complete
>   refactoring roadmap ADR-0001"). Poi il sistema di classifica è stato
>   **ridisegnato** (ADR-013), lasciando `scoring/` orfano. Quindi non è
>   pre-costruito-per-il-futuro: è una **implementazione superata** da un redesign.
> - L'intero cluster (orchestration + caching + optimization + MatchmakingOrchestrator)
>   nasce nello stesso push "Phase 3 backend architecture" di agosto 2025: molta
>   infrastruttura *forward-looking* aggiunta in blocco e mai cablata al prodotto.
>   Questa è l'origine del dead-code cluster.
>
> **VERIFICA "abbandonato vs pianificato" (2026-06-05).** Il dubbio legittimo è:
> sono *feature da completare* o *codice morto da rimuovere*? Riscontro
> documentale: il handoff interno
> [`docs/_archive/2026-02-handoff-technical-debt.md`](./2026-02-handoff-technical-debt.md)
> (TASK 4.1, righe 209-213, 257-258) **aveva già classificato `DomainOrchestrator`
> e `MatchmakingOrchestrator` come "codice morto"** a febbraio 2026, cancellando i
> task collegati ("nessun beneficio in produzione"). Stessa cosa per
> `UtilityMixin`/duplicazione `BaseModel` (TASK 4.2). Quindi **non sono inizi di
> feature: sono già stati riconosciuti come abbandonati dal maintainer**, solo non
> rimossi. I documenti di roadmap/spec (`docs/wishlist*.md`,
> `_bmad-output/.../deferred-work.md`, `SPECIFICHE.md`) **non li elencano** tra il
> lavoro pianificato. *Eccezione che richiede conferma:* `models/scoring/` —
> vedi caveat in F1.5.

- **F1.1 🔴 `DomainOrchestrator` (e `MatchmakingOrchestrator`) sono codice morto e per giunta rotti.**
  > Confermato dead code dal handoff 2026-02 (TASK 4.1). `MatchmakingOrchestrator`
  > vive in `models/matchmaking/service.py`; stesso status del `DomainOrchestrator`.
  `models/orchestration/service.py`. Istanziato solo in `tests/legacy/`
  (non mantenuti). 5 helper privati sono stub che ritornano `[]`/`{}`
  (`:334-366`, "Implementation would…"). Inoltre `setup_complete_campionato`
  (`:111`) chiama `TournamentService.create_campionato(name=…)` come **statico**,
  ma la classe reale è instance-based con `__init__` (`tournament_service.py:37`)
  → fallirebbe a runtime. *Fix:* eliminare la classe `DomainOrchestrator` e gli
  stub; **conservare** solo le dataclass `OperationResult`/`OperationType`
  (queste sono realmente usate da `competition/services.py` e `match_service.py`)
  spostandole in `models/shared/`.

- **F1.2 🔴 `QueryOptimizer`/`QueryAnalyzer` (monitoring N+1, ~400 LOC) inutile in produzione.**
  `models/optimization/query_optimizer.py:94-540`. `detect_n1_problems`,
  `get_performance_dashboard`, `get_optimization_recommendations` sono usati
  **solo** da `tests/legacy/`. *Solo* il decoratore `optimized_query` e
  `bulk_load_relationships` hanno un consumatore reale
  (`classification/campionato_classification.py:72`). *Fix:* tenere il decoratore
  + `cache_manager`; rimuovere la macchina di analisi/dashboard.

- **F1.3 🔴 `TransactionManager`: feature speculative su SQLite-only.**
  `models/transaction/manager.py`. Isolation level (`:198-212`) e read-only
  (`:215-222`) sono no-op dichiarati su SQLite (l'app è SQLite sia dev che prod,
  cfr. ARCHITECTURE.md). `_metrics_history`, `get_performance_summary`,
  `_transaction_stack` (quest'ultimo **mai usato**, lo stato vive in
  thread-local) non hanno consumatori. *Fix:* ridurre il manager all'essenziale
  (begin/commit/rollback + savepoint) — vedi anche F2.

- **F1.4 🟡 `DomainService` base class quasi inutilizzata.**
  `models/transaction/manager.py:472`. Solo **3 servizi su 79** la estendono
  (`user/services.py`, `campionato/statistics_service.py`, indirettamente
  `tournament_service.py`). Astrazione non guadagnata. *Fix:* rimuoverla o
  adottarla davvero — non lasciarla a metà.

- **F1.5 🟡 Gerarchia `ScoringPolicy` morta in `models/scoring/` — ⚠️ CONFERMARE prima di rimuovere.**
  `models/scoring/strategies.py` (`ClassicScoringPolicy`/`FargoRatingScoringPolicy`/
  `EloRatingScoringPolicy`) + `policies.py`: nessun consumatore in produzione (solo
  `tests/legacy/`; il `routes/admin/match/scoring.py` è omonimo ma non li usa).
  **Caveat importante:** `SPECIFICHE.md:60,91,144` descrive Fargo/Elo come concetto
  *reale e desiderato* (primo abbinamento basato su rating, handicap per differenza
  rating). MA quel concetto è servito dal dominio **`models/rating/`** (live:
  `rating_service.py`, `handicap_service.py`, `routes/rating.py`), **non** da
  `models/scoring/`, che è un tentativo parallelo precedente mai cablato. *Fix
  consigliato:* **non eliminare di slancio** — confermare col maintainer che la
  roadmap Fargo/Elo passa da `rating/` (probabile), poi rimuovere `scoring/` come
  duplicato. Rischio basso ma è l'unico componente "morto" con un aggancio a una
  feature di spec, quindi merita una conferma esplicita.

> **Impatto cluster:** rimuovere ~1.5–2k LOC riduce superficie di manutenzione,
> tempo di onboarding e rischio di drift, senza alcuna perdita funzionale.

---

## 2. Astrazione transazionale (🟡) — ⚠️ AREA AD ALTO RISCHIO, NON RIFATTORIZZARE IL CORE

> **REVISIONE 2026-06-05 dopo lettura ADR-012 e ADR-025.** La mia prima stesura
> consigliava di rendere `@transactional` rientrante riscrivendo
> `TransactionManager.transaction()`. **Ritiro quella raccomandazione.** Motivi:
> 1. **Due meccanismi savepoint distinti, da non confondere.** (a) Il
>    `begin_nested()` *manuale* applicato nei service è una **scelta deliberata e
>    testata** (ADR-025): serve a forzare `IntegrityError` a flush-time e tradurlo
>    in `ValueError` di dominio per le UNIQUE TOCTOU. È coperto da
>    `tests/new/integration/test_unique_constraints_toctou.py`. **Va lasciato
>    intatto.** (b) Il savepoint *automatico* dentro il decoratore
>    (`is_true_nested`/`is_pseudo_nested`) è il meccanismo che genera il footgun.
> 2. **Storia di bug subdoli.** ADR-012 documenta un bug "ritorna success ma non
>    persiste" causato proprio dal layer transazionale. La logica
>    `is_pseudo_nested` (gestione dell'autobegin di SQLAlchemy) è quasi certamente
>    stata calibrata *contro* test reali. Riscriverla = rischio alto, ROI incerto.
> **Conclusione:** trattare il core di `TransactionManager` come *load-bearing e da
> non toccare* senza un caso di fallimento concreto e riproducibile. Gli interventi
> a valore sicuro sono solo quelli **locali e coperti da test** sotto (F2.2/F2.3).

- **F2.1 🟡 (declassato da 🔴) `@transactional` non rientrante è un footgun, ma il
  costo/rischio di rimuoverlo supera il beneficio — DA NON FARE ora.**
  `models/transaction/manager.py:144-318`. Una chiamata annidata crea un savepoint
  invece di unirsi alla transazione; la correttezza dipende dalla regola umana
  "decora solo il metodo più interno". È un debito *reale* ma **gestito** via
  convenzione documentata + test. *Raccomandazione rivista:* **non riscrivere il
  manager.** Se in futuro si vuole eliminare il footgun, farlo solo con: (1) un
  test di caratterizzazione che cattura il comportamento attuale di autobegin/
  savepoint, (2) verifica esplicita che i test TOCTOU (ADR-025) restino verdi,
  (3) un caso concreto che giustifichi il rischio. Finché non c'è, la mitigazione
  corretta è quella già in uso: rimuovere i decoratori *ridondanti* (F2.2/F2.3).

- **F2.2 🔴 Nested `@transactional` ancora presente in `IndividualMatchService`.**
  `models/individual_match/services.py:180-360` (~20 metodi facade tutti
  `@transactional`) che delegano a `ProposalService.*` **anch'essi**
  `@transactional` (es. facade `accept_proposal:293` → `proposal_service.py:417`).
  Esattamente l'anti-pattern vietato da CLAUDE.md. *Fix:* togliere il decoratore
  dai facade di pura delega.

- **F2.3 🔴 Duplicazione superficie scoring: `MatchService` riavvolge `ScoringService`.**
  `models/match/match_service.py:425-520`: `add_rack_for_player`,
  `forfeit_match`, `confirm_match_result`, … sono wrapper `@transactional` su
  metodi omonimi di `ScoringService` (`scoring_service.py`), a loro volta
  `@transactional` (stesso pattern di F2.2 + violazione SRP: due servizi
  possiedono "scoring"). *Fix:* un solo owner — le route chiamano `ScoringService`,
  o `MatchService` delega senza decoratore.

- **F2.4 🟡 Boundary transazionale incoerente nelle transizioni di stato.**
  `models/competition/state_service.py`: `reopen_setup`/`complete`/`start_ssr`
  sono `@transactional` (`:48,86,121`) ma `to_inscription`/`start_playing`
  **no** (`:31,57`). Il fatto che una transizione persista dipende da quale
  metodo fratello chiami. *Fix:* rendere uniforme il decoratore su tutte le
  transizioni.

- **F2.5 🟡 `apply_batch_corrections` non atomico.**
  `models/match/match_service.py:305-420`: nessun `@transactional`; ogni
  correzione è una transazione a sé → un fallimento a metà loop lascia le
  precedenti committate mentre ritorna `success=False`. *Fix:* avvolgere il
  batch in un'unica transazione (o documentare la semantica per-item).

---

## 3. Eccezioni: nessuna tassonomia di dominio (🟡→🔴 per i call site)

- **F3.1 🔴 458 `raise ValueError` grezzi, 1 sola eccezione custom.**
  `models/exceptions.py` definisce solo `InvalidTransitionError`. Validazione,
  not-found, conflitto, permessi, regole di business → tutti `ValueError`
  indistinguibili. Le route fanno `except ValueError` generico (cfr.
  `utils/route_helpers.handle_service_action`) e non possono mappare a status
  HTTP corretti (404 vs 409 vs 422). *Fix proporzionato:* mini-gerarchia in
  `models/exceptions.py` (`DomainError(Exception)` → `ValidationError`,
  `NotFoundError`, `ConflictError`, `PermissionDeniedError`), adottata
  incrementalmente partendo dai servizi più chiamati. Non serve un'eccezione per
  ogni caso: 4–5 categorie coprono il 95%.

---

## 4. Base classes & inheritance (🔴/🟡)

- **F4.1 🟡 (declassato da 🔴) `BaseModel` duplica `UtilityMixin` — ma entrambi
  sono quasi inutilizzati in produzione.**
  `models/base.py:230-275` re-implementa `save`/`delete`/`to_dict`/`find_by_id`/
  `find_all` già in `UtilityMixin` (`:69-114`); copie **già divergenti**
  (`UtilityMixin.to_dict:88` gestisce `__table__ is None` e ha `refresh()`,
  `BaseModel.to_dict:257` no). **Riscontro:** il handoff 2026-02 (TASK 4.2) ha già
  verificato che *tutti* i metodi di `UtilityMixin` sono usati **solo nei test
  legacy** (i servizi usano `@transactional` + query dirette). Quindi non è un
  rischio runtime ma rumore/confusione. *Fix proporzionato:* poiché il mixin è
  morto in prod, la mossa più pulita è **rimuovere `UtilityMixin` e
  `TimestampedModel`** e tenere il solo `BaseModel`; oppure, se si preferisce
  riuso, far ereditare `BaseModel` dai mixin ed eliminare i corpi duplicati.
  Verificare prima che i pochi `find_by_id`/`save` eventualmente usati siano
  coperti.

- **F4.2 🟡 `User` mixa `TimestampMixin` già fornito da `BaseModel`.**
  `models/user/models.py:34` —
  `User(UserMixin, BaseModel, TimestampMixin, SoftDeleteMixin)`: `created_at/
  updated_at` arrivano due volte (MRO ambiguo). *Fix:* togliere `TimestampMixin`.

- **F4.3 🟡 Status `Match` (str) vs `IndividualMatch` (Enum) sotto lo stesso
  `BaseMatchMixin` → LSP/contratto fragile.**
  `models/match/models.py:62` usa `db.String(20)`; `individual_match/
  match_models.py:58` usa `db.Enum(MatchStatus)`. Il mixin condiviso deve
  difendersi ovunque con `self.status.value if hasattr(self.status,"value")`
  (`base_match.py:86,118`) e `_complete_match_after_confirmation` fa
  `isinstance(self.status, str)` per scegliere il comportamento (`:211-217`):
  la base conosce le sue sottoclassi (dipendenza invertita). *Fix:* unificare la
  rappresentazione (preferibilmente `db.Enum` per entrambi) o nascondere lo
  storage dietro una property comune.

---

## 5. Anemic/Fat models & primitive obsession (🟡)

- **F5.1 🔴 `RoundClassification.calculate_classification_after_round`: god-method
  statico (~260 LOC) su un modello altrimenti anemico.**
  `models/classification/models.py:106-368`. Query + aggregazione bye/trio/
  multi-set + scelta sort-key + upsert, tutto in uno `@staticmethod` **già
  deprecato** in favore di `StrategyBasedClassificationService`. *Fix:* completare
  la migrazione ed eliminare il metodo dal modello.

- **F5.2 🟡 `Gara` god-model (718 LOC).**
  `models/competition/models.py`. ~30 metodi: passthrough di config strategia
  (`:409-490`), `get_podium` che interroga un service (`:625`), parsing JSON
  tavoli, `can_cancel_round` che itera i match e raggiunge interni del trio
  (`:517-572`). *Fix:* estrarre un collaboratore `GaraStrategyPolicy`/`GaraView`;
  lasciare a `Gara` identità + relazioni + invarianti.

- **F5.3 🟡 Primitive obsession sugli stati: liste di `.value` e stringhe grezze
  sparse.**
  Confronti `m.status in [COMPLETED.value, VALIDATED.value]`
  (`competition/models.py:334`), e **letterali raw** `"playing"`/`"completed"`
  in `user/models.py:257,270,280` e `individual_match/match_models.py:509,553`
  (un typo valuta silenziosamente `False`). *Fix:* predicati su enum
  (`MatchStatus.is_finished()/is_active()`) — elimina decine di call site e una
  classe di bug da typo. (Allineato a F4.3.)

- **F5.4 🟡 Adozione VO incompleta (rischio ADR-027).**
  `classification/models.py:226-255` e `user/models.py:284,304` ricalcolano a
  mano `player1_score+player2_score` / leggono `gara.distance` invece di usare
  `match.distance_config`/`MatchScore`. Sono proprio i path che ADR-027 segnala
  come a rischio di perdere gli override per turno. *Fix:* instradare
  completamento/winner/aggregazione attraverso i VO.

- **F5.5 🟢 `Campionato`: colonne deprecate + metodi no-op + UI nel modello.**
  `models/campionato/models.py:52-60,285-315` (`without_x`, `final_playoffs`,
  `scoring_policy`, `set_scoring_policy` no-op) e `get_status_badge_class`/
  `get_status_text` (`:161-181`) con stringhe CSS/IT (view concern nell'entità).
  *Fix:* drop colonne via migration; spostare badge/text in un presenter/filtro.

---

## 6. Strategy/Factory: per lo più corretto, con leak (🟡)

> Nota positiva: i registry (`matchmaking/registry.py`,
> `classification/registry.py`) sono factory reali register-based; il ranking
> usa `get_sort_key` polimorfico (Template Method pulito).

- **F6.1 🟡 `PairingStrategy.create_round` non è astratto: fallback duck-typed.**
  `models/matchmaking/strategies/base.py:155-178`: `if hasattr(self,'propose')…`
  — dispatch riflessivo che lo Strategy pattern dovrebbe eliminare; nessuna
  strategia definisce `propose` (ramo morto). *Fix:* rendere `create_round`
  `@abstractmethod` o fondere le due basi.

- **F6.2 🟡 Wiring NetworkX max-weight-matching duplicato 3×.**
  `amalfi.py:509-557`, `random_anti_rematch.py:376-415` e `:645-698`: blocchi
  quasi identici `nx.Graph()`+`max_weight_matching(maxcardinality=True)`+check
  perfect-matching, differenti solo per la weight-fn. CLAUDE.md dice "non
  reimplementare algoritmi di grafo" ma il *wiring* è reimplementato. *Fix:*
  helper unico `perfect_matching(players, weight_fn) -> Optional[pairs]`.

- **F6.3 🟡 Selezione trio duplicata e divergente tra Amalfi e Random.**
  `amalfi.py:641-714` (tupla a 4) vs `random_anti_rematch.py:593-643`
  (tupla a 3): stesso problema, obiettivi/tie-break diversi → un fix di fairness
  in una non raggiunge l'altra. *Fix:* `TrioSelector` condiviso parametrizzato.

- **F6.4 🟡 Tie-resolution copiata 3×.**
  `classification/strategies/gara_strategies.py:113-175` e `:260-311` (identiche)
  + `classification/tiebreaker_resolver.py:45-116`. *Fix:* entrambe le gara
  strategy chiamano `TiebreakerResolver`.

- **F6.5 🟡 Switch-on-classification-system lato chiamante.**
  `classification/gara_classification.py:128-138,149-155`: due dict
  `strategy_map = {"WINS":…, "POSITION":…}` nel consumatore (duplicati) invece di
  sfruttare `registry.get_for_scope`. Aggiungere un sistema richiede editare i
  dict oltre a registrare la strategia. *Fix:* spostare l'associazione nella
  metadata della strategia / registry.

- **F6.6 🔴 Ramo "Mock-aware" dentro una strategia di produzione.**
  `amalfi.py:46-56`: `if "Mock" in str(gara.__class__): …validazione semplificata`.
  La strategia cambia comportamento se "sente" di essere in test (leaky
  abstraction + LSP). *Fix:* i test passano fake che onorano il contratto
  `inscriptions`; rimuovere il ramo.

- **F6.7 🟢 `_clone_strategy` finge isolamento su strategie stateful.**
  `matchmaking/registry.py:96-111` ritorna l'istanza condivisa ("stateless"), ma
  `RandomAntiRematchStrategy` tiene `self._rng`/`self._precomputed_schedule`
  (`random_anti_rematch.py:63-71`), singleton per nome (`bootstrap.py:35`). La
  signature-check mitiga ma l'astrazione "factory+isolation" è fittizia. *Fix:*
  clonare davvero le strategie stateful o documentare/instanziare per-request.

---

## 7. Fat controllers & duplicazione nelle route (🟡)

> **CHIARIMENTO SUL PATTERN (risposta a "è colpa dell'MVC?").** No: **MVC non è il
> pattern sbagliato e va bene così**. Il problema wizard/edit *non* è MVC; è una
> **astrazione mancante DENTRO il layer controller/view**. In termini MVC:
> - *Model* = `Gara`/`Campionato` → corretti.
> - *View* = i template (create, wizard, edit) → tre viste, legittime.
> - *Controller* = `create_gara`/wizard/`edit_gara` → **ciascuno parsa il form per
>   conto suo**.
>
> Il difetto nasce perché il mapping **form↔modello** (parsing + validazione +
> quali campi sono editabili) è *duplicato* tra i controller invece di vivere in un
> unico posto. La soluzione classica e leggera è il pattern **Form Object** (DTO/
> "form schema": in Flask sarebbe `FlaskForm`/WTForms; qui esiste già in forma
> embrionale come `GaraFormParser`) che: (1) definisce l'insieme dei campi UNA
> volta, (2) è condiviso da create+wizard+edit, (3) codifica le regole di
> editabilità per-campo. Quindi la tua terza ipotesi è quella giusta: **il pattern
> corretto esiste ed è buono, ma non è applicato ovunque** (l'edit lo bypassa →
> drift → bug F9.2). MVC da solo non previene questa classe di bug; la previene il
> Form Object + un **controllo che sia sempre applicato** (es. un test che verifica
> che create ed edit coprano lo stesso set di campi). *Non* serve migrare tutto a
> WTForms (sarebbe sovraingegnerizzazione): basta rendere `GaraFormParser` l'unica
> fonte usata da tutti e tre i percorsi, più un test-guardia anti-drift.


> Nota positiva: **nessun `db.session.add/commit/delete` diretto nelle route**
> (boundary service+@transactional rispettato), ed esistono buoni helper
> (`handle_service_action`, `GaraFormParser`, `is_ajax_request`) — ma applicati
> in modo incoerente.

- **F7.1 🟡 `gara_detail` fat controller (~375 LOC).**
  `routes/admin/competition/detail.py:27-401`: auth + query multiple + calcolo
  classifica + SSR/tiebreaker + playoff + assemblaggio template in un'unica
  funzione. *Fix:* `GaraDetailViewService.build_view_data(gara_id, user)` → la
  route diventa load→call→render.

- **F7.2 🟡 `campionato_detail` con logica di dominio nel controller.**
  `routes/admin/campionato.py:362-467`: regola "gara tecnicamente completata"
  (`p.status=="playing" and p.current_round>p.rounds_count`, `:396-407`) e join
  `campionato_players` inline. *Fix:* spostare in `TournamentService`.

- **F7.3 🟡 Validazione "start round" duplicata e annidata nelle route.**
  `routes/admin/competition/rounds.py:505-593` (`amalfi_start_round`) e
  `596-709` (`start_round_generic`): ~90 LOC quasi identiche (bounds, idempotenza,
  "round precedente incompleto"). È logica di matchmaking nel controller, doppia.
  *Fix:* `RoundService.start_next_round` con le precondizioni; collassare le due
  route (`amalfi_start_round` è in gran parte ridondante).

- **F7.4 🟡 Query "è director di questa entità?" ripetuta 5+ volte.**
  `campionato.py:376-385,447`, `crud.py:181-192`, `detail.py:170-191`. *Fix:*
  `User.is_director_of(entity_type, entity_id)` o `DirectorAssignment.exists(...)`.

- **F7.5 🔴 (upgrade) Nessuna "single source of truth" per il mapping form↔modello:
  create / wizard / edit hanno parser separati e sono già divergenti.**
  Per la **gara** esistono 3 copie del mapping: `GaraFormParser.parse()` (create),
  l'inline in `edit_gara` (`crud.py:263-327`), e il wizard. Divergenze verificate:
  - `classification_system` è gestito dal parser (create) ma **assente** nell'edit
    → **bug F9.2** (perdita silenziosa).
  Per il **campionato**: il wizard
  (`campionato_wizard_step1/2.html`) espone `playoff_elite_*`/`playoff_academy_*`
  e usa `name="classification_system"`; il form di **modifica**
  (`_campionato_edit_form.html`) **omette** la config playoff e usa
  `name="default_classification_system"`. Quindi divergono sia l'insieme dei campi
  sia i *nomi* dei campi (impedendo il riuso del template).
  > **Nota onesta:** alcune differenze create-vs-edit sono *legittime e volute*
  > (es. la config playoff ha verosimilmente una UI dedicata — ADR-024 + backlog
  > "Redesign playoff configuration UI"; certi campi vanno bloccati dopo l'avvio
  > della gara). Il problema **non è il modello di dominio** (`Gara`/`Campionato`
  > sono coerenti) ma il fatto che l'editabilità per-campo è un *incidente* di quale
  > handler ha cablato cosa, invece di una regola *dichiarata*.
  *Fix proporzionato:* un unico schema/parser per entità, condiviso da
  create+wizard+edit, con regole esplicite di editabilità per-campo (quali campi
  sono immutabili dopo iscrizioni/avvio). Risolve insieme F9.2, la divergenza
  campionato e la duplicazione. **Ambito:** concentrato su questi form CRUD admin;
  non è un anti-pattern pervasivo (poche entità hanno il triplo create+wizard+edit),
  ma la lezione "una sola fonte di verità form↔modello" vale ovunque ci sia >1 form
  per la stessa entità.

- **F7.6 🟡 Logica di scoring in una route (e viola ADR-027).**
  `routes/main.py:357-450` (`debug_complete_current_round`) muta
  `match.player1_score`/`winner_id`/`status` e legge `gara.is_race_to`/
  `gara.distance` direttamente. *Fix:* delegare a un helper di `RoundService`.

- **F7.7 🟡 Export GDPR/CSV: ~215 LOC di data-collection nel layer route.**
  `routes/player/exports.py:175-389` (`_collect_user_data`) interroga 10+ modelli
  con catene `match.gara.campionato.name`; spawna anche un thread dalla route.
  *Fix:* `models/user/gdpr_export_service.py` / `ProfileCsvExporter`.

- **F7.8 🟢 Error-handling incoerente: `except Exception` + flash `str(e)`.**
  `venue.py:255,314,447,554,595`, `campionato.py:282`, `crud.py:100` espongono
  l'eccezione grezza all'utente mentre `handle_service_action` esiste apposta.
  *Fix:* instradare tutto attraverso l'helper.

---

## 8. Convenzioni di servizio incoerenti (🟡)

- **F8.1 🟡 Static vs instance nello stesso layer.**
  `GaraService`/`MatchService`/`ScoringService`/`UserProfileService` sono
  interamente `@staticmethod`; `TournamentService`
  (`campionato/tournament_service.py:31`) è instance-based con `__init__`,
  istanziata come singleton stateless nelle route. *Fix:* standardizzare (il
  codice tende all'all-static); preferire composizione all'ereditare
  `TournamentStatisticsService`.

- **F8.2 🟡 Più servizi non correlati in un solo modulo (`services.py` grab-bag).**
  `models/user/services.py`: 5 classi (`UserServiceCore`, `UserService`,
  `DirectorRequestService`, `UserDeletionService`, `VenueManagementService`).
  Stesso pattern in `individual_match/services.py`, `competition/services.py`.
  *Fix:* un servizio per modulo.

- **F8.3 🟡 `UserProfileService` (639 LOC, 16 metodi) viola SRP.**
  `models/user/profile_service.py`: CRUD + autenticazione + verifica email +
  reset password + override admin. *Fix:* split in `AuthService` /
  `EmailVerificationService` / `PasswordResetService`.

- **F8.4 🟡 Import locali ripetuti come workaround di cicli.**
  `gamification/achievement_service.py:214,223,245` importa
  `UserStatsService` **dentro** i metodi 3 volte; pattern analogo in
  `round_service.py`, `inscription_service.py`, `state_service.py`. Sintomo di
  accoppiamento inter-service / cicli di import. *Fix:* port/interfaccia o
  spostare la query condivisa in un modulo più basso importabile a top-level.

- **F8.5 🟡 Logica statistiche giocatore duplicata su 3+ superfici.**
  `User.get_statistics` (`user/models.py:242`), `UserStatsService.get_user_stats`
  **e** `get_user_statistics` (due metodi quasi omonimi nello stesso file,
  `stats_service.py:38,116`), più `player/history_service.py` e
  `campionato/statistics_service.py`. *Fix:* un solo `UserStatsService` come
  fonte; il modello delega.

- **F8.6 🟡 `uninscribe_user` (~120 LOC) con query waitlist copiate 4×.**
  `models/competition/inscription_service.py:276-400` (+ duplicazione in
  `admin_uninscribe_user:464-602`). *Fix:* `_next_waitlist(gara, reason)` +
  routine di promozione condivisa.

---

## 9. Bug reali individuati

- **F9.1 🔴 `BilliardHall.is_active is True` → query sempre vuota.**
  `models/user/models.py:222`:
  `BilliardHall.query.filter(BilliardHall.id.in_(venue_ids),
  BilliardHall.is_active is True)`. `is True` è un confronto d'identità Python
  valutato subito a `False` (non un'espressione SQL); il filtro diventa
  `WHERE … AND 0` → `get_managed_venues` **non restituisce mai nulla**. Tutti gli
  altri filtri nel codebase usano correttamente `== True` (E712). *Fix:*
  `BilliardHall.is_active == True` (o `.is_(True)`); aggiungere test di
  regressione. **Intervento minimo, alto valore.**

- **F9.2 🔴 Edit gara scarta silenziosamente `classification_system`.**
  Il form di modifica (`templates/components/_gara_edit_form.html:50,61`) invia
  `classification_system` (c'è perfino un doppio input: hidden + `<select>`), ma
  l'handler `edit_gara` (`routes/admin/competition/crud.py:263-327`) **non lo
  legge mai** e non lo passa a `GaraService.update_gara`. Risultato: il direttore
  cambia il sistema di classifica, la UI mostra "Gara aggiornata con successo!",
  ma il valore **non viene salvato**. È la conseguenza diretta del fatto che
  creazione e modifica hanno parser di form *separati* (F7.5): `GaraFormParser`
  (create) gestisce il campo, l'edit a mano se l'è dimenticato. *Fix:* far passare
  l'edit dallo stesso `GaraFormParser` (risolve bug + duplicazione insieme).
  Bonus bug: i due input con lo stesso `name` nel form sono di per sé un difetto.

---

## 10. Incompletezza di prodotto ≠ debito tecnico (risposta onesta)

Domanda: feature "appena accennate" (match individuali, gamification,
monitoraggio admin/KPI) → sono debito tecnico / errori OO-architetturali?
**Risposta verificata: no, sono per lo più maturità di prodotto, non debito.**

Riscontri:
- **Non sono "appena accennate" nel codice.** Volumi misurati: gamification
  **6.834 LOC** + 27 template + 1.325 LOC di route; individual_match **3.882 LOC**
  + 11 template + 974 LOC di route; KPI **1.878 LOC**. Sono tra i domini più
  costruiti e sono event-driven/architetturati, non stub.
- **La gamification è deliberatamente disattivata in produzione "until the feature
  stabilises"** (`utils/feature_flags.py:182-188`: visibile solo a director, non a
  player/anonimo). Questa è una **decisione di rilascio**, la definizione stessa di
  "feature completa ma non ancora rilasciata" — non di debito.

Quindi la distinzione che fai è corretta: una feature sottile/da rifinire è
**scope/prodotto**, non un errore architetturale o OO.

**Dove però l'incompletezza *diventa* debito (la sfumatura onesta):** quando lascia
*impalcatura o accoppiamento* dietro di sé — codice che esiste ma non fa nulla, o
che vincola il resto. Esempi che abbiamo già catalogato a parte: orchestratori
morti (F1.1), `ScoringPolicy` morto (F1.5). La linea è netta:
- "Esiste codice che non fa nulla / vincola altro codice?" → **debito** (vedi §1).
- "Esiste una feature che funziona ma è sottile/non rilasciata?" → **prodotto**.

Per gamification/individual_match il backend è sostanzioso e disaccoppiato via
eventi: completarli è soprattutto lavoro di prodotto/UX/QA. **Unica tassa reale da
nominare:** una sottosistema event-wired grande e spento (gli handler gamification
scattano su ogni match/iscrizione) impone una *manutenzione continua* ai domini
core (ogni evento deve continuare ad alimentarlo). È un costo vero, ma è un
**trade-off architetturale voluto** (decoupling a eventi), non un errore.

## Falsi positivi corretti (verifica sul codice)

Per onestà metodologica, alcune segnalazioni iniziali degli agent sono state
**scartate** dopo verifica:

- ❌ "`match.validated_by_admin` è un attributo fantasma / no-op silenzioso"
  (`match/models.py:708`): **falso** — è una colonna reale
  (`db.Column(db.Boolean)` a `:391`). Nessun bug.
- ❌ "`models/optimization` è interamente morto": **parziale** — il monitoring sì
  (F1.2), ma `optimized_query`/`bulk_load_relationships` hanno un consumatore
  reale. Rettificato.

---

## Cosa è fatto bene (da preservare)

- Bounded context DDD chiari; event bus pub/sub pulito con isolamento Sentry.
- VO `Distance`/`Score` immutabili e ben progettati (il problema è l'adozione
  incompleta, non il design).
- Convenzione `@transactional` rispettata: **nessun** `commit()` manuale nei
  servizi.
- Registry/Factory reali per matchmaking e classification (no if-elif chains).
- `ScoringService` grande ma ben decomposto in helper privati (buon SRP interno).
- Route: nessuna scrittura DB diretta; helper condivisi esistono (vanno solo
  applicati con coerenza).
- Documentazione (ADR, CLAUDE.md) ricca e, salvo le note sotto, allineata.

---

## Note di allineamento docs ↔ codice

- ARCHITECTURE.md descrive `TransactionManager` con isolation level/metrics come
  feature: nel codice sono no-op su SQLite e senza consumatori (F1.3). La doc
  sovrastima le capacità reali.
- ARCHITECTURE.md cita `DomainOrchestrator` come layer di orchestrazione
  cross-domain "Phase 3.2": di fatto è dead/rotto (F1.1).
- CLAUDE.md ripete in ≥4 punti il warning sulla doppia `@transactional`: è il
  sintomo documentale di un'astrazione che andrebbe resa rientrante (F2.1),
  così il warning diventerebbe superfluo.
</content>
