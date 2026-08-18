# ADR-046 Il beta tester vede in anticipo, non vede di più

**Data**: 2026-08-18
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

ADR-028 rende la visibilità degli endpoint in produzione **deny-by-default**:
una funzione nuova la vede solo l'admin finché qualcuno non la dichiara in
`ENDPOINT_ROLES`. È una buona regola e ha un costo preciso: **non si può far
provare niente a nessuno prima di aprirlo a tutti**. Chi scrive la funzione la
prova in sviluppo, dove l'allowlist è pass-through; chi dovrebbe dire se
funziona — un direttore, un giocatore — la incontra solo il giorno del
rilascio.

Serviva un modo per dare a **singole persone** l'accesso alle funzioni non
ancora aperte al loro ruolo, in produzione, sui dati veri.

La domanda difficile non era come farlo: era **fin dove**. «Vede tutto quello
che vede l'admin» è la lettura più semplice della richiesta, ed è anche quella
che mette la lista utenti — con email e telefoni di tutti gli iscritti —
l'unione degli account, l'anonimizzazione e la traccia degli accessi
(`user_session`) sotto gli occhi di qualcuno che era stato invitato a provare
una schermata.

## Decisione

Il beta tester è un **ruolo concedibile** di ADR-041
(`GrantableRole.BETA_TESTER`, tabella `role_grant`), non una colonna su
`User`: si concede, si revoca, e resta scritto chi l'ha concesso e quando.

In `is_endpoint_visible` non è un ruolo della matrice: è l'**ultimo controllo**,
dopo che tutti gli altri hanno detto di no.

```python
if not e_amministrazione(endpoint) and _e_beta_tester(user):
    return True
```

Cioè: **tutto quello che non è amministrazione**, comprese le voci dichiarate
`set()` — che in ADR-028 significa «chiusa per ora», non «riservata a chi
amministra». `help.hints_index` è il caso vivo: materiale per l'interfaccia
adattiva, che si aprirà ai player quando la consumeranno davvero.

«Amministrazione» è definita **dal decoratore, non dal nome**:

```python
def e_amministrazione(endpoint):
    vista = current_app.view_functions.get(endpoint)
    if vista is not None and getattr(vista, "_richiede_admin", False):
        return True
    return endpoint.startswith("admin.") or endpoint.rsplit(".", 1)[-1].startswith("admin_")
```

Il nome resta come seconda rete (schermate sotto `admin.` protette da altri
decoratori). Che la prima rete servisse davvero l'ha dimostrato subito il
presidio: tre endpoint — `rating.manage_handicap_rules`,
`rating.create_handicap_rule`, `rating.rating_statistics` — sono
`@admin_required` e **non** seguono la convenzione di nome. Con la sola regola
sul prefisso sarebbero finiti sotto gli occhi dei beta tester.

Il ruolo **non è propagante** (`self_propagating=False`) e **non si può
chiedere** (`request_feature_code=None`).

## Alternative Considerate

### Alternativa 1: bypass identico a quello dell'admin
- Pro: tre righe, nessuna nuova nozione.
- Contro: espone dati personali di terzi e azioni distruttive (merge,
  anonimizzazione) a chi è stato invitato a provare un'interfaccia. La
  richiesta era «vedere le funzioni», non «amministrare».

### Alternativa 2: un ruolo `beta` dentro `ENDPOINT_ROLES`
- Pro: nessun bypass, la matrice resta l'unica fonte, controllo massimo.
- Contro: ogni giro di prova richiede di toccare `feature_flags.py` e di
  ricordarsi di ripulirlo dopo. La funzione da provare è **quella che nessuno
  ha ancora dichiarato**: chiedere una dichiarazione per provarla riporta al
  problema di partenza.

### Alternativa 3: elenco esplicito di endpoint vietati ai beta tester
- Pro: controllo puntuale, nessuna convenzione da rispettare.
- Contro: è una blocklist. Una schermata amministrativa nuova nascerebbe
  **esposta** finché qualcuno non si ricorda di aggiungerla — esattamente
  l'errore che ADR-028 esiste per evitare. La regola strutturale, invece, la
  esclude da sola.

### Alternativa 4: colonna `is_beta_tester` su `User`
- Pro: una query in meno, nessuna dipendenza da ADR-041.
- Contro: nessun audit (chi l'ha concesso, quando, chi ha revocato), e una
  migration per una cosa che il meccanismo generico già fa. ADR-041 è nato per
  questo.

## Conseguenze

### Positive
- Si può far provare una funzione in produzione a una persona precisa, senza
  aprirla a una categoria.
- La revoca resta all'admin ed è immediata: il grant torna `revoked_at`, la
  visibilità sparisce alla richiesta dopo.
- La gamification si allinea **da sola**: `feature_visible_to_user` delega a
  `is_endpoint_visible`, quindi un beta tester riceve anche i nudge delle
  funzioni che vede — e nessun altro li riceve per sbaglio.
- Una schermata amministrativa nuova nasce esclusa senza che nessuno debba
  ricordarsene.

### Negative
- Una query in più per richiesta, e **solo** nelle richieste in cui almeno un
  link protetto avrebbe risposto «no». Memoizzata in `request.environ` (non su
  `g`: `g` vive quanto il contesto applicativo, che nei test è di sessione).
- La visibilità di un beta tester non è più leggibile dalla sola matrice: per
  sapere cosa vede bisogna sapere anche che è un beta tester.

### Rischi
- **Un endpoint amministrativo senza `@admin_required` e con un nome
  qualunque** sfuggirebbe a entrambe le reti. È il rischio residuo, ed è
  presidiato solo in parte: il test confronta i view function marcati con la
  classificazione, ma non può sapere che una schermata *dovrebbe* essere
  marcata. La difesa vera resta il decoratore.
- Visibilità non è autorizzazione: un beta tester che raggiunge una schermata
  trova comunque i decoratori. Se una schermata non ne ha ed era protetta solo
  dall'allowlist, adesso è raggiungibile — ed è la stessa esposizione che
  avrebbe avuto al momento del rilascio, ma prima.

## Note Implementative

- Ruolo: `models/user/role_enum.py` (`GrantableRole.BETA_TESTER`), policy in
  `models/user/role_grant_service.py` (`GRANT_POLICY`).
- Titolarità: `User.is_beta_tester` — a differenza di `is_examiner` **non** è
  vero d'ufficio per l'admin: vede già tutto per bypass, e dirlo lo stesso
  falserebbe l'elenco di chi sta provando.
- Visibilità: `utils/feature_flags.py` (`e_amministrazione`, `_e_beta_tester`,
  `is_endpoint_visible`).
- Marchio a runtime: `models/user/role_decorators.py` imposta
  `_richiede_admin` sui view function `@admin_required`.
- Concessione e revoca: le route generiche di ADR-041
  (`roles.grant_role` / `roles.revoke_role`), con i comandi nella lista utenti
  e nella scheda utente.
- Presidio: `tests/new/unit/test_beta_tester.py`.
