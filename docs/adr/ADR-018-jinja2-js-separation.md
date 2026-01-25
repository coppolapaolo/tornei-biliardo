# [ADR-018] Separazione Jinja2 e JavaScript via JSON Configuration

**Data**: 2026-01-25
**Stato**: Accepted
**Decisori**: Antigravity, User

## Contesto

In molte templates Jinja2 (es. `gara_detail.html`), il codice JavaScript conteneva espressioni Jinja2 inline (es. `{{ _("messaggio") | tojson }}` o `{{ gara.id }}`). 
Questa pratica presentava diversi svantaggi:
1. **Errori del Formatter**: Gli editor e i formatter (come Prettier) non riconoscono la sintassi Jinja2 all'interno di file `.html` (che trattano come HTML/JS), portando a indentazioni errate o errori di parsing.
2. **Readability**: Il codice JavaScript risulta difficile da leggere a causa del mix di linguaggi.
3. **Falsi Positivi Syntax Error**: Gli IDE segnalano spesso errori di sintassi JS laddove compaiono tag Jinja2.
4. **Interpolazione Babel**: Flask-Babel richiede che le stringhe con placeholder (es. `%(pos)s`) siano interpolate correttamente nel comando `_()`, altrimenti solleva `KeyError`. Gestire questo mix in JS è prono a errori.

## Decisione

Abbiamo deciso di adottare un pattern di **separazione netta** tra Jinja2 e JavaScript:

1. **JSON Configuration Block**: Tutte le variabili e le traduzioni necessarie al JavaScript devono essere raccolte in un blocco `<script type="application/json" id="gara-config">` (o simile, con ID specifico per la risorsa).
2. **GARA_CONFIG Constant**: All'inizio della sezione JavaScript, i dati vengono letti e memorizzati in una costante globale (es. `const GARA_CONFIG = JSON.parse(document.getElementById('gara-config').textContent);`).
3. **JS-Only Logic**: Le funzioni JavaScript devono fare riferimento esclusivamente a questa costante, evitando qualsiasi espressione `{{ ... }}` nel corpo del codice JS.
4. **Babel Interpolation**: Se una stringa tradotta richiede variabili Jinja2, l'interpolazione deve avvenire **dentro** il comando `_()` di Jinja2 nel blocco JSON, non in JavaScript (a meno di placeholder dinamici gestiti interamente via JS).

## Alternative Considerate

### Alternativa 1: Continuare con Jinja2 inline
- **Pro**: Più veloce da implementare per piccole modifiche.
- **Contro**: Mantiene i problemi di formattazione e leggibilità.

### Alternativa 2: Attributi Data-* su elementi HTML
- **Pro**: Standard HTML.
- **Contro**: Inefficiente per grandi set di dati o traduzioni complesse; sparge la configurazione nel DOM invece di centralizzarla.

## Conseguenze

### Positive
- **Formatter Friendly**: JavaScript è ora puro JS valido, permettendo l'uso di formatter automatici senza errori.
- **Centralizzazione**: Tutte le configurazioni e le traduzioni sono visibili in un unico punto nel template.
- **Leggibilità**: Le funzioni JS sono più pulite e focalizzate sulla logica.
- **Sicurezza**: L'uso di `| tojson` nel blocco JSON previene vulnerabilità XSS.

### Negative
- **Verbosity**: Richiede un po' di boilerplate iniziale per definire l'intero oggetto JSON.
- **Memory**: I dati sono presenti due volte nel DOM (una nel JSON, una (indirettamente) nell'oggetto JS). Trascurabile per le dimensioni attuali.

## Note Implementative

### Esempio di implementazione

```html
<!-- Blocco di Configurazione -->
<script type="application/json" id="gara-config">
  {
    "gara": {
      "id": {{ gara.id }},
      "discipline": {{ gara.discipline | tojson }}
    },
    "i18n": {
      "confirmMessage": {{ _("Sei sicuro di voler avviare la gara %(num)s?", num=gara.number) | tojson }}
    }
  }
</script>

<script>
  // Lettura configurazione
  const GARA_CONFIG = JSON.parse(document.getElementById('gara-config').textContent);

  function startGara() {
    // Uso della configurazione in JS puro
    showConfirm(GARA_CONFIG.i18n.confirmMessage, () => {
       fetch(`/api/start/${GARA_CONFIG.gara.id}`);
    });
  }
</script>
```

## Riferimenti

- [gara_detail.html](file:///Users/paolo/My%20Drive/Programming/Python/tornei-biliardo/templates/gara_detail.html)
- [ADR-014-mobile-first-card-layout.md](ADR-014-mobile-first-card-layout.md) (per contesto su pattern UI)
