# ADR-049 L'handicap non spegne l'Elo: lo spegne la differenza di categoria

**Data**: 2026-08-19
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Dal giugno 2026 una gara «con handicap» non aggiorna i rating. La regola vive
in un flag booleano ereditato (campionato → gara → match,
`effective_has_handicap`) e la sua motivazione è corretta: se un giocatore parte
avvantaggiato, il risultato non dice quanto valgono i due.

Ma è troppo grossolana. In una gara aperta a più categorie **la maggioranza
delle partite si gioca fra pari**: due giocatori della stessa categoria non
hanno alcun handicap fra loro, e il loro risultato è esattamente il segnale che
l'Elo cerca. Scartarlo significa buttare via quasi tutta la gara.

Perché la regola fine sia applicabile servono le categorie come dato, e non
esistevano. Vincoli emersi discutendone:

1. il vocabolario **non è universale**. «C, B, A, N» è la scala della
   federazione italiana per il pool; aggiungere «E» per gli esordienti è una
   scelta arbitraria di chi organizza, e altrove nel mondo la scala è un'altra;
2. le categorie le conosce **il direttore**, e le assegna prima di far partire
   la gara;
3. il giocatore non deve poterle scrivere: decidono se le sue partite muovono
   il rating;
4. chi non usa l'handicap non deve vedere cambiare nulla, e **nessuna gara già
   esistente** deve cambiare comportamento al deploy.

C'era anche un ostacolo: un impianto categorie **esisteva già** in
`models/rating/` — `CategoryLevel` (enum A/B/C/D cablato), `PlayerCategory`,
`HandicapRule` e figlie, `RatingService`, `HandicapService` — insieme al
blueprint `/rating` che lo esponeva. Codice morto verificato: la cartella
`templates/rating/` non è mai esistita, quindi ogni view cadeva nell'`except` e
finiva in un flash; nessuna entry in `ENDPOINT_ROLES`; zero righe in tutte e
quattro le tabelle. Ed era il modello sbagliato: categoria **globale per
utente**, con il vocabolario in un enum — cioè le due proprietà che rendono
impossibile «ogni competizione definisce le sue».

## Decisione

### La regola

In una gara con handicap l'Elo si aggiorna **se e solo se** i giocatori
condividono la categoria.

```
handicap=no   (qualunque categoria)      → Elo aggiornato
handicap=sì   cat(p1)=B   cat(p2)=B      → Elo aggiornato
handicap=sì   cat(p1)=B   cat(p2)=A      → Elo NON aggiornato
handicap=sì   cat(p1)=B   cat(p2)=—      → Elo NON aggiornato
handicap=sì   cat(p1)=—   cat(p2)=—      → Elo NON aggiornato
walkover      (qualunque)                → Elo NON aggiornato  (invariato)
trio          → conta solo se tutti e tre condividono la categoria
```

**Categoria mancante ⇒ niente Elo.** «Non lo so» non è «sono uguali». È la
scelta che rende il cambio innocuo: finché nessuno assegna categorie il
comportamento è identico a quello storico, e accendere l'Elo su una gara con
handicap richiede un atto esplicito del direttore. C'è un test di
non-regressione che asserisce proprio questo.

Per i **trii** servono tutte e tre le categorie uguali: il girone interno li fa
incontrare tutti, quindi due su tre non è «ad armi pari».

### Il modello: per competizione, come le squadre

`models/categoria/` è il calco di `models/squadra/` (ADR-039), e per la stessa
ragione: l'elenco appartiene al **campionato** — condiviso da tutte le sue gare
— oppure alla **gara** se standalone, mai a entrambi, con un `CHECK` a livello
di DB. `Inscription.categoria_id` è l'unica fonte autorevole per quella gara.

Un'anagrafica globale è stata scartata per il vincolo 1: renderebbe chi la cura
il collo di bottiglia di ogni torneo, e trasformerebbe «qui usiamo un'altra
scala» da caso normale a eccezione da modellare.

### Definire ed assegnare sono lo stesso gesto

Il campo accanto a ogni iscritto è un **combobox** (`<input list>` +
`<datalist>`): un nome già in elenco si completa da solo, uno nuovo **crea** la
categoria. Non esiste un momento «prima configuro l'elenco»: si scrive «B» sul
primo giocatore e la categoria nasce lì, sul secondo la si trova in tendina.
Il servizio espone quindi `set_inscription_categoria_by_name`, che lavora su un
nome e non su un id.

Il rovescio del testo libero è il refuso: «B», «b» e « B » si fondono da sole
(`normalized_name`), ma «BB» no. Il presidio non è un controllo, è il
**conteggio per categoria** mostrato accanto all'elenco: una categoria con un
solo giocatore fra altre da otto si riconosce a colpo d'occhio, e da lì si
cancella.

### Nessun ordinamento: alfabetico

Le categorie si mostrano in ordine alfabetico, senza colonna di posizione. La
regola Elo confronta solo l'uguaglianza, quindi l'ordine non le serve.

La scelta è stata presa **sapendo che l'alfabeto mente** su questa scala:
`A B C E N` mette gli esordienti prima dei nazionali mentre sono i più bassi di
tutti. È il prezzo accettato per non costruire e mantenere controlli di
riordino.

Va detto agli atti perché non si scopra per caso: quando arriverà l'**handicap
sul punteggio** (`docs/wishlist.md`, «A vs C → 2 rack in più per A») l'ordine
diventerà indispensabile, perché la differenza fra due categorie *è* il numero
di rack. A quel punto servirà una colonna `position` e un modo per dichiararla,
su categorie già scritte. È una migration da una colonna, non un rifacimento.

### La finestra si chiude all'avvio del primo turno

Come per le squadre: dopo il sorteggio ogni tentativo è rifiutato con
`ConflictError` (→ 409). La ragione qui è più forte che per le squadre: le
categorie hanno già deciso quali partite contano, e cambiarle darebbe un rating
che non corrisponde più a ciò che si vede.

All'avvio del turno compare quanti iscritti sono senza categoria e cosa
comporta, e si può proseguire: è l'ultimo istante in cui la dimenticanza è
rimediabile da schermata, e lasciare fuori qualcuno di proposito è una scelta
legittima.

### Chi scrive: solo il direttore

È lo scostamento voluto rispetto ad ADR-039, dove la squadra della propria
iscrizione la sceglie anche il giocatore. La squadra al più influenza il
sorteggio; la categoria decide se le partite muovono l'Elo, e autoassegnarsela
sarebbe un pulsante «fammi contare». Il vincolo sta nel servizio, non nella
schermata.

La categoria è comunque **visibile** al giocatore in sola lettura: chi gioca una
gara con handicap ha diritto di sapere se le sue partite contano.

### Una policy sola, in un posto solo

`models/rating/eligibility.py` è l'unica fonte su quali partite entrano
nell'Elo. Prima la condizione era duplicata in quattro punti — l'handler degli
eventi, i due ricalcoli e `scripts/diagnose_elo.py`, che nella docstring
**dichiarava** di essere una replica. Aggiungere una seconda condizione a
quattro copie è il modo sicuro per farle divergere, e qui la divergenza non dà
errore: dà un Elo che non torna, mesi dopo.

`exclusion_reason` restituisce **il motivo** e non un booleano, perché i
chiamanti ne fanno usi diversi: log, diagnosi, contatori. Con un `bool` il
perché andrebbe ricostruito a valle, cioè riscritto.

Sulle prestazioni: i ricalcoli ciclano su ogni partita mai giocata, quindi
`build_index` carica le categorie di tutte le gare toccate in **una** query e
la si passa alla policy. La property `Match.counts_for_rating` esiste come
accessore comodo, ma paga due letture e non va usata nei cicli.

### Le gare già giocate

`scripts/set_gara_categorie.py` le recupera: trova le gare con handicap già
avviate e senza categorie e le percorre dalla più vecchia. Chiede la categoria
**solo di chi non si sa già** — la porta dietro da una gara precedente, propria
o del DB — perché su un circuito di otto prove chiederle tutte ogni volta
significa ottanta risposte invece di otto. Mostra poi tutti gli iscritti
ordinati per categoria e nome, marcando i riportati: sono quelli che nessuno ha
riguardato, quindi è lì che si nasconde chi nel frattempo è salito di categoria.
Da lì si salva, si rivede (e allora le chiede **tutte**, con i valori attuali
come proposta), o si salta la gara. Scavalca la finestra di modifica con un
`force=True` documentato, usato **solo** da lì.

Alla fine propone il ricalcolo dell'Elo, dicendo cosa comporta: è **globale**,
non chirurgico. L'Elo è path-dependent, quindi far entrare partite prima
escluse sposta il rating di tutti, non solo dei giocatori toccati. Non esiste
una versione locale onesta di quell'operazione.

### Rimozione del vecchio impianto

Cancellati `PlayerCategory`, `CategoryLevel`, `HandicapRule`,
`CategoryHandicapRule`, `RatingHandicapRule`, `RatingService`,
`HandicapService` e il blueprint `routes/rating.py`. Lasciarli avrebbe
significato due vocabolari di categoria coesistenti, di cui quello morto è il
primo che si trova cercando «categoria».

Ne è emerso un guasto vero, non solo codice morto: i traguardi «Scalatore di
Categoria» e «Giocatore Élite» erano **attivi e visibili**, con 200 e 600 XP
promessi, e poggiavano su una tabella che nessun codice di produzione ha mai
scritto. Ricablati sul requisito `elo_reached` con le soglie 1500/1800 — la
stessa taratura del rimosso `get_category_equivalent` — sono ottenibili per la
prima volta.

## Alternative Considerate

### Alternativa 1: elenco globale d'istanza, curato dall'admin
- Pro: nessuna ridigitazione, un solo vocabolario da mantenere.
- Contro: contraddice il vincolo 1. Chi cura l'elenco diventa il collo di
  bottiglia di ogni torneo, e «qui usiamo un'altra scala» torna a essere
  un'eccezione invece del caso normale.

### Alternativa 2: riusare `PlayerCategory`
- Pro: la tabella c'era già, con assegnatore, motivo e scadenza.
- Contro: è per-utente e globale, con la categoria come `db.Enum` in colonna.
  Sono esattamente le due proprietà che rendono impossibile il requisito.

### Alternativa 3: categoria mancante = si assume parità (Elo aggiornato)
- Pro: senza configurare nulla la funzione «si accende da sola».
- Contro: ribalta in silenzio il comportamento delle gare con handicap già
  chiuse, che è il caso più comune (nessuno ha ancora assegnato niente).

### Alternativa 4: impedire l'avvio del turno finché mancano categorie
- Pro: nessuna gara parte a metà.
- Contro: toglie una scelta legittima — un ospite di cui non si conosce la
  categoria e che accetta di non contare.

### Alternativa 5: colonna `position` per l'ordine, subito
- Pro: pronta per l'handicap sul punteggio; l'alfabeto non mentirebbe.
- Contro: controlli di riordino da costruire e mantenere per una funzione che
  oggi non li usa. Rinviato consapevolmente (vedi sopra).

### Alternativa 6: schermata dedicata «assegna categorie», un solo salvataggio
- Pro: una ricarica invece di N, e un posto naturale per «assegna a tutti».
- Contro: una schermata in più e un momento «prima definisci l'elenco» che il
  combo elimina. Il salvataggio senza ricarica risolve lo stesso problema senza
  aggiungere superficie.

## Conseguenze

### Positive
- In una gara con handicap la maggioranza delle partite torna a contare.
- Chi non usa l'handicap, o non assegna categorie, non vede alcuna differenza.
- La policy dell'Elo smette di essere duplicata in quattro punti, e la
  diagnostica ora **spiega** perché una partita non ha mosso il rating.
- Due traguardi promessi da mesi diventano ottenibili.
- Sparisce un intero sottosistema morto, e con esso il rischio che qualcuno lo
  trovi per primo cercando «categoria».

### Negative
- L'ordine alfabetico è sbagliato rispetto alla forza reale, e resterà tale
  finché non arriverà l'handicap sul punteggio.
- Correggere una categoria a gara avviata richiede uno script e un ricalcolo
  globale dell'Elo.
- Il testo libero ammette refusi: il presidio è il conteggio, non un controllo.

### Rischi
- Il ricalcolo globale sposta il rating di tutti. Va detto a chi lo lancia — lo
  script lo stampa — e va eseguito con la web app disabilitata (storage NFS).
- `handicap_rule` **resta in piedi vuota** in produzione, e con essa
  `match.handicap_rule_id`. Non è pigrizia: con `PRAGMA foreign_keys=ON` anche
  un INSERT con la FK a NULL fallisce se la tabella padre non esiste, quindi
  droppare la tabella romperebbe ogni avvio di turno; e la colonna non è
  eliminabile, perché SQLite rifiuta `DROP COLUMN` su una colonna citata in una
  chiave esterna — verificato sperimentalmente anche sulla 3.51, non solo sulla
  3.31.1 di PythonAnywhere. L'unica via sarebbe ricostruire l'intera tabella
  `match`. La colonna non è più mappata dal modello, quindi è inerte.

## Note Implementative

- Modello e servizio: `models/categoria/`
- Policy dell'Elo: `models/rating/eligibility.py`; accessore
  `Match.counts_for_rating`
- Route: `routes/admin/competition/categorie.py` (assegnazione JSON, gestione
  form) + `ENDPOINT_ROLES` in `utils/feature_flags.py`
- Interfaccia: `templates/components/_categorie_management.html` (che ospita
  anche il `<datalist>` e lo script, perché `_gara_inscriptions.html` è incluso
  due volte) e il campo dentro `_gara_inscriptions.html`
- Migration: `migrations/20260819_categorie_competizione.py`
- Recupero gare giocate: `scripts/set_gara_categorie.py`
- Test: `test_rating_eligibility.py` (la tabella di verità riga per riga),
  `test_categoria_model.py`, `test_categoria_service.py`,
  `test_categorie_routes.py`, più i casi aggiunti a
  `test_rating_idempotency_revert.py`
