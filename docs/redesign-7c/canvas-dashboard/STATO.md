# Redesign delle dashboard — stato al 2026-08-30

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

Le quattro pagine del canvas: **Mobile** e **Desktop** ritraggono l'app com'è
oggi; **Confronto** mette a fianco le alternative fra cui si è scelto; **Casi**
contiene dieci stati disegnati nella forma scelta.

La cartella è versionata (PR `docs:` del 30/08); il canvas seminato no, vedi
«Nota sui file» in fondo.

## Le decisioni prese

**Giocatore — forma C: ogni cosa dentro ciò a cui appartiene.**
La partita vive dentro la card della sua gara (non in una sezione «I tuoi
match» gemella), l'invito ai playoff dentro la card del suo campionato. La
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
./build.sh <NomeArtboard> ...       # cuce sorgenti/base.css + corpo -> .dc.html
```

Gli artboard «com'è oggi» (`Main`, `Ospite`, `Direttore`, `*Desktop`) sono
scritti a mano in `sorgenti/*.body`, senza generatore.

`build.sh` decide quali fogli aggiungere in base al **nome** dell'artboard
(`*Desktop` → `desktop.css`; `Giocatore[ABC]`, `Direttore[ABC]`,
`Ospite[ABC]`, `Caso*` → `extra.css`). Chi aggiunge un foglio deve
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

## Cosa resta

Dei casi dell'inventario restano da disegnare i profili **«di rientro»** e
**«solo esercizi»** del saluto, e il **desktop nella forma C**.

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
