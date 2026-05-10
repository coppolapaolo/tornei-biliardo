# ADR-029 Amalfi: garanzia zero-rematch nel caso pari via maximum weighted matching

**Data**: 2026-05-10
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

L'algoritmo Amalfi (`models/matchmaking/strategies/amalfi.py`) abbina i giocatori turno per turno usando un "salto" sulla classifica precedente: per ogni giocatore `p1` il partner target è `p2 = (p1 + salto) mod N`, dove `salto = max_turni - turno + 1`. Quando il partner target è già abbinato o ha già giocato contro `p1` (anti-rematch attivo), il greedy avanza ciclicamente cercando un altro candidato. Se dopo `N` tentativi non trova nessuno, **accetta un rematch** come fallback.

Questo comportamento ha causato il fallimento intermittente del test di regressione `test_anti_rematch_prevents_rematches_6_players_3_rounds` (CI run del 2026-05-10, exit 1, 1 rematch trovato al round 3 sulla coppia `(6, 7)`). Il test asseriva `len(rematches_found) == 0` su una configurazione 6 giocatori / 3 round dove **è matematicamente sempre possibile evitare i rematch**: con 6 giocatori esistono 15 coppie distinte, ne servono 9 (3 round × 3 match), e il grafo completo `K_6` si decompone in 5 1-fattori disgiunti.

Il greedy salto, però, non garantisce di trovare questa decomposizione. Per certe permutazioni iniziali (la classifica del primo turno è determinata da `random.shuffle`, non seedata) e per certi esiti dei round precedenti, il greedy può infilarsi in un vicolo cieco e cadere nel ramo di fallback.

La specifica `docs/reference/SPECIFICHE.md` § "Selezione trio nell'algoritmo Amalfi" definisce un esplicito *Ordine di sacrificio* per il caso **trio** (dispari + policy=trio):

1. Posizione in classifica (cede per prima)
2. Anti-rematch (si accetta un rematch nel trio per garantire rotazione equa)
3. Rotazione equa dei trii (ultima a cedere)

Per il caso **pari** (e per il dispari+bye) la specifica non era esplicita: diceva solo "Amalfi abbina ad ogni turno i giocatori partendo dalla classifica precedente e saltando un numero di posizioni pari ai turni che mancano alla fine". L'intent del codice era best-effort no-rematch, ma senza alcuna garanzia formale.

## Decisione

Per il caso **pari** (numero di giocatori divisibile per 2, nessun trio, nessun bye sentinel), l'algoritmo Amalfi garantisce **zero rematch quando matematicamente possibile**, ovvero quando esiste un matching perfetto sul grafo complementare degli incontri già giocati. La garanzia è ottenuta sostituendo il greedy salto con un *maximum weighted matching* su grafo pesato:

- **Nodi**: i giocatori in classifica.
- **Archi**: ogni coppia `(a, b)` che NON appare ancora in `encounter_matrix`. Le coppie già incontrate sono escluse a priori, quindi un matching del grafo non può contenere rematch.
- **Pesi**: `max_weight_offset - |position_diff(a, b) - salto_target|`, con `max_weight_offset = N + 1` per garantire pesi `≥ 1`. Pesi più alti per coppie con `position_diff` vicino al salto target → preserva lo "spirito Amalfi".
- **Algoritmo**: `networkx.max_weight_matching(graph, maxcardinality=True)`. La proprietà `maxcardinality=True` impone l'ordine lessicografico richiesto: prima si massimizza la cardinalità del matching (= zero rematch quando matematicamente possibile), poi tra le soluzioni di cardinalità massima si massimizza il peso totale (= spirito Amalfi).

Se la cardinalità del matching ottimo è `N/2` (matching perfetto sul complementare), l'algoritmo usa quel matching. Altrimenti — quando i rematch sono matematicamente inevitabili — l'algoritmo cade sul greedy salto preesistente come prima.

Per il caso **dispari** (con bye sentinel o trio) il comportamento resta invariato:

- **Trio**: la priorità rotazione-equa-dei-trii > anti-rematch è preservata (vedi specifica esistente).
- **Bye**: il greedy salto resta in vigore. La generalizzazione del matching ottimo al caso bye è fuori scope: il vincolo bye-doppio è esprimibile nel grafo (bye come nodo virtuale connesso solo a giocatori senza bye precedente), ma non c'è evidenza empirica di flakiness su questo caso, quindi rimandiamo l'estensione a quando emergerà.

## Conseguenze

### Positive

- Il test `test_anti_rematch_prevents_rematches_6_players_3_rounds` e `test_anti_rematch_prevents_all_rematches_8_players_3_rounds` diventano contratti validi e stabili (non più flaky in CI).
- Per il caso pari, la specifica e l'implementazione coincidono ora su una garanzia formale ("zero rematch quando possibile") invece di un best-effort sottilmente ambiguo.
- Lo spirito Amalfi (top vs bottom nei primi turni, consecutivi nei finali) resta espresso esplicitamente nei pesi e viene rispettato come tie-break tra matching di cardinalità massima.

### Negative

- L'output del matching ottimo non è bit-identico al greedy salto: per certi input più matching perfetti sono tied al peso totale e networkx può scegliere uno qualunque. Il test `test_amalfi_round1_of_3_produces_wide_spread_pairings` è stato riformulato da pinning test (output esatto) a property test ("almeno 3 pair su 4 hanno position_diff = salto target") — questo è coerente con la nuova garanzia ma è un cambio di contratto a livello di test.
- Costo computazionale: `O(N²)` per costruzione grafo + `O(N³)` per `nx.max_weight_matching`. Per i tornei tipici (N ≤ ~64) è trascurabile rispetto al carico DB. Per tornei molto grandi non c'è regressione rispetto al greedy `O(N²)` perché solo nel caso pari si attiva il matching ottimo, e per N grandi i matching perfetti sono comunque la norma (il fallback greedy si attiva raramente).
- Dipendenza da `networkx` esplicitata anche per Amalfi (era già presente per `random_anti_rematch.py`).

### Neutre

- Il caso dispari+bye continua col greedy: non cambia nulla per le gare esistenti che usano `odd_number_policy=bye`. Se in futuro emergesse una flakiness anche lì, l'estensione è naturale (nodo virtuale bye con archi pesati verso i giocatori non-bye-history).

## Alternative considerate

- **Fissare il seed nei test** (`random.seed(...)`): risolveva il flake ma lasciava il bug latente nel codice — un cerotto, non un fix. Scartato.
- **Backtracking sul greedy**: invece di accettare il rematch al fallback, fare back-track e riprovare con scelta diversa. Più complesso, output non meglio formalizzato del matching ottimo, performance peggiori nel worst case.
- **Rilassare il test** ad asserzione tipo "rematch ≤ soglia": coerente con la spec attuale ma rinunciava al regression-power del test. Scartato.

## Riferimenti

- Specifica aggiornata: `docs/reference/SPECIFICHE.md` § "Garanzia anti-rematch nel caso pari".
- Implementazione: `models/matchmaking/strategies/amalfi.py::AmalfiStrategy._try_optimal_pair_matching` e l'integrazione in `_amalfi_pairing` per `len(players) % 2 == 0`.
- Test contract: `tests/new/unit/test_anti_rematch_regression.py::TestAntiRematchRegression::test_anti_rematch_prevents_*_3_rounds`.
- Test rifrasato: `tests/new/unit/test_amalfi_algorithm_implementation.py::test_amalfi_round1_of_3_produces_wide_spread_pairings`.
- ADR correlato: ADR-001 (Amalfi strategy unification), ADR-002 (anti-rematch encounter cleanup).
