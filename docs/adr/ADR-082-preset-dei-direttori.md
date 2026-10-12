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
- Route: `routes/admin/preset.py`, tutte `{"director"}` in `ENDPOINT_ROLES`.
- Interfaccia: `templates/components/_preset_modulo.html` e
  `static/js/preset_modulo.js`; l'editor delle catene rilegge il campo
  nascosto quando riceve `change`.

## Riferimenti

- Piano: UC8 e «PR 7».
- ADR-074 (conferme), ADR-075 (modifiche tracciate), ADR-028 (allowlist).
