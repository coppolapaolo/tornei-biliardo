# ADR-069 · Istruttore e allievo: il legame passa dalla scheda

**Stato**: accettata · **Data**: 2026-09-20 · **Issue**: #173
**Fase**: 8 del redesign «TPA ed esercizi»
([PIANO.md](../redesign-7c/canvas-tpa-esercizi/PIANO.md))

## Contesto

L'app non sa che cosa sia un istruttore. Esistono i **ruoli concedibili**
(ADR-041: richiesta → approvazione → grant → revoca, oggi usati
dall'esaminatore e dal beta tester) e, dalla fase 6, esistono le **schede di
allenamento** con una tabella `training_sheet_reader` nata vuota e senza
interfaccia (ADR-067). Manca la persona che quelle schede dovrebbe leggerle.

Il disegno della fase 0 era partito nella direzione opposta — l'istruttore che
«aggiunge» un allievo — e l'utente l'ha rovesciata due volte, il 19/09:

> «il consenso va al contrario: è il **giocatore** che aggiunge (o toglie) un
> istruttore e gli permette di seguirlo»

> «purché il legame non sia allievo–istruttore, ma
> **allievo–scheda–istruttore**: ogni allievo può aggiungere e togliere n
> istruttori diversi a ogni sua scheda»

Sono le decisioni D10, D11 e D18 del piano. C'è anche un vincolo che non è di
comodità: **molti allievi sono minorenni**, e ogni cosa che si vede di loro
deve passare da un consenso che hanno dato loro, esplicito e per quella cosa lì.

## Decisione

### 1 · Il ruolo è un `RoleGrant` come gli altri

`GrantableRole.INSTRUCTOR`, con la sua `GrantPolicy`. Nessun meccanismo nuovo:
si chiede dal profilo (sezione **Ruoli**) con lo stesso percorso di «Diventa
esaminatore», l'approva chi il ruolo ce l'ha già, e lo revoca solo un
amministratore.

**È propagante** (`self_propagating=True`), come l'esaminatore. La
preoccupazione che ferma il beta tester — una catena di deleghe allarga in
silenzio la platea di chi *vede* cose che gli altri non vedono — qui non si
pone, perché il ruolo **non fa vedere niente**: rende trovabili. Chi insegna sa
chi insegna; l'amministratore di una piattaforma nazionale no.

**`User.is_instructor` non è vero d'ufficio per l'admin**, al contrario di
`is_examiner`. Quella property decide chi compare nella ricerca di un allievo
che sta scegliendo a chi aprire la propria scheda: col bypass ci finirebbero
tutti gli amministratori, e il consenso si dà a una persona, non a chi
amministra il sito. Un amministratore che insegna davvero si concede il grant
come chiunque altro.

### 2 · Il legame è la riga di `training_sheet_reader`, e basta

Non c'è nessuna tabella `allievo–istruttore`. «I miei istruttori» e «I miei
allievi» sono **due letture della stessa riga**, una da ciascun lato
(`models/istruttore/viste.py`). Un istruttore compare perché gli è stata aperta
almeno una scheda, e sparisce quando gli si toglie l'ultima.

La conseguenza voluta è che **non esiste «Luca mi segue»**: esiste «questa
scheda la legge Luca». Non c'è uno stato globale da tenere in pari con i
permessi, e non c'è modo che i due divergano. E **l'andamento generale non si
condivide**: quello che si apre è una scheda, non una persona.

### 3 · Si apre a un istruttore, e il controllo sta nel servizio

`add_reader` rifiuta chi non ha il grant. Nascondere i non-istruttori
dall'elenco di ricerca non è una regola: una POST costruita a mano la
aggirerebbe, e le schede di un minorenne non si difendono con l'ordine dei
risultati.

### 4 · Vale subito, e chi lo riceve può restituirlo (D18)

Nessuno stato «in attesa»: il permesso è attivo dal momento in cui l'allievo lo
dà. Chi lo riceve ne viene avvisato, e può **togliersi** (`leave_sheet`).

I due avvisi **non sono simmetrici**, di proposito:

| Chi agisce | Chi viene avvisato | Perché |
|---|---|---|
| L'allievo **apre** la scheda | l'istruttore | altrimenti non saprebbe di doverla guardare |
| L'istruttore **si toglie** | l'allievo | aveva invitato qualcuno, e ha diritto di sapere che non legge più |
| L'allievo **toglie** l'istruttore | **nessuno** | è una decisione sua, e annunciarla ne farebbe un atto da giustificare — per un minorenne, una pressione |

### 5 · La scuola sta sulla persona

`User.organization`, facoltativa, non cifrata: compare accanto al nome quando
un allievo sceglie a chi aprire una scheda. Sta sulla persona e non sulla
richiesta di ruolo perché si cambia scuola senza rifare il percorso del ruolo,
e a correggerla dev'essere l'interessato. Non cifrata al contrario del telefono
perché è il contrario di un dato da proteggere: chi la scrive lo fa per farsi
trovare.

### 6 · La soglia per chiedere il ruolo è bassa

`request_instructor`, cinque esercizi completati — contro i venti
dell'esaminatore. Le due soglie misurano cose diverse: l'esaminatore fa un
mestiere **dentro** l'app, e quei venti esercizi sono la prova di saperla
usare; l'istruttore fa un mestiere **in sala**, e il filtro vero è che qualcuno
dica di sì. Un maestro invitato dalla sua associazione ha zero di tutto il
primo giorno.

Cinque, e non zero, perché il pulsante non compaia a chi si è appena registrato
e non ha ancora visto com'è fatta l'area allenamento: una richiesta mandata
senza sapere che cosa si chiede è lavoro per chi deve valutarla. Il numero si
ritocca dalla console senza deploy.

## Alternative scartate

**Un legame allievo–istruttore, con le schede come conseguenza.** È il disegno
del primo giro, ed è quello che l'utente ha rovesciato. Avrebbe un solo
vantaggio — «aggiungi Luca» si fa una volta invece di tre — e due difetti seri:
il permesso diventa grossolano (apri *tutto*, comprese le schede che scriverai
domani), e il consenso perde il suo oggetto. Con un minorenne, un consenso
senza oggetto non è un consenso.

**Uno stato «in attesa» prima che il permesso valga.** Simmetrico alla
richiesta di ruolo, e sbagliato qui: il permesso lo dà chi possiede la cosa, e
chi lo riceve non ha niente da approvare. Può solo rifiutare, e per rifiutare
basta togliersi.

**Aprire una scheda a chiunque, non solo agli istruttori.** Più libero, e
tentante: un amico può aiutare quanto un maestro. Ma la stessa casella di
ricerca diventerebbe un modo per chiedere a un quattordicenne di farsi
guardare l'allenamento da uno sconosciuto. Se un giorno servirà, sarà una
decisione esplicita con le sue tutele, non un effetto collaterale di questa.

**Il ruolo che dà visibilità da solo.** Sarebbe comodo per l'istruttore di una
scuola che vuole vedere i suoi allievi senza chiedere niente a nessuno. È
esattamente ciò che questa ADR rifiuta: il ruolo è un'etichetta, il permesso è
un atto dell'allievo.

## Conseguenze

* Le due pagine derivate non possono mai divergere dai permessi: non c'è un
  secondo posto dove il legame è scritto.
* Un allievo che archivia una scheda la toglie anche dalla vista
  dell'istruttore. Il permesso resta sulla riga, che dice «da quando a quando»;
  se la scheda tornasse, tornerebbe anche il legame.
* I gruppi di allievi (D12, fase 8c) raggrupperanno **persone che hanno già
  aperto una scheda**: un gruppo non è un modo per ottenere l'accesso, è un
  modo per ordinare chi te l'ha già dato.
* Chi revoca il ruolo a un istruttore **non chiude le sue righe di lettura**:
  i permessi restano dove sono, e con loro la traccia di chi leggeva cosa. È
  coerente con la revoca dell'ADR-041, dove «ciò che il titolare ha prodotto
  resta valido». Se serve che la revoca chiuda anche i permessi, è una
  decisione da prendere a parte, con il suo perché.

## Presidi

* `tests/new/unit/test_istruttore_e_lettori.py` — il ruolo, le regole di
  apertura, i due avvisi, e le due viste derivate.
* `tests/new/unit/test_istruttore_migration.py` — la feature ABAC e la colonna.
