# Regolamento di gara: modifiche tracciate invece che impedite

Specifica nata dall'intervista del 2026-09-29 e rivista lo stesso giorno dopo
una verifica sul codice e sulla documentazione. Parte da tre fonti:

- il caso della **finale dei playoff** che, nata già con gli iscritti, non si
  poteva più modificare (né la sala né chi spacca);
- la issue **#549**: modificare una gara a iscrizioni aperte, con notifica e
  conferma degli iscritti;
- la issue **#265** (29/08/2026): «rilassare `can_be_modified` con la modifica
  tracciata». Da lì vengono il segno in classifica e la correzione del peso a
  gara finita; altre scelte di quella issue sono state riconsiderate e
  decise diversamente, come scritto sotto.

## Il principio

Il direttore può correggere quasi tutto, quasi sempre. In cambio ogni
correzione resta **scritta e visibile a tutti**: chi, quando, cosa (prima →
dopo) e, se lo scrive, perché. Serve a gestire gli imprevisti della serata
senza stratagemmi, e a dare una base concreta a eventuali contestazioni.

Tre cose non cambiano mai:

1. **come si è già giocato**: una partita giocata resta con le regole con cui è
   stata giocata;
2. **la struttura della gara dopo l'avvio** (strategia, numero di turni,
   sistema di classifica): si cambia solo annullando l'avvio;
3. **i criteri di qualificazione ai playoff dopo l'invio degli inviti**.

## 1. Quando vale un cambio di regole

Le regole di gioco (distanza, «al N» o «esattamente N», disciplina, set, chi
apre, chi spacca, handicap e categorie, gestione dei dispari, anti-reincontro)
si possono cambiare in ogni momento prima della fine della gara.

- **Prima dell'avvio**: il cambio vale per tutta la gara.
- **A gara avviata**: il cambio si salva subito e vale **dal turno successivo**.
  Il turno in corso e quelli già giocati restano con le regole che avevano.
  La pagina lo dice prima di salvare: «Vale dal turno 4».
- In tutti i formati tranne la casuale il turno successivo si avvia solo
  quando il precedente è chiuso (`verifica_turno_chiuso`); nel tabellone le
  partite dei due lati giocate insieme sono lo **stesso** turno. Il «turno» è
  quindi quello che la gara conosce già (`round_number`), uguale per tutti i
  formati.
- **Strategia casuale**: tutti i turni nascono all'avvio e si giocano senza
  ordine. Dopo l'avvio **le regole di gioco sono bloccate**; restano
  modificabili solo le cose pratiche (sala, orario, tavoli, quota).
- **Formati a tabellone**: le impostazioni che il tabellone impone (dispari,
  ritiro, spareggio, «al N», anti-reincontro) restano non modificabili come
  oggi.

Impostazioni particolari:

| Impostazione | A gara avviata |
|---|---|
| Cosa succede a chi si ritira | vale per i ritiri successivi al cambio |
| Spareggio | modificabile finché lo spareggio non è cominciato |
| Numero di turni | **bloccato**, in tutti i formati (nell'Amalfi cambierebbe gli abbinamenti dei turni rimanenti) |
| Strategia, sistema di classifica | bloccati: si cambiano solo con «Annulla l'avvio», finché nessuna partita ha un risultato |
| Capienza | si può alzare a iscrizioni aperte; chi è in lista d'attesa entra, in ordine |

### Correzioni a gara finita

A gara finita **come si è giocato** non si tocca. Si può invece correggere
**quanto conta la gara** nel campionato:

- il **peso** della gara;
- i **punti per posizione** del campionato.

La classifica si ricalcola, con la traccia e il segno descritti al punto 5.

## 2. Campionato: valori proposti, non ereditati

Il campionato **propone** i valori di partenza delle sue gare; ogni gara poi
decide per sé. Una regola sola per tutti i valori.

- Quando il direttore cambia un valore del campionato, l'app elenca le gare
  **non ancora avviate**, ciascuna con una casella. Sono già spuntate quelle
  che avevano il vecchio valore del campionato; non spuntate quelle con un
  valore proprio. Esempio: la quota passa da 10 a 12 €; la gara 7 (10 €) è
  spuntata, la gara 9 (15 €) no.
- Ogni gara aggiornata così ha la sua voce nella storia («modificato dal
  campionato») e la sua notifica ai propri iscritti.
- Le gare in corso o finite non compaiono: si modificano dalla loro pagina.
- **Chi apre, chi spacca e handicap**, che oggi seguono il campionato in
  diretta, passano allo stesso sistema: al passaggio ogni gara riceve il
  valore che segue adesso, e da lì si comporta come le altre.
- Il blocco attuale del campionato (niente modifiche appena una gara ha
  iscritti) viene tolto.
- **Disciplina e distanza** restano come oggi: la gara nuova le copia dalla
  precedente.

## 3. Playoff

- **Come si gioca la finale** (sala, data, distanza, disciplina, turni…): la
  configurazione propone, la finale decide, con lo stesso meccanismo del
  campionato. Se la finale esiste e non è avviata, l'app chiede se applicare
  il cambio anche a lei. La finale si modifica anche direttamente.
- **Chi si qualifica** (posizioni, posti, gare minime): **bloccato** dopo
  l'invio degli inviti, come oggi. Si chiude anche la strada che oggi cambia
  il minimo di gare senza controllo (`update_playoff_min_garas`).
- Gli strumenti a mano che esistono già (aggiungere un giocatore, toglierlo,
  rispondere al suo posto) restano, e ogni loro uso entra nella **storia dei
  playoff** con chi, quando e motivo facoltativo.
- **Correzione che sposta la classifica dopo gli inviti**: l'app prepara una
  proposta («ritirare l'invito a Bianchi, ora 10°; invitare Rossi, ora 7°»).
  Il direttore la accetta (l'app ritira e invia gli inviti, con le
  notifiche), la rifiuta, o sistema a mano. La scelta va nella storia. Dopo
  l'avvio della finale la proposta non compare più.

## 4. Storia delle modifiche

- Ogni **salvataggio** è una voce, con le sue righe campo per campo (prima →
  dopo). La storia non si accorpa mai: sala A → B → A restano due voci.
- Ogni voce porta: quando, **nome e ruolo** di chi ha modificato (direttore,
  co-direttore, amministratore), da dove (gara, campionato, playoff), motivo.
- Il **motivo è sempre facoltativo**; il campo è in evidenza con un
  suggerimento («Scrivi perché: servirà in caso di contestazioni»).
- Le voci non si cancellano e non si correggono: si aggiunge al massimo una
  nota successiva, datata e firmata.
- La storia **appartiene alla gara**: se la gara viene cancellata, la sua
  storia se ne va con lei.
- Entrano nella storia anche: «Annulla l'avvio», le riconferme date dal
  direttore per un giocatore, le proposte accettate o rifiutate.
- Nessuna storia per le modifiche precedenti all'introduzione; la pagina lo
  dice.
- **Due direttori che salvano insieme**: si applicano solo i campi che chi
  salva ha davvero cambiato; se uno di quei campi l'ha cambiato l'altro nel
  frattempo, il salvataggio si ferma e lo dice.

## 5. Dove si vede

### Regolamento di gara

Una pagina pubblica, visibile a tutti, raggiungibile dalla pagina della gara
e dalla vetrina, dove sostituisce il pulsante del link esterno.

1. **In vigore**: ogni impostazione, e se è stata cambiata da quale turno
   vale.
2. **Per turno**, solo se ci sono differenze fra turni: «Turni 1–3: al 5 ·
   dal turno 4: al 7 (cambiato il 29/09 alle 21:40)».
3. **Storia delle modifiche**, dalla più recente.
4. In fondo, se c'è, il pulsante **«Regolamento completo»** verso il documento
   esterno (il campo «Link esterno» di oggi).

Sulla pagina del campionato, lo stesso per i valori proposti dal campionato e
per i playoff, con la storia dei playoff.

### Segno in classifica

- Nell'**elenco delle gare** del campionato: «Gara 5 · ×2», con il vecchio
  «×1» barrato.
- **Sopra la classifica**, una riga ben visibile: «Classifica ricalcolata il
  12/10: peso della gara 5 da ×1 a ×2 — Mario Rossi». Toccandola si leggono
  i dettagli e il motivo. Lo stesso per i punti per posizione.
- Un segno su ogni riga di giocatore (dettaglio gara per gara) **non** si fa
  ora: richiederebbe di rifare il calcolo, che produce solo totali.

## 6. Notifiche accorpate

La storia è la verità; le **notifiche** si accorpano.

- La prima modifica apre una notifica in attesa per quella gara; le
  successive ci confluiscono. Si confronta lo stato di partenza con quello
  attuale: A → B → C diventa «A → C»; A → B → A non manda niente.
- Parte dopo **30 minuti** senza nuove modifiche (in pratica 30–90 minuti,
  perché il controllo gira ogni ora), **subito** se il direttore preme «Invia
  ora», **subito** se la gara comincia entro **3 ore**.
- Solo notifiche nell'app, come oggi; testi nella lingua e nel fuso di chi
  riceve (ADR-043, ADR-062).
- Competizione di prova: si comporta come le altre notifiche di prova, con il
  prefisso «Prova ·» (ADR-058).

## 7. Riconferma degli iscritti

Scatta solo per ciò che può cambiare la decisione di esserci:

| Modifica | Riconferma |
|---|---|
| data, o ora spostata di più di **1 ora** | sì |
| sala | sì |
| quota in aumento | sì |
| regole di gioco, formato | no, solo notifica |
| nome, tavoli, quota in diminuzione, piccoli spostamenti d'orario | no, solo storia |

- Su ogni iscrizione si conserva la **versione accettata** (data, ora, sala,
  quota). La riconferma serve solo se i valori attuali ne differiscono oltre
  soglia: più modifiche danno **una sola** richiesta; tornando al valore
  accettato, la richiesta sparisce.
- Chi non riconferma resta iscritto **«da riconfermare»**; nessun ritiro
  automatico. Decide il direttore, al più tardi all'avvio.
- Il direttore può **riconfermare al posto del giocatore**; va nella storia.
- Vale anche per chi ha accettato l'invito ai playoff. Per il campionato non
  c'è riconferma.
- Lo stato è **visibile come le iscrizioni**.
- Non è un voto sulla modifica, che resta decisione del direttore: chiede
  solo «ci sei ancora?». Per questo non contraddice il «niente consenso»
  della #265.

## 8. Date in un campionato

Le gare restano in ordine di data (ADR-016). Se una nuova data scavalca le
gare successive, l'app propone di spostarle dello stesso numero di giorni
(«Spostare anche le gare 8 e 9 di 10 giorni, al 27/10 e al 3/11?»). Il
direttore accetta (ogni gara spostata ha la sua voce e le sue notifiche),
rifiuta (e il cambio non si salva) o modifica a mano.

## Criteri di accettazione

- [ ] La finale dei playoff appena creata, con gli iscritti, permette di
      cambiare sala e chi spacca; la modifica compare nel Regolamento di gara.
- [ ] Amalfi al turno 3: la distanza portata da 5 a 7 lascia al 5 il turno 3
      (anche le partite non iniziate) e mette al 7 il turno 4.
- [ ] Una partita in corso non cambia chi spacca quando il direttore cambia
      la regola; la partita del turno dopo usa la regola nuova.
- [ ] Un ricalcolo del punteggio ELO usa le categorie che valevano quando la
      partita è stata giocata.
- [ ] Gara casuale avviata: distanza e chi spacca non si modificano; la sala sì.
- [ ] Il numero di turni non si modifica dopo l'avvio.
- [ ] Cambio della quota nel campionato: compaiono le gare non avviate, già
      spuntate quelle che avevano la quota vecchia.
- [ ] Peso della gara 5 corretto a campionato finito: la classifica si
      ricalcola, «×2» con «×1» barrato nell'elenco gare, riga di ricalcolo
      sopra la classifica.
- [ ] Correzione dopo gli inviti che cambia chi rientra nei posti: il
      direttore vede la proposta e può accettarla, rifiutarla o fare a mano.
- [ ] Sala A → B → C in 10 minuti: due voci nella storia, **una** notifica
      «A → C», **una** richiesta di riconferma. A → B → A: nessuna notifica.
- [ ] Chi non riconferma resta iscritto «da riconfermare»; il direttore può
      riconfermare per lui, e la storia lo dice.
- [ ] Gara 7 spostata dopo la gara 8: compare la proposta di spostare le
      successive.
- [ ] La promessa del modulo («gli iscritti ricevono una notifica») è vera.

## Verifica sul codice (rifatta il 2026-09-29, su `main` a385248)

Controllo rifatto da capo sul codice, senza fidarsi della prima versione di
questa sezione. Riferimenti a file e righe al momento della verifica. Le
affermazioni che toccano una decisione sono state riverificate a mano.

### Cosa regge

- **I turni** sono quelli che la specifica descrive, e per le ragioni che dà:
  - solo la **casuale** crea tutti i turni all'avvio
    (`creates_all_rounds_at_startup`, `matchmaking/configuration.py:198`;
    `RoundService.start_first_round`, `round_service.py:106-163`);
  - in tutti gli altri formati il turno dopo parte solo a turno chiuso:
    `verifica_turno_chiuso` (`pendenze_turno.py:195`) è chiamata da
    `RoundCreationService.start_next_round` (`round_creation.py:340-350`),
    quindi vale per ogni strada; per la casuale è un no-op
    (`pendenze_turno.py:56-64`);
  - nel **doppio KO** le partite del lato vincenti e del lato perdenti giocate
    insieme sono **lo stesso turno** (`double_knockout.py:318-332`,
    `bracket.py:243-282`): per 8 giocatori T2 = V2 + P1, T3 = V3 + P2;
  - l'**Amalfi** usa il numero totale di turni per calcolare il salto
    (`amalfi.py:107`, `:268-270`): bloccarlo dopo l'avvio è necessario.
- **«Annulla l'avvio»** esiste (`admin.competition.cancel_first_round`,
  `rounds.py:79`; servizio `round_cancellation.py:19`): rifiutato se una
  partita ha un vincitore; riporta la gara a iscrizioni aperte (in
  preparazione la finale dei playoff) e riapre gli inviti. Le etichette sono
  quattro (`direttore/_menu_turno.html:29-40`): «Annulla l'avvio della gara»
  (casuale), «… del turno 1», «Annulla il sorteggio» (tabellone), «… del turno
  N». Oggi, tornata in iscrizioni aperte con gli iscritti, la gara resta
  comunque bloccata da `can_be_modified`: la struttura diventa davvero
  modificabile solo col passo 4.
- **Blocchi da sostituire**: `Gara.can_be_modified()` (`competition/models.py:841`:
  SETUP e **nessuna riga** di iscrizione, ritirati e lista d'attesa compresi),
  controllato in `crud.py:322` e `services.py:312`, e in **7** template (non
  nove); `Campionato.can_be_modified()` (`campionato/models.py:178`), in 4
  template; `RoundConfiguration` solo in SETUP, controllo nella route
  (`rounds.py:1024`, `:1106`, chiusure `@transactional` scritte nella route);
  `PlayoffService.update_configuration` (`playoff/services.py:785`, bloccata da
  `has_qualifications`); categorie (`categoria/service.py:99-111`).
- **Il blocco del campionato è più largo** di quanto scritto prima: basta una
  gara in iscrizioni aperte, in corso o **conclusa**, anche senza iscritti.
  Una gara finita blocca il campionato per sempre.
- **Classifica generale** calcolata al volo a ogni lettura
  (`statistics_service.py:424`), moltiplicando per
  `Gara.classification_weight` (`competition/models.py:333-344`); i punti per
  posizione stanno in `Campionato.position_points` e sono modificabili solo
  con il campionato sbloccato. `/aiuto` (`creare_un_campionato.yaml:228-229`)
  dice il contrario: **confermato falso**.
- **Link esterno** (`Gara.external_url/external_label`): compare solo nelle due
  vetrine (`public/vetrina_gara.html:189`, `vetrina_campionato.html:239`).

### Le regole di gioco, una per una

`Match` ha già: `match_distance`, `is_multi_set`, `is_race_to` e
`is_race_to_sets` (NULL = eredita), `discipline` (NULL = eredita),
`lag_winner_id`, `first_break_player_id`, `has_handicap` (**mai scritta**).
Non ha: regola di inizio, regola di apertura, triangoli per set, categorie, X
con prova. `IndividualMatch` ha già tutte le colonne di regola
(`individual_match/match_models.py:93-121`): è il modello da copiare.

| Regola | Dove sta | Quando si legge | Oggi un cambio è retroattivo? | Per fissarla |
|---|---|---|---|---|
| Distanza (set unico) | gara, override per turno | copiata in `match_distance`; ma `effective_distance` tratta 1 come «non scritto» e rilegge la gara (`match/models.py:330-352`) | solo per le partite «al 1» | togliere l'eccezione dopo il riempimento |
| «Al N» / «esattamente N» | gara, turno | copiata solo se diversa dalla gara (`round_creation.py:99-104`), altrimenti riletta a ogni punteggio | **sì**, anche sulle partite chiuse (validazione) | copiarla sempre, riempire le vecchie |
| Set: quanti per vincere | gara, turno | copiata (`match_distance`) | no | niente |
| Set: triangoli per set | gara | riletta dalla gara (`distance.py:174`, `match_service.py:603-610`) | sì, sui set non ancora cominciati | colonna nuova sulla partita |
| Disciplina | gara, turno | scritta solo con un cambio per turno, altrimenti riletta (`get_effective_discipline`, anche storico e filtri: `history_service.py:282`) | **sì**, anche sulle partite chiuse | copiarla sempre, riempire le vecchie |
| Chi apre (inizio), chi spacca (apertura) | gara → campionato **in diretta** (`competition/models.py:459-491`) | a ogni triangolo (`base_match.py:174-185`) e per le domande dell'acchito (`:100-125`) | **no sui triangoli giocati**: chi ha aperto è scritto sul triangolo (`Rack.break_player_id`, ADR-056). **Sì sulla partita in corso**: il triangolo successivo, e le domande dell'acchito che ricompaiono | colonne nuove sulla partita |
| Handicap | partita (mai scritta) → gara → campionato, in diretta (`:446-456`) | a ogni ricalcolo ELO (`rating/eligibility.py:152`) | **sì**: cambia quali partite passate contano per l'ELO | scriverla alla creazione, riempire le vecchie |
| Categorie | `Inscription.categoria_id` | a ogni ricalcolo ELO (`eligibility.py:77-124`, trio compreso) | sì, dove si cambiano dopo l'avvio: `force=True` in `participant_reassign_service.py:731` e nello script `set_gara_categorie.py` | fissarle sulla partita |
| X con prova | `gara.odd_number_policy`, `gara.x_challenge_id` | in diretta in quattro punti (`match/models.py:319`, `direttore_view.py:393`, `pendenze_turno.py:89`, `challenge/services.py:717`); il punteggio no (`score_aggregator.py:225`) | sì, sulla presentazione e sul turno | segno sulla partita |
| Ritiro | gara | al momento del ritiro, poi scritto sull'iscrizione | no | niente |
| Spareggio | gara | a fine gara (`spareggio_service.py:59`) | — | controllo «spareggio non cominciato» |
| Dispari, anti-reincontro | gara | alla creazione del turno | no | niente (nella casuale tutti i turni esistono già) |

Solo cinque valori della gara seguono il campionato in diretta: handicap, chi
apre, chi spacca, **locandina** e **link esterno**. Gli altri sono copiati a
ogni salvataggio dal modulo (strategia e sistema di classifica ricopiati dal
campionato, `form_parser.py:168-190`).

### Tutte le strade che cambiano impostazioni

Nessun servizio di modifica riceve oggi chi agisce: ognuno dovrà riceverlo.

- **Gara**: `update_gara` (modulo, scrive **tutti** i campi e mette i valori
  predefiniti a quelli assenti; unica eccezione chi apre/chi spacca);
  `update_tables_config` (tavoli, sempre); `open_inscriptions` (minimo,
  capienza, date d'iscrizione); `modify_inscription_dates`; chiusura delle
  iscrizioni (`reopen_setup`); vetrina (`update_gara_showcase`: indirizzo,
  link esterno) e locandina; direttori (`add_director`, `remove_director`);
  cambi per turno (`upsert_round_config`, `delete_round_config`); esercizi fra
  i turni (`add_challenge_to_gara`, `remove_challenge_from_gara`); avvio
  (`start_first_round` scrive la X all'ultimo iscritto); «Annulla l'avvio»;
  categorie (assegnare, rinominare, attivare, eliminare: l'elenco è **del
  campionato**, quindi un cambio da una gara vale per le sorelle).
- **Effetti indiretti** sulla gara: esercizio della X sostituito da una copia
  quando l'autore lo disattiva (`challenge/services.py:165-221`); sistema di
  classifica propagato dal campionato (`_propaga_sistema`); peso da
  `update_scoring`; data e ora da `aggiorna_calendario`; numero di turni
  scritto dal sorteggio del tabellone.
- **Campionato**: `update_campionato` (tutti i valori proposti, punti per
  posizione, sistema di classifica con il suo blocco a parte
  `_verifica_cambio_sistema`); vetrina e locandina; attivo/non attivo;
  terminazione; direttori.
- **Playoff**: `update_configuration`, `add_configuration`,
  `deactivate_configuration`, `update_scoring`, `update_playoff_min_garas`
  (**senza** il blocco sugli inviti), `aggiorna_calendario`, `start_playoff`,
  `create_playoff_gara`, `admin_add_player`, `admin_remove_player`,
  `respond_on_behalf` (l'unico che salva chi ha agito, `responded_by_id`).
- **Script** che cambiano impostazioni senza passare dall'interfaccia:
  `set_gara_discipline.py`, `set_gara_handicap.py`, `set_gara_categorie.py`,
  `verify_classification_configs.py --fix`, `adotta_gara_come_playoff.py`,
  `riallinea_inviti_playoff.py`.

`Gara` non ha una colonna di ultima modifica (solo `created_at`); `Campionato`
sì. `AuditMixin` (`models/base.py:160`) non è usato da nessuno.

### Da costruire (confermato)

Storia delle modifiche; modulo che sa quali campi sono cambiati; pagine di
proposta (campionato → gare, configurazione → finale, date successive, inviti
dopo una correzione); colonne di riconferma su `Inscription` e
`PlayoffQualification`; notifiche accorpate con tabella propria e lavoro
orario (oggi l'unico lavoro orario è `send_match_reminders.py`, che riguarda
solo le sfide individuali); pagina del Regolamento con voce `anonimo`;
ripescaggio dalla lista d'attesa quando si alza la capienza (oggi la capienza
si scrive **solo** all'apertura delle iscrizioni e la lista d'attesa si muove
solo quando qualcuno si toglie, `inscription_service.py:523`).

Accorgimenti che discendono dal codice:

- un lavoro fuori da una richiesta **non vede** le competizioni di prova
  (`prova/visibility.py:92-95`): va aperto con `prova_visibili()`; e la
  tabella delle notifiche in attesa, interrogata da sola, non è filtrata;
- `create_notification` scarta in silenzio la notifica se il giocatore ha
  spento quel tipo, è nelle sue ore di silenzio o ha raggiunto il limite del
  giorno (`notification/services.py:92-101`). La notifica accorpata resta in
  attesa finché può partire, invece di andare persa; il tipo spento resta
  rispettato;
- la notifica per un giocatore di prova prende da sola il prefisso «Prova ·»
  se porta `gara_id` fra le entità collegate (`:41-53`);
- con una riassegnazione di partecipante (ADR-048) le categorie fissate sulla
  partita seguono il giocatore che ha giocato davvero: è la correzione di un
  fatto, non un cambio di regola;
- un cambio di regola a gara avviata va rivalidato come alla creazione
  (`validate_gara`): per esempio il trio esiste solo con distanza 2–7.

### Correzioni alla prima versione

- «nove template» → sette per la gara, quattro per il campionato;
- blocco del campionato: vedi sopra, è più largo;
- **chi spacca**: i triangoli giocati sono già al sicuro
  (`Rack.break_player_id`); il rischio vero è la partita in corso;
- **Handicap** e **categorie** rendono oggi l'ELO retroattivo: sono la ragione
  più forte per fissarle sulla partita;
- anche **locandina e link esterno** seguono il campionato in diretta;
- `docs/ROADMAP.md` (non `ROADMAP.md`); la #265 è in «Fuori dalle fasi», riga
  207, e non c'è una sezione «in corso»;
- la specifica dice «Per l'Amalfi non c'è sorteggio», ma l'app oggi scrive
  «Il turno 1 si sorteggia adesso» (`_avvia_gara.html:53`) e ne parlano
  `SPECIFICHE.md:150` e `/aiuto`: i testi nuovi usano «avvia», quelli esistenti
  restano.

### Problemi trovati per strada

- il modulo di modifica promette notifiche (`_gara_edit_form.html:19`, `:41`)
  che nessuno manda; oggi quel testo non si vede mai (la pagina non si apre con
  degli iscritti), diventerebbe falso col passo 4;
- `/aiuto` sui punti per posizione (`creare_un_campionato.yaml:228-229`);
  `abbinamenti.yaml:188-189` («chi spacca? L'app non lo decide») è falso da
  ADR-056;
- l'aggiunta a mano ai playoff non registra chi l'ha fatta sull'iscrizione
  (`_iscrivi_alla_gara`, `playoff/services.py:184-203`);
- **sei route dei playoff** non controllano che la configurazione appartenga
  al campionato dell'indirizzo: `playoff_add_player`, `playoff_remove_player`,
  `playoff_respond_for_player`, `playoff_update_scoring`, `playoff_edit_config`,
  `playoff_deactivate_config` (`routes/admin/campionato.py:851-1079`). Il
  permesso è controllato sul campionato dell'indirizzo: il direttore di un
  campionato può agire sui playoff di un altro cambiando il numero;
- in multi-set il cambio di distanza per turno si perde (i triangoli per set
  si rileggono dalla gara), e i set nascono da `gara.is_race_to` ignorando il
  cambio per turno (`match_service.py:603-610`); i triangoli dei set non
  salvano chi ha aperto (`set_models.py:220`). Il passo 2 sistema i primi due;
- ogni salvataggio di una gara a tabellone riporta `seeding_rating` a «elo»
  (`form_parser.py`, `_parse_bracket_options`: il modulo non manda il campo);
- la **bella** del doppio KO: `start_round_generic` rifiuta i turni oltre
  `rounds_count` (`rounds.py:688`), e la bella è il turno `rounds_count + 1`;
  i test la avviano solo dal servizio. Da verificare a parte;
- `cancel_gara`, `soft_delete_gara`, `soft_delete_campionato` ricevono chi
  agisce e lo buttano via.

### Domande aperte

1. Gli script di correzione `set_gara_discipline.py`, `set_gara_handicap.py`
   e `set_gara_categorie.py` esistono per correggere gare **già giocate**, e
   funzionano proprio perché le partite rileggono la gara. Con le regole
   fissate sulla partita smetterebbero di avere effetto.
2. Il sistema di classifica del campionato: «tutte le gare dello stesso
   sistema» (`SPECIFICHE.md:294`) non sta insieme alle caselle da spuntare
   gara per gara.
3. Il link esterno: oggi serve anche per il modulo di pagamento o la pagina
   della sala, e ha già un'etichetta scelta dal direttore; e, con la
   locandina, segue il campionato in diretta.

## Documenti da emendare

- `SPECIFICHE.md`: riga 21; riga 294 (sistema di classifica del campionato, e
  «il resto della finale si eredita come valore iniziale»); riga 458; riga 88
  (anche la capienza alzata ripesca dalla lista d'attesa); riga 214 (la
  partita ha una copia delle regole, non le eredita); sezione Playoff
  (298-309). Nota datata per ciascuna.
- ADR nuovo, ed emendamenti a: **ADR-016** (la data che scavalca diventa una
  proposta); **ADR-027** (cambi per turno non più solo in SETUP; NULL =
  «eredita» resta solo per le righe vecchie); **ADR-047** (le gare «ereditano
  il sistema senza poterlo cambiare»); **ADR-049** (la finestra delle
  categorie si chiude all'avvio; le categorie ora sono fissate sulla
  partita); **ADR-053** e la riga di `CLAUDE.md` sul blocco dei playoff;
  **ADR-056** («a gara cominciata i campi si affossano», eredità in diretta);
  **ADR-058** (le gare del campionato di prova ereditano «come la regola di
  apertura»). Numeri di riga vecchi da aggiornare in ADR-053:205, ADR-073:54 e
  :153, `tournament_service.py:251`.
- `CLAUDE.md`: righe sul blocco dei playoff, su `playoff_weight` copiato sulla
  gara, sulle `effective_*` che ripiegano sulla gara, sulla categoria che vive
  sull'iscrizione, sulla sintesi di ADR-056.
- `/aiuto`: `opzioni_della_gara`, `creare_una_gara`, `gestire_le_iscrizioni`,
  `turni_su_misura`, `formati_di_gioco`, `abbinamenti`, `playoff`,
  `creare_un_campionato`, `far_conoscere_la_gara`, e inoltre
  `condurre_la_gara` (:481), `categorie` (:107-109), `notifiche` (l'elenco di
  cosa arriva) e `hints.yaml` (:833, il link esterno).
- `docs/ROADMAP.md`: la #265 passa fra le cose in corso.

## Parole

- Ai giocatori si mandano **notifiche**, non avvisi.
- Per l'Amalfi non c'è sorteggio: si **avvia** il primo turno. Il gesto per
  cambiare la struttura è **«Annulla l'avvio»**, che esiste già.
- «Regolamento di gara» riunisce la pagina nuova e il link esterno al
  regolamento, che oggi si chiama allo stesso modo.
