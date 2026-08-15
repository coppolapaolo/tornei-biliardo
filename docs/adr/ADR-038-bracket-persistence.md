# ADR-038 Il tabellone è un dato, non una ricostruzione

**Data**: 2026-08-15
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Eliminazione diretta e doppio KO esistevano nel dominio da mesi, ma il
**tabellone non era persistito da nessuna parte**: un `Match` sapeva a quale
turno apparteneva e chi lo giocava, non che posto occupasse nell'albero.

Le conseguenze non erano teoriche.

- Dal turno 2 l'eliminazione diretta riaccoppiava i vincitori nell'ordine di
  ritorno della query (`pop(0), pop(0)`). Non era casuale: era
  *sistematicamente* sbagliato. I match venivano inseriti prima i bye e poi le
  coppie, quindi al turno 2 tutti i giocatori usciti da un bye — cioè le teste
  di serie — si incontravano fra loro.
- Il doppio KO ricostruiva i due rami a runtime contando le sconfitte nello
  storico, e accoppiava il losers bracket partendo da `list(set(...))`: non
  deterministico fra due esecuzioni sullo stesso stato.
- Non esisteva modo di *mostrare* il tabellone, perché non esisteva il dato da
  mostrare.

Vincoli:

1. il losers bracket **non è un albero binario completo**: alterna round
   "minori" (i perdenti che si incontrano fra loro) e "maggiori" (chi
   sopravvive contro chi scende dal winners), che hanno lo stesso numero di
   match;
2. il formato FISBB (ADR successivo nel tempo, stesso lavoro) gioca **più
   gironi in parallelo** dentro la stessa gara;
3. le gare già in corso al momento del rilascio non devono cambiare
   comportamento a metà;
4. la struttura deve reggere il rendering, cioè essere ordinabile e
   raggruppabile in SQL senza post-elaborazioni.

## Decisione

Il tabellone si **persiste sul match** come quadrupla:

| colonna | semantica |
|---|---|
| `bracket_type` | `W` winners · `L` losers · `GF` finale · `GFR` bella · `3P` finalina |
| `bracket_round` | turno **interno al bracket**, 1-based |
| `bracket_slot` | posizione 0-based dentro il round |
| `bracket_group` | girone della fase a gironi; NULL = tabellone finale o gara senza gironi |

NULL su tutte = match non appartenente a un tabellone (Amalfi, round robin,
random) oppure gara antecedente all'introduzione delle colonne.

Le regole di avanzamento diventano aritmetica su queste coordinate, in un
modulo puro senza Flask né SQLAlchemy (`models/matchmaking/bracket.py`): il
vincitore di `(W, r, s)` va in `(W, r+1, s//2)` al posto `s%2`; il nodo `j` di
un turno accoppia gli slot `2j` e `2j+1` del precedente.

Tre decisioni collegate, tutte discendenti dalla stessa idea ("il dato dice
dove sei, non come ci sei arrivato"):

**Il seat non è una colonna.** Il posto occupato nel match successivo è
`bracket_slot % 2`. Persisterlo sarebbe ridondanza desincronizzabile: due
fonti per la stessa verità, con la certezza che prima o poi divergono.

**La convenzione di seat della grand final è normativa.** Nella `GF` player1 è
il campione del winners bracket e player2 quello del losers. Il rilevamento
del bracket reset è tutto qui: se `gf.winner_id == gf.player2_id` si crea la
bella, altrimenti il torneo è chiuso. È l'unico punto in cui la correttezza
dipende da un ordine di costruzione, quindi ha un test dedicato che lo asserisce.

**Il tabellone si dimensiona sugli iscritti effettivi**, non sui posti
dichiarati: `S = 2^ceil(log2(n))` con il pavimento del formato (4 per
l'eliminazione diretta, 8 per il doppio KO). `max_participants` resta
obbligatorio, ma come *capienza dichiarata* da cui stimare i turni in fase di
creazione; `rounds_count` viene **riscritto all'avvio del primo turno**, che è
l'unico momento in cui il numero di presenti è certo. Sedici posti con sei
presenti significa tabellone da 8 e 3 turni, non 16 con dieci rami vuoti.

Da qui discende l'invariante che semplifica tutto il resto: poiché `S` è la
potenza di 2 *immediatamente* superiore a `n`, i buchi sono sempre meno della
metà degli slot — quindi **mai due buchi nella stessa coppia** e **mai un bye
oltre il primo turno** del winners bracket. Nel losers bracket i buchi si
propagano comunque: un bye al turno 1 non produce alcun perdente, e il nodo
corrispondente semplicemente non viene materializzato.

## Alternative Considerate

### Alternativa 1: nessuna persistenza, ricostruzione a runtime
Era lo stato di partenza.
- Pro: nessuna migration, nessuna colonna.
- Contro: il tabellone non è ricostruibile dallo storico senza assumere di
  averlo generato correttamente — cioè assumere la cosa che era rotta. E il
  losers bracket ricostruito dalle sconfitte non è deterministico: due
  giocatori con una sconfitta ciascuna sono indistinguibili, ma nel tabellone
  vero occupano posti diversi.

### Alternativa 2: un solo indice "heap" (il classico `2i`, `2i+1`)
- Pro: una colonna sola, aritmetica nota.
- Contro: descrive alberi binari completi. Il losers bracket non lo è, e
  forzarcelo dentro significa inventare una numerazione parallela per i round
  maggiori — cioè riscrivere la tripla, con più passaggi.

### Alternativa 3: una tabella `bracket_node` separata, con FK al match
- Pro: `Match` resta pulito, il tabellone è un'entità esplicita.
- Contro: ogni lettura del turno diventa una join, e ogni creazione di match
  due insert da tenere allineate. Il tabellone non ha vita propria: un nodo
  senza match non significa nulla, e un match senza nodo nemmeno. Quando due
  entità nascono e muoiono insieme, sono una entità sola.

### Alternativa 4: `bracket_group` come parte di `bracket_type` (es. `W:2`)
- Pro: nessuna colonna in più.
- Contro: un campo che contiene due informazioni non si indicizza né si
  raggruppa; e la prima query che deve dire "tutti i winners" tornerebbe a
  fare `LIKE`.

## Conseguenze

### Positive
- Gli accoppiamenti dei turni successivi sono **verificabili**: il nodo `j`
  deve accoppiare i vincitori di `2j` e `2j+1`, ed è un'asserzione che un test
  può scrivere.
- Il doppio KO diventa deterministico per costruzione: ogni giocatore ha una
  destinazione calcolata, non dedotta.
- La vista tabellone esiste perché esiste il dato: le colonne si leggono in
  una query sola, ordinate per `(group, type, round, slot)`.
- Un ritiro dopo il sorteggio non tocca l'albero: il walkover si gioca nel
  nodo che c'era già.

### Negative
- Quattro colonne nullable su `match`, che per la maggioranza delle gare
  (Amalfi, round robin, random) restano vuote.
- Le strategie a tabellone hanno ora due percorsi da mantenere finché esistono
  gare senza coordinate (vedi sotto).

### Rischi
- **Gare preesistenti**: l'eliminazione diretta mantiene un ramo legacy che
  scatta quando anche un solo match del turno precedente ha `bracket_slot`
  NULL, con un `logger.warning`. È il comportamento che quella gara ha già
  avuto nei turni precedenti — cambiarlo a metà sarebbe peggio. Il doppio KO
  **non** ha ramo legacy e solleva: il vecchio accoppiamento era non
  deterministico, quindi non esiste un "comportamento precedente" da
  preservare.
- **Backfill**: la migration `20260815_backfill_bracket_coordinates` riempie
  le coordinate **solo** per gare ferme al primo turno. Ricostruire un
  tabellone e applicarlo a turni già giocati con altri accoppiamenti
  produrrebbe un tabellone falso, che è peggio di nessun tabellone.

## Note Implementative

- Aritmetica pura: `models/matchmaking/bracket.py` (nessun import da Flask o
  SQLAlchemy, asserito da un test).
- Generazione: `models/matchmaking/strategies/direct_elimination.py` e
  `double_knockout.py`.
- Modello di vista: `models/matchmaking/bracket_view.py` (lavagne → rami →
  colonne), reso da `templates/components/_bracket_view.html`.
- Schema: `migrations/20260809_bracket_and_squadre.py`.
- Backfill: `migrations/20260815_backfill_bracket_coordinates.py`.
