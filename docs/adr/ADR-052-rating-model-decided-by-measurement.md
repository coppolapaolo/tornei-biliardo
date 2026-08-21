# ADR-052 Fra Elo iterativo a rack e rifit globale si decide misurando

**Data**: 2026-08-21
**Stato**: Proposed
**Decisori**: Paolo Coppola

## Contesto

Il motore dei rating è l'Elo classico, invariato dall'inizio:
`RatingCalculationService.calculate_expected_score` (`models/rating/calculation_service.py:30`)
usa la logistica in base 10 con divisore 400, `ELO_K_FACTOR = 32` è costante, e
`_process_two_player` (riga 313) legge **soltanto** `winner_id` per produrre
`s = 1 / 0 / 0.5`.

Da qui discendono due limiti che si vedono a occhio nudo su una gara vera:

1. **il margine è buttato via**. Un 7–0 e un 7–6 muovono i rating in modo
   identico, benché il numero di rack sia già in tabella
   (`Match.player1_score` / `player2_score`). Nel biliardo il punteggio esatto
   è il segnale più ricco che abbiamo, e lo stiamo scartando ogni volta;
2. **la lunghezza della corsa non conta**. Una vittoria in una corsa a 3 pesa
   quanto una in una corsa a 9, pur avendo una componente di fortuna molto più
   alta. Con `K=32` fisso, sulle corse brevi il rating insegue il rumore.

La domanda nasce da un documento su FargoRate (una conversazione con Gemini,
allegata alla discussione del 2026-08-21) che propone di passare a un modello
**Bradley-Terry a livello di rack** in base 2 — 100 punti = probabilità doppia
di vincere **il singolo rack** — con `ΔR = k·(W − N·p)`, un `k` decrescente
sulla *robustness* (rack accumulati) e una deviazione standard σ(N) stile
Glicko. La tesi di fondo è corretta e va raccolta. I numeri di quel documento
invece **non** vanno raccolti: sono in buona parte non eseguiti (vedi
*Note implementative → Cosa non prendere dal documento sorgente*).

Il documento chiude però con una conclusione che per noi è **falsa**, e che è
la ragione di questo ADR: «FargoRate vero non è implementabile, richiede
ottimizzazione numerica su grafi enormi, quindi usa l'iterativo». Quel consiglio
vale per chi ha centinaia di migliaia di giocatori. Noi abbiamo lo storico
completo in un file SQLite, qualche centinaio di giocatori, e già uno script
che rigioca l'intera storia da zero (`scripts/recalc_elo.py`). Per noi il
rifit globale è alla portata — quindi la scelta è aperta, e non è ovvia.

## Fuori perimetro

Questo ADR parla **solo** del calcolo del rating. In particolare **non** decide
niente sull'handicap, che è un tema separato e più grande di quanto il
documento sorgente lasci intendere:

- l'handicap usato finora nelle gare è la **wild ball**, e i giocatori lo
  gestiscono **fuori dall'app**: per il sistema quelle partite sono partite
  normali con un flag acceso;
- esistono handicap «classici» a rack assegnati (uno o più rack di vantaggio
  alla partenza), che l'app non modella;
- l'handicap *automatico* calcolato dai rating — la parte del documento
  sorgente su corse asimmetriche e tabelle di equità — è solo una terza
  possibilità fra queste, ed è quella più lontana da ciò che si usa oggi.

Sono tutte cose da valutare eventualmente in seguito, e sono tracciate a parte
nella issue [#192](https://github.com/coppolapaolo/tornei-biliardo/issues/192).
Tirarle dentro adesso significherebbe far dipendere una decisione misurabile
(quale motore di rating prevede meglio) da un progetto di dominio non ancora
iniziato.

## Decisione

Tre cose si decidono adesso, una si decide misurando.

### 1. L'unità di misura passa dal match al rack (deciso)

Qualunque delle due strade si prenda, il dato osservato non è più
«chi ha vinto» ma «quanti rack a quanti». Non serve nessuna migrazione: i rack
sono già persistiti, e le partite già escluse restano escluse (walkover e
handicap fra categorie diverse, `RatingEligibility`, ADR-049).

### 2. La scala nuova non converte la vecchia: le si affianca (deciso)

100 punti in base 2 corrispondono a circa 120 punti in base 10/400, ma la
conversione **non si può fare**, perché le due scale non misurano la stessa
cosa: 2:1 *per rack* significa circa 80% *per match* in una corsa a 7. I rating
attuali non si riscalano, si rifanno da zero.

Il pool `ELO` esistente pilota categoria e handicap
(`models/rating/models.py:26`) e alimenta la gamification, con soglie tarate
sul valore iniziale 1200: cambiargli la scala sotto i piedi romperebbe
traguardi e livelli. Il modello nuovo nasce quindi come **membro aggiuntivo di
`RatingSystem`**, calcolato in parallelo e non mostrato, finché la misura non
ha deciso. Aggiungere un membro a un enum usato da una colonna `db.Enum` è
sicuro; *rinominarne* uno no (presidio in
`tests/new/unit/test_enum_columns_store_values.py`).

### 3. Fra iterativo e rifit globale decide un backtest, e il protocollo è questo (deciso il protocollo, aperto l'esito)

Le due strade in gara:

- **A — Iterativo a rack.** Un aggiornamento per match, in ordine cronologico:
  `ΔR = k·(W − N·p)`, con `p = 1/(1 + 2^((R_b − R_a)/100))` e `k` funzione
  decrescente dei rack accumulati.
- **B — Rifit globale notturno.** Massima verosimiglianza Bradley-Terry su
  **tutto** lo storico, con regolarizzazione L2 verso il valore iniziale;
  rieseguita ogni notte come fa FargoRate.

Il protocollo, fissato *prima* di guardare i risultati:

**Passo 0 — c'è abbastanza segnale?** Prima di scrivere qualunque modello si
contano, in produzione: partite ammissibili, rack totali, giocatori con almeno
30 rack, e quante **componenti connesse** ha il grafo dei confronti. Un rating
confronta solo dentro una componente: se il circolo è spezzato in gruppi che
non si incontrano mai, i numeri fra gruppi diversi non significano niente, e
questo colpisce il rifit globale più dell'iterativo. Se il passo 0 dice che i
dati sono troppo pochi, l'ADR si chiude qui e non si tocca niente.

**Dati.** Le partite vengono da **due** tabelle, `match` e `individual_match`;
la forma unificata la produce già
`PlayerHistoryService.get_unified_match_history`. Interrogarne una sola non dà
errore, dà meno partite di quelle giocate.

**Divisione fra addestramento e verifica: temporale, mai casuale.** Un rating è
una previsione, e va valutato sul futuro. Uno split casuale lascerebbe filtrare
nel passato le partite successive dello stesso giocatore — il modello
sembrerebbe bravissimo. Si taglia quindi a una data `T`: si addestra su tutto
ciò che è `≤ T`, si valuta su `(T, T+1 mese]`. E non su un solo `T`: **origine
mobile**, un taglio al mese, i risultati si sommano — altrimenti si sta
misurando la fortuna di aver scelto quel mese.

**Metrica: log-loss, non accuratezza.** «Quante partite indovina» è la metrica
sbagliata: è cieca alla calibrazione e degenera quando il favorito vince quasi
sempre. Si usa la **log-loss** (che è esattamente la verosimiglianza fuori
campione, quindi la stessa quantità che il modello B massimizza in
addestramento), affiancata dal punteggio di Brier e da una verifica di
**calibrazione**: raggruppate le previsioni in decili di `p`, la frequenza
osservata deve seguire quella prevista. Un modello può vincere sulla log-loss
ed essere scalibrato; per l'handicap serve la calibrazione, non solo l'ordine.

**Due livelli, perché il motore attuale non parla di rack.** L'Elo binario di
oggi non produce una probabilità per rack, quindi il confronto a tre non può
avvenire a quel livello:

- *a livello di rack*: solo A contro B, più la baseline `p = 0.5`;
- *a livello di match*: tutti e tre. Le probabilità per rack di A e B si
  portano a probabilità di match con la binomiale negativa (corse) o la
  binomiale semplice (formati a rack fissi), e lì si confrontano con l'Elo
  attuale sulla stessa scala.

Senza questo passaggio il confronto col motore in produzione non esiste, e
resterebbe il dubbio — legittimo — che il modello nuovo sia solo più
complicato.

**Incertezza: bootstrap sui giocatori, non sulle partite.** Le partite dello
stesso giocatore sono correlate: ricampionarle come indipendenti restringe
l'intervallo di confidenza fino a farlo mentire. Si ricampionano i **giocatori**
con reimmissione, e si guarda l'intervallo sulla *differenza* di log-loss fra i
due modelli, appaiata sugli stessi match.

**Regola di aggiudicazione, dichiarata adesso.** Se l'intervallo al 95% sulla
differenza **contiene lo zero**, vince **A (iterativo)**. Non perché sia
migliore, ma perché a parità di accuratezza è preferibile ciò che l'utente può
capire: «hai preso +6 punti stasera» contro un rating che cambia di notte senza
aver giocato. La regola è scritta prima della misura di proposito: dopo, si
troverebbe sempre il modo di far vincere il modello che nel frattempo è
piaciuto di più.

## Alternative Considerate

### Alternativa 1: A — Elo iterativo a rack

- **Pro**: costo per match costante e trascurabile; delta immediato e
  spiegabile, che la gamification può notificare; `MatchRatingHistory` continua
  a funzionare com'è, quindi `revert_match_result` resta valido; nessuna
  dipendenza nuova; nessun job notturno che scriva sul DB.
- **Contro**: dipende dall'ordine cronologico (`[M1,M2,M3]` e `[M3,M2,M1]` non
  danno lo stesso risultato); il passato resta congelato al valore che
  l'avversario aveva allora; un valore iniziale sbagliato si smaltisce in
  decine di partite; la variante con `k` asimmetrico fra novizio e veterano
  — quella consigliata dal documento sorgente — **rompe la somma zero** e
  genera deriva (vedi note).

### Alternativa 2: B — Rifit globale Bradley-Terry notturno

- **Pro**: indipendente dall'ordine; retroattivo (una vittoria di un anno fa
  contro un giocatore che si è poi rivelato forte vale di più, oggi);
  insensibile al valore iniziale; è il modello che i dati giustificano, non una
  sua approssimazione; e si sposa meglio con ADR-048, che già stabilisce che i
  **derivati si ricalcolano da zero** — con B il ricalcolo *è* il normale
  funzionamento, non un'operazione eccezionale.
- **Contro**: il rating cambia senza aver giocato, il che è difficile da
  spiegare e mal si accorda con le notifiche di gamification; `ΔR` per singolo
  match non esiste più, quindi `revert_match_result`
  (`calculation_service.py:235`) perde significato e va ripensato; richiede un
  job notturno che **scrive** sul DB — e su PythonAnywhere ogni scrittura
  pesante di notte va guardata con sospetto (ADR-045); serve un ottimizzatore
  (fattibile in Python puro con Newton/IRLS su matrice sparsa; `scipy` non è in
  `requirements.txt` e aggiungerlo va motivato a parte).

### Alternativa 3: Glicko-2 da libreria

- **Pro**: RD e volatilità già implementate e collaudate, niente da tarare.
- **Contro**: è un modello **per match**. Butterebbe via il margine di
  vittoria, cioè esattamente il motivo per cui questo ADR esiste.

### Alternativa 4: non cambiare niente

- **Pro**: costo zero, nessun rischio su categoria/handicap/gamification.
- **Contro**: continuiamo a scartare il dato migliore che raccogliamo, e le
  gare con corse brevi continuano a produrre rating rumorosi. È comunque
  l'esito da accettare senza aggirarlo se il passo 0 dice che i dati non
  bastano, o se nessuno dei due modelli batte quello attuale in modo
  significativo.

## Conseguenze

### Positive

- La scelta smette di essere un'opinione: si decide su dati nostri, con una
  regola scritta prima.
- Il banco di prova resta utile dopo la decisione: è lo stesso strumento con
  cui si tarano i parametri del modello scelto quando i rack saranno di più, e
  con cui si verifica che una modifica al motore non abbia peggiorato le
  previsioni. Oggi una modifica del genere non è verificabile in alcun modo.
- La calibrazione misurata dice quanto ci si può fidare del rating quando lo si
  mostra a un giocatore. È una domanda che ci si pone comunque, e finora non
  aveva risposta.

### Negative

- Due sistemi di rating convivono per tutta la durata della misura: il pool in
  produzione e quello nuovo, silente. Va scritto chiaramente quale piloti cosa,
  o si genera la stessa confusione che ADR-049 ha dovuto sbrogliare.
- Il backtest è codice che serve una volta e va mantenuto lo stesso, perché
  senza di esso la decisione non è riproducibile.

### Rischi

- **`PlayerRating.rating_value` è `Integer`** (`models/rating/models.py:41`).
  Con l'unità a rack i delta sono dell'ordine di 1–2 punti: l'arrotondamento a
  intero è dello stesso ordine del segnale, e su migliaia di partite
  introdurrebbe una deriva sistematica. Il pool nuovo richiede una colonna in
  virgola mobile. Con `K=32` il problema non si vedeva.
- **Il backtest non deve toccare la produzione.** Si esegue su una **copia del
  file `.db`**, per la stessa ragione documentata in ADR-048: un
  `@transactional` annidato committa la transazione esterna, e un rollback non
  annullerebbe nulla. Copiare il file è più semplice che essere prudenti.
- **Esito nullo.** È possibile — e va accettato — che la differenza fra i tre
  modelli non sia distinguibile dal rumore con i dati che abbiamo. In quel caso
  la risposta è «non ancora», e l'ADR si rilegge quando i rack saranno il
  doppio.

## Note Implementative

### Perché contare i rack di una corsa a N è lecito

Obiezione naturale: in una corsa a 7 il match si ferma quando uno arriva a 7,
quindi i rack non sono un campione di prove indipendenti — l'ultimo lo vince
sempre il vincitore. Sembra un bias, e non lo è: la regola d'arresto dipende
solo dagli esiti già osservati, quindi il nucleo della verosimiglianza resta
`p^W · q^L` e il fattore combinatorio non dipende da `p`. Di conseguenza
`W − N·p` è il **gradiente esatto** della log-verosimiglianza, non
un'approssimazione. È la ragione per cui FargoRate può contare i rack di corse
di lunghezza diversa nello stesso calderone, ed è il motivo per cui questa
strada è praticabile senza correzioni.

Attenzione a non estendere l'argomento all'handicap. L'handicap usato finora
nelle gare è la **wild ball**, e agisce *dentro* il rack: cambia la probabilità
di vincerlo, quindi i rack di quelle partite non sono un campione valido più di
quanto lo sia l'esito del match. Il rack come unità di misura **non** rende
recuperabili quelle partite, e la regola di ADR-049 resta esattamente com'è.
Diverso sarebbe l'handicap a rack regalati o a corsa asimmetrica — ma sono
formati che l'app oggi non modella (vedi *Fuori perimetro*).

### I parametri non si copiano, si stimano

`σ₀ = 75`, `N_ref = 180`, `k_max = 2.5`, `β ∈ [0.05, 0.25]`: i valori del
documento sorgente hanno l'aria di costanti di riferimento, ma non sono
calibrati su niente. Vanno stimati sui nostri dati, dentro lo stesso backtest,
e ogni valore preso a prestito va segnato come tale.

### Il `k` asimmetrico rompe la somma zero

Il documento consiglia `ΔR_A = k(N_A)·s` e `ΔR_B = −k(N_B)·s` con `k` diverso
per i due giocatori, così che il novizio si muova in fretta e il veterano no.
Ma allora i punti persi da uno non sono quelli guadagnati dall'altro, e il
sistema crea o distrugge punteggio a ogni partita: simulando 1000 incontri
novizio/veterano con sorpresa a media nulla si vedono decine di punti comparire
dal nulla. Se si sceglie A, la sensibilità differenziata va ottenuta senza
rompere la conservazione (per esempio ripartendo un delta comune in proporzione
alle incertezze), oppure va accettata consapevolmente insieme a un'ancora che
ricentri il pool.

### Cosa non prendere dal documento sorgente

Gli esempi numerici del PDF sono in larga parte **non eseguiti**. Verificati:

| Affermazione nel documento | Valore reale |
|---|---|
| Corsa equa fra 620 (σ=8) e 530 (σ=35): **8–5**, equity 49,7% | 8–5 vale **58,2%**; la corsa equa è **9–5** (49,9%) |
| Robustness: `k` veterano ≈ 0,51, delta +6,55 / −1,53 | con la sua stessa `compute_k`: `k` = **0,67**, delta **+5,77 / −1,77** |
| Correzione per incertezza: «vincolo di sicurezza» | sposta la probabilità di rack di **0,15 punti percentuali**: inerte |
| Formato a 10 rack, 580 vs 500: 72,5 / 17,3 / 10,2 % | **71,8 / 16,8 / 11,4 %** |
| Winner-breaks: `p_on = p+β`, `p_off = p−β` | non conserva la frequenza marginale: con `p=0,70` e `β=0,15` la frequenza reale diventa **0,785**, cioè il modello rende il favorito più forte di quanto dica il suo rating, e il «+4–8% di equity» attribuito alle strisce è in buona parte artefatto |
| `find_best_handicap(...)` rispetta `base_race` | con due giocatori pari livello restituisce **5–5**: nessuno spareggio fra le coppie che valgono 50% |

Corretti invece, e verificati: l'esempio 7–2 / 7–6 (+1,58 / −0,83), la
binomiale negativa, e l'impianto concettuale generale.

Le sezioni del documento su winner-breaks e sulle tabelle di handicap restano
fuori da questo ADR (vedi *Fuori perimetro*); se un giorno serviranno, la
simulazione markoviana va comunque riscritta calibrando `p_on` e `p_off` in
modo che la frequenza marginale stazionaria torni a `p`.

### Dove vive cosa

- Il banco di prova: `scripts/rating_backtest.py`, di sviluppo, su copia del
  `.db`, con `--dry-run` come comportamento predefinito (convenzione di
  `scripts/repair_round_classification_racks.py`).
- Lo script **non** usa `prod_env` finché resta di sviluppo, quindi resta fuori
  dalla regola sull'ordine degli import; se un giorno dovesse girare in
  produzione va prima agganciato a `bootstrap_and_create_app`.
- Il filtro di ammissibilità resta uno solo:
  `RatingEligibility.exclusion_reason`, con `build_index` per non fare due
  query per match.
- La policy scelta atterrerà in `models/rating/`, accanto a
  `calculation_service.py`, non nei chiamanti: la lezione di ADR-049 è che una
  condizione duplicata in quattro posti diverge in silenzio.

### Riferimenti

- ADR-049 — quali partite contano per l'Elo (categorie e handicap)
- ADR-048 — fatti riassegnati, derivati ricalcolati
- ADR-045 — niente scritture spensierate sul DB di produzione
- `models/rating/CLAUDE.md`
