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

## Emendamento 2026-10-18 (sera) — la revisione delle partite

**Decisione dell'utente**: «se qualcuno riscatta l'utente, allora gli si può
chiedere se vuole rivedere tutti i match passati ed eventualmente contestarne
alcuni oppure riconoscerli tutti oppure contestarli tutti. I match contestati
rimangono all'utente che li ha registrati come contestati e contribuiscono a
ELO solo nel calcolo più generale.»

- **L'invito.** `ClaimService.approve` chiama `_invita_a_rivedere`, che
  sostituisce `_avvisa_delle_sfide_da_firmare`: **una** notifica
  (`MATCH_RESULT_TO_CONFIRM`, link `/match/revisione`), composta nella lingua
  di chi la riceve (ADR-062: titolo `lazy_gettext`, testo una funzione con
  `ngettext`), e solo se c'è qualcosa da rivedere.
- **Cosa si rivede** (`models/individual_match/revisione.py`,
  `RevisioneService.da_rivedere`): le sfide *registrate da uno* in cui l'utente
  è l'altro giocatore (`IndividualMatch.awaits_review_from`), e le partite di
  altri due che aspettano la sua decisione. Le partite di gara no: le
  certifica il torneo. Dopo l'unione non resta traccia di quali partite di
  altri due venissero dal non registrato, quindi la pagina mostra tutte quelle
  che aspettano la decisione dell'utente: per un utente appena registrato
  sono le stesse. _(Superato dall'emendamento della notte: ora la traccia si
  scrive all'approvazione.)_
- **I tre esiti** sono una chiamata sola, `RevisioneService.rivedi(user_id,
  rivedute, contestate)`: riconoscere tutte è `contestate` vuota, contestare
  tutte è `contestate == rivedute`, la scelta è a metà. La route
  `individual_match.review_matches` (`/match/revisione`, GET e POST, in
  `ENDPOINT_ROLES` per giocatori e direttori) traduce i tre pulsanti; la
  pagina di ogni sfida manda la stessa richiesta con una partita sola. I
  pulsanti passano da `confirmSubmit` (ADR-074): toccano chi l'ha registrata e
  non si disfano.
- **Riconosciuta** (`recognize_by`): la seconda firma arrivata tardi.
  `CONFIRMED_BY_BOTH`, livello *Confermata*, l'evento della doppia conferma
  che muove l'ELO globale; vincitore e data restano quelli della partita, e
  `recorded_by_id` resta scritto come storia.
- **Contestata** (`contest_by`): `contested_at`, stato invariato. Per chi l'ha
  registrata resta *In attesa* — vista *Tutte*, ``ELO_ALL`` — ed è segnata
  «Contestata» nella pagina, nell'elenco e nel profilo; riceve l'avviso «Sfida
  contestata» (`MATCH_CANCELLED`, nella sua lingua).
- **Default scelto: per chi l'ha contestata sparisce.** La regola non lo
  diceva; sparisce da liste, profilo, statistiche e pagina
  (`is_hidden_from`, `livello_di_sfida_per`, `sfide_della_vista(…,
  user_id=…)`, `IndividualMatch.non_contestate_da` nelle query delle
  statistiche e delle attività). L'ELO di *Tutte* resta di coppia, come
  dice l'ADR-083: la conta per tutti e due. È la scelta più semplice che
  rispetta «contribuiscono a ELO solo nel calcolo più generale»; separare
  l'ELO del solo registrante vorrebbe un motore a una gamba sola.
- **Partita di altri due** (ADR-084): riconoscere è `confirm_as_player`,
  contestare è `reject_as_player` con `avvisa_del_rifiuto` — le regole già in
  vigore, compreso il rifiuto che basta per tutti e due.
- **Default scelto: niente scadenza.** Le partite non rivedute restano come
  sono, *In attesa*, e la revisione non blocca niente: `PendingConfirmationService`
  guarda solo le sfide in corso. «Le mie sfide» mostra in cima quante ne
  restano. Una scadenza che le riconoscesse da sola sarebbe una firma data a
  nome di chi non l'ha data.
- **Ritiro durante la revisione.** Chi l'ha registrata può ritirarla finché
  non è riconosciuta; chi la stava rivedendo riceve l'avviso del ritiro.
- Test: `tests/new/integration/test_revisione_dopo_il_riscatto.py`,
  `test_specifiche_conformita.py::TestRevisioneDopoIlRiscatto`, l'e2e
  `test_sfida_avversario_non_registrato_e2e.py` (UC14 di
  `docs/usecases/sfide-e-certificazione.md`).

## Emendamento 2026-10-18 (notte) — quali partite erano del non registrato

**Difetto trovato dall'utente**: la pagina della revisione mostrava tutte le
partite di altri due che aspettavano una decisione di chi aveva riscattato,
non solo quelle che erano del giocatore riscattato. Dopo l'unione non restava
traccia di quali fossero: l'emendamento della sera lo aveva messo in conto
(«per un utente appena registrato sono le stesse»), ma chi riscatta può
essere registrato da tempo, e avere partite sue segnate da un istruttore.

- **La traccia.** Tabella nuova `claim_request_match` (`ClaimRequestMatch`:
  `request_id`, `individual_match_id`, unicità sulla coppia, `created_at` e
  `updated_at` di `BaseModel`), migration
  `migrations/20261018_partite_del_riscatto.py`. `ClaimService.approve` la
  scrive con `_annota_le_partite` **prima** di `UserMergeService`: le sfide
  *registrate da uno* contro il giocatore e le partite di altri due in cui
  era un giocatore, in qualunque stato. È la storia di cosa ha portato il
  riscatto; che una vada ancora rivista lo dice la sfida.
- **Scartata la colonna sulla sfida** (`riscattata_con_richiesta_id`): una
  partita di altri due fra **due** non registrati, riscattati da due persone,
  ne vorrebbe due, e la seconda approvazione cancellerebbe la prima.
- **La revisione** (`RevisioneService.da_rivedere`): le partite di altri due
  compaiono solo se sono annotate sotto un riscatto approvato dell'utente
  (`RevisioneService.riscattate`). Le registrate da uno restano tutte quelle
  che aspettano la sua revisione: si chiudono così solo contro un non
  registrato, quindi per un utente registrato vengono per forza da un
  riscatto o da un'unione dell'admin. Con `richiesta_id` la domanda è
  ristretta a un riscatto: è quella dell'invito, che conta le partite di quel
  giocatore e non di eventuali riscatti precedenti.
- **Default scelto per i riscatti approvati prima di questa correzione**: la
  traccia non si ricostruisce, perché l'unione ha già spostato le partite.
  Valgono le sole sfide registrate da uno; le partite di altri due non
  compaiono più nella revisione e si decidono dalla pagina di ciascuna, con
  conferma e rifiuto, come ogni partita di un terzo. È la scelta sicura: una
  partita di altri due mostrata per sbaglio si poteva rifiutare in blocco con
  «contesta tutte», e un rifiuto basta per tutti e due.
- Test: `tests/new/integration/test_revisione_dopo_il_riscatto.py::TestSoloLePartiteRiscattate`,
  `test_specifiche_conformita.py::TestRevisioneSoloDellePartiteRiscattate`,
  `tests/new/unit/test_migration_partite_del_riscatto.py`.

## Emendamento 2026-10-19 — l'email ricevuta basta, e la registrazione non rivela gli indirizzi

**Le segnalazioni dell'utente.** I giocatori non registrati possono avere
un'email vera: quella che avevano quando lo script degli storici li ha segnati
(`placeholder_storici.py`), o quella che l'admin ha scritto. Per loro la
registrazione rispondeva «email già in uso» — «non è compliant con GDPR dire
che c'è già un utente con quella email» — e il recupero password mandava un
link valido, ma il login li rifiutava anche con la password nuova: «non va
bene che sia bloccato».

**Decisione: un'email ricevuta con l'attivazione è la prova sufficiente.** Non
serve la conferma del creatore né dell'admin. Aprire un link mandato a quella
casella dimostra la stessa cosa che il recupero password dimostra per chiunque.
L'**Alternativa 2** («email verificata obbligatoria») era stata scartata perché
un'email non dice *chi* sia la persona: qui non serve dirlo, perché l'email è
quella del giocatore stesso, non di chi chiede.

- **L'attivazione** (`models/user/attivazione.py`, `AttivazioneService`):
  token `UserToken` di tipo nuovo `activation` — il nome lungo
  `placeholder_activation` non entra in `String(20)` —, 24 ore, uso singolo,
  e chiederne uno nuovo spegne i precedenti. Il link `/auth/attiva/<token>`
  (`auth.activate_account`, in `ENDPOINT_ROLES` per anonimo, giocatore e
  direttore) chiede nome utente, precompilato, e password. La stessa riga di
  `user` diventa un account normale: `is_placeholder` falso, `claimed_at`
  valorizzato, `is_verified` vero. **Nessuna unione**: le partite sono già sue.
  Dopo l'attivazione si entra dal login, come dopo un recupero password.
- **Chi si attiva**: `AttivazioneService.attivabile` — non registrato, non
  fittizio, non cancellato, non ancora riscattato, con un'email.
- **Due ingressi.** La registrazione con quell'email
  (`avvisa_registrazione_con_email_nota`) e il recupero password
  (`UserProfileService._prepara_reset_password`, che per un non registrato
  prepara l'attivazione invece del reset). In entrambi i casi il token nasce
  nella transazione e l'email parte dopo il commit, nella lingua di chi la
  riceve (`nella_lingua_di`, ADR-062).
- **La registrazione non rivela più niente.** Con un'email già presente la
  pagina risponde come a una riuscita: stesso flash, stesso redirect, stesso
  evento analytics, e un hash della password calcolato e buttato perché i
  tempi siano simili. Nessun account nasce. `create_user` solleva
  `EmailGiaRegistrata` (sottoclasse di `ValueError`, così chi crea utenti da
  script continua a vederla) e cerca l'email per `email_hash` invece di
  decifrare tutti gli utenti. All'indirizzo arriva l'avviso con i link al login
  e al recupero password se è di un account normale, il link di attivazione se
  è di un non registrato attivabile, niente altrimenti. Lo username già preso
  si dice ancora: è pubblico, e il messaggio non nomina l'email.
- **Default scelto: la richiesta di riscatto in attesa si chiude rifiutata.**
  L'attivazione ha la precedenza. *Ritirata* direbbe che l'ha ritirata chi
  l'aveva fatta, che non è vero; *rifiutata*, con `decided_by_id` uguale al
  giocatore stesso, dice esattamente cos'è successo — la persona vera ha detto
  no — e la pagina della richiesta lo mostra così senza toccare i template.
  Gli avvisi «Decidi» dei destinatari si spengono
  (`ClaimService._risolvi_avvisi_ai_destinatari`) e chi aveva chiesto riceve
  `CLAIM_REQUEST_PROCESSED` nella sua lingua.
- **Default scelto: da collegato, il cambio email nel profilo rifiuta un
  indirizzo già di un altro account**, con un messaggio che non dice di chi
  sia. Prima non c'era nessun controllo e nascevano due account con la stessa
  email, che si contendevano recupero password e attivazione. È una
  rivelazione limitata a chi è già collegato e identificato; l'alternativa —
  accettare in silenzio e mandare l'avviso al proprietario — lasciava il
  giocatore convinto di aver cambiato indirizzo.
- **Cosa resta uguale.** Il login continua a rifiutare i non registrati
  (ADR-085): la strada per entrare è l'attivazione, non una password scritta
  su un non registrato. Il riscatto con conferma del creatore resta per chi
  l'email del giocatore non ce l'ha.

- **I link delle email non vengono dalla richiesta** (dalla revisione di
  sicurezza della stessa PR). Verifica, recupero password, avviso e
  attivazione costruivano il link da `request.host_url`: con un `Host` o un
  `X-Forwarded-Host` falsificato, chi faceva partire l'email mandava alla
  vittima un link verso il proprio dominio, e aprendolo lei gli consegnava il
  token. Ora l'origine è `PUBLIC_BASE_URL` (`Config.environment_settings`,
  in produzione `https://www.torneibiliardo.it` se la variabile manca),
  letta da un solo punto, `utils/indirizzo_pubblico.indirizzo_per_le_email`.
  In sviluppo e nei test, senza valore, si ripiega sulla richiesta.

**Presidi.** `tests/new/integration/test_email_senza_rivelare.py` (risposta
identica, nessun account, contenuto delle email, attivazione e login con le
partite, recupero password, token scaduto o usato, richiesta pendente di un
altro, cambio email nel profilo, link sul dominio configurato con un `Host`
falsificato);
`tests/new/unit/test_specifiche_conformita.py::TestAttivazioneDallEmail`.
Regola in `docs/reference/SPECIFICHE.md`, «L'attivazione dall'email» e «La
registrazione non rivela gli indirizzi»; flussi in
`docs/reference/AUTHENTICATION.md`.

## Riferimenti

- ADR-035 (onboarding), ADR-041 (richieste con destinatari), ADR-062
  (notifiche), ADR-074 (conferme), ADR-085 (giocatori non registrati).
- File: `models/user/claim_request.py`, `models/user/claim_service.py`,
  `models/user/merge_service.py`, `models/user/attivazione.py`,
  `routes/riscatto.py`, `routes/auth.py`, `templates/auth/attiva_account.html`,
  `templates/riscatto/`, `templates/components/_nome_giocatore.html`.
