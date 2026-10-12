# [082] I preset dei direttori: personali, copiati, solo per precompilare

**Data**: 2026-10-12
**Stato**: Accepted
**Decisori**: Paolo Coppola (piano «gironi multipli, limite di tempo, listino, ordinamenti, preset», UC8), Claude

## Contesto

Il direttore che organizza «Lunedì al 74» ogni settimana riscrive ogni volta
la stessa serata: due gironi, fase finale a tabellone, partite al 3, trenta
minuti, punti 3/1/0, catena degli spareggi, listino. I moduli della gara sono
cresciuti molto (gironi, fase finale, regole della finale, punti, catene,
limite di tempo, listino): rifarli a mano è lento e si sbaglia.

Serve un modo per **salvare una configurazione e ripartire da lì**, senza
che diventi un secondo modo di creare gare, con regole sue, e senza che una
gara resti appesa a qualcosa che il suo direttore può cambiare dopo.

## Decisione

1. **Il preset è personale.** `ConfigPreset` ha un solo proprietario
   (`owner_id`), l'unico che lo vede, lo usa, lo modifica e lo cancella. Per
   chiunque altro non esiste: chiederlo dà 404, non 403. I preset sono dei
   direttori (e degli admin): un giocatore riceve 403.
2. **Condividere vuol dire copiare.** Non c'è una tabella di condivisione: chi
   riceve un preset ne riceve una copia sua, che ricorda solo da chi arriva e
   quando (`received_from_user_id`, `ondelete=SET NULL`; `received_at`). I
   due preset restano indipendenti. Non esiste «togliere la condivisione».
3. **Il preset precompila e basta.** Applicato, scrive nei campi del modulo
   come farebbe il direttore; al salvataggio della gara il modulo passa dal
   parser di sempre (`GaraFormParser`), quindi nessun controllo viene
   scavalcato. Nessuna gara e nessun campionato tengono un riferimento al
   preset: cambiarlo o cancellarlo non tocca niente di già creato.
4. **Whitelist positiva, in un posto solo** (`models/preset/payload.py`):
   i campi del modulo della gara (`GaraFormParser.CAMPI_DEL_MODULO`) meno
   quelli che dicono *quale* serata è — nome, data, ora, sala, tavoli, note,
   peso nel campionato. Iscritti, token e link pubblici non sono campi del
   modulo. Il listino viaggia accanto, come elenco nome/quota senza id.
   Per il **campionato** la base è `CampionatoFormParser.CAMPI_DEL_MODULO`
   meno nome e sala; la lista e `parse_configurazione` (che legge il modulo
   per la modifica del campionato e per il preset) sono tenute allineate da
   un test. I playoff, configurati a parte, non entravano: vedi l'emendamento
   del 2026-10-12, in fondo.
5. **Il payload usa i nomi delle colonne**, non quelli dei campi HTML, e
   porta uno `schema_version`. Si legge con tolleranza: un campo che l'app
   non conosce più si scarta e la pagina lo dice; un campo che manca resta al
   valore che il modulo propone. La traduzione verso i campi HTML è una
   funzione sola (`valori_per_il_modulo`), usata dal JavaScript.
6. **Il preset conserva ciò che la gara riceverebbe**, non ciò che c'è scritto
   nei campi: «Salva come preset» dal modulo passa dal parser. Dentro un
   campionato i valori ereditati («come il campionato») si scrivono espliciti,
   così il preset dice cosa si giocava anche applicato altrove.
7. **I campi già toccati non si sovrascrivono senza chiedere.** Si applica il
   resto, poi il foglio di conferma (ADR-074) chiede se usare anche lì i
   valori del preset.
8. **Il wizard del campionato è in due passi**, e il preset li attraversa: al
   passo 1 scrive tipo e sistemi e passa la scelta (`preset_id`) al passo 2,
   che si apre applicando i valori proposti alle gare. «Salva come preset»
   sta al passo 2 e completa il modulo col passo 1 tenuto nella sessione.
9. **La condivisione** (parte B, 2026-10-12): una copia per destinatario,
   solo direttori o admin, notifica composta nella lingua di chi riceve
   (ADR-062). Il nome già presente prende «(da X)», scritto nella lingua del
   destinatario perché il preset è suo, e poi un numero. La ricerca dei
   direttori è per nome utente, da due lettere in su: l'elenco intero non si
   sfoglia.

## Alternative Considerate

### Alternativa 1: preset condiviso per riferimento

**Descrizione**: una tabella `preset_reader`; chi riceve legge l'originale.

- **Pro**: l'autore aggiorna una volta per tutti.
- **Contro**: chi riceve si ritrova cambiato un preset che non ha toccato, e
  perde tutto se l'autore lo cancella; servono permessi di lettura e
  scrittura distinti. L'utente ha scelto la copia.

### Alternativa 2: gara legata al preset («modello»)

**Descrizione**: la gara ricorda il preset e ne eredita i cambi.

- **Pro**: correggere il preset correggerebbe le gare future già create.
- **Contro**: una terza fonte di verità accanto a gara e campionato, contro
  l'ADR-075 (le regole si fissano e i cambi restano scritti nella storia
  della gara). Il preset precompila, la gara decide.

### Alternativa 3: payload coi nomi dei campi HTML

**Descrizione**: salvare il modulo così com'è, campo per campo.

- **Pro**: applicarlo non richiede traduzioni.
- **Contro**: i nomi HTML cambiano più spesso delle colonne, e «Salva come
  preset» da una gara esistente dovrebbe ricostruire il modulo a mano. Con
  le colonne la gara e il modulo hanno la stessa forma, e il parser resta
  l'unica traduzione modulo → gara.

## Conseguenze

### Positive

- Un campo nuovo del modulo entra nei preset senza toccare la whitelist.
- Nessuna migrazione dei preset quando la gara cambia: al peggio un campo si
  scarta, e la pagina lo dice.

### Negative

- Un preset ricevuto non segue gli aggiornamenti dell'autore: per
  aggiornarlo si condivide di nuovo.

### Rischi

- La traduzione colonne → campi HTML (`valori_per_il_modulo`) deve seguire i
  moduli: il presidio è l'andata e ritorno modulo → preset → modulo in
  `tests/new/unit/test_preset_dei_direttori.py`.

## Note Implementative

- Modello: `models/preset/models.py` (`ConfigPreset`, `TipoPreset`), nome
  unico per proprietario (vincolo dello schema), migration
  `migrations/20261012_preset_dei_direttori.py`.
- Servizio: `models/preset/service.py` (`ConfigPresetService`).
- Route: `routes/admin/preset.py`, tutte `{"director"}` in `ENDPOINT_ROLES`;
  la pagina «I miei preset» è `admin.preset.miei` (`templates/admin/preset_miei.html`,
  `static/js/preset_miei.js`), raggiungibile dal menu utente.
- Notifica: `NotificationType.PRESET_SHARED`, link a «I miei preset».
- Interfaccia: `templates/components/_preset_modulo.html` e
  `static/js/preset_modulo.js`; l'editor delle catene rilegge il campo
  nascosto quando riceve `change`.

## Emendamento del 2026-10-12: i playoff entrano nel preset di campionato

**Decisione dell'utente.** Il preset di campionato comprende anche le
configurazioni dei playoff (Elite, Academy e le altre aggiunte dalla pagina
del campionato). Il punto 4 escludeva i playoff perché si configurano a
parte; ma chi rifà ogni anno lo stesso campionato rifà anche gli stessi
playoff, e un preset che li dimentica è a metà.

- **Whitelist positiva sua** (`payload.CAMPI_DEL_PLAYOFF`): criteri di
  qualificazione (`positions_from`, `positions_to`, `max_participants`,
  `min_garas_played`), modalità di classifica finale e peso, formula e regole
  della finale (`discipline`, `distance`, `rounds_count`, `strategy_type`,
  `odd_number_policy`, `classification_system`, `entry_fee`), nome e
  descrizione. Fuori: id, campionato, gara creata, stato, date, scadenza,
  sala, il tipo storico e i criteri JSON di una volta, qualificati e inviti.
- **Il payload** porta `playoff`, un elenco (anche vuoto: il campionato non
  ne aveva). `schema_version` sale a 2. Un preset della versione 1 dei
  playoff non sa niente: si legge con `playoff` assente (None), che vuol
  dire **non toccarli** — gli interruttori del passo 1 restano come sono, e
  «I miei preset» non dice niente — distinto dall'elenco vuoto della
  versione 2, che vuol dire «nessun playoff» e li spegne.
- **Salvare**: dal passo 2 del wizard i playoff sono quelli che il wizard
  creerebbe (`payload.configurazioni_dal_wizard`, la stessa funzione della
  creazione); dalla modifica e dal dettaglio sono le configurazioni attive
  del campionato (`payload.playoff_del_campionato`).
- **Applicare nel wizard**: il passo 1 sa esprimere due configurazioni, Elite
  e Academy, una dopo l'altra in classifica. La prima del preset va su Elite,
  la seconda su Academy: il preset scrive interruttori e posti, e il passo 2
  rilegge dal preset scelto criteri e regole della finale. I posti restano
  quelli del modulo e le posizioni si ricalcolano come sempre. Oltre la
  seconda non si crea niente, e la pagina lo dice. La creazione
  (`TournamentService.create_playoff_config`) passa dagli stessi controlli
  della correzione (valori ammessi, finale sommabile): campionato, listino e
  playoff nascono in una transazione sola, così una finale rifiutata non
  lascia un campionato a metà.
- **Applicare nella modifica**: non tocca i playoff. La modifica del
  campionato non li gestisce: si cambiano dalla pagina del campionato, dove
  `update_configuration` blocca i criteri a inviti partiti (ADR-075).
  Applicarli da qui scavalcherebbe la storia dei playoff e la proposta alla
  finale già creata; la pagina dice invece che il preset li comprende, e se
  in quel campionato gli inviti sono già partiti.
- **«I miei preset»** dice per ogni preset di campionato se ha i playoff, e
  quali; duplicare e condividere copiano il payload, playoff compresi.

**Alternativa scartata**: applicare i playoff del preset anche nella modifica
del campionato, configurazione per configurazione. Servirebbe un abbinamento
fra le configurazioni del preset e quelle del campionato (per nome? per
posizione?), e ogni cambio andrebbe proposto alla finale già creata: è il
lavoro della pagina del campionato, che lo fa già con storia e blocchi.

## Riferimenti

- Piano: UC8 e «PR 7».
- ADR-074 (conferme), ADR-075 (modifiche tracciate), ADR-028 (allowlist).
