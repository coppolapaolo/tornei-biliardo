# Design: UI Wizard Sistema Classificazione

**Data**: 2026-01-14
**Stato**: Approvato

---

## Obiettivo

Aggiornare il wizard campionato e il form gara per:
1. Permettere la selezione del sistema di classificazione (RACK/WINS/POSITION)
2. Nascondere automaticamente le opzioni incompatibili
3. Mostrare warning per combinazioni problematiche

---

## Decisioni Prese

| Domanda | Decisione |
|---------|-----------|
| Dove inserire sistema classifica? | Step 1 wizard campionato |
| Relazione sistema ↔ matchmaking? | Sistema prima, filtra matchmaking |
| Gestione dispari Step 2? | Nascondi opzioni incompatibili + nascondi sezione per POSITION |
| Warning combinazioni? | Alert inline sotto il campo |
| Gare standalone? | Stesso approccio del wizard |

---

## Architettura

```
Campionato (Step 1)
    │
    ├─► classification_system (RACK/WINS/POSITION)
    │       │
    │       └─► filtra matchmaking_strategy disponibili
    │
    └─► matchmaking_strategy (filtrato)

Campionato (Step 2)
    │
    └─► default_odd_policy (filtrato in base a classification_system)

Gara (dentro campionato)
    │
    ├─► classification_system = ereditato (readonly)
    └─► odd_number_policy (filtrato)

Gara Standalone
    │
    ├─► classification_system (selezionabile)
    │       │
    │       └─► filtra matchmaking + odd_policy
    └─► altre opzioni (filtrate)
```

---

## File da Modificare

1. `templates/admin/campionato_wizard_step1.html`
2. `templates/admin/campionato_wizard_step2.html`
3. `templates/components/_gara_edit_form.html`
4. `templates/admin/gara_edit.html`
5. `routes/admin/campionato.py`

---

## Dettagli Implementazione

### Step 1: Sistema Classifica + Matchmaking

**Posizione:** Dopo "Nome Campionato", prima di "Tipo Campionato".

**Select Sistema Classifica:**
```html
<select id="classification_system" name="classification_system">
    <option value="WINS">Vittorie (match vinti → diff rack)</option>
    <option value="RACK">Rack Totali (rack accumulati)</option>
    <option value="POSITION">Posizione Bracket (eliminazione)</option>
</select>
```

**Descrizioni dinamiche:** Alert info che cambia in base alla selezione.

**Filtro Matchmaking:**
| Sistema | Matchmaking Disponibili |
|---------|------------------------|
| WINS | Amalfi, Random |
| RACK | Amalfi, Random |
| POSITION | Eliminazione, Doppio KO |

**Default:** WINS (più comune).

### Step 2: Gestione Dispari Filtrata

**Filtro odd_policy:**
| Sistema | Opzioni Disponibili |
|---------|---------------------|
| RACK | NO, Trio, Bye+Challenge, Bye+N rack |
| WINS | NO, Trio, Bye, Bye+Challenge |
| POSITION | Sezione nascosta |

**Per POSITION:** La sezione "Gestione Numero Dispari" non appare (il bracket gestisce internamente).

### Form Gara

**Gara in campionato:**
- Campo `classification_system` readonly (mostra valore ereditato)
- Opzioni filtrate automaticamente

**Gara standalone:**
- Campo `classification_system` selezionabile
- Stesso comportamento di filtro del wizard

### Warning Inline

**RACK + Race to N:**
```html
<div class="alert alert-warning">
    ⚠️ Con sistema RACK, "Race to N" può distorcere la classifica:
    chi perde di misura accumula più rack. Considera "Exactly N".
</div>
```

Il warning appare dinamicamente quando:
- `classification_system == RACK`
- `is_race_to == true` (o equivalente)

---

## Matrice Compatibilità (per JavaScript)

```javascript
const CLASSIFICATION_CONSTRAINTS = {
    RACK: {
        matchmaking: ['amalfi', 'random'],
        odd_policies: ['no', 'trio', 'bye_with_challenge'],
        multi_set: false,
        distance_warning: 'race_to'  // warning se race_to
    },
    WINS: {
        matchmaking: ['amalfi', 'random'],
        odd_policies: ['no', 'trio', 'bye', 'bye_with_challenge'],
        multi_set: true,
        distance_warning: null
    },
    POSITION: {
        matchmaking: ['elimination', 'double_ko'],
        odd_policies: [],  // nasconde sezione
        multi_set: true,
        forfeit_policy: 'forfeit'  // solo FORFEIT
    }
};
```

---

## Mobile-Friendly (CRITICO)

L'UI DEVE essere ottimizzata per mobile:

1. **Select full-width:** Tutti i select devono essere `w-100` su mobile
2. **Descrizioni collassabili:** Le descrizioni lunghe devono essere nascoste di default su mobile, visibili con tap
3. **Warning compatti:** Gli alert warning devono usare testo breve su mobile
4. **Touch target:** Minimo 44x44px per elementi interattivi
5. **Font leggibile:** Minimo 16px per input (evita zoom iOS)
6. **Stack verticale:** Su mobile, i campi in row devono diventare stack verticale (già gestito da Bootstrap col-md-*)

**Classi Bootstrap da usare:**
- `form-select form-select-lg` per select principali
- `d-none d-md-block` per contenuti opzionali su desktop
- `small` per descrizioni secondarie
- `py-2` per padding touch-friendly

---

## Note Implementazione

1. **Round Robin:** Non presente nel wizard attuale, non aggiungerlo ora
2. **Bye+N rack:** Non presente nel form attuale, da aggiungere
3. **Eliminazione/Doppio KO:** Non implementati nel backend, mostrare come "Coming soon" disabilitati
4. **Passaggio dati Step 1 → Step 2:** Via session (già funziona così)

---

## Riferimenti

- `docs/CLASSIFICATION_SYSTEM.md` - Regole complete
- `models/competition/validators.py` - Validazione backend
- `docs/adr/ADR-013-classification-system-redesign.md` - ADR
