# ADR-060: I tavoli della gara si scelgono in ogni stato

**Data**: 2026-09-13
**Stato**: Accepted
**Decisori**: Paolo, Claude

## Contesto

Una gara usa un elenco ordinato di tavoli (`Gara.available_tables`, JSON; se
vuoto valgono quelli della sala) e da quell'elenco `TableAssignmentService`
assegna i tavoli alle partite, nell'ordine di pregio e — con
`assign_tables_by_ranking` — secondo la classifica.

Fino al 2026-09-12 l'elenco si poteva cambiare **solo a iscrizioni aperte**:
`GaraService.update_tables_config` sollevava se `gara.status !=
INSCRIPTION`, e il componente `_gara_tables_config.html` mostrava il modulo
solo in quello stato (in preparazione una nota, in gioco la sola lettura).

Il canvas «Pagina gara del direttore» (decisione 1 del 12/09/2026) ha
rovesciato la domanda: **quando lo sa, il direttore, quanti tavoli gli
servono?** Non in preparazione, quando gli iscritti non ci sono; spesso
nemmeno a iscrizioni aperte. Lo sa la sera della gara: quando vede quanti si
sono presentati, quando la sala gli toglie un tavolo per un'altra
prenotazione o gliene libera uno a serata iniziata. Il guard proteggeva
un'invariante che non esiste — l'elenco dei tavoli non entra negli
abbinamenti né nella classifica — e impediva l'unico momento in cui la
modifica serve.

## Decisione

I tavoli si scelgono **in ogni stato** della gara: preparazione, iscrizioni,
gioco, fra un turno e l'altro. Il guard è stato tolto dal servizio e dal
template (PR #345); il comando vive nella pagina «Impostazioni gara» e nel
passo «Tavoli» della preparazione.

La regola che rende sicura la modifica a gara in corso è una sola: **la lista
nuova vale per le assegnazioni successive**. Le partite già al tavolo tengono
il loro tavolo, anche se non è più in elenco.

## Alternative Considerate

### Alternativa 1: lasciare il guard alle iscrizioni aperte

**Descrizione**: com'era, con la sola lettura in gioco.

- **Pro**:
  - nessun caso nuovo da pensare in `TableAssignmentService`.
- **Contro**:
  - il direttore scopre il numero dei tavoli quando non può più cambiarlo;
  - l'unica via d'uscita era assegnare a mano, partita per partita, i tavoli
    fuori elenco.

### Alternativa 2: modificabile in gioco, riassegnando le partite in corso

**Descrizione**: cambiato l'elenco, le partite su un tavolo tolto vengono
spostate o rimesse in attesa.

- **Pro**:
  - l'elenco e le partite in corso restano sempre coerenti.
- **Contro**:
  - sposta due giocatori a metà partita, con il punteggio già segnato;
  - una correzione di battitura nell'elenco muoverebbe mezza sala.

### Alternativa 3: in ogni stato, la lista vale da qui in avanti (scelta)

- **Pro**:
  - la modifica non tocca niente di ciò che è già al tavolo;
  - l'algoritmo esistente la regge senza cambiare: i tavoli liberi sono
    quelli in elenco meno quelli occupati da una partita in gioco.
- **Contro**:
  - per qualche minuto una partita può stare su un tavolo che l'elenco non
    ha più.

## Conseguenze

### Positive

- Il comando c'è quando serve, anche a turno in corso.
- Nessuna migrazione e nessun cambiamento di schema: si è tolto un controllo.

### Negative

- Una partita su un tavolo tolto lo tiene fino alla fine; alla chiusura quel
  tavolo non viene riassegnato, perché non è più fra i configurati.

### Rischi

- Chi aggiunge una regola che legge l'elenco dei tavoli come **fatto
  passato** — per esempio «su che tavolo si è giocato» — deve leggerlo dalla
  partita (`Match.table_assignment`), non dalla gara: l'elenco della gara
  cambia nel tempo.

## Note Implementative

- `models/competition/services.py::GaraService.update_tables_config` — senza
  guard sullo stato; il docstring racconta la decisione.
- `models/match/table_assignment_service.py::_get_free_tables` — liberi =
  configurati, in ordine e senza doppioni, meno gli occupati da una partita
  in gioco: un tavolo tolto e occupato resta alla sua partita.
- Presidi: `tests/new/unit/test_gara_tables_config_service.py::test_si_scelgono_in_ogni_stato`
  e `tests/new/integration/test_tables_config_route.py::test_accepted_when_gara_is_playing`.

## Riferimenti

- Canvas: `docs/redesign-7c/canvas-gara-direttore/STATO.md`, decisione 1 e fase B.
- PR #345 «feat: la preparazione della gara, passo per passo».
- ADR-059, la pagina del direttore per fasi.
