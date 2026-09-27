# [074] Le conferme seguono cosa fa l'azione, non l'epoca in cui è stata scritta

**Data**: 2026-09-27
**Stato**: Accepted
**Decisori**: Paolo Coppola, Claude

## Contesto

Il 27 settembre 2026, in produzione, il direttore premeva «Accetta» per conto
dell'ultimo invitato ai playoff del campionato 5 e non succedeva niente.
L'error.log era pulito, in console non c'erano errori e il form era corretto.
Dopo sei conferme sulla stessa pagina il browser aveva offerto «impedisci a
questa pagina di creare altre finestre di dialogo»: da lì `confirm()`
restituisce `false` senza mostrare niente, e il form non parte. Con una scheda
nuova ha funzionato.

Facendo l'inventario è venuto fuori che l'app chiedeva conferma in **quattro
modi diversi**, e che a decidere quale fosse era il momento in cui era stata
scritta la pagina, non cosa facesse l'azione:

| Forma | Quante | Da quando |
|---|---|---|
| `confirm()` del browser | 17 | ricomparsi dopo gennaio |
| `showConfirm` / `confirmSubmit`: modale Bootstrap, pulsante rosso «Conferma» | ~80 | gennaio 2026 |
| Foglio 7c dedicato, che spiega le conseguenze | 20 | redesign 7c, da agosto |
| «Tre secondi con Annulla», senza domanda | card della gara, rack, colpi | #557 e affini |

Il dato più istruttivo è che la regola esisteva già: l'**11 gennaio 2026** tutte
le 67 chiamate a `confirm()` erano state migrate a `showConfirm`
(`UI_CONVENTIONS.md`, registro delle decisioni). Nessun test la presidiava, e
in otto mesi ne sono ricomparse diciassette, tutte in codice scritto dopo.
Tre di queste non funzionavano nemmeno: avevano `|tojson` dentro un attributo
fra doppi apici, il JSON chiudeva l'attributo, e la conferma non compariva
**mai** («Chiudi il corso», «Non seguirla più», «Archivia»).

## Decisione

La forma della conferma la decide **l'azione**, con due domande: *si disfa
dalla stessa pagina?* e *tocca qualcun altro?*

1. **Azione frequente, dentro un flusso, reversibile** (segnare, validare o
   chiudere una partita dalla card, un colpo, un rack) → **nessuna domanda**:
   si esegue dopo **tre secondi con Annulla** (`CardPartita.attendi`).
   Chiedere «sei sicuro?» cento volte a sera abitua a premere OK senza leggere,
   e allora la domanda non protegge più niente.
2. **Azione con conseguenze per altri, o difficile da disfare** (un rifiuto
   che fa partire la cascata degli inviti, eliminare, ritirare, chiudere un
   corso, correggere un risultato cancellando i triangoli) → **foglio**. Il
   foglio dice cosa succederà, e il pulsante porta **il nome dell'azione**
   («Registra il rifiuto», «Chiudi il corso»), mai un generico «Conferma».
   Per una domanda sola si usa il foglio condiviso (`confirmSubmit`, sopra
   `showConfirm`); un foglio dedicato serve solo quando c'è altro da chiedere,
   come campi o scelte.
3. **Mai il `confirm()` del browser.** L'unico ammesso è il ripiego dentro
   `showConfirm`, per una pagina senza il modale di `base.html`.

Le due regole di presidio che mancavano:

* `tests/new/unit/test_nessun_confirm_del_browser.py`: nessun `confirm(` o
  `window.confirm(` in template e JS, commenti esclusi;
* `tests/new/unit/test_tojson_negli_attributi_evento.py`: nessun `|tojson`
  dentro un attributo `on…` fra doppi apici. La regola era già in
  `templates/CLAUDE.md`, ma senza test.

## Alternative Considerate

### Alternativa 1: tutto foglio

- Pro: una forma sola, la più facile da spiegare.
- Contro: durante la gara il direttore valida decine di partite. Una domanda
  a ogni tocco rallenta proprio dove il tempo conta, e insegna a confermare
  senza leggere, quindi le conferme importanti perdono valore. La #557 aveva
  già scelto l'Annulla per questo motivo.

### Alternativa 2: solo il presidio, la regola dopo

- Pro: ripara subito il guasto con il minimo di modifiche.
- Contro: toglie `confirm()` ma lascia le altre tre forme, scelte a caso.
  Chi scrive la prossima pagina continuerebbe a non sapere quale usare.

### Alternativa 3: lasciare `confirm()` e spiegare agli utenti come riattivare i dialoghi

- Contro: il guasto è silenzioso, perché chi lo subisce vede un pulsante che non
  fa nulla e non ha modo di capire perché. Non si risolve con una nota.

## Conseguenze

### Positive

- Un pulsante non può più «non fare nulla» perché il browser ha zittito i
  dialoghi.
- La conferma dice cosa succede e il pulsante dice cosa fa: «Registra il
  rifiuto» si legge, «Conferma» no.
- Chi scrive una pagina nuova ha una regola, non un precedente da copiare.

### Negative

- Il foglio condiviso di `base.html` è ancora il modale Bootstrap di gennaio:
  si rifà in stile 7c in una PR a parte, con un sottotitolo sulle conseguenze.
- Circa 80 chiamate a `showConfirm` vanno ripassate una per una: alcune
  passano all'Annulla, altre devono prendere il nome dell'azione.

### Rischi

- `confirmSubmit` invia con `form.submit()`, che non trasmette `name`/`value`
  del pulsante premuto né rispetta un suo `formaction`. Un form che distingue
  due pulsanti con `name` va convertito a un foglio dedicato, non a
  `confirmSubmit`. Nessuno dei 17 punti convertiti ne dipendeva.
- Su un pulsante `type="submit"`, `onclick` scatta **prima** della
  validazione HTML5, e `form.submit()` la salta. Nei form con campi veri la
  conferma va quindi in `onsubmit`, che scatta dopo la validazione.

## Note Implementative

```html
{# Pulsante di un form con soli campi nascosti #}
<button type="submit"
        onclick='return confirmSubmit(this.form, {{ _("Registrare il rifiuto? L'invito passa al primo degli esclusi.")|tojson }},
                                      {confirmText: {{ _("Registra il rifiuto")|tojson }}, confirmClass: "btn-danger"})'>

{# Form con campi da validare #}
<form method="POST" onsubmit='return confirmSubmit(this, {{ msg|tojson }}, {confirmText: {{ _("Chiudi il corso")|tojson }}})'>
```

Gli attributi vanno fra **apici singoli** (`templates/CLAUDE.md`). Titolo e
testo predefiniti del foglio arrivano già tradotti da `base.html`
(`data-default-title`, `data-default-confirm`): prima erano il letterale
`'Conferma'` scritto nel JS, italiano anche per chi usa l'app in inglese.
