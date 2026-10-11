# [081] Il tabellone dopo i gironi

**Data**: 2026-10-11
**Stato**: Accepted
**Decisori**: Paolo Coppola (committente), Claude

## Contesto

La serata «Lunedì al 74» si gioca in due gironi all'italiana, e ai primi due
di ogni girone tocca la semifinale: 1ºA–2ºB e 1ºB–2ºA, poi finale e
finalina. Con l'ADR-076 i gironi esistono, ma la gara finisce con loro: la
classifica è «prima i primi, poi i secondi», per partita giocata.

Servono tre cose che il girone all'italiana non aveva:

- un **tabellone** dopo l'ultimo turno dei gironi, coi suoi bye quando i
  qualificati non sono una potenza di 2 (tre gironi da due qualificati fanno
  sei giocatori in un tabellone da otto);
- una **classifica finale** che metta insieme le due fasi: il podio dal
  tabellone, il resto dai gironi;
- un **limite di tempo** proprio della fase finale (30 minuti nei gironi,
  per esempio, e semifinali senza limite).

Il tabellone a eliminazione diretta esiste già ed è persistito sulle partite
(ADR-038); la formula FISBB ha già un tabellone finale dopo i gironi, con la
separazione di chi viene dallo stesso girone (ADR-039).

## Decisione

1. **Configurazione sulla gara** (proposta dal campionato a piazzamenti, nei
   moduli della PR successiva): `Gara.final_phase_mode` (`FaseFinale`:
   nessuna, tabellone, piazzamento — l'ultima la realizza la PR 6),
   `Gara.qualifiers_per_group` (`K`, di norma 2), la finalina riusa
   `Gara.third_place_match`. Si leggono da `effective_final_phase_mode`,
   `ha_tabellone_finale`, `effective_qualifiers_per_group`; solo il girone
   all'italiana ha una fase finale. Nei campionati che sommano i totali la
   fase finale è rifiutata, come i gironi (ADR-080); con «esattamente N» la
   gara col tabellone è rifiutata, come ogni tabellone.
2. **I turni si fissano all'avvio**: quelli dei gironi più quelli del
   tabellone (`GironiService.fissa_all_avvio`), che verifica anche che `K` non
   superi il girone più piccolo e che i qualificati siano almeno due.
3. **La generazione sta nella strategia del girone all'italiana**: oltre
   l'ultimo turno dei gironi (`fase_finale_service.turni_dei_gironi`, calcolato
   dalle taglie dei gironi) il primo turno **sorteggia** il tabellone, i
   successivi sono l'eliminazione diretta letta dal tabellone persistito. Il
   lavoro lo fa `_TabelloneFinale`, una sottoclasse di
   `DirectEliminationStrategy` che cambia solo il pavimento della taglia (2
   invece di 4). I nodi portano `bracket_group` NULL: è così che si
   distinguono dalle partite dei gironi.
4. **Teste di serie per colonne** (`group_phase.seed_per_colonne`, la
   generalizzazione di `qualifier_seeding`): prima tutti i primi, poi tutti i
   secondi; dentro la colonna l'ordine della classifica a gironi. I bye vanno
   alle prime teste di serie. La separazione è quella della formula FISBB
   (`_assign_slots(groups_of=…)`): il girone di provenienza, o le squadre se la
   gara le separa.
5. **Il taglio**: la classifica del girone con la catena di gara senza lo
   spareggio SSR, poi il sorteggio della gara (`ordine_dei_gironi(completa=
   True)`). Chi si è ritirato non va al tabellone: passa il successivo.
6. **La classifica finale si compone** (`classification/fase_finale.py`,
   puro): le bande del tabellone (`elimination_bands` sulle sole partite della
   fase finale), con i semifinalisti terzi a pari merito senza finalina, e chi
   esce allo stesso turno ordinato per piazzamento nel girone; poi i non
   qualificati nell'ordine dei gironi. La usano la classifica di turno e di
   gara (`StrategyBasedClassificationService._con_il_tabellone`) e quella
   scritta a gara finita (`SpareggioService._fasce_col_tabellone`). Nei turni
   del tabellone i **numeri** delle righe restano quelli dei gironi.
7. **Niente spareggio SSR** con il tabellone dopo i gironi
   (`SpareggioService.tiebreakers_apply_to`): il podio lo dà il tabellone,
   come nel sistema POSITION (ADR-040).
8. **Limite di tempo della fase finale** a tre stati,
   `Gara.final_phase_time_limit_minutes` (NULL come i gironi, 0 senza limite,
   N minuti). Precedenza in `tempo.limite_del_turno`, l'unico posto che la
   decide: override del turno → fase finale → gara. `fissa_regole` la scrive
   sulla partita quando nasce (ADR-075, ADR-077).

## Alternative Considerate

### Alternativa 1: una seconda gara a eliminazione diretta

**Descrizione**: finiti i gironi, si crea una gara nuova coi qualificati,
come la gara di playoff di un campionato.

- **Pro**: il tabellone resta la strategia di sempre, senza casi nuovi.
- **Contro**: la serata diventa due gare, con due classifiche da riunire a
  mano, due iscrizioni e due pagine; nel campionato a piazzamenti entrerebbe
  due volte.

### Alternativa 2: cambiare strategia alla gara a metà

**Descrizione**: dopo i gironi `matchmaking_strategy` passa a
`direct_elimination`.

- **Pro**: tutta l'infrastruttura del tabellone (viste, sistema POSITION)
  scatterebbe da sola.
- **Contro**: la strategia è struttura (ADR-075): cambiarla a gara avviata
  riscrive le regole delle partite già giocate, e il sistema della gara
  (vittorie, punti) ordina ancora i gironi.

### Alternativa 3: spareggio SSR al taglio

**Descrizione**: se la catena lascia pari il `K`-esimo e il `K+1`-esimo, la
gara si ferma in attesa dello spareggio, come a fine gara.

- **Pro**: lo spareggio è già nella catena di molte gare.
- **Contro**: lo stato `awaiting_ssr` porta alla chiusura della gara, non a un
  turno successivo: servirebbe una macchina a stati nuova. Scelta provvisoria
  il sorteggio, da confermare con il committente.

## Conseguenze

### Positive

- La serata della locandina si gioca per intero dentro una gara sola.
- Il tabellone dopo i gironi riusa il codice del tabellone (slot canonici,
  bye, finalina, separazione) senza copiarlo.
- La classifica finale è una funzione pura, testabile senza database.

### Negative

- La domanda «in quale fase è questo turno?» richiede le taglie dei gironi: si
  paga una query in più dove serve (generazione, classifiche, limite di
  tempo), solo nelle gare col tabellone finale.
- Le viste del tabellone sono ancora legate alle strategie a tabellone
  (`BRACKET_STRATEGIES`): mostrarle anche qui è il lavoro della PR dei moduli.

### Rischi

- Le due scelte provvisorie (sorteggio al taglio, tabellone anche col girone
  unico) aspettano la conferma del committente: sono una funzione ciascuna
  (`ordine_dei_gironi`, `verifica_qualificati`).

## Note Implementative

- Regole pure: `models/matchmaking/fase_finale.py`,
  `models/classification/fase_finale.py`; database:
  `models/competition/fase_finale_service.py`; strategia:
  `RoundRobinStrategy._tabellone_finale`.
- Migration: `migrations/20261011_fase_finale.py` (le gare esistenti ricevono
  «nessuna fase finale», scritto).
- Presidi: `test_gironi_fase_finale_regole.py`,
  `test_gironi_tabellone_finale.py`, `test_fase_finale_migration.py`,
  `test_specifiche_conformita.py::TestLaFaseFinaleDopoIGironi`.

## Riferimenti

- SPECIFICHE.md: «Turno» → «Fase finale dopo i gironi»; «Limite di tempo»;
  «Classifica» → «La classifica a gironi».
- ADR-038, ADR-039, ADR-040, ADR-075, ADR-076, ADR-077, ADR-078, ADR-080.
