# ADR-064 Chi accede resta collegato su quel dispositivo per trenta giorni

**Data**: 2026-09-17
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Il 16/09/2026, alla terza gara della Ronin Cup, il direttore ha dovuto rifare
l'accesso dal telefono **a ogni apertura dell'app**, in sala e a gara in
corso. A ogni login partivano i suggerimenti di due gestori di password —
quello di Chrome e quello di iOS — e nessuno dei due proponeva l'utente
giusto.

La causa stava nel codice ed era una scelta, non un guasto: `login_user` era
sempre chiamato senza durata e `session.permanent` non veniva mai impostato,
quindi il cookie di sessione nasceva **senza scadenza**. Un cookie senza
scadenza vive quanto decide il browser. L'ADR-063 partiva dall'idea che «su un
telefono il browser non si chiude mai davvero»; su iOS è vero il contrario:
il sistema termina schede e web app installate appena gli serve memoria, e
con loro butta i cookie di sessione.

Due precisazioni su ciò che si vedeva:

* l'app **non ha passkey**: nel repository non c'è una riga di WebAuthn. I due
  prompt sono i gestori di password, agganciati ai campi `autocomplete` del
  form. Non si tolgono da qui; si smette di farli comparire smettendo di
  chiedere il login;
* l'app installata sulla schermata Home ha un archivio di cookie **separato**
  da Safari e da Chrome: l'accesso fatto nel browser non vale lì, e viceversa.

## Decisione

Il form di login porta la casella **«Resta collegato su questo dispositivo»**,
spuntata per default. Con la spunta la sessione diventa *permanent* e il
cookie scade dopo `PERMANENT_SESSION_LIFETIME` = **30 giorni** (`config.py`).
Senza spunta resta un cookie di sessione, come prima.

Due scelte non ovvie, entrambe in `utils/sessione_duratura.py`:

1. **`SESSION_REFRESH_EACH_REQUEST = False`.** La sessione di Flask sta nel
   cookie firmato, non sul server. Il default rimanda il cookie a ogni
   risposta, e con i poll ogni tre secondi una risposta partita prima e
   arrivata dopo riscriverebbe la sessione con lo stato vecchio: un messaggio
   flash che ricompare, l'ultima attività dell'admin che torna indietro.
2. **La scadenza si rinnova al più una volta al giorno**, e solo sulle pagine.
   Chi usa l'app non viene mai scollegato; chi la lascia per un mese sì. I
   poll non contano, come nell'ADR-063: una scheda dimenticata aperta non deve
   tenersi viva da sola.

L'**admin** resta sotto l'ADR-063. Il cookie dura trenta giorni anche per lui,
ma dopo mezz'ora senza aprire pagine la sessione cade comunque: i due
controlli convivono, e il più stretto vince.

## Alternative Considerate

### Il cookie «ricordami» di Flask-Login (`login_user(remember=True)`)

Un secondo cookie, con la sua configurazione (`REMEMBER_COOKIE_*`) e il suo
ciclo di vita, che ricrea la sessione quando manca. Scartato: due cookie che
autenticano sono due cose da invalidare, e la sessione ricreata perderebbe
ciò che ci vive dentro — il token CSRF legato alla sessione (ADR-050),
l'ultima attività dell'admin (ADR-063). L'impronta della credenziale
(ADR-055) vive già nell'id di sessione: con la sessione *permanent* continua
a valere senza toccare niente.

### Nessuna casella, tutti collegati per trenta giorni

Più semplice, ma toglie la scelta proprio a chi accede dal computer della
sala o dal telefono di un amico. La casella costa una riga di form e nasce
spuntata: chi non la guarda ottiene il comportamento comodo.

### Lasciare il rinnovo a Flask (`SESSION_REFRESH_EACH_REQUEST = True`)

Scadenza che scorre senza scrivere codice. Scartato per la corsa fra
risposte descritta sopra, e perché avrebbe aggiunto un `Set-Cookie` a ogni
poll.

### Scadenza fissa, senza rinnovo

Trenta giorni esatti dal login. Scartato: prima o poi il trentesimo giorno
cade su una sera di gara.

## Conseguenze

### Positive

* Sul telefono si accede una volta, e poi per un mese dall'ultimo uso.
* I prompt dei gestori di password compaiono solo quando serve davvero.
* Le statistiche di permanenza erano già pronte: `UserSessionService.segna_vivo`
  chiude la sessione analitica dopo una pausa lunga proprio pensando a questo
  caso, e la sincronizzazione del fuso (ADR-043) copre la sessione ripresa.

### Negative

* Un dispositivo perso o prestato resta collegato fino a trenta giorni. I
  rimedi esistono già: **cambiare password** fa cadere ogni sessione aperta
  (ADR-055), e «Esci» chiude quella corrente.
* Chi era già collegato prima di questa modifica ha ancora il cookie vecchio:
  diventa duraturo al primo nuovo accesso.

### Neutrali

* Il cookie resta `HttpOnly`, `Secure` e `SameSite=Lax` in produzione: cambia
  solo quanto vive.

## Note Implementative

* `utils/sessione_duratura.py`: `applica_scelta_al_login()` dopo `login_user`
  in `routes/auth.py`; `rinnova_sessione_duratura()` come `before_request`.
* Il rinnovo non legge `current_user`: gli basta la sessione.
* Presidio: `tests/new/integration/test_sessione_che_dura_un_mese.py`. Guarda
  l'orario del rinnovo **dentro la sessione** e non la presenza del
  `Set-Cookie`, perché altri `before_request` scrivono nella sessione per
  conto loro.

## Riferimenti

* ADR-055 — sessione legata alla credenziale
* ADR-063 — admin scollegato dopo inattività
* ADR-050 — token CSRF legato alla sessione
* `docs/reference/AUTHENTICATION.md`, sezione «Session Lifetime»
