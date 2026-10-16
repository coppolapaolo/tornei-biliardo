# [083] Le prestazioni hanno livelli di certificazione

**Data**: 2026-10-17
**Stato**: Accepted
**Decisori**: Paolo Coppola, Claude

## Contesto

Un risultato può essere garantito da tre parti diverse:

- una partita di **torneo** l'ha garantita un direttore di gara;
- una sfida **confermata** l'hanno garantita i due giocatori, firmando entrambi (ADR-051);
- una sfida **in attesa** l'ha firmata uno solo.

Il terzo caso è diventato frequente: con chi non usa l'app la seconda firma
non arriva mai. Dal 2026-10-16 chi ha firmato può anche giocare un'altra
sfida con lo stesso avversario (emendamento all'ADR-051), quindi queste sfide
si accumulano. Sono comunque fatti: chi ha firmato li ha dichiarati.

Fino a questo ADR i numeri dei giocatori mescolavano i livelli senza dirlo, e
ognuno con una regola sua:

| Numero | Cosa contava |
|---|---|
| ELO competitivo | solo tornei |
| ELO globale | tornei + sfide confermate, ma il ricalcolo da zero contava anche i pareggi che l'evento saltava |
| Vittorie e sconfitte | tornei + sfide chiuse; i pareggi si ricavavano per sottrazione |
| TPA | **ogni** referto, anche di sfide annullate o in corso senza firme |
| Runout | **ogni** triangolo marcato, anche di partite annullate o in corso |

L'utente ha chiesto di renderlo esplicito: tre ELO, tre conteggi di
vittorie, sconfitte e pareggi, e due TPA, perché il TPA esiste solo nelle sfide.

## Decisione

**1. Tre livelli, decisi in un posto solo.** `models/certificazione.py`
assegna a ogni partita un `Livello`, oppure `None` se non ne ha:

| Partita | Livello | Muove l'ELO |
|---|---|---|
| Partita di torneo conclusa | `TORNEO` | se la ammette `RatingEligibility` (ADR-049) |
| Sfida confermata da entrambi | `CONFERMATA` | sì, salvo pareggio |
| Sfida chiusa con un forfait | `CONFERMATA` | no |
| Sfida in corso firmata da uno solo | `IN_ATTESA` | sì, salvo pareggio |
| Tutto il resto | nessuno | no |

Il forfait è *confermato* perché chi abbandona ammette la sconfitta, ma resta
fuori dall'ELO come il walkover nei tornei: è un risultato certo che non
misura la forza (decisione dell'utente del 2026-10-06).

**2. Tre viste cumulative**:

- *Tornei* = `TORNEO`;
- *Confermate* = `TORNEO` + `CONFERMATA`;
- *Tutte* = *Confermate* + `IN_ATTESA`.

La predefinita è *Confermate*, che è anche quella che si vedeva prima.

**3. Ogni numero si chiede per vista**:

- **Storico e statistiche**: `get_unified_match_history(vista=…)`. Le voci
  portano il loro `livello`. `stats_per_vista` dà le tre viste a partire
  dalle stesse voci, e `MatchStats.tied_matches` conta i pareggi.
- **TPA**: `career_stats` / `profile_summary`, entrambi con `vista`. Nella
  vista *Tornei* il TPA non c'è.
- **Runout**: `runout_summary(…, vista=…)`.
- **ELO**: un pool per vista. `ELO` per *Tornei*, `ELO_GLOBAL` per
  *Confermate*, `ELO_ALL` (nuovo) per *Tutte*.

Una sfida in attesa non ha ancora `winner_id`, perché lo scrive la seconda
firma. Il suo esito è quello **dichiarato**, cioè il punteggio che chi ha
firmato ha accettato (`esito_dichiarato`).

**4. `ELO_ALL` segue le firme con un ascoltatore di sessione**
(`models/rating/elo_tutte.py`). Dopo ogni flush si annotano le sfide toccate.
Prima del commit si confrontano due domande per ciascuna: «conta?»
(`sfida_conta_per_elo`) e «è già nel pool?» (`MatchRatingHistory`).

- **Entra** con un'aggiunta in coda, come fa l'evento della seconda firma per
  `ELO_GLOBAL`.
- **Esce** con un ricalcolo da zero del solo pool. L'ELO dipende dall'ordine,
  e sottrarre un delta lascerebbe sbagliati i rating venuti dopo.

**5. `recalculate_all_pools()`** è l'unica chiamata per chi cambia i fatti
sotto l'ELO: unione di account, riassegnazione di un partecipante, categorie
corrette, `scripts/recalc_elo.py`.

## Alternative Considerate

### Alternativa 1: chiamare il rating in ogni servizio che tocca le firme

**Descrizione**: aggiungere una chiamata esplicita in conferma, rifiuto,
triangolo tolto, forfait, chiusura del referto TPA e firma d'ufficio.

- **Pro**:
  - niente di implicito: si legge nel servizio cosa succede.
- **Contro**:
  - i punti sono almeno otto, sparsi in quattro moduli, e alcuni scrivono
    le colonne a mano (`IndividualRackService.remove_rack_for_player`);
  - il nono, aggiunto domani, si dimenticherebbe del rating, e nessun test
    se ne accorgerebbe.

### Alternativa 2: calcolare `ELO_ALL` al volo, senza salvarlo

**Descrizione**: rigiocare tutte le partite in memoria a ogni lettura del
profilo, con al più una cache per processo.

- **Pro**:
  - nessuno stato da tenere allineato.
- **Contro**:
  - duplica il replay di `RatingCalculationService`, compresi i trio, in una
    versione senza database;
  - costa una lettura di tutte le partite a ogni profilo aperto, su
    PythonAnywhere e su NFS.

### Alternativa 3: sottrarre il delta quando una sfida esce

**Descrizione**: come `revert_match_result` per i tornei.

- **Pro**:
  - costa poco.
- **Contro**:
  - è esatto solo se la sfida era l'ultima dei due. Un rifiuto arriva spesso
    giorni dopo, con altre partite in mezzo.

### Alternativa 4: una vista sola, con le sfide in attesa dentro o fuori

- **Contro**:
  - è esattamente la confusione che l'utente vuole togliere: un numero che
    non dice quanto è certificato.

## Conseguenze

### Positive

- Ogni numero del profilo dice da quali partite viene, e i numeri di una
  stessa vista vengono dalla stessa regola.
- TPA e runout smettono di contare partite annullate o mai firmate.
- L'ELO globale smette di contare i pareggi nel ricalcolo da zero: ora
  coincide con quello costruito dagli eventi.
- L'unione di account ricalcola tutti i pool. Prima rigiocava solo il
  competitivo e lasciava indietro il globale.

### Negative

- Il primo ELO di *Tutte* in produzione va calcolato con
  `scripts/recalc_elo.py --commit`, a web app **Disabled** (UC9). Fino ad
  allora il pool contiene solo ciò che è successo dopo il rilascio.
- Un rifiuto o un forfait su una sfida già firmata costano un ricalcolo
  completo del pool dentro la richiesta. Con i volumi attuali (centinaia di
  partite) sono frazioni di secondo; va riguardato se lo storico cresce di
  ordini di grandezza.
- Nel profilo, fino al selettore della vista (PR successiva), si vede
  *Confermate*. Chi ha solo sfide in attesa non vede ancora il proprio TPA.

### Rischi

- Un ascoltatore di sessione agisce lontano da chi scrive. Due presidi:
  1. il flush delle modifiche del chiamante avviene **fuori** dal savepoint,
     così i suoi errori arrivano a lui
     (`test_unique_constraints_toctou.py`);
  2. un errore del rating finisce nel log senza far perdere l'azione
     (`test_se_il_rating_fallisce_la_firma_resta`).

## Note Implementative

- `models/certificazione.py`: `Livello`, `Vista`, `livello_di_partita`,
  `livello_di_sfida`, `esito_dichiarato`, `sfida_conta_per_elo`,
  `sfide_della_vista` (la stessa regola in SQL).
- `models/rating/elo_tutte.py`: l'ascoltatore, registrato da
  `models/rating/__init__.py`.
- `RatingCalculationService`:
  - `recalculate_all_elo_global` e `recalculate_all_elo_all` condividono
    `_ricalcola_pool_largo(system, vista)`, dove una sfida in attesa è
    datata alla prima firma;
  - `process_individual_match_result(sfida, system)`.
- `User.elo_all_rating`, come `elo_global_rating`.
- Il nuovo membro `RatingSystem.ELO_ALL` non richiede migration: la colonna
  `rating_system` salva il **nome** del membro e non ha un vincolo CHECK
  (vedi `test_enum_columns_store_values.py`).
- Test: `tests/new/unit/test_livelli_di_certificazione.py`,
  `TestIlTpaSegueLaCertificazione` in
  `tests/new/integration/test_tpa_referto.py`.

## Riferimenti

- Casi d'uso: `docs/usecases/sfide-e-certificazione.md` (UC4–UC9)
- Regola: `docs/reference/SPECIFICHE.md`, «Livelli di certificazione»
- ADR-049 (quali partite di torneo muovono l'ELO), ADR-051 (doppia conferma e
  suo emendamento), ADR-052 (motore a rack)
