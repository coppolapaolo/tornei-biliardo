# [014] Mobile-First Card Layout per Vista Gara

**Data**: 2026-01-14
**Stato**: Accepted
**Decisori**: Paolo, Claude

## Contesto

La vista dettaglio gara (`gara_detail.html`) utilizza tabelle HTML per visualizzare le partite. Su dispositivi mobile, questa scelta causa:

1. **Colonne troncate**: Header come "Risultato" diventano "Risu\nltato"
2. **Testo illeggibile**: Nomi giocatori e punteggi compressi
3. **Azioni inaccessibili**: Bottoni troppo piccoli per il touch
4. **Scroll orizzontale**: Esperienza utente degradata

L'applicazione è usata principalmente da direttori di gara durante tornei, spesso da smartphone. L'operazione più frequente è:
- **Monitorare lo stato** delle partite
- **Inserire risultati** quando le partite terminano

## Decisione

Implementare un **layout a card stack** per dispositivi mobile (< 768px), mantenendo la tabella esistente per desktop.

### Specifiche Tecniche

1. **Breakpoint**: 768px (Bootstrap `md`)
2. **Switch tecnica**: Classi CSS `d-md-none` / `d-none d-md-block`
3. **Template separati**:
   - Mobile: `_match_cards_mobile.html`
   - Desktop: `_gara_matches.html` (esistente)
4. **Zero JavaScript** per lo switch layout

### Struttura Card

```
┌──────────────────────────────────────────┐
│ ● Stato                     [Tavolo N]   │ Header
├──────────────────────────────────────────┤
│    Player1    vs/·    Player2            │ Body
│              Score                       │
├──────────────────────────────────────────┤
│ [Azioni contestuali per stato]           │ Footer
└──────────────────────────────────────────┘
```

### Touch Target

- Bottoni: minimo 44 × 44 px
- Gap tra bottoni: minimo 8 px
- Padding card: 16 px

## Alternative Considerate

### Alternativa 1: Tabella Responsive con Scroll Orizzontale

**Descrizione**: Mantenere la tabella, wrappata in `.table-responsive` (approccio attuale).

- **Pro**:
  - Nessun nuovo codice
  - Layout consistente desktop/mobile
- **Contro**:
  - Scroll orizzontale scomodo su mobile
  - Colonne comunque troppo strette
  - Azioni difficili da toccare

### Alternativa 2: Tabella con Colonne Nascoste

**Descrizione**: Nascondere colonne secondarie (Tavolo, Azioni) su mobile.

- **Pro**:
  - Modifica minimale
  - Un solo template
- **Contro**:
  - Rimuove funzionalità critiche per il direttore
  - Non risolve il problema touch target

### Alternativa 3: Compact List con Swipe Actions

**Descrizione**: Lista compatta con azioni accessibili via swipe gesture.

- **Pro**:
  - Molto compatto
  - Pattern comune in app native
- **Contro**:
  - Azioni nascoste, meno intuitivo
  - Richiede JavaScript per swipe
  - Curva di apprendimento per utenti

## Conseguenze

### Positive

- **Usabilità mobile**: Partite leggibili, azioni accessibili
- **Touch-friendly**: Target 44px rispettano standard iOS/Android
- **Manutenibilità**: Template separati, logica condivisa
- **Performance**: Switch CSS puro, nessun JS per layout
- **Progressivo**: Desktop rimane invariato

### Negative

- **Duplicazione parziale**: Due template per le partite
- **Manutenzione doppia**: Modifiche alla logica azioni vanno replicate
- **Test aggiuntivi**: Verificare entrambi i layout

### Rischi

- **Drift tra template**: Col tempo, desktop e mobile potrebbero divergere
  - Mitigazione: Estrarre logica comune in macro Jinja2
- **Breakpoint non ottimale**: 768px potrebbe non coprire tutti i tablet
  - Mitigazione: Testare su dispositivi reali, eventualmente aggiungere breakpoint intermedio

## Note Implementative

### Switch Template in gara_detail.html

```html
<div class="row">
  <div class="col-md-8">
    <!-- Mobile: Card view -->
    <div class="d-md-none">
      {% include "components/_match_cards_mobile.html" %}
    </div>

    <!-- Desktop: Table view -->
    <div class="d-none d-md-block">
      {% include "components/_gara_matches.html" %}
    </div>
  </div>
</div>
```

### Struttura _match_cards_mobile.html

```html
{% for round_num in active_rounds %}
<h6 class="mt-3 mb-2">{{ _('Turno %(num)s', num=round_num) }}</h6>
{% for match in round_matches %}
  {% include "components/_match_card.html" %}
{% endfor %}
{% endfor %}

{% for round_num in completed_rounds %}
{# ... stesso pattern ... #}
{% endfor %}
```

### CSS Card (inline o in mobile.css)

```css
.match-card {
  border-radius: 8px;
  margin-bottom: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.match-card-header {
  padding: 8px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.match-card-body {
  padding: 16px;
  text-align: center;
}

.match-card-footer {
  padding: 12px 16px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.match-card-footer .btn {
  min-height: 44px;
  flex: 1;
}
```

### Mappa Azioni per Stato

| Stato | Condizione | Azioni |
|-------|------------|--------|
| PENDING | no tavolo | Assegna Tavolo |
| PENDING | con tavolo | Risultato, Dettaglio |
| PLAYING | - | Risultato, Dettaglio, Reset* |
| PLAYING | score finale | Risultato, Valida, Dettaglio, Reset |
| COMPLETED | - | Reset |
| BYE | - | (nessuna) |
| BLOCCATO | match_can_modify=false | Testo "Bloccato" |

*Reset appare solo se ci sono punteggi inseriti

## Riferimenti

- `docs/plans/2026-01-14-mobile-first-gara-view-design.md` - Design completo
- `templates/components/_match_result_row.html` - Logica azioni esistente
- Apple Human Interface Guidelines: [Touch Targets](https://developer.apple.com/design/human-interface-guidelines/inputs)
- Bootstrap 5 Breakpoints: [Documentation](https://getbootstrap.com/docs/5.3/layout/breakpoints/)
