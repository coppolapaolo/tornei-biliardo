# ADR-039 Squadre: due livelli, e un sorteggio che rinvia i derby

**Data**: 2026-08-15
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Requisito nuovo, arrivato insieme ai formati a tabellone: nei tabelloni i
**compagni di squadra non devono incontrarsi nei primi turni**, salvo
impossibilità matematica, e l'incontro va rinviato al turno più avanzato
possibile.

Il concetto di squadra **non esisteva** nel codebase: nessun modello, nessuna
colonna, nessuna menzione nelle specifiche. Andava creato, e la prima domanda
era quanto grande farlo.

Vincoli:

1. le squadre servono a **una cosa sola**: separare i compagni nel sorteggio
   di *quella* competizione. Non esistono classifiche, statistiche o punteggi
   per squadra;
2. il giocatore non deve ridigitare la propria società a ogni iscrizione;
3. la stessa persona può giocare per società diverse in gare diverse — è
   normale, non un'eccezione da gestire dopo;
4. i doppioni ("Circolo Nord", "C. Nord", "circolo nord") sono la modalità di
   fallimento tipica di qualunque elenco compilato da più persone;
5. la separazione dev'essere **spenta di default**: chi non usa le squadre non
   deve vedere cambiare nulla.

## Decisione

### Modello a due livelli, deliberatamente asimmetrico

- **Sul profilo** (`user.squadra`) la squadra è **testo libero**, senza FK, e
  la scrive **solo il giocatore**. Da sola non produce alcun effetto.
- **Nella competizione** è un'**entità** (`squadra`) che appartiene al
  campionato — condivisa da tutte le sue gare — oppure alla gara, se
  standalone. Mai a entrambi: un `CHECK` a livello di DB lo impedisce.
- **Sull'iscrizione** (`inscription.squadra_id`) c'è l'unica fonte
  autorevole per il sorteggio. NULL = "gioco senza squadra qui", che è una
  scelta e non un dato mancante.

Il testo del profilo viene letto **una volta sola**, al momento
dell'iscrizione, per precompilare. Da lì in poi nessuno lo rilegge: cambiare
il profilo a gara in corso non muove nulla, ed è una proprietà sancita da un
test invece che una conseguenza da scoprire.

I doppioni si affrontano **prima**: quando qualcuno sta per aggiungere una
voce, gli si mostrano i nomi simili già presenti (confronto su una forma
normalizzata — minuscole, spazi compattati — che è anche ciò su cui il DB
impone l'unicità). L'unione resta disponibile come rimedio, e riassegna le
iscrizioni della voce assorbita.

### L'obiettivo del sorteggio: lessicografico, non booleano

Con `c_r` = numero di coppie di compagni che si incontrerebbero al turno `r`,
l'algoritmo minimizza lessicograficamente `(c_1, …, c_k)`. Il primo
componente non nullo è il turno del primo derby: "rinviare il più possibile"
**non richiede un obiettivo separato**, è già dentro questo.

Il limite è matematico e va detto all'utente invece che nascosto: con `m` =
taglia della squadra più grande, il primo derby non può cadere oltre il turno
`R* = floor(log2(S/m)) + 1`. Nove giocatori della stessa società su un
tabellone da 16 significa derby al primo turno, comunque si sorteggi.
L'algoritmo **misura** il risultato ottenuto, non lo assume.

Il vincolo di seeding resta quello federale: le bande (seed 1; seed 2; seed
3-4; seed 5-8; …) devono distribuirsi un elemento per blocco, ma *quale*
membro della banda vada in *quale* blocco è libero — ed è esattamente la
libertà che serve per separare i compagni. I bye restano ai primi seed.

### La finestra di modifica si chiude al sorteggio

Superato l'avvio del primo turno, ogni tentativo di cambiare la squadra di
un'iscrizione viene **rifiutato con un `ConflictError`** (→ 409), non
accettato e ignorato: il tabellone è già estratto e una modifica non avrebbe
effetto retroattivo. Il vincolo vive nel servizio, non nella schermata — una
schermata non è un vincolo.

## Alternative Considerate

### Alternativa 1: anagrafica globale delle squadre
- Pro: nessun doppione fra competizioni, una società = una riga.
- Contro: struttura da mantenere (chi la cura? chi approva le nuove?) al
  servizio di una funzione sola. E il caso "gioco per un'altra società questa
  sera" diventerebbe un'eccezione da modellare, mentre col modello per
  competizione è semplicemente un'altra `inscription.squadra_id`.

### Alternativa 2: solo il testo libero sul profilo, senza elenco
- Pro: zero UI in più.
- Contro: la separazione lavorerebbe su stringhe scritte a mano, quindi su
  gruppi sbagliati; e il director non avrebbe modo di correggere.

### Alternativa 3: separazione come vincolo rigido (fallire se impossibile)
- Pro: garanzia netta.
- Contro: farebbe fallire il sorteggio proprio nei casi in cui serve di più —
  una società numerosa — invece di fare la cosa migliore possibile. La
  decisione presa con l'utente è "rinvia il più possibile", e la nota accanto
  all'opzione lo dice.

### Alternativa 4: `networkx` per l'assegnazione degli slot
- Pro: già in `requirements.txt`, usato dalle altre strategie.
- Contro: il sottoproblema qui è un assignment bipartito su matrici ≤ 64×64;
  `minimum_weight_full_matching` richiede `scipy`, che **non** è fra le
  dipendenze. L'uso esistente di networkx (`amalfi`, `random_anti_rematch`) è
  `max_weight_matching` su grafo generale, dove la dipendenza è giustificata.
  Qui bastano greedy per taglia decrescente, 2-opt fra membri della stessa
  banda e qualche restart guidato dallo stesso RNG del sorteggio.

## Conseguenze

### Positive
- Chi non usa le squadre non vede alcuna differenza: opzione spenta, campo
  assente ovunque, tabellone identico all'ordine canonico (c'è un test di
  non-regressione che lo asserisce).
- Il costo del modello è proporzionale a cosa serve: una tabella, due colonne.
- Il sorteggio resta riproducibile: `gara.draw_seed` è persistito, quindi lo
  stesso tabellone si può ricostruire se qualcuno lo contesta.

### Negative
- Due posti dove appare una "squadra" (profilo ed elenco), che vanno spiegati
  nella UI perché la differenza non è ovvia.
- L'elenco è per competizione: due campionati dello stesso circolo avranno due
  righe con lo stesso nome. È voluto, ma va detto.

### Rischi
- Un director che attiva la separazione **dopo** che le iscrizioni sono
  aperte avrebbe metà iscritti senza squadra. Impedito: le opzioni del
  tabellone si decidono in `setup`, come ogni altra configurazione della gara.
- La qualità della separazione dipende da quanto l'elenco è pulito. Da qui
  l'insistenza sui nomi simili *prima* della creazione, invece che sull'unione
  dopo.

## Note Implementative

- Algoritmo puro: `models/matchmaking/team_separation.py` (nessun DB).
- Modello ed elenco: `models/squadra/models.py`, `models/squadra/service.py`.
- Precompilazione dall'iscrizione:
  `InscriptionService.inscribe_user` (unico punto in cui `user.squadra` viene
  letto).
- Schermate: `templates/components/_squadra_choice.html` (giocatore),
  `_squadre_management.html` (director), colonna nell'elenco iscritti.
