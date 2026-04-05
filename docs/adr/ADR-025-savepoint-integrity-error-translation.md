# [025] Savepoint + Flush per tradurre IntegrityError in ValueError

**Data**: 2026-04-05
**Stato**: Accepted
**Decisori**: PaCo, Claude

## Contesto

Il codebase ha diverse UNIQUE constraints a livello DB che possono essere violate in scenari TOCTOU (Time-Of-Check-Time-Of-Use) quando due richieste concorrenti superano entrambe il guard applicativo prima che la prima committi. Esempi concreti emersi dall'Edge Case Hunter review (commit `1d0a486`):

- `individual_match.proposal_id` UNIQUE: due utenti accettano la stessa `MatchProposal` OPEN → entrambi superano `can_be_accepted_by()`, entrambi tentano di creare un `IndividualMatch` con lo stesso `proposal_id`.
- `proposal_invitation(proposal_id, invited_user_id)` UNIQUE: doppio click, retry, o race su `invite_player_to_match` producono righe duplicate.

Quando la violazione scatta, SQLAlchemy solleva `IntegrityError` **al commit** (non al momento dell'`add()`), per via del flush differito. Questo causa due problemi:

1. **UX degradata**: il caller riceve uno `IntegrityError` con stacktrace DB-level ("UNIQUE constraint failed: individual_match.proposal_id") invece di un errore di dominio traducibile. Espone dettagli interni via JSON error responses.
2. **Ordine di gestione sbagliato**: il decorator `@transactional` intercetta l'eccezione in coda alla funzione, fa rollback, e rilancia l'errore grezzo. Il service non ha *dove* catturare l'errore per tradurlo, perché al termine del suo blocco il flush non è ancora avvenuto.

Serve un pattern ripetibile per **anticipare l'errore a flush-time dentro il service**, tradurlo in un `ValueError` di dominio, e lasciare che `@transactional` continui a fare il rollback esterno come di consueto.

## Decisione

Adottiamo il pattern **savepoint annidato + flush esplicito + traduzione errore**:

```python
from sqlalchemy.exc import IntegrityError
from flask_babel import _

try:
    with db.session.begin_nested():
        db.session.add(entity)     # o qualunque mutazione che possa violare il vincolo
        db.session.flush()          # forza la violazione a emergere QUI
except IntegrityError as exc:
    raise ValueError(_("Messaggio di dominio user-friendly")) from exc
```

**Regole di applicazione**:

1. Usare questo pattern in service methods decorati con `@transactional` quando un'operazione può violare una UNIQUE constraint.
2. Il `ValueError` risultante propaga fuori dal service; il `@transactional` esterno fa rollback dell'intera transazione — **questo è corretto**: non vogliamo persistere mutazioni parziali fatte prima del flush fallito.
3. Il savepoint non preserva lavoro "in più" (il rollback esterno avviene comunque): **serve solo a forzare l'IntegrityError a flush-time per poterlo catturare**.
4. Usare `from flask_babel import _` (non `lazy_gettext`) per messaggi che vengono valutati immediatamente al raise.

## Alternative Considerate

### Alternativa 1: Lock applicativo / SELECT FOR UPDATE

**Descrizione**: Acquisire un lock pessimistico sulla riga prima di operare.

- **Pro**:
  - Elimina la race condition a monte invece di gestirla a valle.
- **Contro**:
  - SQLite non supporta `SELECT FOR UPDATE`; solo single-writer a livello DB.
  - Aumenta latenza e contesa.
  - Richiede gestione timeout/deadlock.
  - Non protegge comunque contro violazioni di UNIQUE se il lock non copre esattamente la chiave.

### Alternativa 2: Catch IntegrityError nel decorator @transactional

**Descrizione**: Estendere `@transactional` per tradurre automaticamente `IntegrityError` in `ValueError`.

- **Pro**:
  - Centralizza la gestione.
- **Contro**:
  - Messaggio generico ("errore di integrità") — perde specificità semantica.
  - Ogni service avrebbe bisogno di mapping custom (quale constraint → quale messaggio).
  - Accoppia il layer transazionale alla semantica di dominio.

### Alternativa 3: Check pre-insert ("look before leap")

**Descrizione**: Prima di `add()`, fare `SELECT` per verificare che la chiave non esista già.

- **Pro**:
  - Errore utente-friendly senza toccare il session state.
- **Contro**:
  - **Non risolve TOCTOU**: tra SELECT e INSERT resta la finestra di race.
  - Doppia query su ogni insert → peggiora performance.
  - Crea falsa sicurezza.

### Alternativa 4: Savepoint + flush esplicito (SCELTA)

**Descrizione**: Wrap dell'operazione rischiosa in `db.session.begin_nested()` con `flush()` immediato, così `IntegrityError` è intercettabile nel service.

- **Pro**:
  - Il vincolo DB resta l'autorità ultima (defense in depth).
  - Nessuna race window: la violazione è impossibile da aggirare.
  - Traduzione dell'errore localizzata e specifica per ogni chiamata.
  - Funziona su SQLite e Postgres senza modifiche.
- **Contro**:
  - Boilerplate per ogni call site (mitigato: il pattern è meccanico).
  - Richiede che il service sia dentro un'outer transaction (ok: è sempre sotto `@transactional`).

## Conseguenze

### Positive

- Gli errori di integrità si presentano al client come `ValueError` di dominio con messaggio i18n-ready ("Proposta già accettata", "Giocatore già invitato a questa proposta").
- Il pattern è **idempotente rispetto al session state**: il savepoint rollbacka solo le mutazioni tentate nel blocco, lasciando la session in uno stato prevedibile per il `@transactional` esterno.
- La UNIQUE constraint DB-level resta la fonte di verità — impossibile da aggirare anche in caso di bug applicativi futuri.
- Riusabile ovunque: proposal invites, user emails, challenge naming, ecc.

### Negative

- Il pattern va applicato **a mano** in ogni call site interessato (no enforcement automatico).
- I model-layer `MatchProposal.accept` e `ProposalInvitation.accept` restano potenzialmente esposti a `IntegrityError` grezzo per chiamanti diretti: mitigato da docstring contract che obbliga i caller service-layer ad applicare il savepoint pattern (P5/P5b).

### Rischi

- Se un caller applica il pattern ma dimentica `flush()`, `IntegrityError` scatterà al commit del savepoint `begin_nested()` (all'uscita del with) — comportamento equivalente, quindi rischio basso.
- Se il `ValueError` non viene catturato dalla route, l'utente vede 500 invece di 400. Le route esistenti lo gestiscono via `safe_json_error`.

## Note Implementative

### Esempio canonico: `proposal_service.py`

```python
# accept_proposal (service decorated with @transactional)
if not proposal.can_be_accepted_by(user_id):
    raise ValueError("User cannot accept this proposal")

try:
    with db.session.begin_nested():
        individual_match = proposal.accept(user_id)
        db.session.flush()
except IntegrityError as exc:
    raise ValueError(_("Proposta già accettata")) from exc
```

### Esempio semplice: `invite_player_to_match`

```python
invitation = ProposalInvitation(
    proposal_id=proposal_id,
    invited_user_id=invitee_id,
    status=InvitationStatus.PENDING,
)
try:
    with db.session.begin_nested():
        db.session.add(invitation)
        db.session.flush()
except IntegrityError as exc:
    raise ValueError(_("Giocatore già invitato a questa proposta")) from exc
```

### Quando NON usarlo

- Se la UNIQUE non esiste a livello DB, aggiungerla prima (creare migrazione e `__table_args__`). Tradurre errori applicativi senza guard DB è fragile.
- Per violazioni di FOREIGN KEY o NOT NULL: quelle indicano bug, non race condition — vanno prevenute da validazione input, non tradotte.
- Se il caller è già fuori da `@transactional`: valutare se aggiungere il decorator invece di annidare savepoint manuali.

## Riferimenti

- Commit: `1d0a486` — implementazione iniziale per UNIQUE TOCTOU su individual match proposals
- File di riferimento:
  - `models/individual_match/proposal_service.py` — due applicazioni del pattern
  - `migrations/20260405_unique_constraints_toctou.py` — vincoli DB corrispondenti
  - `models/user/privacy_models.py:60-74` — precedente uso di `begin_nested()` + `IntegrityError` per get-or-create
- Test: `tests/new/integration/test_unique_constraints_toctou.py`
- Deferred (P5): estensione ai caller residui in `_bmad-output/implementation-artifacts/deferred-work.md`
- Correlati: `ADR-012-transactional-circular-import-fix.md` (contesto sul decorator `@transactional`)
