# Roadmap

Questo documento risponde a una domanda che il backlog non sa rispondere:
**perché una cosa viene prima di un'altra.**

Le issue portano una label di *area* (`campionati`, `tabellone`, `segnapunti`,
`allenamento`, `sfide`, `piattaforma`), che dice **di che tipo** è un lavoro.
Non dice a cosa serve. Con quarantacinque issue aperte, guardare l'elenco non
restituisce nessuna visione d'insieme: si vedono quarantacinque cose tutte
ugualmente da fare.

Qui c'è l'ordine, e soprattutto il motivo dell'ordine. Ogni fase esiste perché
**abilita la successiva**: non è una scala di importanza, è una catena.

> Scritto il 2026-08-30. È una **decisione**, non una previsione: invecchia, e
> va corretta quando cambia l'intenzione — non quando slitta una data.

---

## Il traguardo, e perché non è l'ultima fase

L'obiettivo finale è che **l'app vada avanti da sola**: che non serva essere
presenti a spiegare a cosa serve, cosa fare, dove cliccare.

Questo **non è la fase 5.** Se fosse una fase resterebbe in fondo per sempre,
perché in fondo c'è sempre qualcos'altro. È lo **sbarramento** che ogni fase
deve superare per dirsi finita:

> Una funzione che ha bisogno di essere spiegata non è pronta, per quanto
> completa sia il suo codice.

In pratica significa che ogni fase si porta dietro la sua quota di
`/aiuto`, di etichette che si spiegano da sole, di schermate che non
richiedono di sapere già come funziona. La skill `help-docs` esiste per questo.

---

## La regola che scavalca tutto: chi usa l'app adesso

**Una issue aperta da un utente reale ha la precedenza** su qualunque altra
della stessa fase, e in genere anche sulla fase in corso.

Il motivo non è cortesia. Chi apre una issue ha incontrato un attrito **vero**,
mentre usava l'app per giocare, e si è preso la briga di scriverlo: è il
riscontro più costoso da ottenere e il più facile da perdere. Un rilievo
ignorato insegna a non segnalarne altri, e la fonte si spegne — senza che
nessuno se ne accorga, perché il silenzio somiglia al funzionamento.

Sono anche, quasi sempre, correzioni piccole: costano poco e sono esattamente
ciò che fa sembrare l'app finita a chi la sta già usando.

---

## Fase 0 · Chi usa l'app oggi

**Stato: in corso, permanente.** Non finisce: si svuota e si riempie.

Oggi girano in produzione le gare **amalfi** e **casuali** e i **campionati**.
Gli utenti sono un gruppo ristretto che fa da beta tester. Questa fase è
l'attrito che incontrano.

| | |
|---|---|
| #90 | modificare l'esito di un incontro «in attesa» · *utente* |
| #152 | testo troncato nell'intestazione della «Classifica complessiva» · *utente* |
| #153 | colonna laterale collassabile · *utente* |
| #154 | mostrare il tavolo delle partite concluse · *utente* |
| #156 | l'email nell'elenco degli iscritti, per il direttore · *utente* |
| #162 | intestazione della classifica incoerente con le altre tabelle · *utente* |
| #88 | l'utente anonimo accede ai risultati dei campionati in corso · *utente* |
| #260 | il forfait trascina l'uscita dalla gara `bug` |
| #255 | segnalare un problema dall'app |

Sette delle nove vengono da un utente. La #260 no, ma tocca il forfait su
amalfi e casuale, cioè i formati in uso adesso. La #255 chiude il ciclo: oggi
un rilievo arriva se qualcuno ha un account GitHub e voglia di usarlo.

---

## Fase 1 · FISBB per il regionale

**Scadenza vera: fine settembre 2026.** È l'unica data di questo documento, e
c'è perché fuori da qui esiste un campionato regionale a cui proporre l'app.

Formula FISBB = **doppio KO con gironi di eliminazione**: gironi da 8 (un
doppio KO troncato dopo due turni di winners), quattro qualificati per girone —
due diretti, due ripescati — e poi tabellone finale a eliminazione diretta.

**Il motore è finito.** Verificato il 2026-08-30 giocando una gara intera
attraverso le route (16 iscritti → 2 gironi → 6 turni → gara chiusa): i gironi
si formano, si giocano, qualificano, e il tabellone finale li accoglie.
Copertura in `tests/new/e2e/test_gara_e2e_fisbb.py`.

Quello che manca è **ciò che il direttore e il giocatore vedono**:

| | |
|---|---|
| #243 | il wizard del campionato non chiede le opzioni del tabellone — oggi FISBB si configura solo su una gara singola, e un regionale è un campionato |
| #240 | la pagina mostra la classifica invece del tabellone; e i gironi non compaiono mai |
| #272 | orario presunto di inizio: su una competizione di più giornate il giocatore deve sapere quando presentarsi |
| #238 | il massimo iscritti è obbligatorio ma il wizard lascia proseguire `bug` |
| #236 | l'anti-reincontro compare dove non ha senso `bug` |
| #237 | punti per posizione oltre la sedicesima |

Il baricentro è sull'interfaccia, non sull'algoritmo. È una buona notizia per la
scadenza e una cattiva per la stima: la #272 è la più grossa delle sei.

---

## Fase 2 · Sfide e TPA

**Perché qui.** Le sfide individuali e il referto TPA sono ciò che **alimenta i
rating**. Senza partite non c'è Elo; senza Elo l'app non ha una ragione per
tornarci fra un torneo e l'altro. È la fase che trasforma uno strumento da
competizione in qualcosa che si apre anche di mercoledì.

| | |
|---|---|
| #216 | la fascia oraria scritta male viene ingoiata in silenzio `bug` |
| #241 | acchito e runout: due schermate raccontano due storie diverse |
| #207 | formato di acchito ereditabile, e chi ha spaccato ogni triangolo |
| #208 | segnare il break and run dal segnapunti |
| #210 | il trio non ha la vista orizzontale |
| #214 | nascondere una partita dal profilo pubblico |

---

## Fase 3 · Allenamento e istruttori

**Perché qui.** Gli esercizi, le schede e gli esami intercettano gli
**istruttori**, e un istruttore porta i suoi allievi: è il primo moltiplicatore
di utenti che non richiede pubblicità. Ma ha senso solo dopo la fase 2, perché
ciò che si propone a un istruttore è un'app dove i suoi allievi già giocano e
hanno un rating che si muove.

Undici issue: #168, #172, #173, #174, #175, #179, #181, #183, #184, #252, #253.

Oggi sono il gruppo più numeroso del backlog e riempiono la vista. Sono anche
le più lontane: metterle qui è il modo di smettere di guardarle.

---

## Fase 4 · Diffusione

**Perché ultima.** Diffondere prima della fase 3 significa portare persone su
un'app che non ha ancora la ragione per cui dovrebbero restarci. Il momento
giusto è quando c'è qualcosa da mostrare a chi non ti conosce.

| | |
|---|---|
| #235 | pagina-vetrina da condividere sui social |
| #205 | rivedere il design della pagina del profilo |
| #169 | dare un voto alle sale da biliardo |
| #266 | rating dei direttori da parte dei giocatori |

---

## Fuori dalle fasi

Non servono a nessuna fase **oggi**. Non vuol dire che siano sbagliate: vuol
dire che rimandarle non costa niente, ed è la risposta alla domanda «cosa posso
lasciare lì».

#1 (match a squadre) · #7 (CSP nonce) · #192 (formati di handicap) ·
#203 e #204 (voci del profilo) · #215 (decisione sul multi-set) ·
#250 (`garas`/`campionatos`) · #257 (livelli dell'error log) ·
#265 (modificare una regola in corsa)

Due meritano una nota, perché il giorno in cui servono si saprà in anticipo:
**#7** diventa urgente se l'app esce dalla cerchia dei conoscenti, e **#257** se
gli utenti diventano abbastanza da non poter più leggere ogni errore a mano.

---

## Come si tiene vivo

- La fase di ogni issue sta nel campo **`Fase`** del
  [project board](https://github.com/users/coppolapaolo/projects/2), che è
  ordinato come questo documento. La vista **Coda** raggruppata per fase
  risponde a «cosa faccio adesso».
- Una issue nuova nasce **senza fase**. Assegnargliela è una decisione, e va
  presa guardando questo documento — non l'area.
- Quando una fase si svuota, la successiva diventa quella corrente. La fase 0
  non si svuota mai, e va bene così.
- Se una issue non entra in nessuna fase e non se ne vuole fare a meno, allora è
  il documento a essere incompleto: manca una fase, o una fase ha un confine
  sbagliato.
