# [073] La classifica generale si calcola in un posto solo

**Data**: 2026-09-24
**Stato**: Accepted
**Decisori**: Paolo Coppola, Claude

## Contesto

La classifica generale di un campionato si calcolava in due modi.

* **La pagina** del campionato (anche pubblica, vetrina, homepage) usava
  `calculate_general_classification`: sommava le classifiche finali delle gare
  concluse — l'ultimo turno di ogni gara, lo spareggio SSR, il piazzamento —
  pesate con `Gara.classification_weight`.
* **Le righe `Classification`**, lette da profilo, export e inviti ai playoff,
  venivano da `update_campionato_classification`: rifaceva i conti dalle
  **partite** (`ScoreAggregator.aggregate_campionato_scores`) e le ordinava con
  una strategia di campionato scelta dal registry.

Ogni regola andava scritta due volte, e tre volte su tre è stata scritta una
volta sola:

1. peso della prova e modalità «solo playoff» (ADR-053) esistevano solo nelle
   righe, e la pagina mostrava la classifica di stagione (#335, 11/09/2026);
2. la zona playoff leggeva le righe, ferme alla gara 1, e segnava il 14° al
   posto del 4° (#433, 14/09/2026);
3. le righe **scartavano la X**: nel campionato 5 serpico67 era ottavo in
   pagina con 5 vittorie, ma senza la X ne aveva 4 e l'invito per l'ottavo
   posto è andato a RIZA, nono (#550, 24/09/2026).

Il confronto sistematico delle due strade ha trovato altre quattro differenze,
nessuna ancora esplosa:

* lo **spareggio SSR** entrava solo in pagina: le righe, a parità di vittorie e
  differenza, ordinavano per id — vinceva chi si era registrato prima;
* una **gara in corso** entrava nelle righe con le partite già finite, non in
  pagina;
* i **punti per piazzamento** venivano da due tabelle: 10/7/5/4 in pagina, dalla
  posizione nell'ultimo turno; 25/18/15/12 nelle righe, dalla posizione finale
  della gara, come dice `CLASSIFICATION_SYSTEM.md` §7.5. Un test difendeva la
  tabella della pagina;
* a piazzamenti i **pari merito** condividevano la posizione nelle righe
  (ADR-040), non in pagina.

Due cose ancora, venute fuori guardando da vicino:

* `update_campionato_classification` era sotto `@cached` per cinque minuti:
  una seconda chiamata ravvicinata tornava il risultato di prima **senza
  scrivere**;
* la pagina leggeva il turno `rounds_count`, mentre la chiusura della gara
  scrive le posizioni finali sull'ultimo turno **giocato**: una gara chiusa con
  meno turni del previsto spariva dalla somma.

`SPECIFICHE.md` riga 292 dice come si fa: «La classifica del campionato
aggrega sommando le classifiche delle singole gare».

## Decisione

**La classifica generale si calcola in un posto solo**,
`TournamentStatisticsService.classifica_generale`, che fa quello che dice la
specifica: somma le classifiche finali delle gare concluse.

* La pagina la legge attraverso `calculate_general_classification`, che è solo
  la sua versione in sessione di sola lettura.
* Le righe `Classification` ne sono la **copia**: `update_campionato_classification`
  le scrive dal suo risultato, campo per campo, senza rifare conti. Non è in
  cache.
* L'aggregatore di campionato sulle partite, le strategie di campionato
  (`amalfi_campionato`, `random_campionato`, `position_campionato`,
  `point_based_campionato`) e la tabella punti 10/7/5/4 sono tolti.

Dove le due strade divergevano, vince la regola che dice la specifica, o che
un ADR ha deciso:

| Punto | Regola tenuta | Fonte |
|---|---|---|
| X | una vittoria, differenza zero (o il punteggio della prova) | SPECIFICHE righe 147-148, 154 |
| Spareggio SSR | terzo criterio a vittorie, secondo a triangoli | `Campionato.get_scoring_system` |
| Gare che contano | solo le concluse | riga 292: «classifiche delle singole gare» |
| Punti per piazzamento | 25/18/15/12…, configurabile, dal piazzamento finale | CLASSIFICATION_SYSTEM §7.5 |
| Pari merito a piazzamenti | condividono la posizione | ADR-040 |
| Ultimo turno di una gara | l'ultimo giocato | `SpareggioService._get_effective_final_round` |

## Alternative Considerate

### Alternativa 1: tenere le due strade, con un test che le confronta

**Descrizione**: è la regola scritta nel CLAUDE.md dopo la #335.

- **Pro**: nessun codice da spostare.
- **Contro**: non ha funzionato. Il test confronta i casi che qualcuno ha
  pensato di metterci, e la X non c'era. Una regola va comunque scritta due
  volte.

### Alternativa 2: una strada sola, ma quella delle righe (dalle partite)

**Descrizione**: la pagina leggerebbe le righe, o ricalcolerebbe dalle partite.

- **Pro**: le partite sono il dato primario.
- **Contro**: contraddice la specifica (la classifica generale somma le
  classifiche delle gare), perde lo spareggio e la banda dei piazzamenti, che
  stanno nella classifica della gara e non nelle partite, e cambierebbe la
  classifica pubblicata di tutti i campionati.

## Conseguenze

### Positive

- Una regola nuova della classifica generale si scrive una volta.
- Pagina, profilo, export, zona e inviti ai playoff dicono la stessa cosa.
- La classifica pubblicata dei campionati esistenti non cambia: cambiano le
  righe, che si allineano alla pagina.

### Negative

- Le righe dipendono dalle classifiche di turno (`RoundClassification`) e di
  gara (`GaraClassification`): se mancano, la gara non entra. È lo stesso
  vincolo che la pagina aveva già, ed è quello che la specifica chiede.
- Una gara in corso non muove più le righe fino alla sua chiusura, come la
  pagina.

### Rischi

- A piazzamenti la pagina cambia tabella punti. In produzione, al 24/09/2026,
  nessun campionato pubblico è a piazzamenti (tre a triangoli, uno a
  vittorie), quindi nessuna classifica pubblicata cambia.
- Le righe restano una **copia**: ferma all'ultimo evento che le ha
  ricalcolate. Chi disegna sopra la classifica in pagina continua a calcolare
  da quella (`models/playoff/zona.py`), e `start_playoff` le ricalcola prima di
  leggerle.

## Note Implementative

- `models/campionato/statistics_service.py`: `classifica_generale`,
  `sistema_della_classifica_generale` (POSITION anche per i campionati a
  tabellone nati prima del sistema), `_aggregate_player_totals` con i punti da
  `GaraClassification` e l'ultimo turno giocato, `_sort_and_rank_players` con
  le bande a piazzamenti.
- `models/classification/campionato_classification.py`:
  `update_campionato_classification` scrive la copia e svuota le cache di chi
  legge le righe.
- Tolti: `ScoreAggregator.aggregate_campionato_scores`,
  `strategies/campionato_strategies.py`, `PositionCampionatoClassificationStrategy`,
  `_get_campionato_strategy`, `_with_position_points`, `position_points_by_player`,
  `_apply_playoff_final_order`, `_count_gare_played`,
  `recalculate_classification_after_match_edit` (senza chiamanti, e ricalcolava
  un turno solo).
- Presidio: `tests/new/unit/test_classifica_generale_una_sola.py` mette righe e
  pagina una accanto all'altra nei casi in cui divergevano.

## Riferimenti

- `SPECIFICHE.md` riga 292; `CLASSIFICATION_SYSTEM.md` §7.5
- ADR-040, ADR-047, ADR-053
- PR #335, #433, #550, #551
