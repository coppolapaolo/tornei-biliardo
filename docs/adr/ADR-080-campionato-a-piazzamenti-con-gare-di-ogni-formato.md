# [080] Il campionato a piazzamenti ammette gare di ogni formato

**Data**: 2026-10-11
**Stato**: Accepted
**Decisori**: Paolo Coppola (committente), Claude

## Contesto

Con i gironi multipli (ADR-076) una gara del girone all'italiana può dividere
gli iscritti in gironi di taglia diversa: 11 iscritti fanno un girone da 6 e
uno da 5. Dentro la gara il confronto si fa per partita giocata; ma la
classifica generale di un campionato **somma i totali** delle gare (ADR-073):
chi capita nel girone più numeroso gioca una partita in più, e porta in
campionato una vittoria o tre punti in più a parità di bravura.

L'utente ha deciso (2026-10-11) che sommare i totali di gironi di taglia
diversa non è sensato. Esisteva già un modo di far entrare le gare in un
campionato che non dipende da quante partite si giocano: il campionato **a
piazzamenti** (punti per posto, `Campionato.position_points`, US-17,
ADR-040). Ma era riservato ai campionati a tabellone: la gara prendeva il
sistema del campionato e la strategia del campionato, e il sistema POSITION
voleva dire «tabellone».

Il sistema di classifica di un campionato diceva così due cose insieme:

1. come si classifica **ogni gara** (vittorie, triangoli, punti, tabellone);
2. come la gara **entra nel campionato** (sommando i totali, o col posto).

È lo stesso genere di equivoco che ADR-047 ha sciolto un livello più sotto,
fra tipo di campionato e sistema di classifica.

## Decisione

1. **Due modi di entrare nel campionato.** Il sistema del campionato
   (`default_classification_system`) dice come le gare entrano nella
   classifica generale: WINS, RACK, POINTS **sommano i totali**; POSITION è
   **a piazzamenti**. Un campionato che propone il tabellone
   (`campionato_type` a eliminazione o doppio KO) è a piazzamenti anche se il
   sistema scritto è un altro: sono i campionati nati prima che POSITION si
   potesse scegliere. Le regole si leggono da un posto solo,
   `models/campionato/piazzamenti.py` (`e_a_piazzamenti`, `somma_i_totali`).
2. **A piazzamenti le gare hanno qualunque formato.** Amalfi, casuale,
   girone all'italiana a uno o più gironi, tabellone: ognuna produce una
   classifica finale completa (`GaraClassification.position`), e il
   campionato ne prende il posto con la sua tabella. Il sistema della gara
   ordina solo la serata: lo **propone** il campionato con una colonna nuova,
   `default_gara_classification_system` (WINS, RACK, POINTS; NULL = WINS), e
   la gara lo può cambiare (ADR-075); sul tabellone resta POSITION. Il modulo
   della gara, in un campionato a piazzamenti, legge strategia e sistema
   (`GaraFormParser`, `sistema_per_la_gara`); sommando i totali li impone
   come prima.
3. **Sommando i totali le gare restano a girone unico.** Il servizio rifiuta
   una gara con più gironi (`GaraService._verifica_gironi_ammessi`) e un
   campionato che li propone (`TournamentService._verifica_gironi_del_campionato`);
   i moduli non mostrano il campo. Fa eccezione la finale dei playoff che
   decide da sola la classifica (peso zero): di lei conta solo l'ordine.
4. **Cosa non cambia nel calcolo.** La classifica generale a piazzamenti era
   già generica: somma i punti di `GaraClassification.position` di ogni gara,
   pesati (ADR-053), con la tabella del campionato. Chi non gioca prende zero,
   i pari merito di una gara prendono i punti del posto condiviso (come le
   fasce del tabellone, ADR-040), oltre la tabella si prende zero. Il suo
   ordinamento (punti, poi vittorie e differenza sommate, i pari condividono
   il posto) resta quello di prima.
5. **Il cambio di sistema** segue ADR-075: si cambia finché nessuna gara è
   avviata. Passando ai piazzamenti ogni gara tiene il sistema della sua
   serata; passando a sommare i totali le gare ricevono il sistema del
   campionato e il girone unico (scritto nella storia), e una gara a
   tabellone ferma il cambio.
6. **Playoff**: in un campionato a piazzamenti la finale si somma col suo
   posto qualunque formato abbia (`_verifica_finale_sommabile`).

## Alternative Considerate

### Alternativa 1: confrontare i totali per partita giocata anche nel campionato

**Descrizione**: come dentro la gara a gironi, la classifica generale
dividerebbe vittorie e punti per le partite giocate.

- **Pro**: nessun nuovo modo di classificare il campionato.
- **Contro**:
  - cambierebbe la classifica di ogni campionato esistente, anche senza
    gironi;
  - premierebbe chi gioca poche serate e le vince: una media su due gare
    batterebbe una media su dieci.

### Alternativa 2: un flag separato «a piazzamenti» accanto al sistema

**Descrizione**: lasciare `default_classification_system` come sistema delle
gare e aggiungere un booleano per come entrano nel campionato.

- **Pro**: i due concetti in due colonne con nomi parlanti.
- **Contro**:
  - i campionati a tabellone esistenti hanno già POSITION come sistema: andrebbero
    migrati, e ogni lettore di `classification_system` (pagina, tessera,
    regolamento, playoff) riscritto;
  - con la colonna nuova per le sole serate nessun dato esistente cambia.

### Alternativa 3: vietare i gironi in ogni campionato

**Descrizione**: gironi solo nelle gare singole.

- **Pro**: nessuna modifica al campionato.
- **Contro**: la serata a gironi non potrebbe mai entrare in un campionato,
  mentre l'utente vuole poter mescolare serate a gironi, Amalfi e tabelloni.

## Conseguenze

### Positive

- Una serata a gironi può entrare in un campionato senza che la taglia del
  girone sposti la classifica generale.
- Un campionato può mescolare formati, una serata per formato.
- I campionati esistenti non cambiano: chi somma i totali non aveva gironi
  (la strategia girone non era selezionabile nel campionato), chi è a
  tabellone era già a piazzamenti, e la colonna nuova nasce NULL (= vittorie,
  quello che le gare non a tabellone ricevevano già).

### Negative

- `default_classification_system` resta un nome storico che dice «come si
  entra nel campionato»; il sistema delle gare si chiede a
  `sistema_delle_gare`, non più alla colonna.
- Il modale «Nuova gara» del campionato propone ancora la strategia del
  campionato: il formato si cambia dalla modifica della gara (PR successiva).

### Rischi

- Nella classifica generale a piazzamenti il secondo e il terzo criterio
  (vittorie e differenza sommate) risentono ancora della taglia dei gironi:
  servono solo a parità di punti.

## Note Implementative

- Dominio: `models/campionato/piazzamenti.py`; colonna
  `Campionato.default_gara_classification_system`, migration
  `migrations/20261011_sistema_delle_gare_a_piazzamenti.py`.
- Lettori aggiornati: `catene._sistema_del_campionato`, `editor_catena`,
  `regolamento.frase_della_catena`, `proposte.CAMPI_PROPOSTI`,
  `PlayoffService._sistema_della_finale`.
- Moduli: wizard del campionato (passo 1 «Classifica di ogni gara», passo 2
  gironi e punti per posizione solo a piazzamenti), modifica del campionato,
  modale nuova gara, modifica della gara (sistema e formato liberi a
  piazzamenti). Il girone all'italiana entra fra i tipi di campionato.
- Presidi: `tests/new/unit/test_campionato_a_piazzamenti.py`,
  `test_specifiche_conformita.py::TestIlCampionatoAPiazzamenti`,
  `test_sistema_delle_gare_migration.py`,
  `tests/new/integration/test_campionato_a_piazzamenti_dal_modulo.py`.

## Riferimenti

- SPECIFICHE.md, «Classifica», «Come una gara entra nel campionato» (nota del
  2026-10-11); «Turno», «Gironi multipli».
- ADR-040, ADR-047, ADR-053, ADR-073, ADR-075, ADR-076.
