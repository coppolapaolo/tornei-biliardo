# ADR-041 Ruoli concedibili: ortogonali a `user.role`, e delegabili a catena

**Data**: 2026-08-15
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Serviva la figura dell'**esaminatore**: chi compone esami e ne certifica di
persona l'esito. La domanda vera non era «come si chiama», ma **dove vive**.

Il progetto aveva già due modi di dire che qualcuno può fare qualcosa, e nessuno
dei due andava bene:

1. **`user.role`** — un campo a valore singolo (`admin` / `director` / `player`
   / `guest`). Aggiungerci `examiner` avrebbe costretto a una scelta: un player
   che diventa esaminatore smetterebbe di essere player, e quindi di iscriversi
   alle gare e sostenere esami altrui. È il contrario di quello che serve.
2. **`VenueManagement`** — l'assegnazione di un gestore a una sala, che invece
   ha la forma giusta: una tabella a parte, un `is_venue_manager` derivato, e il
   ruolo primario che resta quello che era. Il precedente esatto.

C'era però un secondo requisito, che nessuno dei due precedenti copre: il ruolo
doveva potersi concedere **anche fra pari**, non solo da admin. Il motivo è
pratico — a regime, se ogni esaminatore nuovo deve passare da admin, admin
diventa il collo di bottiglia di una funzione che dovrebbe diffondersi da sola.

E `DirectorRequest`, il workflow di promozione già esistente, non era riusabile:
l'approvazione è **hardcodata ad admin** (`permission_service.py:132-133`), e la
richiesta ha un solo destinatario implicito.

## Decisione

### Un grant ortogonale, non un quarto valore di `user.role`

`RoleGrant` è una tabella di concessioni: `user_id`, `role`, chi l'ha concesso,
quando, e se è stato revocato. `User.is_examiner` la interroga, esattamente come
`is_venue_manager` interroga `venue_management`. **Il ruolo primario non si
tocca**: un player che diventa esaminatore resta player.

`GrantableRole` è un enum **separato** da `UserRole`, e la separazione è la
sostanza: i ruoli primari sono mutuamente esclusivi, i concedibili sono
cumulabili. Tenerli nello stesso enum inviterebbe a confonderli.

### La catena è una proprietà del ruolo, non del meccanismo

```python
GRANT_POLICY = {
    GrantableRole.EXAMINER: GrantPolicy(
        self_propagating=True,
        request_feature_code="request_examiner",
    ),
}
```

`self_propagating` decide se un titolare può nominare altri titolari.
L'esaminatore sì; un ipotetico *venue manager* no, perché gestisce **una sala
specifica** e farlo decidere su sale altrui non avrebbe senso.

La domanda «chi può concedere cosa» ha quindi **una sola risposta in un solo
posto**, `RoleGrantService.can_grant`: admin, oppure un titolare se il ruolo è
`self_propagating`. Le route non contengono logica sui ruoli. Estendere a
`director` domani è una riga qui dentro.

### La revoca resta ad admin, e non è una svista

`can_revoke` è **separato** da `can_grant`. Con la propagazione a catena il
ruolo si diffonde senza controllo dall'alto: la revoca è l'unico punto di
contenimento rimasto, e darla anche ai pari significherebbe permettere a due
esaminatori di revocarsi a vicenda.

### La richiesta va a N destinatari, e il primo che approva chiude

`RoleRequest` + `RoleRequestRecipient`: la richiesta è una, i destinatari sono
quelli scelti dal richiedente (o tutti i titolari, se non sceglie). **Il primo
che approva concede il ruolo** e chiude la richiesta per gli altri, che ricevono
una notifica.

Nessun quorum, nessun secondo assenso: un quorum su un ruolo che si diffonde a
catena sarebbe un attrito senza una minaccia corrispondente — chi concede è già
un titolare, e chi sbaglia risponde all'audit.

### Indici UNIQUE **parziali**, non vincoli su colonne di stato

```sql
CREATE UNIQUE INDEX uq_role_grant_active
ON role_grant (user_id, role) WHERE revoked_at IS NULL;
```

Un solo grant attivo per utente/ruolo, ma **quante revoche si vuole**. Un
`UniqueConstraint(user_id, role, is_active)` su una colonna booleana — che è la
forma che `venue_management` ha oggi (`models/user/models.py:619-621`) —
ammetterebbe una sola riga revocata, e renderebbe impossibile la seconda revoca:
un bug latente che si manifesta solo quando qualcuno viene revocato due volte.

Stessa forma su `role_request`: `(user_id, role) WHERE status = 'pending'`.

## Alternative Considerate

### Alternativa 1: `examiner` come quarto valore di `user.role`

**Descrizione**: aggiungere il valore all'enum esistente.

- **Pro**:
  - Nessuna tabella nuova, nessun servizio nuovo.
  - Il gating esistente (`_user_role`, `ENDPOINT_ROLES`) funzionerebbe da subito.
- **Contro**:
  - **Un player che diventa esaminatore smette di essere player.** Non si
    iscriverebbe più alle gare e non sosterrebbe più esami altrui — che è il
    contrario del requisito.
  - Il ruolo non sarebbe cumulabile con `director`.
  - Sarebbe un cambio di semantica su un campo letto da mezzo progetto.

### Alternativa 2: estendere `DirectorRequest`

**Descrizione**: generalizzare il workflow di promozione già esistente.

- **Pro**:
  - Riuso di un percorso che gli utenti già conoscono.
- **Contro**:
  - L'approvazione è hardcodata ad admin, che è esattamente ciò da cui si voleva
    uscire.
  - Un solo destinatario implicito: la richiesta a N esaminatori non ci sta.
  - Migrare i dati esistenti sarebbe stato un prerequisito, non un contorno.

### Alternativa 3: grant generico **con scope** fin da subito

**Descrizione**: `scope_type` / `scope_id` sul grant, per assorbire anche
`VenueManagerRequest` (che è per-sala).

- **Pro**:
  - Un meccanismo solo per tutti i ruoli, presenti e futuri.
- **Contro**:
  - Nessuno dei ruoli **di oggi** ha bisogno dello scope: l'esaminatore è
    globale. Si pagherebbe complessità per un utente che non c'è ancora.
  - Lo scope va progettato guardando il caso reale, e il caso reale
    (`VenueManagerRequest` con `venue_id`, `is_contested`, `admin_notes`) ha
    forma sua. Indovinarlo prima è il modo di sbagliarlo.

## Conseguenze

### Positive

- Il ruolo è cumulabile: un esaminatore resta player, e può essere anche
  director.
- «Chi può concedere cosa» ha un solo punto di verità, e aggiungere un ruolo
  nuovo è una entry in `GRANT_POLICY`.
- L'audit della catena è completo: ogni grant sa da chi viene e quando.
- La revoca non cancella il lavoro svolto: gli esami composti e le
  certificazioni rilasciate da un ex esaminatore restano validi.

### Negative

- Due concetti di ruolo convivono (`UserRole` e `GrantableRole`), e chi legge il
  codice deve sapere quale sta guardando.
- `utils/feature_flags` ha dovuto passare da «un ruolo» a «un insieme di ruoli»:
  senza, un esaminatore che non è anche director ricadeva su `"player"` e
  perdeva in produzione gli endpoint dichiarati per `{"examiner"}`.

### Rischi

- **La propagazione è per sua natura senza freno dall'alto.** Il contenimento è
  la revoca, che resta ad admin, più l'audit. Se un giorno il ruolo si
  diffondesse troppo, la leva è `self_propagating = False` — una riga, senza
  migration.

## Note Implementative

`_grant_unchecked` è il corpo condiviso fra `grant`, `process_request` e
`debug_self_grant`, ed è **deliberatamente non decorato** con `@transactional`:
gira dentro la transazione già aperta dal chiamante. Annidare i decoratori causa
rollback silenziosi (vedi `models/transaction/CLAUDE.md`).

Il presidio TOCTOU sulla concessione è un savepoint attorno al flush, che fa
emergere la violazione dell'indice parziale e la traduce in `ConflictError`
invece di lasciarla uscire come 500 opaco (pattern ADR-025).

`debug_self_grant` (US-D1) ha **doppia guardia**: la route fa `abort(404)` fuori
da `DEBUG_MODE` — l'endpoint non deve nemmeno esistere in produzione — e il
servizio rifiuta comunque. Il grant creato è normale: revocabile e visibile
nell'audit con la nota `debug self-grant`.

## Emendamento del 2026-09-20 · la catena si vede, e l'admin la fa partire

Nato guardando la propagazione decisa per l'istruttore (ADR-069). L'utente:

> «va bene la propagazione, ma deve essere visibile chi ha nominato chi. Deve
> anche essere possibile per admin assegnare il ruolo, altrimenti non parte
> mai.»

Due difetti veri, e nessuno dei due era una svista del disegno: erano **buchi
fra il meccanismo e le schermate**.

**1 · Un ruolo nuovo non compariva dove lo si assegna.** I pulsanti «Rendi
esaminatore» e «Rendi beta tester» erano scritti a mano in due template
dell'amministrazione. Aggiungere un ruolo a `GRANT_POLICY` — che è tutto ciò
che l'ADR chiedeva di fare — non lo faceva comparire da nessuna parte, e senza
un primo titolare la catena non parte mai: `eligible_recipients` ripiega sugli
admin, quindi la *richiesta* funzionava, ma la concessione diretta no.

Adesso le due schermate ciclano su `GRANT_POLICY`
(`roles_view.azioni_ruoli`, `templates/components/_role_grant_actions.html`) e
i testi stanno in `models/user/role_copy.py`, uno per ruolo. `copy_for` ha un
**ripiego** per un ruolo senza voce: un pulsante sgraziato è un difetto, un
pulsante che non c'è è il difetto che stiamo correggendo.

**2 · La catena era persistita e invisibile.** `granted_by_id` si scrive dal
primo giorno, e `roles/holders.html` la mostra da sempre — ma **nessun
collegamento raggiungeva quella pagina** (l'unico `url_for('roles.role_holders')`
del repo stava dentro la pagina stessa) e la vedeva solo l'admin.

Adesso la leggono **l'admin e i titolari di quel ruolo**, ed è raggiungibile
dall'elenco utenti e dalla pagina «Ruoli» di chi il ruolo ce l'ha. Titolari *di
quel* ruolo: essere esaminatore non dà diritto a guardare gli istruttori. E
ciascuno vede, nella propria pagina «Ruoli», **chi ha nominato lui**.

Perché fin lì e non oltre: chi può nominare deve poter vedere da dove arriva un
collega — una catena che non si guarda è una delega al buio. Un allievo no: la
catena resta interna al mestiere, e pubblicarla accanto a ogni istruttore
significherebbe pubblicare una rete di relazioni a chiunque abbia una scheda.

**La revoca resta dell'admin** (US-A3), e il comando compare solo a lui:
`can_revoke` non è cambiato. Con la propagazione è l'unico punto di
contenimento, e i pari non devono potersi disfare a vicenda.

Presidio: `tests/new/integration/test_catena_delle_nomine.py`.

## Fuori scope

Migrare `DirectorRequest` e `VenueManagerRequest` sul nuovo meccanismo. Il primo
entrerebbe liscio (non ha scope); il secondo richiede uno `scope_type` /
`scope_id` che oggi non esiste. Meglio che il primo utente della macchina sia
uno solo, e che lo scope si progetti quando il meccanismo avrà girato.

## Riferimenti

- ADR-031 — i tre layer di gating; le responsabilità si gattano su metriche
  d'attività, mai sul livello
- ADR-028 — allowlist endpoint in produzione (`ENDPOINT_ROLES`)
- ADR-025 — traduzione di `IntegrityError` in eccezioni di dominio
- File correlati: `models/user/role_grant.py`, `models/user/role_grant_service.py`,
  `models/user/role_enum.py`, `routes/role_grant.py`,
  `migrations/20260809_add_role_grant_tables.py`, `utils/feature_flags.py`
