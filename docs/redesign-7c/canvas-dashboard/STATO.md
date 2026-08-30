# Redesign delle dashboard — stato al 2026-08-30

Lavoro di design sulle tre dashboard (ospite, giocatore, direttore).
Niente codice dell'app è stato toccato: qui ci sono solo i disegni e le
decisioni prese guardandoli.

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

## Rilievi sul codice emersi disegnando

Indipendenti dal redesign: valgono come correzioni anche da soli.

1. **La sfida a due in corso non compare in nessuna dashboard.**
   `vm.individual_matches` e `vm.match_proposals` sono calcolati da
   `DashboardSectionBuilder` e **nessun template li usa** (zero occorrenze in
   `templates/`). Si vede solo `vm.match_opportunities`, cioè le proposte
   aperte altrui. `IndividualMatch` usa lo stesso `MatchStatus`: una sfida
   `playing` è una partita da giocare come quella di gara.
2. **«Le gare» non sono le tue.** `build_unified_items` include tutti i
   campionati visibili e tutte le gare standalone vive, iscritto o no.
3. **`WaitlistReason` ha due valori e l'interfaccia non li distingue.**
   `CAPACITY` (gara piena) e `PARITY` (la gara non prevede la X, quindi serve un
   numero pari e l'ultimo iscritto aspetta). Il template legge `is_waitlist` e
   non `waitlist_reason`: il secondo caso si legge come un errore — «Lista
   d'attesa #1» su una gara con 17 posti occupati su 24. Correzione di poche
   righe, indipendente dal resto.
4. **Il badge «N da chiudere» del direttore non porta da nessuna parte**: è uno
   `<span>`, e le gare che conta (`playing` + `awaiting_ssr` dirette da lui)
   stanno nell'elenco sotto con la stessa pastiglia che vede un giocatore.
5. **`_index_campionato_cards.html` è l'unico pezzo della home ancora Bootstrap
   legacy** (list-group, alert, `col-md-*`, medaglie in emoji).
6. **`no_campionato.html` non è 7c** (`text-center`, `fa-5x`, `lead`,
   `btn-outline-primary`).
7. **Per il visitatore anonimo la barra laterale si presenta come
   «giocatore»** (`base.html`, ramo `else` del ruolo).

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

## Cosa manca

Dei casi dell'inventario restano da disegnare i profili **«di rientro»** e
**«solo esercizi»** del saluto, e il **desktop nella forma C**.

## Prossimo passo: portare la forma nei template

I file che la forma C tocca, in ordine di dipendenza:

- `templates/components/_separated_dashboard_content.html` — è il cuore: qui
  «I tuoi match» si fonde nella card della gara e l'elenco si divide fra le tue
  e le aperte;
- `templates/components/_unified_dashboard_header.html` — il saluto sale in
  testata (`page_title` in `dashboard/base.html`), il blocco sparisce;
- `templates/components/_playoff_invitations.html` — l'invito scende dentro la
  card del campionato;
- `templates/components/_player_dashboard_content.html` e
  `_director_dashboard_content.html` — la sezione delle sfide a due, che oggi
  mostra solo le proposte altrui, deve mostrare anche la sfida in corso;
- `templates/index.html` + `_index_registration_info.html` +
  `_index_open_inscriptions.html` — l'ordine dell'ospite e l'account chiesto
  dove serve;
- `models/dashboard/` — la divisione «tue / aperte» e la posizione in
  classifica provvisoria vanno preparate nel view model, non ricavate in Jinja.

Vincoli del progetto da non perdere di vista: ogni stringa in `_()`, il token
CSRF su ogni form, `ENDPOINT_ROLES` per le route nuove, e la verifica a 500px
di larghezza dal browser pilotato (skill `ui-7c`).

## Nota sui file

Il canvas seminato (`dashboard-tre-ruoli.html`, 3 MB) **non è committato**: è
l'editor impacchettato, e si rigenera con `seed-canvas.mjs` della skill
`design` a partire da `sorgenti/` e `canvas.json`. Gli `.dc.html` invece sì:
sono piccoli, leggibili, e rendono la cartella comprensibile senza eseguire
niente.

Gli artboard scartati (la variante B del giocatore, la proposta bocciata del
30/08) sono stati rimossi: la decisione resta scritta qui sopra.
