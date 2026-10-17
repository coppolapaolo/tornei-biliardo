Le sfide individuali si chiudono con la firma di **entrambi** i giocatori
(ADR-051): è la difesa contro chi bara. Con chi non usa l'app, però, la seconda
firma può non arrivare mai. Questi casi d'uso descrivono come si gioca lo
stesso, e come i numeri di un giocatore dicono **quanto sono certificati**.

I livelli di certificazione di una partita sono tre:

| Partita | Livello |
|---|---|
| Partita di torneo conclusa | **Torneo** |
| Sfida confermata da entrambi, o chiusa con un forfait | **Confermata** |
| Sfida firmata da uno solo, in attesa dell'altro | **In attesa** |

Il profilo li mostra in tre viste cumulative: *Tornei*, *Confermate* (tornei
più sfide confermate) e *Tutte* (anche le sfide in attesa).

Personaggi:

- **Paolo**, che usa l'app;
- **Pietro**, che non la apre quasi mai;
- **Gianni**, che la usa;
- **Luca**, che guarda i profili da ospite.

Stato: UC1 è realizzato (PR #696), UC2 e UC3 con l'emendamento all'ADR-051.
UC4, UC5, UC7, UC8 e UC9 sono realizzati lato dominio con l'ADR-083
(PR #698). UC6, il selettore nel profilo, è realizzato con la PR del
selettore di certificazione (`test_profilo_selettore_certificazione.py` e
`tests/frontend/test_vista_certificazione.cjs`).
UC10, il ritiro di una sfida rimasta senza seconda firma, è realizzato con la
PR del ritiro (`test_ritiro_sfida_senza_seconda_firma.py`, unitario e di
integrazione).

## Use case 1 — Avvio rapido dal telefono

- Paolo è al circolo con Pietro e apre l'app sul telefono. Dalla dashboard
  tocca «Giochi adesso?».
- Sceglie Pietro, la distanza e la disciplina.
- In fondo allo schermo il pulsante «Inizia a segnare» è **a tutta larghezza e
  alto quanto gli altri pulsanti dell'app**, e si preme col pollice senza
  mirare.
- Lo preme e arriva al segnapunti.
- _(variante: entra da «Rigioca adesso» nel dettaglio di una sfida finita)_
- _(variante: la stessa barra in fondo nella proposta di sfida, nella modifica
  di una sfida, nel modulo di un esercizio e nel dettaglio di un esercizio di
  gara)_
- _(variante: su desktop il pulsante resta largo quanto il suo testo)_

## Use case 2 — Due sfide di fila con chi non usa l'app

- Paolo e Pietro giocano «al 5». Paolo segna tutti i triangoli. Al quinto vinto
  da Paolo la partita arriva alla distanza, e Paolo firma d'ufficio.
- Pietro non apre l'app: la sfida resta **in attesa della sua firma**. Paolo la
  vede fra le sue sfide con lo stato «In attesa di conferma».
- Rigiocano subito. Dal dettaglio della sfida Paolo tocca «Rigioca adesso»:
  **si apre una partita nuova**, non quella vecchia.
- Paolo segna anche la seconda e la firma. Ora ci sono due sfide in attesa
  della firma di Pietro.
- _(variante: formato «libero» — Paolo firma premendo «Termina»)_
- _(variante: Paolo entra dall'avvio rapido della dashboard invece che da
  «Rigioca adesso»)_
- _(variante: prima che qualcuno firmi, Paolo preme due volte l'avvio rapido
  → resta una sola partita: il doppio tocco è ancora protetto)_
- _(variante: dal dettaglio della sfida in attesa Paolo sceglie «Proponi
  un'altra data» → parte una proposta per un'altra sera)_

## Use case 3 — Chi deve firmare viene riportato alla firma

- Il giorno dopo Pietro apre l'app e tocca l'avvio rapido contro Paolo.
- Non nasce una partita nuova: viene **riportato alla sfida che deve
  firmare**, e nel dettaglio non vede «Rigioca adesso».
- La firma, e da quel momento può avviarne di nuove.
- _(variante: Pietro ha due sfide da firmare e prova a giocare contro Gianni →
  arriva alla pagina «Da confermare», le firma entrambe e torna all'avvio
  rapido con Gianni già scelto)_
- _(variante: Pietro prova ad accettare una proposta di Gianni → stesso blocco,
  stesso ritorno)_

## Use case 4 — La firma che arriva tardi certifica la sfida

- Pietro firma la prima sfida di UC2.
- Nel profilo di Paolo la sfida passa da «in attesa» a «confermata». Nella
  vista *Confermate* le vittorie crescono di uno, nella vista *Tutte* non
  cambia niente: c'era già.
- Si muove l'ELO di *Confermate*. L'ELO di *Tutte* resta dov'era, perché la
  partita era già contata.
- Nello storico la sfida perde il segno «in attesa».
- _(variante: la sfida finisce in pareggio, «esattamente 4» chiusa 2-2 → si
  conta un pareggio e nessun ELO si muove)_

## Use case 5 — Il risultato contestato esce dalle statistiche

- Pietro apre la seconda sfida e **rifiuta** il risultato: l'ultimo triangolo
  viene tolto, le firme si azzerano e la partita torna in corso.
- Paolo riceve la notifica.
- Nella vista *Tutte* del profilo di Paolo quella sfida sparisce, e l'ELO di
  *Tutte* è **identico a quello che avrebbe avuto se la sfida non fosse mai
  entrata**.
- Paolo corregge e firma di nuovo: la sfida torna «in attesa».
- _(variante: invece di correggere, Paolo dichiara forfait → vedi UC7)_
- _(variante: Paolo toglie tutti i triangoli e annulla la sfida → sparisce del
  tutto)_

## Use case 6 — Il profilo con il selettore di certificazione

- Paolo apre il proprio profilo. In testa c'è il selettore **Tornei ·
  Confermate · Tutte**, già sulla vista che aveva scelto l'ultima volta. La
  prima volta è su *Confermate*.
- Tocca *Tutte*. Cambiano **insieme** ELO, vittorie, sconfitte, pareggi, TPA e
  runout. Fra le partite recenti compaiono quelle in attesa, con il loro
  segno.
- Tocca *Tornei*: ELO competitivo e statistiche delle sole gare. Il TPA mostra
  «—» e spiega che esiste solo nelle sfide.
- Ricarica la pagina: la vista resta *Tornei*.
- Apre il profilo di Gianni: è anche lui in vista *Tornei*.
  _(nota del 2026-10-17: la prima stesura chiudeva con «apre la classifica
  ELO, ordinata sulla stessa vista». È stata tolta perché quella pagina non
  esiste: le classifiche globali, ELO compresa, sono uscite dall'interfaccia
  con l'ADR-037, che le ha sostituite con «La tua zona» e «Contributo». Il
  selettore non è un motivo per riportarle, e l'utente ha deciso di lasciare
  l'ADR-037 com'è. Il selettore vale per il profilo.)_
- _(variante: il profilo di un giocatore che ha solo sfide, in vista *Tornei* →
  la frase «Nessuna partita di torneo», non una fila di zeri)_
- _(variante: Luca, da ospite, o un browser che non conserva le preferenze →
  vista *Confermate*; il selettore funziona ma non ricorda)_
- _(variante: telefono a 500px → il selettore sta su una riga sola, senza
  scorrimento orizzontale)_

## Use case 7 — Il forfait

- Paolo sta perdendo contro Gianni e dichiara forfait. Gianni vince.
- Nel profilo di entrambi la sfida conta fra vittorie e sconfitte già nella
  vista *Confermate*: chi abbandona ammette la sconfitta.
- **Nessun ELO si muove**, in nessuna vista, come per i forfait di torneo.

## Use case 8 — TPA e runout seguono la certificazione

- Paolo apre una sfida con il referto TPA e segna qualche colpo. Poi la sfida
  viene annullata, oppure resta in corso senza firme: il suo TPA e i suoi
  runout **non la contano in nessuna vista**.
- Firmata solo da Paolo → conta nella vista *Tutte*.
- Firmata da entrambi → conta anche in *Confermate*.
- I runout dei triangoli di torneo contano già in *Tornei*.

## Use case 9 — Primo calcolo dell'ELO di *Tutte* in produzione

- Dopo il rilascio, l'admin mette la web app su **Disabled**.
- Lancia lo script di ricalcolo dell'ELO, che di default è una prova a vuoto e
  dice quanti giocatori ricevono il nuovo ELO.
- Lo rilancia con `--commit` e rimette la web app su **Enabled**.
- Nel profilo di Paolo la vista *Tutte* mostra un ELO. Senza sfide in attesa
  coincide con quello di *Confermate*.

## Use case 10 — Paolo ritira una sfida che Pietro non firmerà mai

_Regola del 2026-10-17, decisa dall'utente (`SPECIFICHE.md`, nota datata)._

- Delle due sfide di UC2 Pietro non ne ha firmata nessuna, e non lo farà. Paolo
  ne vuole togliere una e tenere l'altra così, *in attesa*.
- Alla prima firma di Paolo, Pietro aveva ricevuto una **notifica**: «Una
  sfida aspetta la tua firma», con il pulsante «Apri la sfida». Prima arrivava
  solo l'aggiornamento in tempo reale, che vede solo chi ha la pagina aperta.
- Nella pagina delle sfide Paolo le trova nella sezione **«In attesa di
  conferma»**, ciascuna con il punteggio, «Manca la firma dell'avversario» e il
  pulsante «Apri la sfida». Non ci sono più fra quelle «Da giocare» con
  «Continua», che lo riportava al segnapunti di una partita già finita.
- Apre la prima e tocca **«Ritira la sfida»**. Un foglio gli chiede conferma
  con il pulsante «Ritira»: tocca Pietro e non si disfa.
- La sfida è annullata. Esce dalla vista *Tutte* del profilo di Paolo e di
  Pietro, e l'ELO di *Tutte* torna quello che sarebbe stato senza di lei.
- Pietro riceve la notifica «Sfida ritirata».
- La seconda sfida resta *in attesa*, e conta nella vista *Tutte* come prima.
- _(variante: Pietro apre la sfida che aspetta la sua firma → non vede «Ritira
  la sfida»: per lui ci sono conferma e rifiuto)_
- _(variante: Pietro firma prima che Paolo la ritiri → la sfida è
  confermata da entrambi e non si ritira più)_
- _(variante: una sfida senza firme, con dei triangoli segnati → non si
  ritira: i due la stanno ancora giocando)_

