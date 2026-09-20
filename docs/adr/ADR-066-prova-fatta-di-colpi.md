# ADR-066 La prova fatta di colpi: il punteggio discende dai colpi, il bersaglio è un dato del disegno

**Data**: 2026-09-20
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Fino a oggi una prova di un esercizio è **un numero solo**: `ChallengeAttempt.score`,
scritto a fine prova (o `passed`, per gli esercizi riuscita-o-no). Tre richieste
chiedono la stessa cosa da tre lati:

* **#183** — registrare ogni colpo, e per ognuno dove si è fermata la battente,
  rispetto a un bersaglio a cerchi concentrici;
* **#452** — esercizi con una consegna estratta dall'app a ogni colpo, e una
  scala di esiti con un nome;
* **#172** — le schede di allenamento, dove una voce lunga «si conta tiro per
  tiro» (D19).

In tutte e tre la prova smette di essere un gesto e diventa una **sequenza di
colpi con esito**. Il piano del redesign «TPA ed esercizi» chiede di disegnarla
**una volta sola**.

C'è poi una dipendenza che il piano non vedeva: il colpo per colpo vuole un
bersaglio come dato (D14), ma il disegnatore lo avrebbe imparato solo nella fase
9. L'utente ha deciso (20/09) di **anticipare il solo bersaglio**.

## Decisione

### 1. `ChallengeShot`, sotto `ChallengeAttempt`

Una tabella, `challenge_shot`: prova, ordine, esito (`made`), punti, e il punto
d'arrivo (`x`, `y`) quando la bilia è entrata. `ChallengeAttempt` resta il
contenitore e continua a esporre `score`, così storico, andamento, record,
«ha provato» e gamification non cambiano.

### 2. Il punteggio **discende** dai colpi

Per questi esercizi `score` non si digita: è la somma dei colpi, scritta alla
chiusura. È lo stesso rapporto che c'è fra referto TPA e punteggio della partita
(ADR-044), con la stessa regola — due segnapunti che si contraddicono al primo
tocco non devono esistere. `ChallengeService.record_attempt` **rifiuta** il
totale a mano su un esercizio colpo per colpo.

Vale per l'allenamento dal catalogo. In **esami e gare** un esercizio colpo per
colpo si registra ancora col totale digitato: lì le prove stanno in altre
tabelle (`ExamChallengeResult`, `GaraChallengeAttempt`, la prova della X), non
c'è un secondo segnapunti da contraddire, e portarci l'esecuzione colpo per
colpo è un lavoro a sé.

### 3. I punti si **persistono** sul colpo

`points` si scrive quando il colpo si registra e non si ricalcola in lettura. Se
domani l'autore sposta il bersaglio, i colpi già tirati valgono quello che
valevano: stesso schema di `break_player_id` (ADR-056) e degli override per
turno (ADR-027).

### 4. Come si registra è una proprietà **dell'esercizio**

`challenge.recording_mode`: `total` (com'è sempre stato) o `shots`; e
`challenge.shots_count`, quanti colpi ha una prova, fissato dall'autore. Non è
una scelta di chi si allena: due prove dello stesso esercizio devono potersi
confrontare, e «a questo ritmo chiudi a 37» ha senso solo se N è lo stesso per
tutti. `max_score` diventa derivato — N per il valore più alto — e il servizio
lo scrive, così chi già lo legge (peso negli esami, grafici) non cambia.

È una `String` col valore, non un `db.Enum`: rinominare un membro di
`RecordingMode` non rompe i dati scritti. La modalità con estrazione (#452)
aggiungerà un valore, non una colonna.

### 5. Il bersaglio vive **nella scena** del disegnatore

Una voce `{"type": "target", x, y, step, values}` dentro `diagram_scene`: centro
in unità del disegnatore (1 diamante = 100), anelli di uguale spessore in
multipli di un quarto di diamante (D14), valori dal centro verso l'esterno, da
uno a cinque anelli, **un bersaglio per scena**. Il disegno è l'unica fonte di
ciò che sta sul tavolo: un bersaglio in una colonna a parte si potrebbe spostare
senza che il disegno lo sappia.

È l'unica voce della scena che il server legge come dato: `parse_scene` la
convalida al salvataggio (`validate_targets`), `target_from_scene` la legge con
tolleranza — chi esegue un esercizio non deve trovare un 500 per un dato scritto
male mesi prima.

Sul confine fra due anelli vale quello **esterno**; fuori dall'ultimo, zero.

### 6. La prova aperta: nasce col primo colpo, si chiude con un gesto

* Non esiste «inizia la prova»: il primo colpo la apre (`completed = False`), e
  annullato l'unico colpo la riga sparisce. Una prova aperta e vuota sarebbe una
  riga che nessuno chiude più.
* Una prova a metà **si riprende**: è l'unica, aperta, di quell'utente su
  quell'esercizio con `gara_id IS NULL` — la prova della X nasce aperta anche
  lei, ma ha la sua gara.
* Dopo l'ultimo colpo la prova **non si chiude da sola**. L'errore sull'ultimo
  tocco è probabile quanto sugli altri, e chiudendo da soli l'annulla dovrebbe
  restituire l'XP appena dato. Chiudere passa da `complete_challenge_attempt`:
  achievement ed eventi sono quelli di ogni altra prova.
* Ogni statistica legge `completed = True`: la prova aperta non conta da nessuna
  parte. `attempted_at` diventa l'ora della chiusura, perché è lì che entra fra
  «le prove di oggi».

Questo **emenda** la nota di `training_session` («non c'è nessuna entità
sessione»): resta vera per la *sessione* — «le prove di oggi» è ancora una
finestra sull'ora — ma la *prova*, per questi esercizi, ha un inizio e una fine.

### 7. Due percentuali, separate

**Imbucate** = imbucati su tirati. **Posizione** = media, sui soli colpi
imbucati, di `1 − distanza ÷ raggio esterno`, mai sotto zero. Il colpo non
imbucato non ha un punto (`x`, `y` NULL): entra nella prima e non nella seconda.
Un numero solo scenderebbe sia per chi sbaglia la bilia sia per chi sbaglia la
forza, cioè non direbbe che cosa correggere. Funzioni pure in
`models/challenge/shot_stats.py`; la regola è in `SPECIFICHE.md` e in
`test_specifiche_conformita.py`.

## Alternative scartate

* **Un JSON dei colpi su `ChallengeAttempt`.** Niente tabella, ma niente query:
  la nuvola dei punti d'arrivo di cento prove (fase 7) vorrebbe leggerle tutte.
* **Ricalcolare i punti dal bersaglio in lettura.** Spostare il bersaglio
  cambierebbe il passato, record compresi.
* **Il bersaglio in colonne di `challenge`.** Due fonti per ciò che sta sul
  tavolo, e il disegno esportato che ne mostra una sola.
* **Chiusura automatica all'ultimo colpo.** Vedi il punto 6.
* **Lasciare a chi si allena la scelta fra totale e colpo per colpo.** Prove non
  confrontabili sotto lo stesso esercizio.
* **Registrare anche dove finisce la bilia oggetto.** Raddoppia i tocchi, e per
  quasi ogni esercizio non aggiunge niente (#183, «Da decidere»).

## Emendamento (2026-09-20) — la modalità con estrazione (#452)

Il quarto modo di registrare, `draw`, arriva nella stessa fase e non cambia
niente di quanto sopra: è la sequenza di colpi del punto 1, con **una consegna
estratta al posto del bersaglio** e una scala di esiti nominati al posto dei
punti d'anello.

* **La specifica sta in una colonna JSON** (`challenge.draw_spec`), non in due
  tabelle: non la interroga nessuno — si legge tutta insieme, e solo mentre si
  esegue — e le tabelle avrebbero chiesto un ordine, due chiavi e una migration
  per ogni ritocco. La convalida è in `models/challenge/draw_spec.py`, con lo
  stesso rapporto che `parse_scene` ha col disegno: severa quando si salva,
  tollerante quando si legge.
* **Le voci sono già a parole.** Da una a tre liste indipendenti — «3 o più
  sponde», «bilia 7» — composte in una consegna. Un generatore che stampasse
  `37` lascerebbe la decodifica al giocatore, che è il lavoro che gli si vuole
  togliere (#452, punto 1).
* **La consegna in attesa si persiste** (`ChallengeAttempt.pending_prompt`). Se
  si riestraesse a ogni lettura, ricaricare la pagina sarebbe un modo di
  cambiarla finché non piace; e annullare un colpo **rimette quella di prima**,
  per la stessa ragione. Consegna ed esito si scrivono poi **sul colpo**
  (`prompt`, `outcome_label`), come i punti: la prova giocata continua a
  raccontare quello che è successo anche se l'autore riscrive le liste.
* **Qui la prova nasce dall'estrazione**, non dal primo colpo: con l'estrazione
  cominciare è un atto — ti dice che cosa fare — mentre col bersaglio il primo
  dato è già il primo colpo. Di conseguenza, tolto l'unico colpo la prova
  **non** sparisce: la consegna rimessa in attesa è ancora da giocare.
* **Fuori dall'allenamento non entra.** In un esame o in una gara due persone
  riceverebbero consegne diverse, quindi prove non confrontabili: `refuse_if_drawn`
  lo rifiuta alla composizione dell'esame, e la lista dell'esercizio della X non
  lo offre. La strada per ammetterli passa da un **seme fissato** ed è la #506.

## Conseguenze

* La fase 5c (#452) aggiunge un valore a `RecordingMode` e ciò che serve
  all'estrazione; la struttura è questa. `made` è già facoltativo per questo.
* La fase 6 (#172) ha da dove partire per «si conta tiro per tiro».
* La fase 9b trova il bersaglio già nella scena: gli resta da vestirlo nel
  disegnatore rifatto, non da inventarne il dato.
* Esami e gare: invariati. Un esercizio con estrazione, invece, lì sarà
  **rifiutato** (decisione del 20/09: prove non confrontabili).
* Un tentativo aperto e abbandonato resta nel DB finché l'utente non torna o non
  ricomincia. È una riga per utente per esercizio, non una perdita.
