# ADR-072 Le prove fatte in scheda sono prove: la misura discende dall'esercizio, e ogni tentativo entra nel catalogo

**Data**: 2026-09-22
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Il 21/09 l'utente ha usato una scheda di allenamento per la prima volta su
esercizi veri, e ha trovato tre cose che non andavano:

* **ogni esercizio aggiunto nasceva «riusciti su 5 tiri»**, qualunque fosse
  l'esercizio. Il 5 era un default della pagina di composizione
  (`compose.html`), la misura un default del modulo. La libertà della voce
  (ADR-067 §1) c'era, ma stava dietro un tocco che nessuno faceva, e il
  default non guardava l'esercizio;
* **un esercizio a punteggio si segnava con un numero solo** per seduta. Non
  c'era modo di dire «fallo tre volte, e conta la media»: la misura
  «punteggio» rifiutava esplicitamente un «quanto farne» (ADR-067 §1);
* **le caselle della scheda non contavano come prove dell'esercizio.** Chi
  faceva un esercizio dieci volte dentro una scheda non risultava fra chi
  «l'ha provato», non poteva votarlo, e le sue medie e il suo record nel
  catalogo restavano fermi. Era una decisione presa apposta (ADR-067 §6,
  confermata dall'ADR-068 §2), motivata dal fatto che un «4 su 5 tiri» non è
  tarato come il punteggio dello stesso esercizio nel catalogo.

La terza è quella che pesa. Il motivo dell'ADR-067 §6 era vero finché la
misura di una voce era **libera**: «riusciti su 5» su un esercizio a punteggio
è davvero un numero di un altro tipo. Ma se la misura discende dal tipo
dell'esercizio — riusciti sugli esercizi a esito netto, punteggio su quelli a
punteggio — allora ogni casella della scheda **è** una o più prove del
catalogo, tarate esattamente come lì. A quel punto tenerle fuori non protegge
niente: nasconde.

Decisioni dell'utente del 22/09/2026, che questa ADR attua:

1. la misura discende dal tipo di esercizio;
2. gli esercizi a punteggio si fanno N volte, con somma, media, mediana o
   massimo a scelta;
3. ogni prova fatta in scheda finisce nelle statistiche dell'esercizio;
4. gli esercizi colpo per colpo (ADR-066) si giocano nella **stessa schermata
   del catalogo**, e la prova torna nella casella;
5. la prova in scheda **non dà XP da sola**: lo dà la seduta chiusa;
6. il numero di tentativi **non ha un default**: chi aggiunge una voce lo
   scrive.

## Decisione

### 1. La misura discende dall'esercizio

`SheetMeasure.for_challenge(challenge)` dice come si segna una voce:
**riusciti** su un esercizio a esito netto (`pass_fail_only`), **punteggio**
su uno a punteggio. Sono le due misure che fanno di una casella una prova del
catalogo, e non si scambiano: «riusciti» su un esercizio a punteggio, o
«punteggio» su uno a esito netto, sono rifiutate alla composizione
(`SheetMeasure.allowed_for`).

Restano **fatto**, **vinte** e **minuti** per le voci che non sono una prova
del catalogo — il riscaldamento spuntato, le partite contro il ghost, i venti
minuti di tiri lunghi. Si segnano come prima e **non** producono prove.

### 2. Il «quanto farne» è il numero di prove, e il punteggio si aggrega

Con «punteggio» il «quanto farne» torna, e vuol dire **quante prove**: tre
volte lo Spot Shot Rally. Non è il secondo tetto che l'ADR-067 §1 rifiutava
— quello era un massimo accanto a `Challenge.max_score`; questo è un numero
di ripetizioni, e il massimo di ogni prova resta quello dell'esercizio.

Come le N prove diventano il numero della casella lo dice `ScoreAggregation`
sulla voce: **somma**, **media**, **mediana**, **massimo**. Si copia sulla
casella al momento in cui si segna, come misura e «su quanto» (ADR-067 §3):
cambiare «media» in «massimo» sulla voce domani non riscrive il registro.

Con «riusciti su N» non c'è niente da scegliere: N prove a esito netto, e il
numero è quante sono riuscite. È la stessa cosa di prima, detta con le prove.

**Nessun default sul numero.** Il 5 era un'assunzione sbagliata su ogni
esercizio che non fosse quello del foglio di Rōnin. Chi aggiunge una voce
dice quante volte, e finché non lo dice la scheda non si salva.

### 3. Ogni prova in scheda è un `ChallengeAttempt`

Una casella «riusciti» con 4 su 5 sono **cinque prove**: quattro riuscite e
una no. Una casella «punteggio» con tre prove sono tre `ChallengeAttempt` con
i loro punteggi, e il numero della casella è l'aggregazione. Le prove portano
`training_entry_id`, il rimando alla casella, e **spariscono con lei**: chi
svuota una casella dice che quelle prove non ci sono state.

È così che le statistiche dell'esercizio si accorgono della scheda **senza
che nessun lettore cambi**: chi ha provato (`popularity.has_tried`), chi può
votare, la riga sulla card, medie e record, lo storico d'allenamento, gli
obiettivi. Sono tutti già sulla tabella `challenge_attempt`.

Due conseguenze dette:

* chi scrive «4 su 5» come totale, senza contare tiro per tiro, produce
  cinque prove con la **stessa ora**. Non si sa in che ordine sono venute, e
  la striscia non c'è: è quello che si sapeva anche sul foglio di carta.
  Riscrivere la casella **rifà** le prove — sono la stessa cosa detta due
  volte;
* `TrainingEntry.value` può essere una **media**, cioè non un intero. La
  colonna resta com'è: SQLite scrive 6,4 dove scriveva 6, e il modello lo
  legge come intero quando lo è, così le caselle «riusciti» non cambiano
  faccia.

### 4. L'andamento conta le prove, non più la casella

L'ADR-068 leggeva le caselle delle schede come osservazioni. Ora che una
casella «riusciti» o «punteggio» è fatta di prove, quelle prove **entrano dal
lato del catalogo** — una osservazione per prova, con `from_sheet=True` — e
la casella non si conta più, o si conterebbe due volte. Le caselle senza
prove (fatto, vinte, minuti) restano lette come prima.

Il divieto dell'ADR-068 §2 di fondere i due mondi *sullo stesso esercizio*
non ha più oggetto: non ci sono più due mondi sullo stesso esercizio. Ci sono
prove, alcune fatte da sole e alcune dentro una scheda.

### 5. Colpo per colpo: la stessa schermata, e la prova torna nella casella

Un esercizio che si registra colpo per colpo o con estrazione (ADR-066) ha
il suo modo di registrare, e la scheda non lo rifà: la seduta manda alla
schermata del catalogo con il **contesto** della casella (seduta, voce,
lato), e alla chiusura la prova si aggancia alla casella e si torna alla
seduta. L'aggancio avviene **prima** della chiusura, così l'evento della
prova completata nasce già con l'origine giusta.

*Scartata*: ammetterli solo come «fatto». Avrebbe tenuto fuori dalle schede
proprio gli esercizi più ricchi di dati.

### 6. L'XP lo dà la seduta

Una prova in scheda pubblica l'evento di prova completata con origine
`sheet`: le serie settimanali lo contano — allenarsi è allenarsi — ma **l'XP
non lo paga**. Lo paga la seduta chiusa, come già faceva: pagare anche ogni
prova avrebbe moltiplicato l'XP di una seduta per il numero di tiri.

### 7. Il totale e la soglia non cambiano

Sommano le sole voci «riusciti» (D17). Una voce «punteggio» con aggregazione
«somma» non entra: sarebbe sommare punti a tiri riusciti, e la soglia è il
numero con cui si decide un passaggio di livello.

## Conseguenze

**Positive**

* Un giocatore che si allena solo con la scheda ha il catalogo che lo
  racconta: prove, medie, record, «l'hai provato», il voto.
* Un solo tipo di numero per esercizio, tarato come lo tara l'esercizio.
* La composizione non chiede più di scegliere fra cinque modi: propone quello
  giusto e chiede quante volte.

**Negative, o da tenere d'occhio**

* Il registro può contenere medie con la virgola accanto a interi: chi lo
  stampa formatta, non tronca.
* Le caselle scritte **prima** di questa ADR non hanno prove dietro: non si
  ricostruiscono (l'ora e l'ordine non si sanno), e l'andamento continua a
  leggerle come caselle. È una discontinuità del 22/09/2026, e si vede solo
  nei numeri del catalogo di chi aveva già usato una scheda.
* Le voci «riusciti» già composte su esercizi a punteggio restano leggibili
  (`allowed_for` vale alla composizione, non alla lettura), ma alla prossima
  modifica della scheda vanno riportate a «punteggio».

## Note di attuazione

* `models/training_sheet/measure.py` — `for_challenge`, `allowed_for`,
  `ScoreAggregation`; `models.py` — `aggregation` su voce e casella,
  `TrainingEntry.attempts`; `session_service.py` — le prove nascono qui
  (`record`, `mark`, `record_score`, `attach_attempt`).
* `models/challenge/models.py` — `ChallengeAttempt.training_entry_id`;
  `events.py` — `DrillOrigin.SHEET`; il gestore XP in
  `models/gamification/event_handlers.py` la riconosce.
* `models/andamento/view.py` — le caselle con prove non si contano più.
* Migration `20260922_prove_in_scheda.py`.
* Presidio: `tests/new/unit/test_prove_in_scheda.py`.

## Riferimenti

* [ADR-067](ADR-067-scheda-di-allenamento.md) §1, §3, §6 — emendata da
  questa.
* [ADR-068](ADR-068-andamento-una-scala-sola.md) §2 — emendata da questa.
* [ADR-066](ADR-066-prova-fatta-di-colpi.md) — la prova fatta di colpi.
* [ADR-065](ADR-065-profilo-dell-esercizio.md) — chi ha provato, e chi vota.
