# [055] La sessione è legata alla credenziale

**Data**: 2026-08-26
**Stato**: Accepted
**Decisori**: Paolo Coppola, Claude

## Contesto

Il recupero password funzionava: token da 256 bit, usa-e-getta, scadenza a 24
ore, nessuna enumerazione degli iscritti, CSRF a posto, endpoint aperti agli
anonimi nella matrice ADR-028. Verificato percorrendo il flusso, non leggendolo.

Mancava però la cosa per cui, molto spesso, una persona resetta la password:
**buttare fuori chi è dentro**. Misurato — login con la vecchia password, reset,
e `/dashboard` rispondeva ancora `200`. Il cookie di Flask-Login porta il solo
`user.id` (`UserMixin.get_id()`), che il cambio password non tocca: una sessione
aperta da chi si era infilato nell'account sopravviveva indefinitamente alla
contromisura presa contro di lui. Nel codice il segnaposto c'era già:
`# Invalidate other sessions/tokens if needed (optional)`.

Nessuna di queste cose era coperta da un test. Il flusso di recupero password
non ne aveva **nessuno**.

## Decisione

`User.get_id()` non restituisce più il solo `id`, ma `id.impronta`, dove
l'impronta è un HMAC-SHA256 di `password_hash` con `SECRET_KEY`, troncato a 16
caratteri esadecimali. `load_user()` la verifica a ogni richiesta tramite
`User.from_session_id()`, con `hmac.compare_digest`.

Cambiare la password cambia `password_hash`, quindi l'impronta, quindi **ogni
sessione già aperta smette di valere** — senza tabelle nuove, senza migration e
senza stato da tenere allineato.

Tre scelte dentro la decisione:

- **HMAC e non un pezzo di `password_hash`.** Il valore viaggia in un cookie:
  un frammento di hash grezzo darebbe a chi lo intercetta materiale per un
  attacco offline sulla password. Un HMAC no, senza il segreto del server.
- **Nessuna compatibilità con il formato vecchio.** `from_session_id()`
  rifiuta l'id nudo. Al primo accesso dopo il rilascio, chi è loggato rifà il
  login una volta sola. Accettare l'id nudo avrebbe lasciato aperto proprio il
  buco che si sta chiudendo, per tutti i cookie emessi finora.
- **Chi cambia la propria password resta dentro.** L'effetto collaterale —
  autologout un istante dopo il cambio, dal proprio profilo — è neutralizzato
  rinnovando il cookie con `login_user()` in `routes/player/profile.py`. Le
  *altre* sessioni cadono lo stesso, che è il comportamento voluto.

Insieme, altre tre correzioni allo stesso flusso:

1. **L'email parte dopo il commit.** `EmailService` spedisce in un thread;
   partendo da dentro la transazione, un commit fallito lasciava in mano
   all'utente un link verso un token mai scritto. La preparazione sta ora in
   `_prepara_reset_password` (`@transactional`) e l'invio fuori — che è già il
   pattern di `create_user`/`send_pending_verification_email`, applicato qui
   per la prima volta.
2. **L'esito dell'invio si riferisce.** `request_password_reset` scartava il
   valore di ritorno: con la posta rotta o non configurata, il recupero era
   morto e il sito rispondeva «riceverai un link» esattamente come quando
   funzionava. Ora l'errore finisce nei log (GlitchTip) e l'utente lo legge.
   Il ramo `else` della route esisteva già: era solo irraggiungibile.
3. **Una richiesta nuova disattiva le precedenti.** Tre richieste lasciavano
   tre link validi per 24 ore. Chiederne uno nuovo è spesso il gesto di chi
   teme che il primo sia finito dove non doveva.

E due minori: un reset riuscito segna l'email come verificata (chi ha letto il
link ha dimostrato di controllare la casella — e al login gli si diceva «senza
email confermata non potrai recuperare la password», a lui che l'aveva appena
fatto); i cinque `flash()` della route passano da `_()`.

## Alternative Considerate

### Alternativa 1: una colonna `auth_epoch` da incrementare

**Descrizione**: un intero su `User`, incrementato a ogni cambio password, che
entra in `get_id()`.

- **Pro**: esplicito, leggibile, indipendente dall'algoritmo di hashing.
- **Contro**: richiede una migration — e una PR con migration **non fa partire
  il reload** in produzione (CLAUDE.md, CI/CD punto 1); soprattutto è uno stato
  in più da ricordarsi di aggiornare a ogni punto che tocca la password. La
  derivazione da `password_hash` non si può dimenticare: è la password stessa.

### Alternativa 2: revocare le righe di `user_session`

**Descrizione**: chiudere le sessioni dell'utente nella tabella `user_session`.

- **Contro**: **non funzionerebbe.** `user_session` è una tabella analitica —
  misura le permanenze sul sito — e non ha parte nell'autenticazione: il
  cookie non la consulta. Chiuderne le righe cambia le statistiche e lascia
  l'intruso esattamente dov'è. Vale la pena scriverlo perché il nome invita a
  credere il contrario.

### Alternativa 3: sessioni server-side

- **Pro**: revoca puntuale, elenco dei dispositivi attivi, logout da remoto.
- **Contro**: sproporzionato. Storage delle sessioni, scadenze, pulizia — su
  PythonAnywhere con SQLite su NFS, dove ogni scrittura in più è un rischio
  già documentato (ADR-045).

## Conseguenze

### Positive

- Cambiare la password fa ciò che chi la cambia si aspetta.
- Vale per **ogni** cambio password: reset via email, cambio dal profilo,
  password impostata dall'amministratore.
- Il flusso ha finalmente dei test: dodici, in
  `tests/new/integration/test_recupero_password.py`.

### Negative

- Al primo accesso dopo il rilascio **tutti rifanno il login**, una volta.
- Chi scrive test non può più fingere una sessione con `sess["_user_id"] =
  str(user.id)`: serve `user.get_id()`. Erano 57 punti in 24 file, tutti
  aggiornati; il conftest lo dice in un commento.

### Rischi

- Se `SECRET_KEY` cambia, tutte le sessioni cadono. Era già così — il cookie è
  firmato con quella chiave — quindi non è un peggioramento.
- `auth_fingerprint()` richiede un application context. Lo ha sempre, essendo
  chiamata da Flask-Login dentro una richiesta.

## Note Implementative

```
models/user/models.py      auth_fingerprint(), get_id(), from_session_id()
app.py                     load_user() -> User.from_session_id(...)
models/user/profile_service.py   _prepara_reset_password() + request_password_reset()
routes/auth.py             messaggi tradotti, esito dell'invio riferito
routes/player/profile.py   login_user() dopo il cambio password
tests/new/integration/test_recupero_password.py   dodici casi
```

**Una trappola per chi scriverà test qui.** In questa suite `g` non è
per-richiesta: sopravvive fra due `client.get()`, quindi Flask-Login trova
l'utente già in cache e **non richiama mai `load_user`**. Un test sulla
validità della sessione scritto senza saperlo passa sempre — anche con il
controllo dell'impronta rimosso, verificato sabotandolo apposta. Da qui
l'elicottero `_simula_richiesta_nuova()`, che cancella `g._login_user` prima
della verifica.

## Riferimenti

- File correlati: `models/user/models.py`, `app.py`,
  `models/user/profile_service.py`, `routes/auth.py`
- ADR-028 (gli endpoint di recupero sono aperti agli anonimi), ADR-045 (perché
  non si aggiunge stato su disco a cuor leggero)
