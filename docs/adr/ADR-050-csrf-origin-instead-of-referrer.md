# ADR-050 Il CSRF si difende con l'Origin, non con il referrer

**Data**: 2026-08-19
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Alcuni utenti non riuscivano a entrare: il login rispondeva **400**, la pagina
«Il tavolo si è raffreddato — la sessione è scaduta». Altri — fra cui i
direttori di gara che hanno segnalato il problema — entravano senza accorgersi
di nulla. Nessuno dei due gruppi faceva qualcosa di diverso dall'altro:
stessa pagina, stesso modulo, stessa password.

La riproduzione contro `https://www.torneibiliardo.it` (2026-08-19) ha isolato
la variabile in due richieste identiche a meno di un header:

```
POST /auth/login  (token valido, sessione valida, senza Referer)  → 400
POST /auth/login  (stesso token, stessa sessione, con Referer)    → 200
```

La causa è `WTF_CSRF_SSL_STRICT`, che Flask-WTF tiene attivo per default: su
richiesta HTTPS, **dopo** aver validato il token, pretende anche un header
`Referer` che combaci con l'host, e senza risponde 400
(`flask_wtf/csrf.py`: *"The referrer header is missing."*).

È una difesa nata prima di `SameSite`, quando il referrer era l'unico modo per
sapere da dove arrivasse un POST. Oggi quell'header è **facoltativo** e viene
tolto da tutta una serie di configurazioni che l'utente spesso nemmeno sa di
avere: browser con la privacy stretta o estensioni che lo rimuovono, webview
dentro altre app, proxy aziendali, alcune VPN. Per quelle persone non falliva
"a volte" il login: falliva **ogni POST del sito**, e siccome il primo POST è
il login, restavano fuori senza alcun modo di entrare — mentre per tutti gli
altri l'applicazione funzionava benissimo. Un guasto che si vede solo addosso
a qualcuno, e che dalla parte di chi lo osserva sembra un problema di ruoli.

A rendere il tutto muto contribuiva la diagnostica: il gestore di `CSRFError`
mostrava la pagina 400 e basta, quindi nei log un token scaduto, un modulo
senza token e un referrer assente erano la stessa identica riga.

## Decisione

**Spegnere il controllo sul referrer** (`WTF_CSRF_SSL_STRICT = False` in
`config.py`) e **mettere al suo posto un controllo su `Origin`**
(`verifica_origine_richiesta`, hook `before_request` in `app.py`):

- se `Origin` è presente e il suo host non è il nostro → `CSRFError` (400);
- se `Origin` è assente (o `null`) → si prosegue: la difesa restano il token e
  `SameSite=Lax`.

Il confronto è **solo sull'host**, non sullo schema: dietro il proxy di
PythonAnywhere l'applicazione vede `http` mentre il browser dichiara `https`,
e un confronto completo rifiuterebbe tutto.

Non è un indebolimento, perché ciò che il referrer fermava davvero — un form
ospitato su un altro sito che spara sul nostro — `Origin` lo ferma meglio: i
browser lo mandano **sempre** su un POST cross-site, mentre il referrer si
poteva già togliere. Restano in piedi, invariati:

- il token CSRF firmato e legato alla sessione, che un sito terzo non può
  leggere;
- il cookie di sessione `SameSite=Lax`, che su un POST cross-site non viene
  proprio inviato — quindi la richiesta arriverebbe comunque senza sessione.

Contestualmente il gestore di `CSRFError` **logga il motivo** (descrizione,
percorso, referrer, origin): la pagina resta quella, ma il log smette di
essere ambiguo.

## Alternative Considerate

### Alternativa 1: lasciare il controllo e dichiarare una Referrer-Policy

**Descrizione**: tenere `WTF_CSRF_SSL_STRICT` e aggiungere un header
`Referrer-Policy` che garantisca l'invio del referrer same-origin.

- **Pro**:
  - Nessuna riga di codice applicativo, solo un header.
- **Contro**:
  - **Non funziona.** `Referrer-Policy` può solo *restringere* ciò che il
    browser manda, non obbligarlo a mandarlo: un'estensione, una webview o un
    proxy che tolgono l'header continuerebbero a toglierlo, e quegli utenti
    resterebbero fuori esattamente come prima.

### Alternativa 2: esentare il login dal CSRF

**Descrizione**: `@csrf.exempt` su `auth.login`, così almeno si entra.

- **Pro**:
  - Risolve il sintomo segnalato in una riga.
- **Contro**:
  - Cura la porta d'ingresso e lascia rotto tutto il resto: per gli stessi
    utenti continuerebbero a fallire iscrizione, referto, profilo — ogni POST.
  - Toglie protezione a un endpoint che ne ha bisogno (login CSRF: un
    attaccante che ti fa entrare nel *suo* account).

### Alternativa 3: pretendere `Origin`, rifiutando chi non lo manda

**Descrizione**: come la decisione, ma con l'header obbligatorio.

- **Pro**:
  - Regola più semplice da enunciare.
- **Contro**:
  - Ricrea lo stesso guasto su un altro header: client legittimi che non
    mandano `Origin` (POST non-browser, vecchie webview) verrebbero rifiutati.
  - Non aggiunge nulla: quando `Origin` manca, la richiesta cross-site è già
    fermata da `SameSite=Lax` e dal token.

## Conseguenze

### Positive

- Chi non manda il referrer torna a poter usare il sito — non solo a entrare.
- Un POST che dichiara di venire da un altro sito viene rifiutato in modo
  esplicito e **loggato**, prima ancora di arrivare alla route.
- I 400 da CSRF smettono di essere indistinguibili nel log.

### Negative

- Si perde una difesa ridondante per i browser che il referrer lo mandano.
  Ridondante è la parola giusta: agiva dopo la validazione del token e su
  richieste che `SameSite=Lax` già non lascia partire con la sessione.

### Rischi

- Il default di Flask-WTF può tornare da solo con un aggiornamento o con una
  configurazione riscritta: il presidio è
  `tests/new/integration/test_csrf_senza_referrer.py`, che verifica sia il
  comportamento (POST senza referrer non è 400, POST con origin estranea sì)
  sia il valore in `Config`.
- Il controllo su `Origin` confronta l'host: se un domani il sito rispondesse
  su più domini con un proxy che riscrive `Host`, andrebbe rivisto.

## Note Implementative

- `config.py`: `Config.WTF_CSRF_SSL_STRICT = False` (vale ovunque — in
  sviluppo il controllo era comunque inerte, perché scatta solo su HTTPS).
- `app.py`: `verifica_origine_richiesta` accanto a `CSRFProtect`, salta i
  metodi sicuri, i casi con CSRF disattivato (test) e le viste marcate
  `@csrf.exempt`.
- `tests/new/integration/test_csrf_senza_referrer.py`: gira con il CSRF
  **acceso** (la suite lo spegne) e su `base_url` `https://`, altrimenti il
  controllo di Flask-WTF non sarebbe mai scattato. Il client apre un contesto
  applicativo per test: quello di sessione, riusato da Flask a ogni richiesta,
  faceva sopravvivere `g.csrf_token` da un test all'altro.
