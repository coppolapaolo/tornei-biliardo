# ADR-063 L'admin viene scollegato dopo 30 minuti di inattività

**Data**: 2026-09-14
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Fino a oggi una sessione restava valida per sempre. Il login non usa
«ricordami», ma il cookie di sessione non ha scadenza lato server e nessun
controllo guarda da quanto tempo l'utente non fa niente. Su un telefono il
browser non si chiude mai davvero, e su un computer condiviso una scheda
dimenticata resta collegata finché qualcuno non la chiude.

Per l'admin è il caso peggiore: può fare tutto, dalle unioni di account alle
gare di chiunque.

Il 14/09 l'analisi dei log di produzione aveva mostrato l'effetto opposto — la
sessione dell'admin cadeva a ogni avvio dell'app per un difetto del bootstrap
(#421) — e correggerlo ha reso esplicita la domanda: se la sessione dell'admin
ora sopravvive ai riavvii, per quanto deve sopravvivere a chi se ne va?

Il prototipo 13a, nel blocco «Sessione», aveva già immaginato un avviso per
«30 minuti di inattività».

## Decisione

Un `before_request` (`utils/inattivita_admin.py`) scollega l'**admin** che non
apre pagine da più di `ADMIN_IDLE_TIMEOUT` (**30 minuti**, `config.py`).

- **Solo l'admin.** Direttori e giocatori restano come prima.
- **L'ultima attività sta nel cookie di sessione** (chiave
  `_admin_ultima_attivita`, secondi epoch), riscritta al più una volta al
  minuto.
- **I poll degli aggiornamenti live non contano come attività** (blueprint
  `sse`).
- Scaduto il limite: `logout_user()`. Una pagina va al login con un flash che
  lo spiega e con `next` verso dove si era — solo per i GET; un poll riceve
  401, e `static/js/polling.js` mostra «La sessione è scaduta» con «Accedi di
  nuovo» (#425).
- All'accesso l'orario riparte da adesso (segnale `user_logged_in`). Un admin
  già collegato senza la chiave — le sessioni aperte prima del deploy — viene
  preso in carico da adesso, non scollegato.

## Alternative Considerate

### Alternativa 1: limite per tutti

**Descrizione**: lo stesso controllo per ogni ruolo.

- **Pro**:
  - una regola sola.
- **Contro**:
  - un direttore gestisce la gara dal telefono con lunghe pause fra un turno
    e l'altro: verrebbe scollegato durante la gara;
  - i giocatori rifarebbero login quasi a ogni visita, e per loro il rischio
    di una sessione dimenticata è molto più basso.

### Alternativa 2: ultima attività in `user_session`

**Descrizione**: usare `last_seen_at` della tabella degli accessi.

- **Pro**:
  - il dato esiste già.
- **Contro**:
  - `user_session` è **analitica** e non autentica (ADR-055): il cookie non la
    consulta, e mescolare le due cose renderebbe le statistiche un meccanismo
    di sicurezza;
  - si aggiorna una volta al minuto con una scrittura sul DB; il controllo
    invece gira a ogni richiesta e nel cookie costa zero query.

### Alternativa 3: `PERMANENT_SESSION_LIFETIME` di Flask

**Descrizione**: sessione permanente con scadenza.

- **Pro**:
  - nessun codice nostro.
- **Contro**:
  - vale per tutti i ruoli;
  - con `SESSION_REFRESH_EACH_REQUEST` la scadenza si rinnova a **ogni**
    richiesta, poll compresi: una scheda aperta non scadrebbe mai. Senza, è
    una durata assoluta dal login, non un'inattività.

### Alternativa 4: i poll contano come attività

- **Pro**:
  - chi guarda una pagina live senza toccarla non viene scollegato.
- **Contro**:
  - è esattamente la scheda dimenticata che si vuole chiudere: il poller
    interroga il server ogni pochi secondi, per sempre.

## Conseguenze

### Positive

- Una sessione di admin dimenticata si chiude da sola dopo mezz'ora.
- Nessuna scrittura sul DB: il controllo legge e scrive solo il cookie.
- Il caso della pagina live aperta è già coperto dall'avviso di #425.

### Negative

- L'admin che tiene aperta una pagina live senza toccarla per più di 30 minuti
  viene scollegato. È voluto.
- Il cookie di sessione dell'admin viene rispedito al più una volta al minuto.

### Rischi

- **Nessun limite assoluto di durata**: un admin che apre una pagina ogni 29
  minuti resta collegato indefinitamente.
- **Il limite sta nel cookie**: firmato, quindi non falsificabile, ma un
  cookie rubato e usato subito resta valido fino al limite. È la difesa contro
  la sessione dimenticata, non contro il furto del cookie.
- Chiudere il browser non basta a proteggere sui telefoni, dove il browser
  non si chiude mai: è proprio il motivo del limite lato server.

## Note Implementative

- Orologio in `_adesso()` (`time.time()`): non `utc_now().timestamp()`, perché
  `utc_now()` è naive e `timestamp()` lo leggerebbe come ora locale.
- Il `before_request` è registrato subito dopo `load_user` in `create_app`,
  prima dell'allowlist (ADR-028) e dell'onboarding: un admin appena scollegato
  deve arrivare al login, non a un 404 dell'allowlist per anonimi.
- Test: `tests/new/integration/test_admin_uscita_inattivita.py`. Ogni
  richiesta ripulisce `g._login_user`, altrimenti Flask-Login usa l'utente in
  cache e il test passa sempre; l'orologio si sposta patchando `_adesso`, non
  `time.time`.

## Riferimenti

- ADR-055 (sessione legata alla credenziale; `user_session` non autentica)
- ADR-028 (allowlist degli endpoint)
- PR #421 (admin scollegato a ogni avvio), PR #425 (avviso di sessione scaduta)
- File correlati: `utils/inattivita_admin.py`, `config.py`, `app.py`,
  `static/js/polling.js`
