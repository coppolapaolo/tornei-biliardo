# Internazionalizzazione (i18n)

**Versione**: 1.0  
**Data**: 2025-12-23

## Architettura

La piattaforma utilizza **Flask-Babel** per l'internazionalizzazione.

### Stack Tecnologico
- **Flask-Babel**: Gestione traduzioni e locale
- **Jinja2**: Funzione `_()` nelle templates
- **pybabel CLI**: Estrazione e compilazione cataloghi

---

## Convenzioni

### Templates Jinja2

```jinja2
{# Testo statico #}
<h1>{{ _("Benvenuto") }}</h1>

{# Con interpolazione #}
<p>{{ _("Ciao, %(name)s!") % {'name': user.name} }}</p>
```

### JavaScript

Per stringhe in JavaScript nelle templates, usare la sintassi semplice:

```javascript
// ✅ Corretto
if (confirm('{{ _("Sei sicuro?") }}')) {
    // ...
}

// ✅ Per stringhe con caratteri speciali
alert({{ _("Messaggio") | tojson }});
```

> [!NOTE]
> Alcuni IDE segnalano errori sui blocchi `{% if %}` in JavaScript. Sono **falsi positivi**: Jinja2 viene processato server-side prima che JavaScript venga eseguito.

### Python/Flask

```python
from flask_babel import gettext as _

flash(_("Operazione completata"))
```

---

## Struttura File

```
translations/
├── en/
│   └── LC_MESSAGES/
│       ├── messages.po  # Traduzioni inglesi
│       └── messages.mo  # Compilato
├── it/
│   └── LC_MESSAGES/
│       ├── messages.po  # Traduzioni italiane
│       └── messages.mo  # Compilato
babel.cfg                  # Configurazione estrazione
messages.pot               # Template (generato)
```

---

## Workflow Traduzioni

1. **Sviluppo**: Usare `_()` per tutte le stringhe user-facing
2. **Estrazione**: 
   ```bash
   pybabel extract -F babel.cfg -o messages.pot .
   ```
3. **Aggiornamento**: 
   ```bash
   pybabel update -i messages.pot -d translations
   ```
4. **Traduzione**: Modificare i file `.po` nella cartella della lingua
5. **Compilazione**: 
   ```bash
   pybabel compile -d translations
   ```

---

## Rilevamento Lingua

La lingua viene rilevata automaticamente dall'header `Accept-Language` del browser. La configurazione è in `app.py`:

```python
@babel.localeselector
def get_locale():
    return request.accept_languages.best_match(['it', 'en'])
```

---

## Aggiungere una Nuova Lingua

```bash
# 1. Inizializzare (es. Spagnolo)
pybabel init -i messages.pot -d translations -l es

# 2. Tradurre translations/es/LC_MESSAGES/messages.po

# 3. Compilare
pybabel compile -d translations

# 4. Aggiungere 'es' alla lista in get_locale()
```
