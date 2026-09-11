# Redesign delle dashboard — stato al 2026-09-10

Lavoro di design sulle tre dashboard (ospite, giocatore, direttore).

Questa cartella contiene **solo** i disegni e le decisioni prese guardandoli:
niente codice dell'app. Il codice è arrivato dopo, in due PR separate — vedi
«La forma nei template» più giù, che dice anche dove è finita ciascuna
decisione.

## Dove sono le cose

| Cosa | Dove |
|---|---|
| Canvas dei disegni (4 pagine) | <https://claude.ai/code/artifact/5e952194-c219-4d38-b95e-7174c1cf3d2b> |
| Inventario dei casi | <https://claude.ai/code/artifact/c1527bf6-4a71-4c5f-9ad1-d84eff348d79> |
| Sorgenti degli artboard | `docs/redesign-7c/canvas-dashboard/sorgenti/` — **non `parts/`**: il `.gitignore` del repo esclude quel nome per buildout |

Le cinque pagine del canvas: **Mobile** e **Desktop** ritraggono l'app com'è
oggi; **Confronto** mette a fianco le alternative fra cui si è scelto; **Casi**
contiene dieci stati disegnati nella forma scelta; **Tessera** (10/09) mostra
la stessa gara vista da chi ha fatti diversi — la regola 1 resa visibile — e
le due schermate della regola 2, «Concluse» e «Storico».

La cartella è versionata (PR `docs:` del 30/08); il canvas seminato no, vedi
«Nota sui file» in fondo.

## Le decisioni prese

**Giocatore — forma C: ogni cosa dentro ciò a cui appartiene.**
La partita vive dentro la card della sua gara (non in una sezione «I tuoi
match» gemella). ~~L'invito ai playoff dentro la card del suo campionato~~ —
**emendato il 10/09**: l'invito sta **in cima**, come sezione a sé, perché è
una cosa da fare con scadenza e dentro la card si scorre. La
sfida a due resta una sezione a sé, perché non ha una gara dove stare: è il
limite dichiarato di questa forma.

**Direttore — forma B: i comandi di direzione sulla card.**
`Avvia Turno N`, `Avvia Spareggio`, `Apri Iscrizioni` — gli stessi pulsanti
della pagina della gara, non funzioni nuove. Sono i comandi **veri**: non
esistono «chiudi il turno» né «assegna i tavoli» (i tavoli li assegna la gara
da sé, secondo `available_tables`).

**Direttore — un elenco solo di gare, non due.**
Una gara può essere insieme «che dirigo» e «in cui gioco» (`can_inscribe()` non
vieta al direttore di iscriversi alla propria gara), quindi la card è una e
porta entrambe le nature: pastiglie `Dirigi` + `Iscritto`, la tua partita
dentro, e il comando di direzione disponibile in quel momento.

**Ospite — forma C: l'account chiesto dove serve.**
Nessun blocco «come si partecipa» in cima: si parte dalla diretta, il comando
resta `Iscriviti` e una riga sotto dice che serve un account gratuito.

**Quattro cose fuori discussione**, applicate ovunque:

1. la testata porta il saluto (`Ciao marco` + ruolo come sottotitolo) invece di
   ripetere «Dashboard Giocatore», e il blocco del saluto sparisce dal
   contenuto: era la stessa cosa due volte;
2. le gare sono divise fra **«Le tue gare»** e **«Aperte, puoi iscriverti»**;
3. la gara in corso porta la **posizione in classifica provvisoria** e le
   **altre partite del turno**;
4. la **sfida a due in corso** compare.

**Il blocco «Come stai andando» resta com'è.** Compare una volta per sessione,
al primo ingresso dopo il login (`claim_activity_feedback_view`), e i suoi nove
casi — otto profili più la card dei tre passi — non sono in discussione. Una
proposta che lo riduceva è stata bocciata il 30/08.

## Rilievi sul codice emersi disegnando — e come sono finiti

Indipendenti dal redesign: valgono come correzioni anche da soli. **Tutti
chiusi** nelle PR #295 (dashboard) e #296 (home dell'ospite), tranne dove
indicato.

1. ~~**La sfida a due in corso non compare in nessuna dashboard.**~~ Corretto
   (#295). `vm.individual_matches` era calcolato e nessun template lo usava:
   si vedevano solo le proposte aperte altrui, cioè gli inviti, e non le sfide
   già accettate. Il campo si chiama ora `sfide_in_corso` e porta solo quelle
   da giocare.
2. ~~**«Le gare» non sono le tue.**~~ Corretto (#295): due elenchi, «Le tue
   gare» e «Aperte, puoi iscriverti», decisi in
   `models/dashboard/gara_cards.py`.
3. ~~**`WaitlistReason` ha due valori e l'interfaccia non li distingue.**~~
   Corretto (#295): la card dice se la gara è piena o se serve un numero pari.
4. ~~**Il badge «N da chiudere» del direttore non porta da nessuna parte.**~~
   Superato (#295): ogni gara diretta porta ora sulla card il comando che
   aspetta, quindi il conteggio aggregato non serve più.
5. ~~**`_index_campionato_cards.html` è l'unico pezzo della home ancora
   Bootstrap legacy.**~~ Corretto (#296): riscritto in 7c, 219 righe → 138.
6. ~~**`no_campionato.html` non è 7c.**~~ Corretto (#296): usa `.c7-empty`.
7. ~~**Per il visitatore anonimo la barra laterale si presenta come
   «giocatore».**~~ Corretto (#296): dice «vista pubblica».

Tre ne sono emersi **scrivendo il codice**, non disegnando:

8. **Una gara con le iscrizioni programmate nel futuro spariva da ogni
   dashboard.** `get_real_status()` risponde `inscription_not_yet_open` e
   quello stato non era fra quelli «vivi»: il direttore che l'aveva appena
   creata non aveva più da nessuna parte il pulsante per gestirla. Corretto
   in #295.
9. **Quattordici fixture creavano gare con `discipline="nine_ball"`**, una
   terza forma che non era né il vocabolario canonico (`9_ball`) né quello
   italiano storico già vietato — quindi non la vedeva nessuno dei due
   controlli. Trovata **guardando la dashboard nel browser**, non leggendo il
   codice: a schermo compariva «Nine Ball» in mezzo a «Palla 8» e «Palla 9».
   Corretta in #295, e il presidio ora copre anche `tests/`.
10. **I rami `is_authenticated` della home erano tutti morti.** `main.index`
    rimanda alla dashboard chiunque sia autenticato, quindi `index.html` e i
    suoi sei componenti li vede solo un ospite: c'era perfino un form di
    iscrizione che nessun iscritto poteva vedere. Tolti in #296.

## Come si ricostruisce il canvas

```bash
cd docs/redesign-7c/canvas-dashboard
python3 sorgenti/gen_confronto.py      # varianti A/B/C giocatore e direttore
python3 sorgenti/gen_ospite.py         # varianti A/B/C ospite
python3 sorgenti/gen_casi.py           # i dieci casi
python3 sorgenti/gen_tessera.py        # pagina Tessera: la tessera decisa, campionato, Concluse, Storico
./build.sh <NomeArtboard> ...       # cuce sorgenti/base.css + corpo -> .dc.html
```

Gli artboard «com'è oggi» (`Main`, `Ospite`, `Direttore`, `*Desktop`) sono
scritti a mano in `sorgenti/*.body`, senza generatore.

`build.sh` decide quali fogli aggiungere in base al **nome** dell'artboard
(`*Desktop` → `desktop.css`; `Giocatore[ABC]`, `Direttore[ABC]`,
`Ospite[ABC]`, `Caso*`, `Tessera*`, `Concluse`, `Storico` → `extra.css`;
gli ultimi tre anche `tessera.css`). Da zsh il ciclo su tutti i nomi vuole
`for f in *.dc.html; do ./build.sh "${f%.dc.html}"; done`: una variabile con
gli spazi non si spezza e arriva come un nome solo. Chi aggiunge un foglio deve
aggiornare **anche** il banco di prova, che ha la stessa regola scritta a parte:
disallineate, le misure sono sbagliate senza dare errore (successo due volte).

Il banco di prova misura con Playwright l'altezza reale del contenuto a 390px
e la confronta con la cornice dichiarata in `canvas.json` — serve perché la
cornice non ridimensiona: se il contenuto è più alto, taglia.

Per ripubblicare: si riseminano tutti gli artboard con `seed-canvas.mjs` della
skill `design` e si ripubblica lo stesso file (`dashboard-tre-ruoli.html`), che
mantiene l'indirizzo.

## La forma nei template: fatto

Il passo successivo al disegno è stato fatto il **2026-08-30**, in due PR che
toccano file disgiunti:

| PR | Cosa |
|---|---|
| [#295](https://github.com/coppolapaolo/tornei-biliardo/pull/295) | Le dashboard di giocatore e direttore |
| [#296](https://github.com/coppolapaolo/tornei-biliardo/pull/296) | La home dell'ospite |

Dove sta ora la logica che prima stava in Jinja:

* `models/dashboard/gara_cards.py` — chi vede quali gare, e in quale dei due
  elenchi. Prima l'appartenenza si ricostruiva iterando `gara.inscriptions`
  card per card: una query a gara per una riga già in memoria in
  `vm.my_inscriptions`. `enrich_with_progress` aggiunge posizione in classifica
  e partite del turno, con tre query in tutto e non tre per gara;
* `models/dashboard/comandi.py` — quale comando una gara aspetta dal suo
  direttore. Rispecchia i rami di `_gara_management.html`, che resta l'unico
  posto in cui i comandi si **eseguono**: quel file dipende da variabili
  calcolate dalla route della gara e da funzioni JS che vivono lì, quindi in
  dashboard il comando si **annuncia** e basta. La scelta è isolata in quel
  modulo: il giorno che si volesse agire sul posto, cambia il template e non il
  ragionamento.

Una cosa che il disegno non poteva prevedere e che è emersa scrivendo: il testo
nato spezzato in frammenti (`Sei` + `su`) non si può tradurre, e in catalogo i
frammenti di due lettere si agganciano a qualunque cosa gli somigli — `pybabel`
aveva proposto *Yes* per «Sei» e *Slug* per «su». I messaggi ora sono interi,
coi placeholder dentro.

## Due regole decise il 2026-09-10, guardando il codice

Non sono emerse disegnando: sono emerse **rileggendo la #295 e la #296** dieci
giorni dopo, con una domanda precisa in mano. Valgono per tutto ciò che
segue, e le PR aperte vanno riallineate a loro prima di unirle.

### 1. Il ruolo è per elemento, non per pagina

Un utente non *è* giocatore o direttore: **lo è rispetto a una gara**. Per
ogni gara (e per ogni campionato) contano tre fatti — sono iscritto, la
dirigo, ho una partita aperta — e la tessera si disegna da quelli:

* senza nessun fatto mio, la tessera è **quella dell'ospite**, qualunque ruolo
  abbia il mio account;
* con un fatto solo, è quella di quel fatto;
* con due, gli elementi che non confliggono **si sommano** (pastiglie
  `Iscritto` + `Dirigi`, «Gioca la tua partita» + il comando di direzione) e
  su quelli che confliggono **vince il direttore** (il comando al posto di
  «Dettagli»).

La *selezione* di cosa entra in pagina è un'altra cosa e resta per ruolo:
«Gare vicine a te» esiste per giocatore e direttore e non per l'ospite,
perché dell'ospite non si sa dove sta. Ma una volta in pagina, la gara si
mostra secondo i fatti, non secondo chi la guarda.

Conseguenza pratica: **una tessera sola per gara e una per campionato**,
condivise fra home dell'ospite e dashboard, che prendono i fatti del lettore
in ingresso e degradano alla vista pubblica quando non ce ne sono. Oggi sono
due componenti per la stessa cosa (`_index_*.html` da una parte,
`_separated_dashboard_content.html` dall'altra), coerenti per intenzione e
non per costruzione.

### 2. Il passato: l'ultima più un mese, il resto nello storico

Vale per le gare e per i campionati, e vale uguale per ospite e loggati:

* in dashboard e in home compaiono **l'ultima conclusa** — sempre, anche se
  vecchia, così dopo l'estate c'è comunque un aggancio — più tutte quelle
  concluse **negli ultimi trenta giorni**;
* sono **di tutti**, non solo mie: quelle che ho giocato o diretto si
  **riconoscono** dalla pastiglia, in dashboard come nello storico;
* la finestra si ancora a `Gara.date`, perché una data di chiusura non esiste
  (lo stato «conclusa» è derivato); per il campionato, alla data della sua
  ultima gara. Una gara chiusa dal direttore due mesi dopo averla giocata
  esce dalla dashboard nel momento in cui viene chiusa: accettato;
* il resto sta nello **storico**: un archivio ricercabile e filtrabile. Per i
  campionati `/campionatos` c'è già, con ricerca per nome e filtro di stato,
  e va esteso con la spia della partecipazione. Per le gare va **fatto**:
  `/garas` copre solo le standalone e non ha né ricerca né filtri, ed è il
  motivo per cui l'archivio dell'ospite non ha un «vedi tutte».

Sostituisce i tagli fissi di oggi: tre gare e due campionati in coda nella
#295, quattro e quattro nell'archivio della #296.

## Verifica del 2026-09-10: dove le PR rispettano le regole e dove no

Fra giocatore e direttore la regola 1 **vale per costruzione**: la tessera è
una (`_separated_dashboard_content.html`, inclusa da entrambi) e non guarda
mai `current_user.is_director`, solo `is_inscribed`, `can_manage` e la
partita. Il direttore iscritto a una gara che non dirige vede byte per byte
la tessera del giocatore; su quella che dirige e gioca le pastiglie si
sommano e il comando vince su «Dettagli».

Dove si rompe, in ordine di costo:

1. **Il direttore non iscritto alla propria gara, con le iscrizioni aperte,
   non ha «Iscriviti»** né la riga «Chiudono il»: la tessera sta in «Le tue
   gare» e lì il pulsante non esiste. Il suo elemento da giocatore è perso
   invece di sommarsi. Correzione piccola, nella #295.
2. ~~**Lo STATO prometteva «l'invito ai playoff dentro la card del suo
   campionato»** e la #295 lo tiene invece in una sezione a sé, in cima
   (`_playoff_invitations.html`).~~ **Deciso il 10/09: resta in cima**, la
   #295 è già giusta; la decisione del 30/08 è emendata (vedi sotto).
3. **«Crea Match» in testata compare solo al giocatore puro**, non al
   direttore che gioca; e le proposte di sfida aperte sono due componenti con
   testi diversi nei due contenuti («Accetta il match» / «Partecipa»).
   Si risolve unificando `_director_dashboard_content.html` con quello del
   giocatore, «Gare vicine a te» compreso.
4. **Chi è loggato vede meno dell'ospite** dove non ha fatti: l'ospite ha «In
   diretta ora» coi tavoli, «In arrivo», il campionato con la testa della
   classifica e un archivio di tutti; il giocatore, per le stesse gare, vede
   solo quelle in `INSCRIPTION` e solo le concluse proprie. È la regola 1
   applicata alle sezioni, e si risolve con la tessera condivisa.
5. **Stesso stato, due disegni**: iscrizioni aperte per l'ospite è `Aperta` +
   barra di riempimento + «N posti liberi», per il loggato è `Iscrizioni
   aperte` + «Quota · 5/16 +2 in lista»; conclusa è podio a righe e pastiglia
   verde da una parte, podio a tre riquadri e pastiglia grigia dall'altra.
6. **I campionati non hanno ruolo per elemento**: la tessera in dashboard
   distingue solo il pulsante finale e non porta pastiglie di appartenenza.

**La pagina «Tessera» del canvas** (10/09) mette in fila questi punti: la
matrice stato × fatti della tessera decisa, la matrice del campionato, e le
schermate «Concluse» e «Storico» della regola 2. Le due basi fra cui si è
scelto — A dalla dashboard, B dalla home dell'ospite — sono state rimosse dal
canvas; la decisione è qui sotto.

### Scelte del 10/09 sulla tessera

* **iscrizioni aperte**: la barra di riempimento di B **e** i numeri di A
  (quota, iscritti/posti liberi, «chiudono il»);
* **in corso**: la tessera **scura** di B, per chiunque la guardi;
* **niente pulsanti piccoli** (`btn-sm`, 40px) sulle tessere: sono difficili
  da tappare. Le azioni hanno l'altezza standard del tema, `--c7-btn-h`
  (56px). Vale anche per «Risultati» e «Classifica e risultati»;
* **niente «Gioca la tua partita»**: il bersaglio è il **riquadro della
  propria partita**, che sta più in alto e ha già tutto (chevron a destra,
  bordo `accent-bright`);
* chi **dirige** una gara in corso ha **«Gestisci»** — la pagina di
  amministrazione della gara — al posto di «Segui la diretta», anche quando
  è pure iscritto;
* il **podio porta le medaglie**, oro, argento e bronzo: icona `i-medal` nel
  chip di posizione. Sono **tre token nuovi** (`--c7-oro`, `--c7-argento`,
  `--c7-bronzo`, con il loro inchiostro), dichiarati in `sorgenti/base.css`
  e da aggiungere a `tokens-7c.css` quando si scrive il codice.
  **Emendata l'11/09/2026**: niente icona. Il podio usa **lo stesso chip
  numerato** delle righe di classifica del campionato (`c7-pos--N`), e sono
  i tre colori delle medaglie a passare sul chip, in entrambe le tessere:
  nell'app le due forme stavano una sotto l'altra e dicevano 1°, 2°, 3° in
  due modi diversi;
* in classifica **la riga di chi guarda è scura** (`is-me`), col solo nome:
  niente «sei tu» scritto accanto;
* **storico**: niente filtro per disciplina; c'è **«nei primi N»**, con N a
  scelta;
* **l'invito ai playoff va in cima**, come sezione a sé (Giocatore A in
  Confronto). La #295 lo fa già; la decisione del 30/08 diceva «dentro la
  card del campionato» ed è **emendata** qui.

Cose che invece **restano come sono** e non vanno rifatte: la divisione «Le
tue gare» / «Aperte, puoi iscriverti», la partita dentro la tessera, il
comando di direzione annunciato sulla tessera, le sfide a due, il blocco «Come
stai andando».

## Cosa resta

Le PR #295 e #296 sono da riallineare alle due regole del 2026-09-10 e alle
scelte sulla tessera (pagina «Tessera» del canvas, decisa il 10/09): la
tessera condivisa fra home e dashboard, le concluse con la finestra di un
mese, lo **storico delle gare** (pagina nuova) e la spia «hai giocato / hai
diretto» su quello dei campionati.

Nel frattempo `main` è andata avanti: la #295 va rifatta sopra la prima tappa
della competizione di prova (ADR-058), che ha messo sulla tessera la pastiglia
«Di prova» presidiata da `test_prova_visibilita.py`.

Dei casi dell'inventario restano da disegnare i profili **«di rientro»** e
**«solo esercizi»** del saluto, e il **desktop nella forma C**. Le schermate
`dashboard-giocatore` e `dashboard-direttore` della guida si catturano dopo
il merge della #295, non prima.

Vincoli del progetto da non perdere di vista quando si continua: ogni stringa
in `_()`, il token CSRF su ogni form, `ENDPOINT_ROLES` per le route nuove, e la
verifica a 500px di larghezza dal browser pilotato (skill `ui-7c`).

## Nota sui file

Il canvas seminato (`dashboard-tre-ruoli.html`, 3 MB) **non è committato**: è
l'editor impacchettato, e si rigenera con `seed-canvas.mjs` della skill
`design` a partire da `sorgenti/` e `canvas.json`. Gli `.dc.html` invece sì:
sono piccoli, leggibili, e rendono la cartella comprensibile senza eseguire
niente.

Gli artboard scartati (la variante B del giocatore, la proposta bocciata del
30/08) sono stati rimossi: la decisione resta scritta qui sopra.
