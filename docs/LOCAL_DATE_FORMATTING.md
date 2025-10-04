# Formattazione Date in Formato Italiano

## Panoramica

Il sistema formatta tutte le date in formato italiano (`dd/mm/yyyy`) direttamente lato server usando Python, garantendo consistenza totale indipendentemente dal browser.

## Come Funziona

### 1. Formattazione Lato Server (Python)

I filtri Jinja formattano le date direttamente in Python usando `strftime()`:
- Formato consistente garantito lato server
- Nessuna dipendenza da JavaScript o locale del browser
- Prestazioni migliori (nessun parsing client-side)

### 2. Filtri Jinja Disponibili

Sono stati creati tre filtri Jinja per la formattazione:

#### `date_local` - Solo Data
```jinja
{{ gara.date|date_local }}
<!-- Output: 04/10/2025 -->
```

#### `datetime_local` - Data e Ora
```jinja
{{ gara.inscription_end|datetime_local }}
<!-- Output: 04/10/2025, 18:30 -->
```

#### `time_local` - Solo Ora
```jinja
{{ gara.time|time_local }}
<!-- Output: 18:30 -->
```

## Migrazione dai Template Esistenti

### Prima (formato strftime manuale)
```jinja
{{ gara.date.strftime('%d/%m/%Y') }}
{{ inscription.created_at.strftime('%d/%m/%Y %H:%M') }}
{{ gara.time.strftime('%H:%M') }}
```

### Dopo (filtri standardizzati)
```jinja
{{ gara.date|date_local }}
{{ inscription.created_at|datetime_local }}
{{ gara.time|time_local }}
```

## Esempi di Utilizzo

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

### Esempio 3: Notifiche
```jinja
<!-- PRIMA -->
{{ notification.created_at.strftime('%d/%m/%Y %H:%M') }}

<!-- DOPO -->
{{ notification.created_at|datetime_local }}
```

## Gestione Valori Null

I filtri gestiscono automaticamente valori `None`:
```jinja
{{ gara.date|date_local }}  <!-- Se None, mostra "N/A" -->
```

## File Implementati

### File di Sistema
1. **`utils/jinja.py`**:
   - `format_date_local()` - filtro per solo data (dd/mm/yyyy)
   - `format_datetime_local()` - filtro per data e ora (dd/mm/yyyy, HH:MM)
   - `format_time_local()` - filtro per solo ora (HH:MM)

2. **`utils/status_ui.py`**:
   - Registrazione filtri nell'app Flask

3. **`templates/base.html`**:
   - JavaScript TourneyUtils per date UTC (mantiene compatibilità)

### Template Migrati
- **56 sostituzioni** in **50 file template**
- Nessun formato `strftime()` manuale rimanente

## Script di Migrazione

Per migrare automaticamente i template esistenti:

```bash
# Dry-run (mostra modifiche senza applicarle)
python scripts/migrate_date_formatting.py --dry-run

# Applica migrazioni
python scripts/migrate_date_formatting.py

# Migra singolo file
python scripts/migrate_date_formatting.py --file components/_gara_info.html
```

Il script sostituisce automaticamente:
- `.strftime('%d/%m/%Y')` → `|date_local`
- `.strftime('%d/%m/%Y %H:%M')` → `|datetime_local`
- `.strftime('%H:%M')` → `|time_local`

## Benefici

1. **Consistenza Totale**: Formato italiano uniforme in tutta l'applicazione
2. **Affidabilità**: Nessuna dipendenza da impostazioni browser
3. **Performance**: Formattazione lato server più veloce
4. **Manutenibilità**: Un solo punto di modifica per cambiare formato
5. **Semplicità**: Nessun JavaScript complesso per parsing date

## Implementazione Tecnica

### Formato Output (Python strftime)

```python
# utils/jinja.py
def format_date_local(value):
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y')
    # ...

def format_datetime_local(value):
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y, %H:%M')
    # ...
```

### Formati Supportati
Indipendentemente dal browser, le date vengono sempre mostrate in formato italiano:
- **Data**: `04/10/2025` (dd/mm/yyyy)
- **Data e Ora**: `04/10/2025, 18:30` (dd/mm/yyyy, HH:MM)
- **Ora**: `18:30` (HH:MM)

## Note per Sviluppatori

1. **Usa sempre i filtri** invece di `strftime()` manuale nei template
2. **Formato consistente** garantito automaticamente
3. **Nessun JavaScript** necessario per formattazione base
4. **Date UTC** ancora gestite da JavaScript per compatibilità

## Migrazione Completata

✅ Tutti i template migrati  
✅ Formato italiano consistente  
✅ Zero dipendenze da locale browser  
✅ Script di migrazione disponibile
