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

Nella partita tenuta da un terzo (UC12) il livello è **per giocatore**: chi
l'ha confermata la vede *Confermata*, chi non ha ancora deciso *In attesa*,
chi l'ha rifiutata non la vede.

Il profilo li mostra in tre viste cumulative: *Tornei*, *Confermate* (tornei
più sfide confermate) e *Tutte* (anche le sfide in attesa).

Personaggi:

- **Paolo**, che usa l'app;
- **Pietro**, che non la apre quasi mai;
- **Gianni**, che la usa;
- **Luca**, che guarda i profili da ospite;
- **Marco**, istruttore, che segna le partite degli altri;
- **Gino**, che non ha un account (ADR-085).

Stato: UC1 è realizzato (PR #696), UC2 e UC3 con l'emendamento all'ADR-051.
UC4, UC5, UC7, UC8 e UC9 sono realizzati lato dominio con l'ADR-083
(PR #698). UC6, il selettore nel profilo, è realizzato con la PR del
selettore di certificazione (`test_profilo_selettore_certificazione.py` e
`tests/frontend/test_vista_certificazione.cjs`).
UC10, il ritiro di una sfida rimasta senza seconda firma, è realizzato con la
PR del ritiro (`test_ritiro_sfida_senza_seconda_firma.py`, unitario e di
integrazione).
UC12, la partita di altri due tenuta da un istruttore o da un direttore, è
realizzato con l'ADR-084 (`test_partita_di_altri_due.py`, unitario e di
integrazione); le varianti del rifiuto, della correzione e dell'admin con il
suo emendamento del 2026-10-18 (anche `test_partita_di_altri_due_e2e.py`).
UC13, la sfida contro un giocatore non registrato, è realizzato con
l'emendamento del 2026-10-18 all'ADR-085
(`test_avversario_non_registrato.py` di integrazione,
`test_sfida_avversario_non_registrato_e2e.py`), e riscritto col secondo
emendamento dello stesso giorno: la sfida si chiude da sola, registrata da
uno. UC14, la revisione dopo il riscatto, è realizzato con l'emendamento del
2026-10-18 all'ADR-086 (`test_revisione_dopo_il_riscatto.py` di
integrazione, lo stesso e2e).

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
- _(variante: a sfida confermata da entrambi Paolo cerca di togliere
  l'ultimo triangolo, dal segnapunti o dal referto TPA → il pulsante non c'è,
  e il server rifiuta: la sfida è conclusa, 2026-10-18)_
- _(variante: Paolo tiene il referto, l'ultimo tocco porta alla distanza per
  sbaglio e Pietro riceve «Una sfida aspetta la tua firma»; Paolo annulla e
  il referto si riapre → la notifica di Pietro scade, e alla nuova chiusura
  ne riceve una col punteggio giusto)_
- _(variante: una sfida senza firme, con dei triangoli segnati → non si
  ritira: i due la stanno ancora giocando)_


## Use case 11 — La finale di giornata ha un nome e un video

Paolo e Pietro giocano la finale della prima giornata del campionato
regionale. Lo dice la sfida stessa, e il video arriva due giorni dopo.

- Paolo apre l'**avvio rapido**, sceglie Pietro, tocca «Aggiungi una
  descrizione» e scrive «Finale della prima giornata, serie C FVG».
- La descrizione compare sotto i nomi nella pagina della sfida, nel referto
  TPA, in `/match/`, in «Le mie sfide» e nello storico del profilo.
- Due giorni dopo, a sfida confermata da entrambi, Pietro apre la sfida e in
  «Video e descrizione» incolla `youtu.be/…?t=95`. Il link si salva nella
  forma `https://www.youtube.com/watch?v=…&t=95s`, e chi apre la pagina tocca
  «Guarda il video»: YouTube si apre in una scheda nuova.
- Video e descrizione non toccano il risultato, né il livello di
  certificazione, né l'ELO.
- _(variante: la sfida nasce da una **proposta** → la descrizione si scrive
  nel campo «Descrizione della partita» e passa alla sfida quando Pietro
  accetta; il «Messaggio» resta sulla proposta)_
- _(variante: Pietro incolla un link di Vimeo → «Il link al video deve essere
  un video di YouTube», e il link che c'era resta)_
- _(variante: un terzo giocatore prova a scrivere il video → rifiutato: lo
  scrivono solo i due giocatori della sfida)_
- _(variante: partita di **gara** → il riquadro «Video della partita» c'è
  anche lì, senza descrizione; lo scrivono i giocatori e i direttori della
  gara)_


## Use case 12 — Marco, istruttore, tiene il referto della finale di Paolo e Pietro

Marco è istruttore (ADR-069). Paolo e Pietro giocano la finale, e Marco la
segna dal bordo del tavolo (ADR-084).

- In `/match/` Marco tocca «Segna la partita di altri due»: la voce la vede
  solo chi è istruttore o direttore, mai l'admin.
- Sceglie Paolo come giocatore A e Pietro come giocatore B, scrive «Finale
  1ª giornata, serie C FVG», palla 9 al 7. Tocca «Inizia il referto».
- La partita nasce in corso, col referto aperto e Marco compilatore. Paolo e
  Pietro ricevono un avviso con la descrizione: la partita compare nelle loro
  sfide, segnata da Marco, **senza «Continua»**.
- Marco annota la partita. Al settimo triangolo di Paolo nessuno firma
  d'ufficio. Marco chiude il referto: la partita è **dichiarata**, e Paolo e
  Pietro ricevono la notifica «Una sfida aspetta la tua firma».
- Paolo conferma: per lui la partita è *Confermata*. Per Pietro, che non ha
  ancora deciso, è *In attesa*. L'ELO di *Tutte* si muove per entrambi.
- Pietro conferma anche lui: la sfida è confermata da entrambi, e si muove
  l'ELO di *Confermate*.
- _(variante: Pietro **rifiuta**, dopo la conferma di Paolo → vale il
  rifiuto: la partita è **rifiutata** per tutti e due, esce da ogni vista e
  dall'ELO di entrambi, e non compare più né a Paolo né a Pietro. Nessun
  triangolo viene tolto. Paolo e Marco ricevono un avviso con la
  descrizione)_
- _(variante: Pietro rifiuta **prima** che Paolo decida → stessa cosa: Paolo
  non ha più niente da confermare)_
- _(variante: Marco apre la partita rifiutata, che lui vede marcata
  «Rifiutata», e tocca **«Correggi la partita»** → il referto si riapre e le
  decisioni dei due si azzerano. Marco corregge l'ultimo triangolo e richiude
  il referto: Paolo e Pietro ricevono di nuovo la richiesta di conferma)_
- _(variante: Marco tocca invece **«Cancella la partita»** e conferma nel
  foglio → la partita è annullata, anche se Paolo l'aveva confermata)_
- _(variante: l'admin prova ad aprire il modulo → rifiutato: l'admin non
  segna partite)_
- _(variante: Pietro non apre mai l'app → non è bloccato su nuove sfide: la
  partita non l'ha chiesta lui)_
- _(variante: a metà partita Paolo si ritira e Marco **annulla** la partita →
  sparisce per tutti; dopo la prima conferma Marco non la può più annullare,
  a meno che l'altro l'abbia rifiutata)_
- _(variante: Gianni, giocatore senza ruolo, non vede la voce, e un modulo
  mandato a mano viene rifiutato)_
- _(variante: Marco prova a mettersi come giocatore A → rifiutato: chi segna
  non gioca)_
- _(variante: Marco prova a chiudere il referto a 3-2 in una partita al 7 →
  rifiutato; la partita a metà si annulla)_
- _(variante: Lucia è l'istruttrice a cui Paolo ha aperto una scheda → può
  guardare il referto in sola lettura)_

## Use case 13 — Marco tiene il referto della sua partita contro Gino, che non ha un account

Marco, istruttore, gioca contro Gino la finale del giovedì, che viene
ripresa su YouTube. Gino non si è mai registrato. La partita è di Marco:
quella di altri due non va, perché chi segna non gioca (UC12).

- Dall'avvio rapido Marco cerca Gino e non lo trova. Sotto la ricerca tocca
  **«Non ha un account? Aggiungilo»**, scrive nome e cognome, sceglie palla 9
  al 3, spunta «Tengo il referto TPA» e scrive «Finale del giovedì». Tocca
  «Inizia a segnare»: Gino nasce **non registrato**, creato da Marco, e Marco
  arriva al referto.
- Gino non riceve niente: non ha un account.
- Marco annota la partita. Al terzo triangolo vince Gino: **firma Marco**,
  perché Gino non firma, e la sfida **si chiude**: è *registrata da un solo
  giocatore*, livello *In attesa*, e conta per l'ELO di *Tutte*. Marco
  chiude il referto.
- Nella pagina della sfida Marco legge **«Registrata da te»**: niente
  «manca la conferma», nessun promemoria. In `/match/` la sfida sta fra le
  giocate, con lo stato «Registrata da te»; in dashboard non è fra le sfide
  in corso.
- Marco **non è bloccato**: apre subito un'altra sfida, anche contro Gino.
- Il giorno dopo Gino si registra e tocca «Sei tu? Riscatta»; Marco, che l'ha
  creato, conferma. La sfida passa all'account di Gino, che la rivede (UC14).
- _(variante: la sfida è a distanza libera → la chiude Marco con «Termina la
  sfida», e la sua firma basta)_
- _(variante: Marco toglie un triangolo dal referto ancora aperto → la sfida
  torna in corso, e si richiude alla firma successiva)_
- _(variante: Paolo, giocatore senza ruolo, non vede «Non ha un account?»: un
  modulo mandato a mano viene rifiutato. Può però cercare e scegliere un
  giocatore non registrato che esiste già, col segno «non registrato»)_
- _(variante: l'admin non apre l'avvio rapido, e non crea giocatori da qui)_
- _(variante: Marco **ritira** la sfida → annullata; prima del riscatto
  nessuno riceve avvisi, durante la revisione Gino sì)_
- _(variante: dalla pagina della sfida Marco cerca «Proponi un'altra data» →
  non c'è: a Gino una proposta non arriverebbe. «Rigioca adesso» apre
  l'avvio rapido con Gino già scelto)_
- _(variante: Marco prova a mandare a Gino una proposta di sfida → rifiutata,
  con l'indicazione di usare l'avvio rapido)_

## Use case 14 — Gino, appena registrato, rivede le partite che Marco aveva segnato contro di lui

Regola del 2026-10-18 (ADR-086, emendamento): «se qualcuno riscatta l'utente,
allora gli si può chiedere se vuole rivedere tutti i match passati ed
eventualmente contestarne alcuni oppure riconoscerli tutti oppure contestarli
tutti».

- Marco ha registrato tre sfide contro Gino quando Gino non aveva un account.
  Gino si registra e riscatta il suo giocatore; Marco conferma.
- A Gino arriva **un** avviso: «Rivedi le partite di Gino». In «Le mie sfide»
  un riquadro in cima gli ricorda quante ne restano.
- La pagina «Partite da rivedere» elenca le tre sfide, ciascuna con chi l'ha
  registrata, il punteggio e la casella «La contesto». Sotto, tre comandi.
- Gino spunta la seconda — quella sera non c'era — e tocca **«Contesto solo
  quelle spuntate»**. Le altre due sono riconosciute: diventano *Confermate*
  e muovono l'ELO globale.
- La seconda resta a Marco, **contestata**: nella sua pagina il riquadro
  «Contestata», nell'elenco lo stato «Contestata», nel profilo la riga
  segnata così. Conta solo fra *Tutte* e nell'ELO di *Tutte*. Marco riceve
  l'avviso «Sfida contestata».
- Per Gino la seconda sparisce: non è in «Le mie sfide», non nel profilo,
  non nelle statistiche; aprendone l'indirizzo torna alla dashboard con un
  avviso.
- _(variante: «Le riconosco tutte» → tutte *Confermate*)_
- _(variante: «Le contesto tutte» → tutte a Marco, contestate)_
- _(variante: Gino riconosce o contesta dalla pagina della singola sfida,
  con «La riconosco» o «La contesto»)_
- _(variante: Gino non rivede niente → le sfide restano registrate da
  Marco, *In attesa*, senza scadenza; Gino gioca e propone sfide lo stesso)_
- _(variante: Gino era uno dei due giocatori di una partita che Lucia,
  istruttrice, aveva segnato per lui e Paolo → compare fra quelle da
  rivedere; riconoscerla è confermarla per sé, contestarla è rifiutarla, e il
  rifiuto la toglie a tutti e due, come in UC12)_
- _(variante: a riscattare Gino è Luca, registrato da tempo, che ha una
  partita sua con Anna segnata da Lucia e ancora da confermare → non compare
  fra quelle da rivedere: non era del giocatore riscattato, e Luca la decide
  dalla sua pagina, 2026-10-18)_
- _(variante: una partita di gara contro Gino → non si rivede: la certifica
  il torneo)_
