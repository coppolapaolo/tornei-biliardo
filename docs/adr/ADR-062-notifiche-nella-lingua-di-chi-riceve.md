# ADR-062 Le notifiche si scrivono nella lingua di chi le riceve

**Data**: 2026-09-13
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

L'interfaccia è tradotta in inglese e la lingua della pagina la sceglie chi la
guarda: sessione, poi browser. Le notifiche però non sono pagine. Sono testi
scritti **per qualcun altro**, e fino a oggi venivano tradotti nella lingua
della richiesta in corso, cioè di chi premeva il pulsante.

Il caso che l'ha fatto emergere: un direttore italiano ritira dalla gara un
giocatore inglese, e il giocatore riceve la notifica in italiano. Ma il difetto
era di tutte le notifiche, in tre forme:

| forma | esempio | chi legge cosa |
|---|---|---|
| `_()` chiamato sul posto | ruoli, esami, proposte di sfida | la lingua di chi preme |
| f-string o letterale | handler degli eventi, inviti ai playoff, prova, gara cancellata | sempre italiano, mai tradotto |
| composto da uno scheduled task | promemoria, scadenze, KPI | la lingua di ripiego, per chiunque |

Nessun test poteva vederlo: in sviluppo e nei test chi preme e chi riceve
parlano italiano entrambi, e ogni frase è plausibile.

Su `User` non esisteva una lingua. `get_locale()` provava a leggere
`current_user.language`, protetto da un `hasattr` sempre falso.

È lo stesso problema dell'orario, risolto da ADR-043 per il fuso: il testo è
per il destinatario, quindi va composto nel **suo** contesto, e fuori da una
pagina quel contesto esiste solo se è scritto in colonna.

## Decisione

### La lingua dell'utente si salva: `User.language`

Codice di una lingua che l'app parla (`it`, `en`), `NULL` = mai dedotta, con
ripiego sull'italiano. Nessun backfill, come per il fuso: indovinare la lingua
degli account esistenti non si può, e un valore plausibile al posto di «non lo
so» renderebbe l'errore permanente.

Due provenienze con pesi diversi:

- il **selettore della lingua** è una scelta: scrive sempre;
- la **deduzione** da sessione o `Accept-Language`, a ogni richiesta di un
  utente senza lingua, riempie solo un vuoto e non scavalca mai una scelta. Chi
  ha scelto l'inglese e apre l'app da un computer in italiano continua a
  ricevere in inglese.

La deduzione scrive una volta sola per utente; dopo è una lettura di
attributo.

### Il testo si compone nel servizio, per ciascun destinatario

`NotificationService.create_notification` risolve titolo, messaggio e pulsante
dentro `nella_lingua_di(user_id)` (`utils/lingua.py`), che fa `force_locale`
sulla lingua del destinatario e all'uscita restituisce quella di prima.
`force_locale` di Flask-Babel lavora su `g`, quindi vale anche fuori da una
richiesta: scheduled task e thread in background, purché dentro il contesto
dell'app.

Perché il servizio possa tradurre, il testo gli deve arrivare **da comporre**:

- una stringa pigra (`lazy_gettext`) per le frasi semplici, anche con parametri;
- una funzione senza argomenti per i testi fatti di pezzi, o con un orario da
  mostrare nel fuso del destinatario (`utils.lingua.data_ora_per`).

Una stringa semplice passa com'è: è il testo scritto da un utente, una nota o
una motivazione, che non si traduce.

Il vantaggio della forma è che un solo testo pigro per N destinatari produce N
traduzioni: `create_bulk_notification` non ha dovuto cambiare forma.

### Un presidio statico

`tests/new/unit/test_notifiche_testi_non_tradotti_da_chi_preme.py` cammina
l'AST di `models/`, `routes/` e `utils/` e rifiuta, negli argomenti di testo
delle funzioni che creano notifiche, f-string, letterali, concatenazioni e
`_()` chiamati sul posto, seguendo anche le assegnazioni alla variabile nella
stessa funzione.

## Alternative considerate

### Tradurre alla lettura

Salvare chiave e parametri e tradurre quando la notifica si mostra. È la strada
già abbozzata da `Notification.template_key`, che nessuno usa. Renderebbe
corrette anche le notifiche già scritte quando un utente cambia lingua.

- **Pro**: una notifica cambia lingua insieme all'utente.
- **Contro**: ogni testo diventa un modello con parametri serializzati in JSON,
  anche quelli fatti di pezzi o con orari, e ogni superficie che mostra una
  notifica deve passare dalla traduzione. È una migrazione di tutte le
  notifiche e del loro modello, per un guadagno che oggi riguarda solo chi
  cambia lingua dopo averle ricevute.

### Una funzione dell'id per ogni messaggio

Come facevano già i promemoria d'esame per il fuso: `message(user_id)`.

- **Pro**: esplicito.
- **Contro**: obbliga ogni chiamata a riscrivere la frase come funzione, anche
  quelle semplici, e a ricordarsi `force_locale`. La stringa pigra ottiene lo
  stesso risultato senza cambiare forma alla chiamata.

### Chiedere la lingua nel profilo

- **Contro**: un campo in più per un dato che il browser conosce già, e che
  l'utente di solito ha già espresso usando il selettore.

## Conseguenze

### Positive

- Ogni notifica esce nella lingua del destinatario, anche da uno scheduled
  task. Chi non ha ancora una lingua riceve in italiano, come prima.
- Il selettore della lingua vale anche per ciò che arriva a browser chiuso.
- Strada facendo: gli orari nelle proposte di sfida e negli handler degli eventi
  escono nel fuso del destinatario, non più in UTC con «alle» in italiano; la
  notifica della disiscrizione dice chi l'ha tolta invece di «L'direttore di
  gara»; «della campionato» diventa «del campionato»; tolti `create_from_template`
  e i `notify_*` a modello, mai chiamati e scritti in inglese.

### Negative

- Una notifica già scritta resta nella lingua in cui è nata: se l'utente cambia
  lingua, le vecchie non si ritraducono. È il prezzo di aver scartato la
  traduzione alla lettura.
- I parametri tradotti vanno pigri anch'essi: `_l("... %(ruolo)s",
  ruolo=_("Esaminatore"))` traduce il ruolo nella lingua sbagliata, e il
  presidio non lo vede.

### Rischi

- Le email (verifica, recupero password) non passano da qui: oggi le compone
  sempre la richiesta dell'utente stesso, quindi la lingua è giusta. Un'email
  futura scritta per qualcun altro dovrà usare `nella_lingua_di`.

## Riferimenti

- ADR-043, il fuso di chi legge: stesso ragionamento, per l'orario.
- `utils/lingua.py`, `models/notification/services.py`,
  `migrations/20260913_add_user_language.py`.
- Test: `tests/new/unit/test_notifiche_lingua_destinatario.py`,
  `tests/new/unit/test_lingua_utente.py`,
  `tests/new/unit/test_notifiche_testi_non_tradotti_da_chi_preme.py`.
