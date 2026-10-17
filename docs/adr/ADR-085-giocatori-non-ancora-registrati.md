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
- **non è un avversario delle sfide**: `User.can_access` gli dice sempre di
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
