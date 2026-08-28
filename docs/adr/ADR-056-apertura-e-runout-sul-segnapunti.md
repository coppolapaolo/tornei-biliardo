# [056] Apertura e runout sul segnapunti da tavolo

**Data**: 2026-08-28
**Stato**: Accepted — implementato il 2026-08-28
**Decisori**: Paolo Coppola, Claude

**Canvas di design**: <https://claude.ai/code/artifact/8570c3bd-91ce-469b-8c6c-2606f8ec2e66>
(dodici schermate su tre pagine: *Al tavolo*, *Dove si sceglie*, *Nel profilo*.
Le note sul canvas portano il ragionamento per esteso.)

## Contesto

Il tabellone orizzontale (`components/_match_scoreboard.html`, ADR-nessuno,
schermata 8b del prototipo) registra solo chi vince il triangolo. Mancano tre
cose che al tavolo esistono: chi ha vinto l'**acchito**, di chi è il **tiro di
apertura** in questo momento, e se un triangolo è stato **chiuso in una
visita**.

Prima di disegnare abbiamo guardato cosa c'è già. Il quadro è più pieno di
quanto sembri, ed è la parte da non perdere:

* **`break_rule` esiste**, ma solo sulle sfide individuali:
  `IndividualMatch.break_rule` e `MatchProposal.break_rule`, `String(20)`,
  default `"alternate"`, con tre valori esposti in tre template
  (`quick_match`, `edit_match`, `create_proposal`): `alternate`,
  `winner_breaks`, `loser_breaks`. **Nessuno lo legge** per dedurre chi apra un
  dato triangolo: è scritto, mostrato e testato, mai usato.
* **Il posto dove scrivere chi ha aperto c'è già su entrambi i lati**:
  `IndividualRack.break_player_id` (`match_models.py:1036`) e l'omologo sui
  rack di gara (`models/match/set_models.py:362`), con tanto di parametro
  facoltativo nei servizi. **Nessun chiamante lo valorizza.** È cablaggio a
  metà: manca la regola, non la colonna.

  > **Correzione, 2026-08-28 (implementazione).** Questo punto era sbagliato a
  > metà, e la metà sbagliata è quella che conta. `set_models.py:362` è
  > `SetRack`, cioè i rack dei match **multi-set**. Sui match di gara a **set
  > singolo** — il caso normale, e quello che il tabellone segna —
  > `models/match/models.py::Rack` la colonna non ce l'aveva affatto: è stata
  > aggiunta dalla migration `20260828_apertura_e_runout`. Il cablaggio era
  > quindi a un terzo, non a metà.
* **Sui match di gara non esiste niente**: né `break_rule` né la regola di
  inizio su `Campionato`, `Gara` o `Match`.
* **Il runout è già implementato, e bene, nel motore TPA**:
  `PlayerTally.run_outs`, `break_and_runs`, `perfect_racks`;
  `detect_rack_achievements()` li riconosce da solo;
  `check_break_and_run()` è «spacca e chiude senza mai cedere il tavolo»;
  `run_out_category()` torna `yes`/`no`/`maybe` e il `maybe` ha già il suo
  pulsante (`TpaButton.RUNOUT`). Il TPA sa anche chi apre (`TurnState.break_turn`,
  `can_choose_seat()`).
* **Tabellone e referto TPA non convivono mai** sulla stessa partita:
  `TpaReferto` ha solo `individual_match_id`, e sulle sfide il tabellone è già
  dietro `{% if user_is_player and not tpa_live %}` (ADR-044). Sui match di
  gara il TPA non esiste proprio.

## Decisione

### 1. Il runout si marca sul trattino, non con un pulsante

I trattini di progresso sono già i singoli triangoli. Premere quello che si è
appena acceso lo marca come chiuso in una visita; premerlo di nuovo lo
smarca. Nessun comando dedicato sul tabellone.

Il motivo è di proporzione: **il runout è un evento raro su una superficie
fatta per un gesto frequente**. In una gara al 5 le metà si toccano otto o nove
volte e il runout capita due. Qualunque bersaglio permanente sbaglia in un
verso o nell'altro — piccolo abbastanza da non disturbare e non lo si prende al
buio; grande abbastanza da prenderlo al buio e ruba spazio e sicurezza al gesto
che si fa sempre. In più il runout **non è un altro modo di vincere il
triangolo: è un aggettivo** di quello appena vinto, e gli aggettivi non
meritano un pulsante pari grado.

Scartate, con il loro perché:

* *pastiglia o striscia dedicata dentro la metà* — ruba area al bersaglio
  grande, e sul bordo esterno finisce dove si appoggia la mano sporgendosi sul
  tavolo: un tocco involontario non segna solo un triangolo di troppo, lo marca
  come runout;
* *domanda dopo ogni triangolo* — costringe a due tocchi sempre, per una cosa
  che capita di rado;
* *scorrimento sulla metà* — costa zero area e non si attiva per sbaglio, ma è
  invisibile.

**Vincolo di implementazione**: i trattini non possono stare dentro il
`<button>` della metà (un bottone dentro un bottone non è HTML valido). Vanno
in una riga a sé sovrapposta in fondo alla metà, e i trattini **spenti** devono
avere `pointer-events: none` perché il tocco passi alla metà sottostante — se
no il bersaglio grande si buca anche dove non c'è niente da marcare.

**Debolezza accettata**: non si scopre da solo. Va insegnato una volta (un
suggerimento nella vista verticale o al primo uso), non con chrome permanente
sul tabellone, che vanificherebbe il guadagno.

### 2. Break and run si deduce, non si sceglie

La sigla sul trattino è **R** se ha chiuso rispondendo, **B** se il triangolo
lo aveva aperto lui. Chi segna preme sempre e solo il trattino: la distinzione
la fa il codice, sapendo chi apriva — è la stessa regola di
`check_break_and_run()` nel motore TPA.

### 3. L'acchito fa due domande, non una

Il regolamento FIBiS («Regole generali pool», 1.2) dice:

> «L'acchito è il primo tiro della partita e determina l'ordine di gioco. Il
> giocatore che vince l'acchito **sceglie chi** eseguirà il tiro di apertura.»

Quindi: *chi ha vinto l'acchito?* e poi *chi esegue il tiro di apertura?* — che
può essere l'avversario. **`SPECIFICHE.md` riga 131 va allineata**: oggi
lascia intendere che chi vince cominci.

Nota lessicale dallo stesso regolamento: «acchito» ha **due** significati — il
primo tiro che decide l'ordine (1.2) e la preparazione delle bilie nel
triangolo (1.4 «Acchito delle bilie», «Riacchito»).

### 4. Quattro modalità di apertura, ereditate su due livelli

Modalità: `winner_breaks` (chi ha vinto), `alternate` (a turno),
`alternate_two` (a turno ogni due, **nuova**), `loser_breaks` (chi ha perso).

Ereditarietà **campionato → gara**, e basta: **il match eredita sempre dalla
gara e non si tocca**. Sulle sfide individuali non c'è gara da cui ereditare,
quindi lì il match resta la radice e continua a portare il proprio
`break_rule`.

La forma è quella dell'handicap (`_gara_edit_form.html:121`), che è un
**`<select>` la cui prima voce è «Eredita dal campionato (X)»** — non delle
card, e non la sola preselezione del valore ereditato: senza quella voce i tre
stati diventano due e non si torna più a «segue il campionato» dopo aver scelto
un valore esplicito.

**A gara cominciata i campi si affossano**, non si avvertono soltanto:
cambiarli a metà riscriverebbe chi ha aperto i triangoli già giocati.

I campi vivono in schermate che esistono già, mai in pagine nuove:

| Momento | File |
|---|---|
| nascita del campionato | `admin/campionato_wizard_step2.html`, fra i `default_*` |
| modifica del campionato | `components/_campionato_edit_form.html` |
| modifica della gara | `components/_gara_edit_form.html`, in «Impostazioni di gioco» |

### 5. Tavolo e ora d'inizio in testata

Il **tavolo** è una pastiglia piena, non una voce in coda all'elenco: è un
localizzatore — è così che chi attraversa una sala con otto biliardi riconosce
il proprio tabellone — e va letto da lontano. Compare **solo quando è
assegnato**: nella schermata senza tavolo la sua assenza *è* il segnale.
Attenzione, `table_assignment` è una **stringa**: `gara.get_available_tables()`
restituisce nomi, anche personalizzati, quindi la pastiglia deve troncare.

L'**ora d'inizio** viene da `Match.started_at` e si stampa con il filtro
`|time_local`: il DB tiene naive-UTC e l'ora è quella di chi legge (ADR-043).
L'etichetta è «Inizio 21:15».

Dalla riga dei metadati **esce la regola di apertura**: è configurazione, e la
pastiglia SPACCA sulla metà dice già la stessa cosa in forma viva.

### 6. Nel profilo una riga sola, che unisce due fonti

Dentro «Le mie Statistiche» (`components/_player_statistics.html`), nello
stampo di «Totali» e «Sconfitte»:

> **Runout:** 26 — *di cui 9 break and run*

Il lessico resta **inglese**: nel regolamento FIBiS non esiste un termine
italiano per run-out o break and run, e «serie» è già occupato (indica il
**gruppo** di bilie assegnato — «la propria serie»). Da confermare con
qualcuno in federazione.

**Il numero è l'unione di due fonti, non un arbitraggio**: il flag sul rack per
le partite segnate col tabellone (tutte le gare, e le sfide senza referto) e il
tally derivato per le sfide col referto TPA. Non serve una precedenza perché i
due segnapunti non convivono mai (vedi Contesto).

**Trappola**: qui «runout» è l'**insieme** e break and run un suo
sottoinsieme, che è come parlano i giocatori; nel motore TPA i due contatori
sono invece **disgiunti** (`is_run_out = not is_break_and_run and …`). Il
totale da mostrare è quindi `run_outs + break_and_runs`, non `run_outs`: chi
leggesse `tally.run_outs` e lo stampasse come «runout totali» mostrerebbe 17
invece di 26.

I **triangoli perfetti** restano fuori dalla voce unificata: contarli vuol dire
contare gli errori, e il tabellone gli errori non li vede. Continuano a vivere
nella pagina del referto.

## Com'è stato implementato (2026-08-28)

Tre note che il disegno non poteva prevedere, e che chi torna qui deve sapere.

**Chi apre si *persiste*, non si ricalcola.** `break_player_for_rack`
(`models/match/break_rules.py`) è una funzione pura, e serve a due chiamanti:
chi registra il triangolo — che ci scrive sopra `break_player_id` — e chi
disegna la pastiglia SPACCA per il triangolo ancora da giocare. Persistere è
necessario: se domani il direttore cambia la regola di apertura della gara, i
triangoli già giocati non devono cambiare padrone, perché con loro
cambierebbero le B/R nel profilo dei giocatori. È lo stesso schema
dell'ADR-027 — `Distance` VO derivato, `match_distance` persistito.

**Le due domande vivono sul mixin, non nelle due classi.** `active_racks()`,
`next_break_player_id`, `needs_lag` e `breaker_of_first_rack` stanno in
`BaseMatchMixin`, condiviso da `Match` e `IndividualMatch`. Il primo servizio
condiviso che ha chiesto `is_player` ha trovato che esisteva **solo** su
`IndividualMatch`: è stato spostato anche quello, ed è il difetto che questa
struttura previene.

**Il tabellone non copre tutti i percorsi, ed è dichiarato.** L'acchito si
registra dal tabellone orizzontale; chi segna dalla vista verticale non lo
incontra, quindi su quel match `first_break_player_id` resta NULL e i triangoli
nascono con `break_player_id` NULL — cioè senza B/R. Non è un ripiego
silenzioso: NULL vuol dire «non si sa chi ha aperto», e un triangolo così non
può essere un break and run. Aperta come
[issue #241](https://github.com/coppolapaolo/tornei-biliardo/issues/241): la
vista verticale è la stessa partita vista da un'altra postura, e il gesto lì
va **disegnato**, non ricopiato — sul tabellone il comando è il trattino di
progresso, che in verticale non esiste.

**Le schermate sono quattro, non tre.** La tabella qui sopra elenca i posti in
cui la scelta si *eredita*, e leggerla come l'elenco completo è stato un errore:
il modulo di **creazione di una gara standalone**
(`admin/gara_create_standalone.html`) è l'unico posto in cui una gara senza
campionato può nascere con le due regole già scelte — non avendo nulla da cui
ereditare, l'alternativa sarebbe crearla e poi modificarla. Il precedente era
sotto gli occhi: `has_handicap`, che ha esattamente la stessa forma, sta in quel
modulo dal giorno in cui esiste. Aggiunte lì il 2026-08-28, senza la voce
«eredita», che su una standalone non vuol dire niente.

Nel modulo di creazione di una gara **dentro un campionato** invece non ci sono,
ed è coerente: lì la gara nasce ereditando, e la voce «eredita dal campionato»
è il valore giusto per una gara appena creata.

## Conseguenze

Da fare prima o durante l'implementazione:

* **`SPECIFICHE.md` va emendato con nota datata** (regola della sezione 0 di
  `CLAUDE.md`) su quattro punti: la riga 131 prevede **due** modalità di break
  mentre il codice ne ha già **tre**; «a turno ogni due» è nuova; la stessa
  riga 131 va allineata al regolamento FIBiS sull'acchito (chi vince *sceglie*,
  non *comincia*); sui match di gara non esiste nulla.
* Ogni regola numerica nuova va in
  `tests/new/unit/test_specifiche_conformita.py`, con la citazione della riga.

Cose viste per strada, indipendenti da questo lavoro, da sistemare a parte:

* ~~**«Rifiuta» e «Annulla ultimo triangolo» fanno la stessa cosa.**
  `routes/player/matches.py:344` è commentata «reject — removes last rack», e
  la conferma a schermo lo dice: «L'ultimo triangolo verrà rimosso». Nello
  stato «da confermare» il tabellone mostra tre pulsanti per due azioni.~~
  **Risolto il 2026-08-28.** Il nome giusto è «Rifiuta», perché in quello stato
  l'ultimo triangolo è quello che ha *chiuso la partita*: non si sta
  correggendo un punto qualunque, si sta dicendo che il risultato non torna.
  Tolto il ⟲ dal solo stato «da confermare», dove era il doppione; negli altri
  resta, perché lì è la sola via d'uscita. La vista verticale non ha mai avuto
  il problema — lì le risposte sono sempre state due.
* ~~**`components/_player_statistics.html` e `_player_ratings.html` sono ancora
  in markup Bootstrap**, non 7c. Le card le ridisegna `theme-7c.css`, ma
  `text-primary` / `text-info` / `text-success` / `text-warning` **non sono
  sovrascritti da nessuna parte**: quei quattro numeri del profilo sono il blu,
  il ciano, il verde e l'ambra di Bootstrap, e sono l'unico punto della pagina
  dove si vedono.~~
  **Risolto il 2026-08-28.** Portati alla forma dei componenti che gli stanno
  accanto nella stessa pagina — `c7-sechead`, `c7-card` con `c7-num-lg`,
  `c7-rows` per le righe etichetta/valore — invece di inventarne una: la
  schermata del profilo nel prototipo sta al turno 5, che la skill `ui-7c`
  dichiara direzione **scartata**, quindi non era riferimento. Presidio in
  `tests/new/unit/test_player_statistics_component.py`. Resta in Bootstrap
  `_user_general_stats.html`, che e' la pagina utente dell'amministratore.
* **`stats.provas_played`** in `_player_statistics.html` è l'anti-pattern
  «radice italiana + `-s` inglese» vietato da `NAMING_CONVENTIONS.md`.

Verifica finale che nessun test può dare: **il tabellone sta dietro
`(orientation: landscape) and (max-height: 520px) and (pointer: coarse)`**, che
il browser pilotato non emula. Il gesto sul trattino va provato su un telefono
vero prima di dire che funziona.
