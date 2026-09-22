# ADR-067 La scheda di allenamento: una forma sola, e un registro che non si riscrive

**Data**: 2026-09-20
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

La issue **#172** chiedeva «una raccolta ordinata di esercizi, come in
palestra». Il materiale che l'ha fatta diventare concreta è invece un foglio di
carta: la **scheda di allenamento di Rōnin ASD** (lv.3, v0.6), che i giocatori
compilano davvero.

Il foglio dice più di quanto dicesse la issue:

* è un **gradino di una scala**: «Scheda di allenamento lv.3», «soglia per il
  lv.4: 40/50 tiri»;
* ha **una riga per seduta**, con la data, e dieci colonne — `1 · 2 · 3dx · 3sx
  · 4dx · 4sx · 5dx · 5sx · 6dx · 6sx` — più il totale. Quattro dei sei
  esercizi si fanno **a destra e a sinistra**, e le due colonne restano
  separate perché la debolezza da un lato è la diagnosi;
* è insieme **strumento di registrazione e andamento**: la griglia riempita
  *è* il grafico;
* si compila con una cifra per colonna, in piedi, col gesso in mano.

Accanto c'è il modo opposto di allenarsi — tiri, partite e minuti distribuiti
su giorni A · B · C per sei settimane, senza nessun totale. Il primo giro di
disegno aveva fatto **due schede diverse**, una «a caselle con soglia» e una
«da palestra». L'utente le ha rifiutate entrambe (19/09): *«una sola scheda,
senza la distinzione. Ogni esercizio ha il suo "quanto farne", libero. Livello
e soglia sono facoltativi.»*

Decisioni già prese che questa ADR attua: **D7** (la seduta è un'entità con
inizio e fine, sopravvive alla chiusura dell'app), **D11** (il legame è
allievo–**scheda**–istruttore), **D17** (la soglia somma le sole voci «a
riusciti»), **D19** (niente serie × ripetizioni: al biliardo una voce è un
numero di tiri, di partite o di minuti).

## Decisione

### 1. La libertà sta sulla **voce**, non sulla scheda

Una scheda è un nome e una sequenza ordinata di voci. Ogni voce dice quale
esercizio, **quanto farne** e **come si segna** (`SheetMeasure`): fatto,
riusciti, punteggio, vinte, minuti. Livello, soglia, giorni e durata sono
interruttori facoltativi della scheda.

Non esistono «tipi di scheda», e non devono nascere: le due schede molto
diverse del contesto si compongono con lo stesso oggetto, e
`tests/new/unit/test_scheda_allenamento.py` le compone tutte e due apposta. È
il test che si accorgerebbe di un `sheet_type` aggiunto per far stare un caso
nuovo.

Col **punteggio** il «quanto farne» non c'è, e non è una svista: quanto vale al
massimo quella prova lo dice già l'esercizio (`Challenge.max_score`). Un
secondo tetto accanto sarebbe il difetto dei due `max_score` (ADR-042) rifatto
in casa d'altri.

> **Emendata il 2026-09-22** dall'[ADR-072](ADR-072-le-prove-in-scheda-sono-prove.md):
> la misura **discende dal tipo di esercizio** e non si sceglie libera, e col
> punteggio il «quanto farne» torna, ma vuol dire **quante prove** — non un
> secondo tetto. Il massimo di ogni prova resta `Challenge.max_score`.

### 2. Nel totale entrano **solo** le voci «a riusciti» (D17)

Il totale della seduta — il «40 su 50» — somma le voci a riusciti e nient'altro.
Partite vinte e minuti non si sommano a dei tiri: darebbero un numero che non
vuol dire niente, e la soglia è un numero che qualcuno guarda per decidere un
passaggio di livello. Una scheda senza voci «a riusciti» ha totale zero e non
può avere una soglia: il servizio lo dice, invece di accettarla e mostrarla
sempre irraggiungibile.

### 3. La casella si porta dietro la **misura** e il «su quanto» di quella sera

`TrainingEntry` copia `measure` e `target_amount` dalla voce al momento in cui
si segna, e non li rilegge più da lì. Se domani la voce passa da cinque tiri a
dieci, il «4 su 5» di stasera resta un quattro su cinque.

È lo stesso schema di `ChallengeShot.points` (ADR-066) e di `break_player_id`
(ADR-056), e qui la posta è il **registro**: una griglia che si riscrive alle
spalle di chi l'ha compilata non è un registro, è un'opinione di oggi sul
passato.

Conseguenza gemella: una voce **con delle registrazioni si ritira, non si
cancella** (`is_active`). Cancellarla porterebbe via le caselle già compilate —
la stessa regola di `ChallengeVariant`, che con delle prove si rinomina e non
si toglie (ADR-065).

### 4. La **versione** della scheda cresce quando cambia ciò che i numeri dicono

`TrainingSheet.version` sale quando cambia la sequenza o un «quanto farne», non
quando si corregge il nome o si sposta la soglia. Ogni seduta si porta dietro la
versione con cui è stata fatta: è così che il registro sa dove le colonne sono
cambiate.

### 5. La seduta è un'entità (D7), e si riprende

Una sola seduta aperta per scheda: «Comincia» due volte riprende quella
lasciata aperta, perché il telefono si spegne e la sala chiude. Una seduta
aperta non entra nel registro e non fa media; una seduta senza **niente**
segnato si butta, una con qualcosa dentro si chiude — un allenamento fatto male
è comunque un allenamento fatto, e cancellarlo falserebbe la serie di chi ci
tiene.

Il gesto di registrazione è **un tocco per casella**: il tocco sul numero *è* la
registrazione, e a proteggere dall'errore c'è il tocco dopo, che sovrascrive.
La stessa scelta dell'allenamento libero, per la stessa ragione — il telefono è
appoggiato alla sponda. Le voci lunghe si possono contare **tiro per tiro**
(`marks`, una stringa di `1` e `0` in ordine): il numero resta `value`, che è la
verità, e la striscia è come ci si è arrivati.

### 6. Le caselle della scheda **non** sono prove del catalogo

Una casella è un `TrainingEntry`, non un `ChallengeAttempt`. Il numero di una
voce di scheda — «4 su 5 tiri» — non è tarato come il punteggio dello stesso
esercizio nel catalogo, che ha il suo massimo e il suo modo di registrare:
mescolarli falserebbe medie e record di entrambi, e su un esercizio colpo per
colpo un totale scritto a mano sarebbe comunque rifiutato (ADR-066).

È la stessa separazione che hanno le prove d'esame, che stanno in
`exam_challenge_result` e non fra i tentativi. Incrociare i due mondi
nell'andamento è una scelta della fase 7, dove si guarda l'insieme; farlo qui
vorrebbe dire prenderla senza dirlo.

> **Chiusa il 2026-09-20** dall'[ADR-068](ADR-068-andamento-una-scala-sola.md):
> nell'andamento i due mondi entrano **insieme**, ridotti entrambi alla quota di
> ciò che era ottenibile, e non si fondono mai su un esercizio. Il divieto qui
> sopra resta intero: media e record di un esercizio sono quelli del catalogo.

> **Rovesciata il 2026-09-22** dall'[ADR-072](ADR-072-le-prove-in-scheda-sono-prove.md):
> con la misura che discende dall'esercizio, una casella «riusciti» o
> «punteggio» **è** fatta di prove del catalogo, e ogni prova nasce come
> `ChallengeAttempt`. Il motivo di questo punto — numeri tarati diversamente —
> non vale più, perché la scheda non può più tararli diversamente.

Per lo stesso motivo la seduta **non emette eventi di dominio**: XP, serie e
traguardi dell'allenamento a scheda sono lavoro della fase 7c, e un evento
aggiunto qui li deciderebbe in silenzio.

### 7. Il legame è allievo–**scheda**–istruttore (D11)

`training_sheet_reader` — scheda, utente, da quando, fino a quando. Non esiste
«Luca mi segue»: «I miei istruttori» e «I miei allievi» sono viste derivate.
Lo decide il giocatore, scheda per scheda, e vale subito (D18); la riga non si
cancella, perché «da quando a quando» è la domanda a cui quella tabella
risponde.

La tabella nasce qui perché è parte della scheda. L'interfaccia che la riempie
arriva con gli istruttori (fase 8): finché il ruolo non esiste non c'è nessuno
da cercare, e una schermata che cerca fra zero candidati è lavoro inerte.

## Conseguenze

**Positive**

* Il foglio di carta si trasferisce nell'app senza perdere niente, e senza che
  l'app diventi il foglio di una sola associazione.
* Il registro regge il tempo: una scheda che cambia non riscrive le sedute.
* Comporre è una transazione sola (`save_composition`, come per l'esame): una
  voce sbagliata non lascia la scheda scritta a metà.

**Negative, o da tenere d'occhio**

* Due mondi di numeri sullo stesso esercizio — le prove del catalogo e le
  caselle delle schede — che l'andamento dovrà **presentare insieme senza
  sommarli** (fase 7).
* Il passaggio di livello (D8: nessuno · automatico alla soglia · conferma
  dell'istruttore) **non** è in questa ADR: `above_threshold_streak` dice
  quante sedute di fila si è sopra la soglia, e chi sancisce il gradino si
  decide con gli istruttori, dove c'è qualcuno che può confermare.

## Note di attuazione

* `models/training_sheet/` — `measure.py` (il vocabolario), `models.py` (le
  cinque tabelle), `services.py` (comporre), `session_service.py` (la seduta).
* Migration `20260920_scheda_di_allenamento.py`, con **due indici unici
  parziali**: la posizione è unica fra le voci attive, e la casella è una per
  (seduta, voce, variante) — in SQL una riga con NULL non collide con nessuna,
  quindi senza il secondo indice due caselle «senza variante» passerebbero
  entrambe. Un `if` applicativo non è un vincolo (CLAUDE.md).
* `ChallengeService.delete_challenge` ora conta fra gli usi di un esercizio
  anche gli **esami** e le **schede**. Gli esami mancavano da sempre: le prove
  d'esame non stanno fra i `ChallengeAttempt`, quindi un esercizio già
  sostenuto risultava «mai utilizzato» e la cancellazione fisica si portava via
  la voce dell'esame — e con lei, in cascata, i risultati.

## Riferimenti

* Issue **#172**; `docs/redesign-7c/canvas-tpa-esercizi/PIANO.md`, fase 6.
* [ADR-042](ADR-042-certified-exam.md) — i due `max_score`, e l'esame come
  sequenza ordinata.
* [ADR-065](ADR-065-profilo-dell-esercizio.md) — le varianti come etichette di
  uno stesso esercizio, mai come secondo esercizio.
* [ADR-066](ADR-066-prova-fatta-di-colpi.md) — il dato che descrive un fatto si
  persiste al momento del fatto.
