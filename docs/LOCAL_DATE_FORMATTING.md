# Formattazione Date Locali nel Browser

## Panoramica

Il sistema ora supporta la formattazione automatica delle date in formato italiano (`dd/mm/yyyy`) indipendentemente dalle impostazioni del browser, eliminando le inconsistenze tra formati.

## Come Funziona

### 1. JavaScript Automatico (base.html)

Il file `templates/base.html` contiene funzioni JavaScript che:
- Formattano tutte le date in formato italiano `it-IT`
- Usano `toLocaleString('it-IT')` per garantire formato dd/mm/yyyy
- Si attivano automaticamente al caricamento della pagina

### 2. Filtri Jinja Disponibili

Sono stati creati tre nuovi filtri Jinja per facilitare la formattazione:

#### `date_local` - Solo Data
```jinja
{{ gara.date|date_local }}
<!-- Output: 04/10/2025 (sempre formato italiano) -->
```

#### `datetime_local` - Data e Ora
```jinja
{{ gara.inscription_end|datetime_local }}
<!-- Output: 04/10/2025, 18:30 (sempre formato italiano) -->
```

#### `time_local` - Solo Ora
```jinja
{{ gara.time|time_local }}
<!-- Output: 18:30 -->
```

## Migrazione dai Template Esistenti

### Prima (formato fisso)
```jinja
{{ gara.date.strftime('%d/%m/%Y') }}
{{ inscription.created_at.strftime('%d/%m/%Y %H:%M') }}
{{ gara.time.strftime('%H:%M') }}
```

### Dopo (formato locale)
```jinja
{{ gara.date|date_local }}
{{ inscription.created_at|datetime_local }}
{{ gara.time|time_local }}
```

## Esempi di Migrazione

### Esempio 1: Card Gara
```jinja
<!-- PRIMA -->
<li><i class="fas fa-calendar"></i> {{ gara.date.strftime('%d/%m/%Y') }}</li>

<!-- DOPO -->
<li><i class="fas fa-calendar"></i> {{ gara.date|date_local }}</li>
```

### Esempio 2: Scadenza Iscrizioni
```jinja
<!-- PRIMA -->
Scade: {{ p.inscription_end.strftime('%d/%m/%Y %H:%M') if p.inscription_end else 'N/D' }}

<!-- DOPO -->
Scade: {{ p.inscription_end|datetime_local }}
```

### Esempio 3: Orario Gara
```jinja
<!-- PRIMA -->
{% if gara.time %} {{ gara.time.strftime('%H:%M') }}{% endif %}

<!-- DOPO -->
{% if gara.time %} {{ gara.time|time_local }}{% endif %}
```

## Pattern Speciali

### Date con Attributi data-*
Per casi in cui serve mantenere il valore originale in un attributo:

```jinja
<span data-date="{{ gara.date.isoformat() }}">{{ gara.date|date_local }}</span>
```

Il JavaScript in `base.html` formatta automaticamente elementi con:
- `data-date` → formato solo data
- `data-datetime` → formato data e ora

### Gestione Valori Null
I filtri gestiscono automaticamente valori `None`:
```jinja
{{ gara.date|date_local }}  <!-- Se None, mostra "N/A" -->
```

## File Modificati

### File di Sistema
1. **`templates/base.html`**:
   - Funzioni JavaScript `TourneyUtils.formatDate()`, `formatDateOnly()`, `formatDateTime()`
   - Auto-formattazione elementi con `data-date` e `data-datetime`
   - Locale forzato a `'it-IT'` per consistenza

2. **`utils/jinja.py`**:
   - `format_date_local()` - filtro per solo data
   - `format_datetime_local()` - filtro per data e ora
   - `format_time_local()` - filtro per solo ora

3. **`utils/status_ui.py`**:
   - Registrazione filtri nell'app Flask

### Template Migrati
- **56 sostituzioni** in **50 file template**
- Nessun formato `strftime()` rimanente

## Task Rimanenti

Per completare la migrazione, cercare nei template:

```bash
# Trova tutti gli usi di strftime
grep -r "strftime" templates/
```

Sostituire pattern comuni:
- `.strftime('%d/%m/%Y')` → `|date_local`
- `.strftime('%d/%m/%Y %H:%M')` → `|datetime_local`
- `.strftime('%H:%M')` → `|time_local`

## Benefici

1. **Consistenza**: Formato italiano uniforme in tutta l'applicazione
2. **Semplicità**: Nessuna configurazione utente necessaria
3. **Manutenibilità**: Cambio centralizzato del formato
4. **User Experience**: Formato familiare per utenti italiani

## Note Tecniche

- I filtri accettano oggetti `datetime`, `date` e `time` di Python
- La formattazione usa `toLocaleString('it-IT')` per formato consistente
- **Locale Forzato**: Sempre `'it-IT'` per formato dd/mm/yyyy indipendentemente dal browser
- **Consistenza**: Tutte le date mostrate nello stesso formato italiano
- Compatibile con tutti i browser moderni (Chrome, Firefox, Safari, Edge)
- Fallback su formato ISO se la data non è valida

### Formato Output
Indipendentemente dal browser, le date vengono sempre mostrate in formato italiano:
- **Data**: 04/10/2025 (dd/mm/yyyy)
- **Data e Ora**: 04/10/2025, 18:30
- **Ora**: 18:30
