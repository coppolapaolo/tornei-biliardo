# ADR-047 La classifica la decide il sistema di classifica, non il tipo di campionato

**Data**: 2026-08-18
**Stato**: Accepted
**Decisori**: Paolo Coppola

> **Aggiornamento 2026-09-24 (ADR-073).** `_get_campionato_strategy` e le strategie di campionato non esistono più: il sistema della classifica generale lo dice `sistema_della_classifica_generale`, e il calcolo è uno solo.

## Contesto

Un campionato ha due configurazioni indipendenti:

- **`campionato_type`** — la strategia di accoppiamento: come si formano le
  partite (`amalfi`, `random`, `direct_elimination`, `double_knockout`);
- **`default_classification_system`** — il sistema di classifica: su cosa si
  ordinano i giocatori (`WINS`, `RACK`, `POSITION`).

Il direttore le sceglie separatamente nel wizard, e le gare del campionato
ereditano il sistema senza poterlo cambiare (`_gara_edit_form.html` lo mostra
col lucchetto). Nella configurazione più comune le due scelte si accompagnano —
un campionato Amalfi si classifica a vittorie, un Random a triangoli totali — e
proprio per questo il codice ha potuto confonderle per mesi senza sintomi.

Tutta la classifica generale sceglieva il criterio guardando il **tipo**:

| Punto | Cosa decideva sul tipo |
|---|---|
| `_campionato_general_classification.html` | quali colonne mostrare |
| `_index_campionato_cards.html` | cosa scrivere nella top-5 di homepage |
| `TournamentStatisticsService._sort_and_rank_players` | l'ordinamento della vista |
| `Campionato.get_scoring_system()` | i criteri dichiarati, «automatic based on campionato type» |
| `ClassificationService._get_campionato_strategy` | la strategia della classifica **persistita** |

È lo stesso equivoco che il fix **B14** aveva già corretto a livello di gara nel
maggio 2026 — «rispetta `classification_system`, non `matchmaking_strategy`».
Quella correzione si era fermata al confine della gara, e nessuno l'aveva
riportata al campionato.

### Come è venuto fuori

Non da un campionato configurato in modo insolito, ma da un secondo difetto che
lo ha reso visibile (issue #89).

La migration `20260728_split_round_classification_racks` ha separato le due
grandezze che convivevano nella colonna `rack_difference`: da allora
`racks_won` è sempre il totale e `rack_difference` sempre la differenza. Le
righe storiche non sono state riparate, di proposito: a mascherarle in lettura
c'è `RoundClassification.ranking_rack_value`.

La classifica generale, però, non passava da lì: sommava `rack_difference`
grezzo e lo mostrava sotto l'etichetta «Rack Totali». Finché quella colonna
*era* il totale funzionava; dalla separazione in poi la stessa classifica ha
iniziato a sommare differenze, e i totali sono diventati una somma di due
semantiche diverse:

| Gara | `rack_difference` in DB | Contributo |
|---|---|---|
| chiusa prima del 28/07, mai ricalcolata | vecchia semantica: il totale | 6 |
| chiusa dopo, ricalcolata | nuova semantica: la differenza | −3 |
| | **mostrato come "totale"** | **3** |

Il segnalatore l'ha descritto con precisione: «da un certo momento in poi il
criterio è cambiato». Il momento era il deploy di una migration di dieci giorni
prima, e i valori negativi apparsi ad alcuni giocatori erano differenze
stampate sotto l'intestazione dei totali.

## Decisione

**Il sistema di classifica è l'unico criterio della classifica generale.** Il
tipo di campionato decide come si formano le partite e nient'altro.

1. **Un vocabolario solo.** `ClassificationSystem` si sposta in
   `models/status_enum.py`, accanto agli altri vocabolari di dominio, con
   `normalize()` (che riconosce il plurale storico `"RACKS"` e restituisce
   `None` sull'ignoto, come `Discipline.normalize`) e `resolve()` (che ripiega
   esplicitamente su `WINS`). `models/competition/validators.py` lo re-esporta:
   era il punto di import storico.

2. **Un punto da cui leggerlo.** `Campionato.classification_system` restituisce
   il sistema normalizzato. Tutti i rami — vista, homepage, strategia
   persistita — passano da lì.

3. **Due colonne, due totali.** `_aggregate_player_totals` accumula
   `total_racks_won` e `total_rack_difference` separatamente. Il primo non è mai
   la differenza: su una riga storica di gara a vittorie, dove il totale non è
   ricostruibile dalle colonne, vale **0** finché non lo si ricalcola dai match.
   Restituire lì la differenza sarebbe rifare esattamente il guasto.

4. **I due percorsi decidono sullo stesso criterio.** La vista on-the-fly
   (`calculate_general_classification`) e la classifica persistita
   (`update_campionato_classification`, che congela il seeding dei playoff)
   restano due implementazioni separate, ma non possono più scegliere criteri
   diversi per lo stesso campionato.

5. **Le righe storiche si riparano ricalcolandole**, non indovinandole:
   `scripts/repair_round_classification_racks.py` rilegge i match con
   `ScoreAggregator.aggregate_round_scores` — la stessa funzione che alimenta il
   calcolo di produzione — e riscrive le due colonne. È di sola lettura per
   default; `--apply` scrive.

## Conseguenze

### Cambia il comportamento per i campionati discordanti

Un Amalfi a triangoli totali ora classifica a triangoli totali; un Random a
vittorie ora classifica a vittorie. Prima entrambi venivano classificati come
diceva il tipo, ignorando la scelta del direttore. **Questo cambia classifiche
già pubblicate** per quei campionati — ed è il punto: mostravano un ordine che
nessuno aveva chiesto.

### I nomi delle strategie restano storici

`amalfi_campionato`, `random_campionato` e `position_campionato` implementano in
realtà i tre sistemi (`WINS`, `RACK`, `POSITION`). I nomi citano la strategia di
accoppiamento perché è così che venivano scelti. Non sono stati rinominati:
`name` è la chiave del registry e compare nei metadata dei risultati, quindi il
riordino è un lavoro a sé. La mappatura esplicita in `_get_campionato_strategy`
documenta la corrispondenza.

### Cosa resta come debito noto

- **Due percorsi per la stessa classifica.** La vista calcola dai
  `RoundClassification`, il seeding dei playoff dai `Classification` persistiti.
  Ora usano lo stesso criterio, ma restano due implementazioni.
- **Due tabelle di punti-posizione.** `statistics_service` usa 10/7/5/4…,
  `position_points.py` usa 25/18/15/12. Il docstring di quel modulo spiega
  perché **non** vanno unificate: alimentano campionati diversi e cambiarne i
  valori riscriverebbe classifiche già pubblicate. Non toccate.
- **`position` non viene riparata.** Lo script ripristina solo le due colonne di
  triangoli. Un ricalcolo completo muoverebbe piazzamenti storici già
  comunicati; il dry-run segnala se e dove l'ordine divergerebbe.

## I dati storici non sono stati riparati — decisione del 2026-08-18

Lo script esiste, il dry-run è stato eseguito in produzione (455 righe in 22
gare) e **non è mai stato applicato**. È una scelta, non un lavoro lasciato a
metà.

Le ragioni, nell'ordine in cui hanno pesato:

1. **Le gare erano già state premiate.** I risultati sono stati consegnati alle
   persone. Un archivio riallineato mesi dopo non cambia un premio: lo
   contraddice soltanto.
2. **Nessun numero mostrato oggi dipende da quelle righe.** Ripercorrendo i
   percorsi di lettura uno per uno: nei campionati a triangoli si legge
   `racks_won`, che il backfill di luglio aveva già riempito correttamente; nei
   campionati a vittorie si legge `rack_difference`, che in quelle gare non è
   mai stato ambiguo; per le gare col valore storico `"RACKS"`, saltate dal
   backfill, interviene il ripiego di `ranking_rack_value` e restituisce il
   totale giusto. La segnalazione della issue #89 si chiude senza toccare il
   database.
3. **Il report iniziale sopravvalutava il problema.** Diceva «455 righe da
   correggere» mettendo nello stesso mucchio le traduzioni di formato — un
   numero giusto in una casella che allora significava altro — e le poche righe
   con un valore che non discende dalle partite. La distinzione è stata aggiunta
   dopo (PR #151), ma la decisione era già informata da quella lettura.

**Cosa resta esposto.** Il contenuto grezzo di `rack_difference` su un
sottoinsieme di righe è un totale, non una differenza. Oggi nessun percorso lo
legge con quel significato. Morderebbe se qualcuno ci costruisse sopra qualcosa
di nuovo — un criterio di spareggio, una statistica, un export — dando per
scontato che la colonna dica ciò che il suo nome promette.

**Se un giorno la situazione cambia**, gli strumenti sono già lì e sono di sola
lettura per default:

```bash
scripts/repair_round_classification_racks.py --anteprima <campionato>
scripts/repair_round_classification_racks.py --campionato <id> --apply
scripts/verify_classification_configs.py
```

## Alternative considerate

**Correggere solo il valore mostrato** (usare `ranking_rack_value` e chiudere la
issue). Un file, rischio minimo — e lasciava in piedi la scelta sul tipo, cioè
la stessa classe di difetto, pronta a riemergere sul primo campionato
discordante con un sintomo che nessuno avrebbe collegato a questa segnalazione.

**Affidarsi al fallback anche per la differenza.** Impossibile: da un totale non
si ricava la differenza. `ranking_rack_value` maschera solo il totale, ed è
questo il limite che rendeva la riparazione dei dati non rimandabile.

**Riparare i dati con una UPDATE in SQL dentro una migration.** Le regole per
ricavare i triangoli da un match stanno in `_process_regular_match`,
`_process_trio_match` e `_process_bye_match` — trio, bye e set multipli contano
in modo diverso. Riscriverle in SQL avrebbe creato una seconda implementazione
divergente: esattamente il difetto che questo ADR chiude.
