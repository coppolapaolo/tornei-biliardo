# ADR-044 Il referto TPA: si annota il gioco, non il punteggio

**Data**: 2026-08-16
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Un match singolo, oggi, produce un dato solo: chi ha vinto quanti rack. È il
minimo che serve per una classifica e non dice niente su come si è giocato. Due
partite finite 5-3 possono essere una passeggiata e una rimonta, un giocatore
che chiude tre rack in una visita e uno che vince perché l'avversario sbaglia.

Il metodo che l'ambiente del biliardo americano usa per dirlo esiste da
trent'anni: il **referto Accu-Stats**, da cui si ricava il *Total Performance
Average*.

```
TPA = bilie imbucate / (bilie imbucate + errori)
```

Si annota ogni visita al tavolo — quante bilie sono entrate e **perché** il
turno è finito — e alla fine esce un numero solo, confrontabile fra partite e
fra giocatori, che si legge come una media di battuta nel baseball.

Esiste già un'applicazione JavaScript che fa esattamente questo
([TPA-scorekeeper](https://github.com/coppolapaolo/TPA-scorekeeper)), scritta
dallo stesso autore di questa piattaforma e usata sul campo. È lo stato
dell'arte da cui si parte, non un requisito da reinventare.

## Decisione

### Il referto è una **funzione da sbloccare**, non un'opzione nel form

Il referto TPA non è più difficile da capire di un segnapunti: è più difficile
da **compilare mentre si gioca**. Chiede di distinguere un tiro sbagliato da una
difesa, un kick da un miss, e di deciderlo in due secondi con la stecca in mano.
Proposto a chi si è appena iscritto sarebbe rumore; a chi ha già giocato gare,
campionati, match, drill ed esami è la cosa che stava aspettando.

**Il gate sta sul *prendere* un referto, non sul leggerlo.** Sbloccare la
funzione vuol dire poter aprire un referto; una volta che il referto esiste,
riguarda tutti e due i giocatori, e chi non ha sbloccato niente lo vede
comunque in sola lettura. È la stessa regola del TPA nel profilo: il dato
esiste e ti riguarda, nasconderlo sarebbe assurdo — e senza questo l'interfaccia
prometterebbe una cosa («l'altro giocatore lo vede aggiornarsi») che il
decoratore smentisce.

Il gate non vale nemmeno sulla scrittura del compilatore, e non per pigrizia:
se l'admin irrigidisse le regole a partita in corso, chi sta compilando
resterebbe chiuso fuori da un referto a metà, con il segnapunti normale
nascosto e nessun modo di segnare i rack. Chi può scrivere resta una cosa sola
— il compilatore — e quel controllo sta nel servizio.

Il gate è la macchina ABAC che c'è già (`FeatureConfig` + `UnlockEngine`), con
codice feature `tpa_scoresheet`. Le soglie iniziali — una gara, un campionato,
tre match individuali, tre drill, un esame certificato — sono **seminate dalla
migration e poi di competenza dell'admin**, che le cambia da
`/gamification/admin/features/tpa_scoresheet` senza toccare il codice. La
migration non le riscrive se la feature esiste già, per non calpestare una
regola decisa a mano.

Sono servite due metriche nuove, perché nessuna delle esistenti diceva
"campionati" e "match individuali": `campionati_played` (campionati distinti in
cui l'utente ha almeno un'iscrizione a una gara) e `individual_matches_played`
(match individuali conclusi e confermati). Entrambe compaiono nel menù a tendina
della gestione feature, altrimenti sarebbero regole scrivibili solo da chi
conosce il codice.

### Il punteggio del match **discende** dal referto

È la decisione che rende la funzione utile invece che noiosa. Chi tiene il
referto non segna i rack: il tasto `G`, o un turno che imbuca l'ultima bilia,
chiude il rack e crea l'`IndividualRack` da solo. Da lì in poi il match prosegue
com'è sempre stato — distanza, conferma bilaterale, validazione.

L'alternativa era tenere le due cose separate, con il referto come traccia
parallela facoltativa. È stata scartata: significava chiedere due volte lo
stesso dato a chi sta giocando, e accettare che prima o poi il punteggio e il
referto raccontassero due partite diverse. Quando divergono, quale delle due è
vera non lo sa nessuno.

Conseguenza pratica: con un referto aperto il segnapunti normale **sparisce**
dalla pagina del match. Due segnapunti sullo stesso incontro si
contraddirebbero al primo tocco. E il referto si può aprire solo **prima del
primo rack**: aperto dopo, dovrebbe cancellare rack veri per ripartire da 0-0.

### Lo tiene **una persona sola**, ed è uno dei due giocatori

Nel TPA vero il referto lo tiene uno statistico a bordo tavolo. Qui lo tiene chi
lo apre; l'altro giocatore vede la stessa schermata aggiornarsi, in sola
lettura. Un solo scrittore significa nessun conflitto da risolvere e nessuna
domanda su chi avesse ragione.

### Si salva **quello che il compilatore preme**, non lo stato che ne risulta

Il dato persistito è un registro ordinato di comandi (`TpaComando`): `"3"`,
`"M"`, `"S"`, `"end"`. Rack, turni, bilie rimaste, errori e TPA non stanno su
nessuna colonna — si ricavano rigiocando il registro nel motore.

Tre motivi, in ordine di importanza:

1. **Una sola verità.** Un totale salvato accanto ai dati che lo generano è un
   totale che prima o poi diverge: dopo un annulla, dopo una correzione, dopo un
   cambio di regola.
2. **L'annulla è esatto.** Togliere l'ultimo comando e rigiocare riporta allo
   stato di un istante prima, comprese le bilie sul tavolo e i rack assegnati,
   senza dover sapere quale casella era stata toccata per ultima.
3. **Le regole restano correggibili.** Se un giorno un errore si conta
   diversamente, i referti già compilati si rileggono con le regole nuove invece
   di restare cristallizzati su un numero vecchio.

Il costo è rigiocare a ogni lettura: qualche centinaio di comandi per partita,
cioè niente. L'alternativa — una riga per turno, con le annotazioni in colonna —
sarebbe più comoda da interrogare in SQL, ma renderebbe l'annulla un'operazione
da inventare e i totali una cosa da tenere in sincrono a mano.

### Il motore è un **port fedele** dell'app JS, e la fedeltà è verificata

`models/tpa/engine.py` è Python puro: niente Flask, niente database, niente I/O.
Le regole Accu-Stats stanno lì e solo lì.

Non è stato riscritto "ispirandosi" all'app JS: è stato tradotto riga per riga e
poi **verificato per differenza**. Un banco di prova esegue l'app JS originale
su 600 partite generate a caso (200 per disciplina, ~37.000 mosse) e confronta
con il motore Python i totali di ogni categoria, il TPA, i riconoscimenti di
rack, l'insieme di pulsanti proposti a ogni passo e il momento in cui si può
passare il tavolo. Zero divergenze. Il corpus è committato
(`tests/new/fixtures/tpa_js_reference_corpus.json.gz`, 68 KB) e girà a ogni
esecuzione dei test.

Questo importa perché i referti compilati con l'app JS e quelli compilati qui
devono essere confrontabili. Un port "quasi uguale" produrrebbe due scale di TPA
diverse che si somigliano abbastanza da non far sospettare niente.

### Le divergenze dall'esempio del PDF Accu-Stats sono **note e conservate**

La sessione d'esempio stampata in *Accu-Stats Scoresheet Instructions* (21
inning) è riprodotta nei test. Il punteggio finale combacia (7-2) e quasi tutte
le categorie, ma tre voci no:

1. **Inning 10**: una bilia, poi kick riuscito che finisce con il battente in
   buca. Il PDF conta solo un errore di posizione; il motore addebita anche un
   errore di kick, perché la regola implementata è "kick che finisce in fallo =
   errore di kick", senza distinguere se la battuta fosse buona.
2. **Inning 4 del giocatore 2**: bilie imbucate *e* battente in buca. Qui valgono
   due errori, come il PDF stesso fa all'inning 14, che è la stessa situazione.
   All'inning 4 il PDF ne conta uno solo: è il PDF a contraddirsi.
3. **Bilie accreditate al giocatore 1**: 40 contro le 38 dichiarate dal PDF, che
   non dice quali due non accredita e non allega il referto compilato.

Si conservano perché sono la lettura dell'app JS con cui i referti si compilano
oggi, e allinearsi al PDF cambierebbe i numeri già prodotti. Un test le fissa
esplicitamente: se un giorno si decide di cambiarle, quel test si rompe, ed è il
segnale che serve una migrazione dei referti, non una correzione silenziosa.

### Solo palla 8, palla 9 e palla 10

Il TPA è definito per le discipline a bilia designata con un rack di dimensione
nota: il motore ci calcola sopra le bilie rimaste. In One Pocket, Straight Pool
e Bank Pool non è che "non è supportato" — è che non vuol dire niente. La pagina
lo dice con quelle parole invece di nascondere il pulsante e basta.

Fuori restano anche i **match a set**: il referto Accu-Stats non modella il
confine fra un set e l'altro, e forzarcelo dentro sarebbe stato inventare.

## Conseguenze

- Una route nuova per pagina (`individual_match.tpa_referto`) e cinque per le
  azioni, tutte in `ENDPOINT_ROLES` (ADR-028). `@feature_required` sta **solo**
  su `tpa_open`: le altre controllano che chi guarda sia uno dei due giocatori
  e, per scrivere, che sia il compilatore.
- Le azioni rispondono con **lo stato completo del referto**, tastierino
  compreso: il client non ricalcola niente, e non può andare fuori sincrono.
- La validazione dei comandi è **server-side e contro il motore**: si accetta
  solo ciò che il tastierino stava davvero proponendo. Vale contro un client
  disallineato e contro i doppi tocchi.
- `models/tpa/` è un dominio nuovo, volutamente sottile: motore, due modelli, un
  servizio.
- **Chi guarda vede il referto cambiare, non solo il punteggio.** Ogni tocco
  annuncia `tpa_updated` sul canale del match e la pagina di chi guarda
  ridisegna senza ricaricarsi; il punteggio annuncia `rack_updated` solo quando
  si e' mosso davvero, e li' la pagina del match si ricarica. Due eventi
  distinti perche' servono a due pagine con due esigenze opposte: chi segue un
  referto non puo' perdere il segno ogni tre secondi.
- Il TPA compare nel **profilo** (accanto all'Elo) e nelle **statistiche dei
  match individuali**, sommato su tutti i referti — non mediato fra le partite.
  Lo si vede se si e' sbloccata la funzione **oppure** se qualcuno ha gia'
  tenuto il referto di una propria partita: in quel caso il dato esiste, e
  nasconderlo perche' non si e' ancora sbloccato il pulsante per compilarlo
  sarebbe assurdo.
- Il referto oggi vive solo sui match individuali. Il motore però non sa niente
  di `IndividualMatch`: portarlo sui match di gara è, se servirà, un lavoro di
  servizio, non di regole.

## Alternative scartate

| Alternativa | Perché no |
|---|---|
| Referto come traccia parallela al punteggio | Doppio inserimento e divergenza garantita |
| Righe per turno invece del registro dei comandi | Annulla da inventare, totali da tenere in sincrono |
| Totali (TPA, errori) su colonna | Si disallineano al primo annulla o al primo cambio di regola |
| Riscrivere le regole da zero dal PDF | Due scale di TPA incompatibili con i referti già compilati |
| Aperto a tutti, senza sblocco | Compilarlo mentre si gioca è un mestiere: proposto troppo presto è rumore |
| Terzo utente statistico a bordo tavolo | Inviti e permessi nuovi per un caso che oggi non si verifica |

## Riferimenti

- `models/tpa/engine.py` — le regole, con le divergenze documentate in testa
- `tests/new/unit/test_tpa_engine.py` — la sessione d'esempio Accu-Stats
- `tests/new/unit/test_tpa_engine_corpus.py` — le 600 partite di confronto col JS
- `docs/adr/ADR-028-production-endpoint-allowlist.md` — visibilità degli endpoint
- *Accu-Stats Scoresheet Instructions* (Accu-Stats Video Productions)
