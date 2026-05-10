---
name: ui-conventions
description: Documenta decisioni UI (icone, colori, bottoni, layout, componenti) nel design system. Attiva quando si sceglie un elemento visivo, si discute di coerenza UI, o si modifica l'aspetto dell'interfaccia.
allowed-tools: Read, Edit, Glob, Grep
---

# UI Conventions - Documentazione Design System

Questa skill garantisce che ogni decisione UI venga documentata per mantenere coerenza nel design system del progetto.

## Trigger di Attivazione

Attiva questa skill quando nella conversazione:
- Si sceglie una nuova icona Font Awesome
- Si decide un colore Bootstrap per stati/elementi
- Si definisce un pattern di layout o spacing
- Si standardizza un componente (card, button, badge, alert)
- Si discute di "quale icona/colore usare per..."
- Si modifica l'aspetto visivo dell'interfaccia
- Si parla di coerenza UI o design system

## File di Riferimento

| File | Contenuto |
|------|-----------|
| `docs/reference/UI_CONVENTIONS.md` | Convenzioni complete del design system |
| `templates/base.html` | Template base con struttura comune |
| `static/css/` | Stili custom se presenti |

## Processo

### 1. Prima di Proporre una Scelta

```
Leggo docs/reference/UI_CONVENTIONS.md per verificare:
- Esiste già una convenzione per questo concetto?
- L'elemento proposto è già usato per altro?
- Quale sezione è rilevante? (Icone, Colori, Bottoni, Badge, etc.)
```

### 2. Durante la Decisione

Quando si converge su una scelta:

1. **Verifica coerenza** con convenzioni esistenti
2. **Segnala conflitti** se l'elemento è già usato diversamente
3. **Proponi l'aggiornamento** della documentazione
4. **Suggerisci refactoring** se serve allineare codice esistente

### 3. Aggiornamento Documentazione

Aggiorna `docs/reference/UI_CONVENTIONS.md` nella sezione appropriata:

**Per Icone** (sezione Icon Conventions):
```markdown
| **Concetto** | emoji | `fa-classe` | Note/Motivazione |
```

**Per Colori/Stati** (sezione Colori e Stati):
```markdown
| Stato | `bg-classe` | `alert-classe` | Descrizione |
```

**Per Bottoni** (sezione Bottoni):
```markdown
| Tipo | `btn-classe` | Uso nel progetto |
```

**Sempre** aggiungi al Changelog:
```markdown
| YYYY-MM-DD | Elemento per concetto | Motivazione della scelta |
```

### 4. Verifica Applicazione

Dopo la documentazione:
```bash
# Cerca usi inconsistenti nel codebase
grep -rn "fa-vecchia-icona" templates/
grep -rn "classe-vecchia" templates/
```

Proponi modifiche per allineare il codice esistente.

## Esempi di Interazione

### Esempio 1: Nuova Icona

**Utente**: "Quale icona usiamo per le sale biliardo?"

**Risposta attesa**:
1. Leggo UI_CONVENTIONS.md → `fa-building` già usato per "Sale Biliardo"
2. Confermo: "È già documentato: `fa-building` per le sale biliardo"
3. Se non esistesse → propongo opzioni, documento la scelta

### Esempio 2: Cambio Colore Badge

**Utente**: "Il badge 'pending' dovrebbe essere arancione invece che giallo"

**Risposta attesa**:
1. Verifico convenzione attuale → `bg-warning` (giallo Bootstrap)
2. Spiego: Bootstrap non ha arancione nativo, opzioni:
   - Usare `bg-warning` (giallo standard)
   - Creare classe custom `bg-orange`
3. Se si decide, aggiorno documentazione + changelog

### Esempio 3: Nuovo Pattern Layout

**Utente**: "Per le pagine di dettaglio usiamo sempre sidebar a destra"

**Risposta attesa**:
1. Documento in sezione Layout:
   ```markdown
   ### Pattern Pagine Dettaglio
   - Contenuto principale: `col-md-8`
   - Sidebar: `col-md-4`
   ```
2. Aggiungo al changelog con motivazione

## Regole Importanti

1. **Non assumere** - Verifica sempre le convenzioni esistenti prima di proporre
2. **Documenta subito** - Non aspettare che l'utente chieda
3. **Motivazioni chiare** - Il changelog deve spiegare il "perché"
4. **Coerenza prima** - Preferisci convenzioni esistenti a nuove
5. **Refactoring incluso** - Se cambia una convenzione, proponi di allineare il codice

## Struttura UI_CONVENTIONS.md

Il file è organizzato in sezioni:
1. Icone (Font Awesome)
2. Colori e Stati
3. Bottoni
4. Badge
5. Alert e Messaggi
6. Card Structure
7. Layout e Spacing
8. Typography
9. Form Conventions
10. Responsive Breakpoints
11. Changelog Decisioni
