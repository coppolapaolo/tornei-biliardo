# [085] Direttori e istruttori creano giocatori non ancora registrati

**Data**: 2026-10-17
**Stato**: Accepted
**Decisori**: Paolo Coppola (decisioni di dominio), Claude (dettagli di implementazione)

## Contesto

In sala arriva chi vuole giocare la serata e non si è mai registrato. Fino a
oggi il direttore aveva una strada sola: «crearglielo insieme», cioè fermarsi
a registrare un account dal telefono del giocatore, con email e password. Lo
stesso succede all'istruttore che segna la partita di altri due (ADR-084): uno
dei due giocatori spesso un account non ce l'ha.

Servono giocatori che **giocano davvero** — iscrizioni, partite, classifiche,
ELO — ma che nessuno può usare per entrare nell'app, finché la persona non si
registra e li **riscatta** (PR successiva: `ClaimRequest`, pulsante «Sei tu?
Riscatta» nelle pagine pubbliche, script sugli utenti storici).

L'app conosce già un utente senza login: il **fittizio** della competizione
di prova (ADR-058). Ma il fittizio è l'opposto di quello che serve qui: vive e
muore con la sua prova, si cancella fisicamente, è invisibile fuori dalla
prova e il motore di rating lo ignora.

## Decisione

Un giocatore non registrato è un `User` normale con tre colonne in più:

| Colonna | Significato |
|---|---|
| `is_placeholder` (bool, indicizzata) | gioca, ma nessuno ha ancora l'account |
| `created_by_id` (FK `user.id`, `SET NULL`) | chi l'ha creato: è lui che confermerà il riscatto |
| `claimed_at` (datetime) | quando è stato riscattato; NULL finché nessuno lo reclama |

Nasce con **email NULL**, `password_hash = PASSWORD_DA_RISCATTARE`
(`"!da-riscattare!"`, che non è un hash di Werkzeug e non verifica nessuna
password), `onboarding_completed=True`, `is_verified=False`, `role=player`,
nome e cognome nell'anagrafica cifrata, username = «Nome Cognome» reso unico
(«Mario Rossi (2)», `models/user/username_libero.py`, la stessa regola dei
fittizi).

**Chi lo crea.** `UserProfileService.can_create_placeholder`: admin,
direttore o istruttore. Il servizio è `UserProfileService.create_placeholder`
(delegato da `UserService.create_placeholder`), `@transactional(domain="user")`.
Due ingressi:

1. **iscrizione da direttore**: «Nuovo giocatore non registrato» sotto la
   ricerca degli iscrivibili (`components/_gara_inscriptions.html`), route
   `admin.competition.admin_inscribe_placeholder`,
   `InscriptionService.iscrivi_non_registrato` (creazione e iscrizione in una
   transazione, ADR-061; non in una prova);
2. **partita di altri due**: «Non ha un account? Aggiungilo» sotto ciascun
   posto (`individual_match/scored_match.html`); il posto arriva al servizio
   come `NuovoGiocatore(first_name, last_name)` e
   `ScoredMatchService._giocatore` lo crea, con `scorer` come creatore.

**Cosa non fa.** Ogni guardia sta in un punto solo:

- **non entra**: `authenticate_user` (entrambe le copie) e
  `User.from_session_id` lo rifiutano anche se qualcuno gli impostasse una
  password;
- **non riceve notifiche**: `NotificationService.create_notification`
  restituisce `None` prima di tutto il resto — non solo perché non le
  leggerebbe, ma perché al riscatto passerebbero al nuovo account;
- **non è un avversario delle sfide** _(superato in parte dall'emendamento
  del 2026-10-18: lo è nell'avvio rapido)_: `User.can_access` gli dice sempre di
  no, quindi la ricerca normale, l'elenco degli avversari e l'avvio rapido lo
  escludono; `ProposalService.create_direct_proposal` rifiuta l'invito con un
  `ValidationError`. Lo trova solo la ricerca `ambito=altri_due`, che
  restituisce anche `is_placeholder`;
- **non firma**: nella partita di altri due la sua decisione resta assente,
  quindi per lui la partita è *In attesa* (`livello_di_sfida_per`, ADR-084) e
  la partita conta nella vista *Tutte* dell'ELO finché nessuno la rifiuta.

**Cosa fa come tutti**: iscrizioni, partite di gara, classifiche, ELO,
gamification. Non è un fittizio e i filtri dell'ADR-058 non lo toccano.

**Il segno visibile.** `templates/components/_nome_giocatore.html` ha due
macro: `nome_giocatore(giocatore)` (nome + segno) e
`badge_non_registrato(giocatore)` (il solo segno, `c7-state c7-nonreg`).
Accettano un `User` o un dizionario di classifica (Jinja legge
`username`/`is_placeholder` da entrambi; la classifica generale porta ora
`is_placeholder` nel suo dizionario). Oggi le usano: iscritti e iscrivibili
della gara, classifica della gara (mobile e dettagliata), classifica generale
del campionato, profilo. Il «Sei tu? Riscatta» della PR del riscatto si
aggiunge **dentro** queste macro.

**Unione.** `UserMergeService.merge_users` accetta un non registrato come
sorgente — rifiuta solo admin e fittizi — ed è la strada del riscatto. In più
riassegna `user.created_by_id`: se si uniscono due account di un creatore, i
non registrati che aveva creato passano al destinatario, che sarà chi conferma.

## Alternative Considerate

### Alternativa 1: riusare il fittizio dell'ADR-058

**Descrizione**: `is_fittizio=True` fuori da una prova.

- **Pro**: nessuna colonna nuova.
- **Contro**: il fittizio è invisibile fuori dalla sua prova, il rating lo
  ignora, si cancella con la prova e il merge lo rifiuta. Sarebbe servito
  rovesciare ognuna di queste regole con un'eccezione.

### Alternativa 2: account vero con email inventata

**Descrizione**: `nome.cognome@segnaposto.invalid` e password casuale.

- **Pro**: nessuna colonna nuova, il codice non sa niente.
- **Contro**: niente distingue l'account da uno vero: le notifiche partono,
  l'utente compare fra gli avversari, il riscatto non sa a chi chiedere
  conferma, e il segno «non registrato» non si può disegnare.

### Alternativa 3: tabella a parte per i giocatori senza account

**Descrizione**: un `GuestPlayer` referenziato da iscrizioni e partite.

- **Contro**: ogni FK verso `user` (più di cento) diventerebbe doppia.

## Conseguenze

### Positive

- Il direttore iscrive chi è in sala in un gesto, l'istruttore segna la
  partita di chiunque.
- Le partite sono vere fin da subito: il riscatto le sposta, non le ricrea.
- La PR del riscatto non tocca più lo schema di `user`.

### Negative

- Una query in più per ogni notifica (`_non_registrato`): una SELECT su
  chiave primaria.
- Un direttore può creare due volte la stessa persona: la ricerca degli
  iscrivibili la mostra col segno, ma non c'è una deduplicazione automatica
  (nome e cognome sono cifrati e non si confrontano in SQL).

### Rischi

- Un nuovo percorso di login che non passa da `authenticate_user` né da
  `from_session_id` farebbe entrare un non registrato. Presidi:
  `tests/new/integration/test_giocatori_non_registrati.py` e
  `tests/new/unit/test_specifiche_conformita.py::TestGiocatoriNonRegistrati`.

## Note Implementative

- Migration `migrations/20261017_giocatori_non_registrati.py` (idempotente,
  presidio `tests/new/unit/test_migration_giocatori_non_registrati.py`).
- Regola in `docs/reference/SPECIFICHE.md`, «Tipologie di utenti» →
  «Giocatori non ancora registrati», nota del 2026-10-17.

## Riferimenti

- ADR-058 (fittizi della prova), ADR-061 (transazioni annidate), ADR-062
  (notifiche nella lingua di chi riceve), ADR-084 (partita di altri due).
- File correlati: `models/user/models.py`, `models/user/profile_service.py`,
  `models/user/username_libero.py`, `models/user/merge_service.py`,
  `models/notification/services.py`,
  `models/individual_match/scored_match_service.py`,
  `models/competition/inscription_service.py`,
  `templates/components/_nome_giocatore.html`.

## Emendamento (2026-10-17)

Il riscatto è arrivato con l'**ADR-086**: `ClaimRequest`, il pulsante «Sei tu?
Riscatta» dentro `nome_giocatore` (macro `riscatta`), la conferma del creatore
o dell'admin per i giocatori senza creatore. `merge_users` non è più solo
dell'admin: lo è ancora, tranne quando lo chiama `ClaimService.approve` con
`riscatto_approvato=True`.

## Emendamento (2026-10-18): l'avversario di una sfida

**La segnalazione.** «Non posso prendere il TPA di una mia partita che vedo
su YouTube con un altro giocatore che non è iscritto. Se scrivo che voglio
prenderla per altri due non mi trovo, mentre se dico che è una mia partita
non posso aggiungere un esterno.» La regola del 2026-10-17 — *non è un
avversario delle sfide* — chiudeva l'unica strada: la partita di altri due
esclude chi segna, e l'avvio rapido escludeva il non registrato.

**Decisione.** Nell'**avvio rapido** l'avversario può essere un giocatore
non registrato.

- **Chi lo sceglie.** Chiunque possa aprire una sfida, se il giocatore esiste
  già: `QuickMatchService.can_be_opponent` accetta chi ha sbloccato le sfide
  **oppure** è non registrato (non i fittizi dell'ADR-058). La regola del
  2026-10-17 lo negava a tutti per una ragione sola — «non può ricevere una
  sfida a cui non saprebbe rispondere» — che con l'avvio rapido non vale: la
  partita nasce in corso e non va accettata. Nel codice nessun'altra regola
  distingueva un giocatore senza ruolo da un direttore per questa scelta.
- **Chi lo crea.** «Non ha un account? Aggiungilo» sotto la ricerca, con nome
  e cognome, solo per `QuickMatchService.can_create_opponent`:
  `can_create_placeholder` **meno l'admin**, che comunque non entra
  nell'avvio rapido (`player_or_director_required`). Il posto arriva al
  servizio come `NuovoGiocatore`, come nella partita di altri due, e
  `QuickMatchService.start` lo crea nella stessa transazione della partita;
  il blocco di `ensure_none_pending` si controlla **prima**, così un giocatore
  non nasce per una sfida che non parte.
- **La ricerca.** `search_players?ambito=sfida` restituisce anche i non
  registrati, con `is_placeholder`; il modulo li segna «non registrato», come
  la ricerca `ambito=altri_due`. Gli avversari abituali e il preselezionato di
  «Rigioca adesso» passano dallo stesso `can_be_opponent`.
- **La proposta no.** `ProposalService.create_direct_proposal` continua a
  rifiutare l'invito: una proposta si accetta, e da un non registrato la
  risposta non arriva. La ricerca senza `ambito` resta senza non registrati,
  «Proponi un'altra data» sparisce dalla sfida contro di lui e `rematch`
  porta all'avvio rapido.
- **Le firme.** Il non registrato non firma: `IndividualMatch.firma_d_ufficio`
  sostituisce `confirm_result` nelle due firme automatiche alla distanza
  (segnapunti e referto TPA) e, se toccava a lui, firma l'altro — chi ha
  aperto la sfida e la segna. La sfida resta allora *In attesa*
  (`livello_di_sfida`, ADR-083) e conta per l'ELO di *Tutte* come ogni sfida
  in attesa che non sia un pareggio: nessuna regola nuova.
- **Nessun blocco.** La sfida aspetta la firma del non registrato
  (`awaiting_confirmation_from_id`): il blocco di `PendingConfirmationService`
  guarda solo chi deve firmare, quindi chi l'ha aperta gioca ancora — anche
  contro di lui — e la può ritirare (`withdraw_by_signer`). Per l'interfaccia
  la sfida è `aspetta_il_riscatto`: fuori subito dalle sfide in corso della
  dashboard e dalla sezione «In attesa di conferma» di `/match/`, fra le
  giocate dell'elenco con lo stato «In attesa del riscatto», e nella sua
  pagina un riquadro che lo spiega al posto di «manca la conferma».
- **Le notifiche.** Nessuna al non registrato: `create_notification` le
  scartava già, e `QuickMatchService` non chiama nemmeno l'avviso di
  apertura.
- **Dopo il riscatto.** `UserMergeService` sposta la partita sull'account di
  chi ha riscattato: la firma che manca è la sua, e la sfida è come qualunque
  altra — lo blocca finché non la conferma o la rifiuta. `ClaimService.approve`
  gli manda l'avviso «Una sfida aspetta la tua firma» per ciascuna
  (`_avvisa_delle_sfide_da_firmare`), che al non registrato non era mai
  arrivato. Il giorno di grazia della dashboard (`DASHBOARD_GRACE`) si conta
  ancora dalla firma di chi l'ha aperta: una sfida riscattata dopo più di un
  giorno non torna fra le sfide in corso della dashboard, e si trova nella
  sezione «In attesa di conferma» di `/match/` e nell'avviso.

**Presidi.** `tests/new/unit/test_specifiche_conformita.py::TestAvversarioNonRegistrato`
e `TestGiocatoriNonRegistrati::test_non_riceve_proposte_ma_si_sfida_con_l_avvio_rapido`,
che sostituisce il test della regola vecchia;
`tests/new/integration/test_avversario_non_registrato.py`;
`tests/new/e2e/test_sfida_avversario_non_registrato_e2e.py`, UC13 di
`docs/usecases/sfide-e-certificazione.md`.
