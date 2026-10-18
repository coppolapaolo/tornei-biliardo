# [084] Istruttori e direttori tengono il TPA della partita di altri due

**Data**: 2026-10-17
**Stato**: Accepted, emendato il 2026-10-18 (vale il rifiuto; l'admin non segna)
**Decisori**: Paolo Coppola (utente), Claude

Emenda [ADR-044](ADR-044-tpa-scoresheet.md) («il referto lo tiene uno dei due
giocatori») e [ADR-083](ADR-083-livelli-di-certificazione.md) (il livello di
certificazione era uno per partita).

## Contesto

Una sera da spettatore: due giocatori in finale, un istruttore a bordo tavolo
che vorrebbe tenere il referto Accu-Stats della partita. Oggi non può.
L'ADR-044 lega il referto ai due giocatori in quattro punti
(`blocking_reason`, `can_open_once_started`, `routes/individual_match/tpa.py::_load`,
`TpaReferto.player_number`), e la sfida a due presuppone che la firmino loro:
a distanza raggiunta chi vince firma d'ufficio.

Con un terzo che segna, entrambe le premesse cadono:

* chi scrive il referto non gioca;
* nessuno dei due giocatori ha chiesto la partita, e nessuno dei due ha visto
  il referto mentre si scriveva. Firmare d'ufficio per il vincitore vorrebbe
  dire far dichiarare a un giocatore un risultato che ha scritto un altro.

## Decisione

**Chi può segnare.** `user.is_instructor`, `user.is_director` o l'admin
(`ScoredMatchService.can_score`) — _l'admin non più dal 2026-10-18, vedi
l'emendamento_. Chi segna non è mai uno dei due giocatori.
I due giocatori, in questa versione, sono utenti registrati
(`ScoredMatchService._giocatore`, il punto da estendere per i giocatori non
registrati).

**Il modello.** `IndividualMatch.scorer_id` (FK `user.id`, nullable): presente
vuol dire «partita presa da un terzo». La partita nasce già in corso e col
referto già aperto, compilatore lo scorer — una partita di un terzo senza
referto non esiste, quindi disciplina e formato sono quelli che il TPA copre.
`TpaReferto.compiler_id` resta chi scrive e qui coincide con `scorer_id`.

**Un permesso solo.** `TpaRefertoService.can_compile(match, user_id)`: un
giocatore della sfida, oppure lo scorer se c'è. Lo chiedono apertura, spunta
all'avvio e le route del referto. La lettura è `can_read`: i due giocatori, lo
scorer, e gli istruttori a cui uno dei due ha aperto una scheda (ADR-069).

**Dichiarata.** La partita di un terzo è *dichiarata* quando lo scorer chiude
il referto (`TpaReferto.closed_at`). Chiudere si può solo a partita pronta per
la validazione (distanza raggiunta, o almeno un triangolo nel formato libero).
Non c'è una colonna in più: il fatto sta già sul referto, e due colonne per la
stessa cosa prima o poi si contraddicono. Alla chiusura `avvisa_chi_deve_firmare`
scrive a **entrambi** i giocatori, con la descrizione della partita.

**Nessuna firma d'ufficio.** `_sync_match_score` con `scorer_id` non firma per
nessuno, né alla distanza né in parità.

**Conferma e rifiuto, per giocatore.** _Il rifiuto per giocatore è sostituito
dall'emendamento del 2026-10-18: un rifiuto basta, per tutti e due._ Ognuno
decide per sé, una volta sola:

* conferma → `player*_confirmed`; con entrambe la partita va a
  `CONFIRMED_BY_BOTH` come ogni sfida, e si emette l'evento dell'ELO globale;
* rifiuto → `player*_rejected_at`. Vuol dire «non la riconosco»: non toglie
  triangoli e non tocca l'altro giocatore. È il contrario del rifiuto della
  sfida normale, che contesta il punteggio e riapre la partita.

**Certificazione per giocatore** (`models/certificazione.py`, unico posto):

| Partita di un terzo, per il giocatore | Livello |
|---|---|
| l'ha confermata (o confermata da entrambi) | Confermata |
| dichiarata, non ha ancora deciso | In attesa |
| l'ha rifiutata, o non è ancora dichiarata | nessuno |

`livello_di_sfida_per(sfida, user_id)` e `sfide_della_vista(vista, user_id=…)`
la applicano a una persona; senza persona la regola è **di coppia** ed è quella
dell'ELO, che misura una partita fra due e non si divide:

| Partita di un terzo | ELO |
|---|---|
| confermata da entrambi | *Confermate* (`ELO_GLOBAL`) e *Tutte* |
| dichiarata, nessun rifiuto | *Tutte* (`ELO_ALL`) |
| almeno un rifiuto | nessuno, per tutti e due |

Chi l'ha confermata se la tiene nelle sue statistiche anche se l'altro la
rifiuta: vittorie, TPA e runout sono suoi, e il referto lo ha scritto un terzo
che non ha interesse nel risultato.

**Esclusioni.** La partita di un terzo non blocca A e B
(`PendingConfirmationService.ensure_none_pending`, che guarda
`awaiting_confirmation_from_id`, `None` per queste partite), non si ritira
(`withdraw_by_signer` la rifiuta: i giocatori hanno conferma e rifiuto) e non
compare come «Continua» ai giocatori: per loro sta fra le partite da
confermare. Lo scorer la può **annullare** finché nessuno dei due ha confermato,
anche a triangoli segnati; dopo la prima conferma no. Forfait, segnapunti a
mano, «Termina» e correzione delle impostazioni non si applicano.

## Alternative Considerate

### Alternativa 1: firma d'ufficio di chi segna

**Descrizione**: alla chiusura del referto lo scorer firma per conto dei due,
e la partita è subito confermata.

- **Pro**: nessuna attesa, nessuna colonna nuova.
- **Contro**: il livello *Confermata* dice «l'hanno garantita i due giocatori»
  (ADR-083). Un risultato che nessuno dei due ha visto non lo è.

### Alternativa 2: il rifiuto di uno toglie la partita a tutti e due

**Descrizione**: come la sfida normale, un rifiuto riapre o annulla.

- **Pro**: un solo stato per partita, livello di coppia.
- **Contro**: l'utente ha deciso il contrario: chi conferma se la tiene. E qui
  non c'è un punteggio da correggere fra i due — lo ha scritto un terzo.

### Alternativa 3: una colonna `declared_at` sulla partita

**Descrizione**: un timestamp «dichiarata» sulla sfida invece di guardare il
referto.

- **Pro**: query più semplici, l'ascoltatore dell'ELO la vede da solo.
- **Contro**: duplica `TpaReferto.closed_at`. L'ascoltatore di
  `models/rating/elo_tutte.py` guarda invece anche il referto che si chiude.

## Conseguenze

### Positive

- Un istruttore può raccogliere il TPA di una finale senza giocarla.
- La certificazione resta in un modulo solo, con una regola per persona e una
  per coppia, e i chiamanti la chiedono con la persona.

### Negative

- _(Superata dall'emendamento del 2026-10-18, che introduce `REJECTED`.)_ Una
  partita in cui uno conferma e l'altro rifiuta resta `in_progress` per
  sempre: non c'è uno stato «chiusa a metà». I livelli la leggono bene; gli
  elenchi la mostrano per quello che è, una partita con due decisioni diverse.
- Il TPA nelle partite di **gara** resta fuori: `TpaReferto` ha solo
  `individual_match_id`.

### Rischi

- Ogni nuova query sulle sfide «di un giocatore» deve passare la persona a
  `sfide_della_vista`: senza, applica la regola di coppia, e una partita
  confermata da A e rifiutata da B sparirebbe anche per A.

## Note Implementative

- Modello: `IndividualMatch.scorer_id`, `player1_rejected_at`,
  `player2_rejected_at`, `is_scored_by_third_party`, `is_declared_by_scorer`,
  `decision_of`, `awaits_decision_from`, `confirm_as_player`,
  `reject_as_player`, `cancel_by_scorer`; migration
  `migrations/20261017_partita_di_altri_due.py`.
- Servizio: `models/individual_match/scored_match_service.py`
  (`ScoredMatchService.can_score`, `start`).
- Route: `individual_match.scored_match` (modulo e creazione). Conferma,
  rifiuto e annullamento passano dalle route di sempre (`confirm_result`,
  `reject_result`, `cancel_match`), che riconoscono la partita di un terzo.
  `player_director_or_scorer` (`routes/individual_match/scored.py`) apre
  all'admin le sole route della partita che sta segnando.
- Presidi: `tests/new/unit/test_partita_di_altri_due.py`,
  `tests/new/integration/test_partita_di_altri_due.py`,
  `tests/new/unit/test_specifiche_conformita.py` (classe della partita di un
  terzo).

## Emendamento del 2026-10-18 — vale il rifiuto

**Decisori**: Paolo Coppola (utente), Claude

Sostituisce la regola «Conferma e rifiuto, per giocatore» per la parte del
rifiuto, la riga «almeno un rifiuto» della tabella dei livelli per persona,
la frase «Chi l'ha confermata se la tiene…», l'Alternativa 2 (che ora è la
decisione) e la prima conseguenza negativa. Cambia anche «Chi può segnare».

La decisione dell'utente: «Se in una partita segnata da un terzo uno conferma
e l'altro rifiuta, allora vale il rifiuto (tutti vengono notificati) e la
partita può essere modificata dal terzo o cancellata. Non compare ai due
giocatori.» E: «admin non dovrebbe segnare partite».

**Un rifiuto basta.** Se uno dei due rifiuta, prima o dopo la conferma
dell'altro, la partita passa a `MatchStatus.REJECTED` (valore `"rejected"`,
`reject_as_player`). È uno stato e non un fatto derivato dalle colonne
`player*_rejected_at`, perché la partita non deve più restare `in_progress`:
`REJECTED` non è né concluso né in corso, quindi ogni filtro su
`finished_values()`/`active_values()` — viste di certificazione, ELO, storico,
TPA, dashboard — la lascia fuori da solo. Le colonne restano e dicono chi ha
rifiutato e quando. La colonna è un `VARCHAR` a valori (`values_callable`),
senza vincolo: il valore nuovo non tocca i dati già scritti
(`test_enum_columns_store_values.py`).

**Non compare ai due giocatori.** `IndividualMatch.is_hidden_from(user_id)`:
vero per chiunque tranne lo scorer. Lo chiedono `match_detail` (che rimanda
alle sfide) e `TpaRefertoService.can_read`; `get_user_matches` la esclude, e da
lì passano «Le mie sfide», la dashboard delle sfide e le statistiche. Gli
avvisi in sospeso che portano alla partita scadono
(`ritira_gli_avvisi_in_sospeso`).

**Tutti vengono avvisati.** `avvisa_del_rifiuto`: all'altro giocatore e a chi
l'ha segnata, con la descrizione della partita, composti nella lingua di chi
riceve (ADR-062).

**Chi l'ha segnata corregge o cancella.** La vede fra «Partite che segni»,
marcata «Rifiutata», e ha due comandi, ciascuno col foglio che porta il nome
dell'azione (ADR-074):

* **Correggi la partita** (`ScoredMatchService.reopen` →
  `reopen_by_scorer`, route `individual_match.reopen_scored_match`): il
  referto si riapre, conferme e rifiuti si azzerano, la partita torna in corso.
  Richiudere il referto è la nuova dichiarazione, e i due ricevono di nuovo la
  richiesta di conferma. L'azzeramento è una scelta di default, non una
  richiesta esplicita dell'utente: senza, il rifiuto di prima varrebbe anche
  sul punteggio corretto;
* **Cancella la partita** (`cancel_by_scorer`): va a `CANCELLED` anche se uno
  dei due l'aveva confermata, e senza un secondo avviso.

Nessun altro può fare queste due cose.

**L'admin non segna.** `ScoredMatchService.can_score` è falso per l'admin,
anche col ruolo di istruttore: è la regola «l'admin non è un player». Il
decoratore `player_director_or_scorer` gli lascia solo le partite di cui è già
scorer, nate prima di questa data, perché nessun altro potrebbe chiuderle.

**Dati già scritti.** `migrations/20261018_partita_di_un_terzo_rifiutata.py`
porta a `rejected` ogni partita di un terzo ancora `in_progress` con un
rifiuto. È idempotente, e l'ELO non si muove: con la regola vecchia una
partita con un rifiuto era già fuori dall'ELO di tutti e due.

**Livelli, dopo l'emendamento.**

| Partita di un terzo, per il giocatore | Livello |
|---|---|
| l'ha confermata (o confermata da entrambi) | Confermata |
| dichiarata, non ha ancora deciso | In attesa |
| rifiutata da uno dei due, o non ancora dichiarata | nessuno, per tutti e due |

Presidi: `TestPartitaDiUnTerzo` in `test_specifiche_conformita.py`,
`tests/new/unit/test_partita_di_altri_due.py`,
`tests/new/unit/test_partita_di_un_terzo_rifiutata_migration.py`,
`tests/new/integration/test_partita_di_altri_due.py`,
`tests/new/e2e/test_partita_di_altri_due_e2e.py`.

## Riferimenti

- `docs/reference/SPECIFICHE.md`, «Ciclo di vita dei Match» e «Livelli di
  certificazione», note del 2026-10-17
- `docs/usecases/sfide-e-certificazione.md`, UC12
- ADR-044, ADR-051, ADR-069, ADR-083
