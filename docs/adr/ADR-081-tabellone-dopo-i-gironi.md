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
   all'italiana ha una fase finale, e il tabellone solo se la gara può avere
   **più gironi** (`max_groups` ≥ 2). Nei campionati che sommano i totali la
   fase finale è rifiutata, come i gironi (ADR-080); con «esattamente N» la
   gara col tabellone è rifiutata, come ogni tabellone.
2. **I turni si fissano all'avvio**: quelli dei gironi più quelli del
   tabellone (`GironiService.fissa_all_avvio`), che verifica anche che `K` non
   superi il girone più piccolo. Se la gara parte con **un girone solo** il
   tabellone non si gioca (`fase_finale_service.si_gioca_il_tabellone`): la
   gara finisce col girone, con la sua classifica e il suo spareggio.
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
5. **Il taglio è una classifica di turno**: chi passa, e con che testa di
   serie, lo dice la catena di turno della gara all'ultimo turno dei gironi
   (`ordine_dei_gironi(per_il_taglio=True)`), che finisce sempre col
   sorteggio; niente spareggio SSR. Chi si è ritirato non va al tabellone:
   passa il successivo.
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
  turno successivo: servirebbe una macchina a stati nuova. Il committente ha
  deciso che il taglio è una classifica di turno.

### Alternativa 4: catena di gara senza SSR, poi sorteggio

**Descrizione**: la prima versione della PR. Respinta dal committente il
2026-10-11: il taglio decide chi gioca il turno dopo, come una classifica di
turno, e ha la sua catena configurata dal direttore.

### Alternativa 5: tabellone anche col girone unico

**Descrizione**: primi 4 di un girone solo in semifinale (1º–4º, 2º–3º).
Respinta dal committente il 2026-10-11: il tabellone è fra i primi di **ogni**
girone, e la gara partita con un girone solo finisce col girone.

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
  (`BRACKET_STRATEGIES`): mostrarle anche qui è il lavoro della PR delle
  pagine, che segue quella dei moduli.

### Rischi

- Una gara col tabellone che parte con un girone solo si comporta come un
  girone all'italiana normale: il foglio di avvio deve dirlo al direttore
  quando sceglie un girone (`Anteprima.girone_unico_senza_tabellone`, usato
  dalla PR dei moduli).

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

## Interfaccia (2026-10-12)

- **Moduli**: il blocco dei gironi (`components/_campo_gironi.html`,
  `static/js/campo_gironi.js`) ha dentro «più gironi» la fase finale —
  nessuna o tabellone, qualificati per girone, finalina, limite della fase
  finale (`components/_campo_limite_fase_finale.html`, tre stati:
  `LimiteDellaFaseFinale`). Col girone unico il blocco si spegne e il parser
  scrive «nessuna» (`form_parser.leggi_la_fase_finale`, lo stesso per gara e
  campionato). «Finali per piazzamento» non si offre e il parser la rifiuta.
  Col tabellone «esattamente N» sparisce dal configuratore della distanza e
  dal modale, con la nota che spiega perché; il servizio resta il garante.
  La finalina del tabellone a eliminazione diretta ha lo stesso nome di
  campo: quella nascosta si spegne (`bracket_options.js`).
- **Proposta del campionato a piazzamenti** (ADR-075):
  `Campionato.default_final_phase_mode`, `default_qualifiers_per_group`,
  `default_third_place_match`, `default_final_phase_time_limit_minutes`
  (migration `20261012_fase_finale_proposta`), copiati alla nascita solo
  sulle gare a girone e, il tabellone, solo con più gironi; proposti solo
  alle gare a girone. Passando a sommare i totali la fase finale torna
  «nessuna», sul campionato e sulle gare da avviare.
- **Foglio di avvio**: ogni voce conta anche i turni del tabellone; «Girone
  unico» dice che il tabellone non si gioca.
- **Frase**: `descrivi_fase_finale`, in coda a quella dei gironi.

## Riferimenti

- SPECIFICHE.md: «Turno» → «Fase finale dopo i gironi»; «Limite di tempo»;
  «Classifica» → «La classifica a gironi».
- ADR-038, ADR-039, ADR-040, ADR-075, ADR-076, ADR-077, ADR-078, ADR-080.
