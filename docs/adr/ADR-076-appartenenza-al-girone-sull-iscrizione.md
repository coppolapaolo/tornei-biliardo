# [076] L'appartenenza al girone sta sull'iscrizione

**Data**: 2026-10-11
**Stato**: Accepted
**Decisori**: Paolo Coppola (committente), Claude

## Contesto

Biliardo 74 organizza ogni lunedì una serata con **due gironi all'italiana**
da 5 o 6 giocatori. Fino a oggi la strategia `round_robin` gestiva **un solo
girone** per gara; i gironi esistevano solo nella formula FISBB, dove sono
doppi KO troncati e l'appartenenza si legge dalle partite
(`Match.bracket_group`, ADR-038).

Nel girone all'italiana quella fonte non basta:

- i gironi si devono **vedere prima delle partite**: il direttore li compone
  all'avvio, e la pagina li mostra insieme al primo turno;
- devono restare **stabili con i ritiri**: con la regola EXCLUDE l'iscrizione
  di chi si ritira viene cancellata, ma il suo posto nel calendario resta (e
  il suo avversario vince a tavolino, SPECIFICHE.md, nota del 2026-10-11);
- il calendario del girone si **rigenera a ogni turno** dalla classifica di
  partenza (`RoundRobinStrategy._calendar_order`): serve sapere, a ogni
  turno, chi sta in quale girone, anche per un girone che ha già finito.

Inoltre la gara deve poter dire **quanti gironi al massimo** (la configurazione
si fa prima di sapere quanti si iscrivono) e **come si compongono**, e il
campionato deve poterli proporre (ADR-075).

## Decisione

1. **Configurazione sulla gara**, con la proposta del campionato:
   `Gara.max_groups` («fino a N»; NULL = come il campionato, su una gara
   singola girone unico; 1 = girone unico) e `Gara.group_seeding`
   (`ComposizioneGironi`: sorteggio, ELO, categoria). Il campionato ha
   `default_max_groups` (1) e `default_group_seeding` (sorteggio). Si leggono
   solo da `Gara.effective_max_groups` / `effective_group_seeding`; le
   strategie diverse dal girone all'italiana valgono sempre 1.
2. **Il numero esatto si fissa all'avvio** (`RoundService.start_first_round(
   groups_count=…)` → `GironiService.fissa_all_avvio`): da 1 al tetto, con
   almeno 3 giocatori per girone; senza scelta, la proposta (un girone ogni 6
   iscritti, per eccesso). L'avvio fissa anche `rounds_count`: i turni del
   girone più numeroso — e, nel girone unico, quelli degli iscritti presenti.
3. **L'appartenenza si scrive su `Inscription.group_index`** (0-based, NULL =
   girone unico) e le partite la **ripetono** in `Match.bracket_group`, che le
   viste del tabellone sanno già leggere. Chi chiede «in che girone è?» passa
   da `GironiService.girone_dei_giocatori`: prima le partite del turno 1 (che
   restano anche quando EXCLUDE cancella l'iscrizione), poi le iscrizioni.
   Con meno di due gironi distinti la risposta è vuota: girone unico.
4. **Composizione**: gli iscritti si mettono in fila (`ordine_di_composizione`,
   RNG dal `draw_seed`) e si distribuiscono uno per girone a turno, andata e
   ritorno, riusando il cuore di `group_phase.assign_groups`
   (`distribute_into_groups`, generalizzato a taglie qualunque con
   `bracket.group_player_counts`) e la separazione dei compagni di ADR-039.
   Nell'interfaccia l'opzione si chiama **«Composizione dei gironi»**: non
   «abbinamenti», che nell'app vuol dire chi gioca contro chi.
5. **Turni paralleli**: il turno `r` è la riga `r` del calendario di ogni
   girone; un girone che ha finito non gioca più. Le regole della riga —
   riposo che non vale niente, tavolino contro l'escluso — sono una funzione
   sola per girone unico e gironi (`RoundRobinStrategy._pairings_della_riga`).
6. **Classifiche**: dentro il girone, sistema e catena della gara; nella gara,
   prima i primi, poi i secondi, confrontati **per partita giocata**
   (`models/classification/gironi.py`, puro). Le righe di classifica di turno
   e di gara portano `group_index` e `group_position`.
7. **Annullare l'avvio** azzera `group_index` (`GironiService.azzera`): al
   riavvio i gironi si ricompongono sugli iscritti di allora.

Specializza ADR-038: lì il seat e il girone si derivano dalle partite, qui
l'appartenenza è un **fatto** scritto all'avvio, e le partite ne sono la copia.

## Alternative Considerate

### Alternativa 1: solo `Match.bracket_group`, come la formula FISBB

**Descrizione**: il girone si legge dalle partite, come nei doppi KO a gironi.

- **Pro**:
  - nessuna colonna nuova sull'iscrizione;
  - una fonte sola.
- **Contro**:
  - prima del primo turno i gironi non esistono, e il foglio di avvio non può
    mostrarli;
  - un giocatore senza partite nel turno 1 (escluso prima di giocare) non ha
    girone.

### Alternativa 2: una tabella `girone` con i suoi membri

**Descrizione**: un'entità per girone (nome, indice, gara) e una tabella di
appartenenza.

- **Pro**:
  - spazio per attributi futuri del girone (tavoli dedicati, orari).
- **Contro**:
  - due tabelle con `created_at`/`updated_at` e vincoli per un dato che è un
    intero per iscritto;
  - l'iscrizione è già **per gara**, ed è dove vivono gli altri fatti del
    giocatore in quella gara (categoria, squadra, ordine del sorteggio).

### Alternativa 3: il numero di gironi fisso sulla gara

**Descrizione**: «due gironi», scritto alla creazione.

- **Pro**:
  - niente scelta all'avvio.
- **Contro**:
  - alla creazione non si sa quanti si iscrivono: con 5 iscritti due gironi
    sarebbero impossibili. Il tetto più la scelta all'avvio è lo stesso schema
    del tabellone, dimensionato sugli iscritti effettivi (ADR-038).

## Conseguenze

### Positive

- I gironi si vedono e si spiegano prima delle partite, e un ritiro non li
  sposta.
- Con `max_groups` NULL o 1 la gara è il girone all'italiana di sempre: nessun
  `group_index`, nessun `bracket_group`, classifiche senza girone.
- La classifica a gironi è un modulo puro, testabile senza database, sopra il
  motore unico di ADR-078.

### Negative

- Il girone vive in due posti (iscrizione e partite): la regola di lettura è
  una sola (`girone_dei_giocatori`) e va rispettata.
- Il girone unico ora fissa `rounds_count` all'avvio: un valore scritto a mano
  alla creazione viene sostituito da quello del calendario.

### Rischi

- Nella classifica generale del campionato contano i **totali** della gara
  (ADR-073): chi gioca in un girone più numeroso gioca una partita in più. È
  la regola di sempre, non cambiata qui.

## Note Implementative

- Regole pure: `models/matchmaking/gironi.py`; database:
  `models/competition/gironi_service.py`; classifica:
  `models/classification/gironi.py` e `gironi_della_gara.py`.
- Migration: `migrations/20261011_gironi.py` (le gare esistenti ricevono
  girone unico e sorteggio, scritti, per non leggere in diretta il tetto del
  campionato).
- Presidi: `tests/new/unit/test_specifiche_conformita.py::TestIGironi`,
  `test_gironi_regole.py`, `test_gironi_classifica.py`,
  `test_gironi_avvio_e_turni.py`, `test_gironi_classifiche.py`,
  `test_gironi_migration.py`.
- Fase finale dopo i gironi (tabellone, finali per piazzamento): PR successive
  del piano. Con più di due gironi, le finali per piazzamento restano un punto
  aperto.

## Riferimenti

- SPECIFICHE.md, «Turno» → «Gironi multipli»; «Classifica» → «La classifica a
  gironi».
- ADR-038 (tabellone persistito), ADR-039 (separazione dei compagni), ADR-073
  (classifica generale), ADR-075 (il campionato propone), ADR-078 (catene).
