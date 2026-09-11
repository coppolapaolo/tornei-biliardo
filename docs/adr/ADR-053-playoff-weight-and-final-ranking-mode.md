# [053] Il peso della prova, e chi decide la classifica finale

**Data**: 2026-08-23
**Stato**: Accepted
**Decisori**: Paolo Coppola, Claude

## Contesto

Un campionato può chiudersi con una gara di playoff. La domanda che nessuno
aveva mai formulato — «e allora *come finisce* il campionato?» — aveva già una
risposta nel codice, ma per accidente e non per scelta.

`PlayoffService.create_playoff_gara` crea la gara di playoff con
`campionato_id` valorizzato e numero `max+1`: è una gara del campionato a tutti
gli effetti. E `ScoreAggregator.aggregate_campionato_scores` cicla *tutte* le
gare del campionato, senza escluderla. Quindi la classifica finale era già
**campionato + playoff, con peso 1** — un esito ragionevole, mai deciso, e
soprattutto non modificabile.

Le due esigenze arrivate dal campo:

1. **la finale deve poter decidere il campionato.** Un direttore che organizza
   un playoff spesso vuole che chi lo vince sia il campione. Con la somma,
   un sesto classificato che vince il playoff resta sesto;
2. **le ultime prove devono poter pesare di più** (issue #64). In un
   campionato lungo capita che qualcuno sia matematicamente primo con tre
   prove d'anticipo: le ultime si giocano a metà organico. Un moltiplicatore
   sul punteggio della prova tiene la stagione aperta fino in fondo.

La issue #64 chiede il peso per **ogni** prova, e nota che nei playoff il peso
ha senso solo insieme a un'opzione «considera anche i risultati del
campionato». Aveva ragione sulla forma e torto sul valore predefinito, perché
presumeva che il playoff *non* si sommasse già.

## Decisione

Tre pezzi, con una sola fonte di verità ciascuno.

### 1. `Gara.weight` — il peso vive sulla gara

Colonna intera, `NOT NULL DEFAULT 1`, su **tutte** le gare, non solo su quelle
di playoff. È l'unica cosa che l'aggregatore legge. La configurazione playoff
ha il suo `playoff_weight`, ma è un *valore di configurazione* che viene
copiato sulla gara quando la gara nasce — esattamente come già succede per
distanza, disciplina e numero di turni.

Metterlo sulla gara e non solo sulla configurazione ha un secondo effetto:
la issue #64 nella sua forma generale («peso su ogni prova») resta solo da
esporre in interfaccia, senza altro lavoro di dominio e senza una seconda
fonte di verità da tenere allineata.

### 2. L'aggregazione diventa **per gara**

`ScoreAggregator.aggregate_campionato_scores` non versa più tutte le partite
in un unico mucchio: aggrega gara per gara e somma i totali moltiplicati per
`Gara.classification_weight`. Con tutti i pesi a 1 il risultato è
bit-per-bit quello di prima — condizione che rende innocua la migration su
ogni campionato esistente, ed è presidiata da un test dedicato.

Il peso moltiplica **tutti** i contributi della gara: vittorie, sconfitte,
triangoli vinti e persi. Non si sceglie cosa moltiplicare, perché il peso deve
funzionare tanto con la classifica a vittorie quanto con quella a triangoli
(ADR-047), e queste sono le grandezze su cui le due ordinano.

Le statistiche — Elo, percentuale vittorie, partite giocate — non lo guardano
mai: passano da altri percorsi e continuano a contare i fatti.

### 3. `PlayoffConfiguration.final_ranking_mode`

Due valori:

* **`campionato_plus_playoff`** (predefinito): il punteggio del playoff si
  somma a quello del campionato, moltiplicato per il peso;
* **`playoff_only`**: la classifica finale è quella dei playoff. Chi ha
  giocato il playoff occupa le prime posizioni, nell'ordine deciso lì; **sotto
  vengono tutti gli altri**, nell'ordine che avevano in campionato.

Il predefinito è `campionato_plus_playoff` perché **è** il comportamento
storico. La issue #64 proponeva il contrario, ma partiva dal presupposto
sbagliato che il playoff non si sommasse: adottarlo avrebbe cambiato in
silenzio la classifica di ogni campionato già archiviato.

In modalità `playoff_only` il peso efficace della gara di playoff è **0**
(`Gara.classification_weight`). Non è un dettaglio: se il punteggio della
finale si sommasse comunque, sposterebbe la posizione dei giocatori che al
playoff non sono nemmeno andati — cioè proprio le posizioni che questa
modalità dichiara di voler lasciare all'ordine di campionato.

Modalità e peso sono **per configurazione playoff**, non per campionato: Elite
e Academy hanno gare distinte e possono comportarsi diversamente, e ciascuna
decide le posizioni dei propri partecipanti. I blocchi si compongono in ordine
di `positions_from`, così Elite (dal 1°) precede Academy (dal 7°).

### Quando si può cambiare

`update_configuration` è bloccata dopo l'avvio dei playoff, ed è giusto: i
criteri di qualificazione non si toccano più quando gli inviti sono partiti.
Modalità e peso passano invece da `PlayoffService.update_scoring`, che **non**
è soggetta a quel blocco: sono decisioni di punteggio, non di qualificazione,
e restano del direttore fino alla fine. Al cambio la classifica generale si
ricalcola — un peso modificato che non muove la classifica sarebbe un peso che
non fa niente (issue #64, ultimo requisito).

## Alternative Considerate

### Alternativa 1: peso solo su `PlayoffConfiguration`

**Descrizione**: nessuna colonna su `Gara`; l'aggregatore riconosce la gara di
playoff e va a leggere il peso sulla configurazione.

- **Pro**:
  - una colonna in meno, ambito più stretto.
- **Contro**:
  - la issue #64 nella forma generale andrebbe rifatta da capo, con una
    seconda fonte di verità;
  - l'aggregatore, che è codice di classifica, dovrebbe conoscere il dominio
    playoff per fare una moltiplicazione.

### Alternativa 2: in `playoff_only`, la classifica finale contiene solo i partecipanti

**Descrizione**: la classifica generale si riduce ai qualificati che hanno
giocato il playoff; gli altri restano solo nella classifica di campionato,
che diventa una graduatoria separata.

- **Pro**:
  - lettura semplicissima: la finale è la finale.
- **Contro**:
  - un campionato di venti giocatori chiuderebbe con una classifica di sei, e
    quattordici persone sparirebbero dal proprio campionato;
  - `Classification` è letta da `start_playoff`, dal profilo giocatore e dallo
    storico: potarla avrebbe effetti ben oltre la presentazione.

### Alternativa 3: azzerare i punteggi e ordinare solo sul playoff

**Descrizione**: in `playoff_only` si ordina tutti sul risultato del playoff;
chi non ha giocato resta a zero.

- **Pro**:
  - un solo criterio, nessuna sovrapposizione da comporre.
- **Contro**:
  - quattordici giocatori a pari merito in fondo, con l'ordine deciso dal
    caso: peggio del silenzio.

## Conseguenze

### Positive

- Il direttore può scegliere come chiude il suo campionato, e la scelta è
  scritta invece che implicita nel modo in cui una gara viene creata.
- La issue #64 nella forma generale («peso su ogni prova») è a un campo di
  distanza: il dominio c'è già tutto.
- I campionati esistenti non cambiano di una posizione.

### Negative

- L'aggregazione per gara è un ciclo in più e un dizionario temporaneo per
  gara. Il costo è irrilevante rispetto alle query, ma la funzione è meno
  immediata da leggere di quanto fosse.
- `Gara.weight` esiste su tutte le gare e oggi è modificabile solo dalla
  configurazione playoff: chi lo scopre nello schema potrebbe cercare
  un'interfaccia che ancora non c'è.
- Un campionato con Elite in `playoff_only` e Academy in
  `campionato_plus_playoff` è configurabile e ha un senso preciso — Elite
  detta le prime posizioni, Academy si somma per le altre — ma è una
  combinazione che nessuna schermata spiega.

## Note di attuazione

- `PlayoffRankingMode` è persistita come **stringa**, non come `db.Enum`:
  senza `values_callable` SQLAlchemy scriverebbe il *nome* del membro invece
  del valore, ed è la cicatrice che `PlayoffQualification.status` porta ancora
  addosso (cfr. il commento in `find_replacement_player`).
  `PlayoffRankingMode.normalize` ripiega sul default su un valore ignoto,
  perché quella lettura sta dentro il calcolo della classifica e un dato
  storto non deve far sparire la classifica di un campionato.
- La sovrapposizione (`ClassificationService._apply_playoff_final_order`) legge
  `GaraClassification` della gara di playoff. Finché la finale non è chiusa
  quelle righe non esistono, la sovrapposizione è un no-op e la classifica
  generale resta quella del campionato: è il comportamento voluto per tutta la
  finestra fra l'avvio dei playoff e la fine della finale.
- Un pari merito di campionato fra due giocatori promossi dal playoff viene
  **cancellato** (`tied_with=()`): lasciarlo scritto manderebbe lo spareggio a
  risolvere una parità che il campo ha già risolto.
- **Emendamento 2026-09-11.** La classifica generale si calcola in due
  posti: le righe `Classification` (profilo, export, avvio dei playoff) e
  `calculate_general_classification` in `statistics_service.py`, che alimenta
  la pagina del campionato, quella pubblica, la vetrina e la homepage. Questa
  decisione era stata attuata solo nel primo: il direttore sceglieva «solo
  playoff», la guida glielo prometteva, e la pagina continuava a mostrare la
  classifica di stagione con peso 1. Ora il percorso al volo moltiplica per
  `Gara.classification_weight` e riordina con gli stessi blocchi
  (`ClassificationService.playoff_final_blocks`, resa pubblica per questo).
  Nella stessa occasione: la chiusura di una gara di campionato ricalcola le
  righe persistite, e lo stato del campionato passa a `COMPLETED` quando la
  **gara** di playoff è chiusa — prima guardava il `PlayoffTournament`
  legacy, che nessuna route chiudeva, e restava «In attesa dei playoff» per
  sempre. Presidio in `test_playoff_classifica_finale_e_peso.py`.

## Riferimenti

- Issue #64 — «impostare il *peso* di una prova»
- ADR-047 — il sistema di classifica decide su cosa si ordina
- `docs/reference/SPECIFICHE.md` righe 183-186 — i playoff e la cascata dei rifiuti
- `tests/new/unit/test_playoff_classifica_finale_e_peso.py`
