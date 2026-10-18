# [086] Chi si registra riscatta il proprio giocatore non registrato

**Data**: 2026-10-17
**Stato**: Accepted
**Decisori**: Paolo Coppola (decisioni di dominio), Claude (dettagli di implementazione)

## Contesto

L'ADR-085 ha introdotto i giocatori **non registrati**: li creano direttori e
istruttori, giocano partite vere, ma nessuno può entrare con loro. Mancava la
seconda metà: quando quella persona si registra, le sue partite devono
diventare sue. Lo strumento c'era già, `UserMergeService`, ma era riservato
all'admin. Bisognava decidere **chi conferma** che chi chiede è davvero quella
persona, **come ci si arriva** da una pagina pubblica senza account, e cosa
fare con i giocatori già presenti in produzione, che un creatore non l'hanno.

## Decisione

**La richiesta.** `ClaimRequest` (`models/user/claim_request.py`), sullo schema
di `RoleRequest` (ADR-041): `placeholder_id`, `claimant_id`, `status`
(`ClaimRequestStatus`: pending/approved/rejected, più withdrawn dall'emendamento del 2026-10-18), `decided_by_id`,
`decided_at`, più `created_at`/`updated_at`. I destinatari stanno in
`ClaimRequestRecipient`. Un indice UNIQUE **parziale**
`uq_claim_request_pending (placeholder_id) WHERE status = 'pending'` tiene
una sola richiesta in attesa per giocatore; le chiuse restano come storia.

**Chi decide** (`ClaimService.destinatari`, decisione dell'utente):

- il **creatore** del giocatore, se c'è ancora;
- altrimenti — giocatori storici senza creatore, o creatore cancellato —
  **solo l'admin**. La riserva vale anche per richieste già aperte
  (`puo_decidere` ricalcola i destinatari).

L'admin **non** decide i giocatori che hanno un creatore attivo: per quelli
gli resta l'unione manuale della pagina utenti, invariata.

**Chi non chiede.** Il creatore stesso, l'admin, un altro non registrato o un
fittizio; nessuno se il giocatore è già riscattato o ha una richiesta in
attesa. **Non** si chiede l'email verificata: chi decide vede nome utente,
email e se è verificata (`templates/riscatto/richiesta.html`).

**L'ingresso dalla vista pubblica.** La macro `riscatta(giocatore)` in
`components/_nome_giocatore.html` (chiamata da `nome_giocatore`) mostra «Sei
tu? Riscatta» accanto al segno «non registrato», a chi non è il giocatore né
il creatore e solo senza richieste in attesa (`puo_riscattare`, global Jinja
che guarda anche l'allowlist: una macro importata non vede i context
processor). Porta a `main.riscatta_giocatore` (`/giocatori/<id>/riscatta`,
aperta anche ad `anonimo`). Lì:

1. un anonimo ha **Accedi** e **Crea un account**: due POST con CSRF che
   salvano in sessione `riscatto_in_sospeso = {giocatore, scade}` (un'ora) e
   portano a `auth.login` o `auth.register` con `next` alla pagina stessa;
2. dopo `login_user`, `consuma_riscatto_in_sospeso` toglie la chiave e chiama
   `ClaimService.richiedi`: flash «Richiesta inviata a …» e redirect alla
   richiesta. Un solo gesto;
3. un utente collegato fa il POST direttamente;
4. un caso impossibile dà un flash e non crea niente.

La richiesta **non nasce mai da un GET**: un link preparato da altri la farebbe
partire all'insaputa di chi accede. La chiave in sessione scade e il logout la
toglie, perché in un browser condiviso non parta per il prossimo che entra.

**L'approvazione.** `ClaimService.approve` chiama
`UserMergeService.merge_users(placeholder, claimant, decider,
riscatto_approvato=True)`. Il controllo «solo admin» del merge è diventato
questo parametro esplicito, che solo il riscatto passa e che vale solo per una
sorgente non registrata e non ancora riscattata. Restano tutte le garanzie
del merge: partite fra i due → `ConflictError` e nulla scritto, iscrizioni
alla stessa gara fuse, ELO e classifiche ricalcolati, sorgente anonimizzata.
Poi `claimed_at` sul giocatore. Il merge **non riassegna**
`claim_request.placeholder_id` (`_KEEP_SOURCE_COLUMNS`): la richiesta continua
a dire chi è stato riscattato.

**Notifiche** (ADR-062, `lazy_gettext`): `CLAIM_REQUEST_RECEIVED` ai
destinatari, `CLAIM_REQUEST_PROCESSED` a chi ha chiesto.

**Le code.** `/riscatti` (`riscatto.richieste`): da decidere e fatte da me.
Ingressi: barra laterale (per i non admin solo se qualcosa aspetta), «I tuoi
ruoli», pagina admin utenti (che ora mostra anche il segno «non registrato»).

**Onboarding** (ADR-035). Un terzo passo facoltativo, nome e cognome. Se un non
registrato si chiama così — confronto in Python, senza accenti né maiuscole,
perché i campi sono cifrati con Fernet — dopo l'onboarding si apre
`riscatto.omonimi` («Hai già giocato in sala?»).

**Gli storici.** `scripts/mark_placeholder_users.py` (prova generale per
default, `--commit` per scrivere) segna `is_placeholder` chi ha almeno
un'iscrizione, nessuna riga `user_session`, `last_active_at` NULL,
`onboarding_completed` falso, e non è admin, fittizio, già non registrato o
cancellato (`models/user/placeholder_storici.py`). Senza creatore, li
riscatta solo l'admin.

**Correzione di passaggio.** `auth.register` non spediva la mail di verifica:
`create_user` preparava il token, ma `send_pending_verification_email` lo
chiamava solo la modifica del profilo. Ora la registrazione la spedisce —
serve a chi decide un riscatto, che guarda se l'email è verificata.

## Alternative Considerate

### Alternativa 1: richiesta creata da un GET su `next`

- **Pro**: nessuna chiave in sessione.
- **Contro**: un link del tipo `/auth/login?next=/riscatta/…/conferma` fatto
  girare da altri farebbe partire la richiesta all'insaputa di chi accede.

### Alternativa 2: email verificata obbligatoria

- **Pro**: un minimo di garanzia sull'identità.
- **Contro**: non dice niente su *chi* sia la persona — lo sa chi l'ha
  aggiunta in sala — e fino a oggi la registrazione la mail non la spediva.

### Alternativa 3: decide sempre l'admin

- **Pro**: un solo punto di controllo.
- **Contro**: l'admin non conosce chi gioca nelle sale; il creatore sì.
  Resta solo per chi un creatore non ce l'ha.

## Conseguenze

### Positive

- Le partite giocate senza account arrivano all'account vero con un gesto di
  chi chiede e uno di chi conferma.
- L'unione resta una sola, con le sue garanzie.

### Negative

- Una query per ogni non registrato disegnato in una pagina (memorizzata per
  richiesta HTTP), più un conteggio per i direttori a ogni pagina.
- Un utente storico segnato dallo script non entra più finché non lo si
  riscatta o non si toglie il segno a mano: per questo la prova generale
  stampa l'elenco.

### Rischi

- Un nuovo punto di login che non passi da `routes/auth.py::login` non
  consumerebbe la chiave: la richiesta non partirebbe (nessun danno, ma il
  gesto sparisce).
- Un nuovo chiamante di `riscatto_approvato=True` aggirerebbe il controllo
  dell'admin: lo passa solo `ClaimService.approve`.

## Note Implementative

- Migration `migrations/20261018_riscatto_giocatori.py` (presidio
  `tests/new/unit/test_migration_riscatto_giocatori.py`).
- Test: `tests/new/integration/test_riscatto_giocatori.py`,
  `tests/new/unit/test_specifiche_conformita.py::TestRiscattoDeiNonRegistrati`.
- Regola in `docs/reference/SPECIFICHE.md`, «Giocatori non ancora
  registrati» → «Il riscatto», nota del 2026-10-17.

## Emendamento 2026-10-18 — la richiesta si ritira

**Decisione dell'utente**: «la richiesta deve poter essere ritirata». Senza
ritiro, una richiesta sbagliata — il giocatore sbagliato, o un omonimo —
teneva fermo quel giocatore finché il creatore o l'admin non la rifiutava:
l'indice parziale ne ammette una sola in attesa, quindi nemmeno la persona
giusta poteva chiederlo.

- **Stato nuovo** `ClaimRequestStatus.WITHDRAWN` (`"withdrawn"`). La colonna è
  `String(20)`, non `db.Enum`, e l'indice `uq_claim_request_pending` guarda
  solo `status = 'pending'`: **nessuna migration**. Una richiesta ritirata
  esce dall'indice e il giocatore torna libero, anche per la stessa persona.
- **Chi ritira**: solo `claimant_id`, e solo finché è `pending`
  (`ClaimService.withdraw`). Il creatore e l'admin no: per loro c'è «rifiuta».
  Ritirata, la richiesta registra `decided_by_id = claimant_id` e
  `decided_at` al momento del ritiro: resta come storia.
- **Gli incroci**: ritirare una richiesta decisa → `ConflictError`; decidere
  una ritirata → `ConflictError` con un messaggio suo («l'ha ritirata chi
  l'aveva fatta»). La route `riscatto.decidi` lo mostra come flash.
- **Notifiche**: l'avviso `CLAIM_REQUEST_RECEIVED` di ogni destinatario si
  **segna letto** (`_risolvi_avvisi_ai_destinatari`). Il meccanismo non
  esisteva: lo stesso aiuto vale ora anche per conferma e rifiuto, perché con
  più admin uno decide e gli altri restavano con un «Decidi» acceso. In più
  ai destinatari arriva un avviso a priorità bassa,
  `CLAIM_REQUEST_WITHDRAWN`, composto con `lazy_gettext` nella lingua di chi
  riceve (ADR-062).
- **Interfaccia**: `POST /riscatti/<id>/ritira` (`riscatto.ritira`, in
  `ENDPOINT_ROLES` come le route sorelle). Il pulsante «Ritira la richiesta»
  sta nella pagina della richiesta e sotto ciascuna richiesta in attesa di
  «Le tue richieste», con `confirmSubmit` (ADR-074): tocca qualcun altro.
- Test: `tests/new/integration/test_riscatto_giocatori.py::TestRitiro`,
  `test_specifiche_conformita.py::TestRiscattoDeiNonRegistrati`.

## Riferimenti

- ADR-035 (onboarding), ADR-041 (richieste con destinatari), ADR-062
  (notifiche), ADR-074 (conferme), ADR-085 (giocatori non registrati).
- File: `models/user/claim_request.py`, `models/user/claim_service.py`,
  `models/user/merge_service.py`, `routes/riscatto.py`, `routes/auth.py`,
  `templates/riscatto/`, `templates/components/_nome_giocatore.html`.
