# Design: Mobile-First Gara View

**Data**: 2026-01-14
**Stato**: Approvato

---

## Obiettivo

Riprogettare la vista gara per essere **mobile-first**, con focus su:
1. Leggibilità delle partite su schermi piccoli
2. Azioni touch-friendly per il direttore
3. Prioritizzazione contestuale basata su ruolo e stato

---

## Problema Attuale

La tabella partite su mobile presenta:
- Colonne troncate ("Risu ltato", "Stat o")
- Testo compresso e illeggibile
- Bottoni azioni troppo piccoli
- Scroll orizzontale scomodo

---

## Decisioni Prese

| Domanda | Decisione |
|---------|-----------|
| Layout mobile | Card stack (non tabella) |
| Breakpoint | 768px (Bootstrap `md`) |
| Tecnica switch | Classi CSS `d-md-none` / `d-none d-md-block` |
| Template | Due template separati |
| Classifica mobile | Toggle Compatta/Completa |
| Sezioni secondarie | Collassabili (Info Gara, Iscritti) |

---

## Architettura Mobile

### Ordine Elementi

```
1. Header (titolo, data, disciplina)
2. Management (stato, progress, azioni gara)
3. Partite (card stack) ← FOCUS PRINCIPALE
4. Classifica (toggle Compatta/Completa)
5. Info Gara [+] (collassato)
6. Iscritti [+] (collassato)
```

### Breakpoint Strategy

```html
<!-- Mobile: Card view -->
<div class="d-md-none">
  {% include "components/_match_cards_mobile.html" %}
</div>

<!-- Desktop: Table view -->
<div class="d-none d-md-block">
  {% include "components/_gara_matches.html" %}
</div>
```

---

## Anatomia Card Match

```
┌──────────────────────────────────────────┐
│ ● Stato                     [Tavolo N]   │ Header
├──────────────────────────────────────────┤
│    Player1    vs/·    Player2 (·P3)      │ Body
│              Score                       │
├──────────────────────────────────────────┤
│ [Azione primaria]    [Azioni secondarie] │ Footer
└──────────────────────────────────────────┘
```

### Colori Stato

| Stato | Colore | Icona |
|-------|--------|-------|
| In Attesa | `bg-warning` (giallo) | ○ cerchio vuoto |
| In Corso | `bg-primary` (blu) | ● cerchio pieno |
| Completata | `bg-success` (verde) | ✓ check |
| Bye | `bg-info` | - |

---

## Azioni per Stato (Director)

| Stato | Footer Card |
|-------|-------------|
| PENDING senza tavolo | `[➕ Assegna Tavolo]` |
| PENDING con tavolo | `[⚡ Risultato]` `[✏️ Dettaglio]` |
| PLAYING | `[⚡ Risultato]` `[✏️ Dettaglio]` `[↩️ Reset?]` |
| PLAYING + score finale | `[⚡ Risultato]` `[✓ Valida]` `[✏️ Dettaglio]` `[↩️ Reset]` |
| COMPLETED | `[↩️ Reset]` |
| BYE | (nessuna azione) |
| BLOCCATO | `🔒 Bloccato` |

### Layout Bottoni (caso 4 azioni)

```
┌──────────────────────────────────────────┐
│ [⚡ Risultato]              [✓ Valida]   │ Azioni frequenti
│ [✏️ Dettaglio]              [↩️ Reset]   │ Azioni rare
└──────────────────────────────────────────┘
```

---

## Viste per Ruolo

| Ruolo | Propria Partita | Altre Partite |
|-------|-----------------|---------------|
| **Director** | Tutte le azioni | Tutte le azioni |
| **Player** | `[👁 Vai alla Partita]` | Nessuna azione |
| **Guest** | N/A | Nessuna azione |

---

## Classifica Mobile

### Vista Compatta (default)

```
┌─────────────────────────────────────────┐
│ 🏆 Classifica        [Compatta ▼]       │
├─────────────────────────────────────────┤
│  1° 🥇 SAMUEL         4 rack            │
│  2° 🥈 PAOLO          3 rack            │
│  3° 🥉 picchio        2 rack            │
│  4°    PIETRO         1 rack            │
│                            [Espandi ↓]  │
└─────────────────────────────────────────┘
```

### Vista Completa

```
┌─────────────────────────────────────────┐
│ 🏆 Classifica        [Completa ▼]       │
├─────────────────────────────────────────┤
│  1° 🥇 SAMUEL                           │
│     4 rack · Pos.Prec: — · SSR: —       │
│  2° 🥈 PAOLO                            │
│     3 rack · Pos.Prec: — · SSR: —       │
└─────────────────────────────────────────┘
```

---

## Touch Target e Accessibilità

| Elemento | Dimensione Minima |
|----------|-------------------|
| Bottoni azione | 44 × 44 px |
| Badge cliccabili | 44 × 32 px |
| Righe classifica | 44 px altezza |
| Gap tra bottoni | 8 px minimo |
| Padding card | 16 px |
| Gap tra card | 12 px |

---

## Casi Speciali

### Match Trio

```
┌─────────────────────────────────────────┐
│ ● In Corso           👥 Trio [Tavolo 7] │
├─────────────────────────────────────────┤
│   MAX P    ·    EMILIO    ·    EGLE     │
│     2            1             0        │
├─────────────────────────────────────────┤
│ [⚡ Risultato]              [✏️ Dettaglio]│
└─────────────────────────────────────────┘
```

### Giocatore Forfait

```
┌─────────────────────────────────────────┐
│   EMILIO          vs    ̶M̶A̶X̶ ̶P̶ 🚫       │
└─────────────────────────────────────────┘
```
Nome barrato + icona ban per forfait.

---

## File da Creare/Modificare

### Nuovi File
- `templates/components/_match_cards_mobile.html` - Card stack mobile
- `templates/components/_match_card.html` - Singola card match
- `templates/components/_classification_mobile.html` - Classifica responsive

### File da Modificare
- `templates/gara_detail.html` - Switch desktop/mobile
- `templates/components/_gara_matches.html` - Wrap con `d-none d-md-block`
- `static/css/mobile.css` - Stili card (opzionale, può essere inline)

---

## Riferimenti

- `docs/adr/ADR-014-mobile-first-card-layout.md` - ADR correlato
- `templates/components/_match_result_row.html` - Logica azioni esistente
- Apple HIG: Touch target 44px minimum
