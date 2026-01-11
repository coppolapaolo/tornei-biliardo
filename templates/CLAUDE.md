# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Templates Directory - Jinja2 Templates

Flask/Jinja2 templates for the American Pool community platform using Bootstrap 5.

---

## Critical Conventions

### Translated Strings in JavaScript (CRITICAL)

When embedding translated strings in JavaScript, **ALWAYS use `|tojson`** filter. This prevents syntax errors from apostrophes in Italian text.

```javascript
// ❌ WRONG - Apostrophe in "l'avvio" breaks JS string
alert('{{ _("Errore durante l'avvio del turno") }}');
// Generates: alert('Errore durante l'avvio del turno');  // SYNTAX ERROR!

// ✅ CORRECT - |tojson escapes and adds proper quotes
alert({{ _("Errore durante l'avvio del turno")|tojson }});
// Generates: alert("Errore durante l'avvio del turno");  // Works!

// For concatenation with variables:
alert({{ _("Errore:")|tojson }} + ' ' + errorMessage);
```

**Why this matters**: Italian text often contains apostrophes (`l'avvio`, `l'errore`, `l'iscrizione`). Without `|tojson`, these break JavaScript and cause silent failures.

### Onclick Attributes with Dynamic Strings (CRITICAL)

When using `|tojson` in HTML onclick attributes, **use single quotes for the attribute**:

```html
{# ❌ WRONG - tojson produces "..." which breaks double-quoted attribute #}
<span onclick="myFunc({{ player_name|tojson }})">

{# Renders as: onclick="myFunc("John")" - BROKEN HTML! #}

{# ✅ CORRECT - single quotes for attribute, tojson produces double quotes inside #}
<span onclick='myFunc({{ player_name|tojson }})'>

{# Renders as: onclick='myFunc("John")' - Valid HTML #}
```

**Why**: `|tojson` always produces JSON strings with double quotes. Using single quotes for the onclick attribute avoids quote conflicts.

### Python-style Placeholders in JS Strings (CRITICAL)

**NEVER use `%(name)s` placeholders** in translated strings that JavaScript will interpolate. Flask-Babel tries to substitute them at render time → `KeyError`.

```javascript
// ❌ WRONG - Flask-Babel tries to substitute %(count)s → KeyError
const i18n = {
    confirmDelete: {{ _("Elimina %(count)s elementi?")|tojson }}
};
const msg = i18n.confirmDelete.replace('%(count)s', count);

// ✅ CORRECT - Use JS-style placeholder, not translated
const i18n = {
    confirmDeleteTemplate: "Elimina {count} elementi?"
};
const msg = i18n.confirmDeleteTemplate.replace('{count}', count);

// ✅ ALTERNATIVE - Pass value at render time (if known)
const msg = {{ _("Elimina %(count)s elementi?", count=items|length)|tojson }};
```

**Rule**: If JavaScript does the interpolation, don't use `%(...)s` in `_()`.

### No Python Imports in Templates

You cannot import Python modules in Jinja2 templates:

```jinja2
{# ❌ WRONG - This will cause TemplateNotFound error #}
{% from "models/classification" import RoundClassification %}

{# ✅ CORRECT - Data must be passed from route/view #}
{% for rc in gara.round_classifications %}
```

### Format Characters in i18n Strings

Avoid `%` in translated strings as it's interpreted as a Python format specifier:

```jinja2
{# ❌ WRONG - % causes ValueError #}
{{ _("% Vittorie") }}

{# ✅ CORRECT - Use alternative text #}
{{ _("Win Rate") }}
{{ _("Perc. Vinte") }}
```

---

## Template Structure

### Hierarchy
- **`base.html`**: Master layout (navbar, scripts, styles)
- **`admin/`**: Admin and director interfaces
- **`player/`**: Player-facing pages
- **`public/`**: Guest-accessible pages
- **`components/`**: Reusable includes (prefixed with `_`)

### Creating New Pages

```jinja2
{% extends "base.html" %}

{% block title %}Page Title{% endblock %}

{% block content %}
<div class="container">
    {# Include reusable components #}
    {% include "components/_some_component.html" %}
</div>
{% endblock %}
```

### Component Naming
- Reusable components: `_component_name.html` (underscore prefix)
- Full pages: `page_name.html` (no prefix)

---

## Common Patterns

### Status Badge Display

```jinja2
{% if gara.status == 'completed' %}
    <span class="badge bg-success">{{ _("Completata") }}</span>
{% elif gara.status == 'playing' %}
    <span class="badge bg-warning">{{ _("In Corso") }}</span>
{% endif %}
```

### Conditional Content by Role

```jinja2
{% if current_user.is_admin %}
    {# Admin-only content #}
{% elif current_user.is_director %}
    {# Director content #}
{% endif %}
```

### Safe Relationship Access

```jinja2
{# Check relationship exists before accessing #}
{% if gara.campionato %}
    {{ gara.campionato.name }}
{% else %}
    {{ gara.name or 'Gara Singola' }}
{% endif %}
```

### Date/Time Display

```jinja2
{# Use custom filters for localized display #}
{{ gara.date|date_local }}
{{ match.created_at|datetime_local }}
```

### Pagination Include

```jinja2
{% set pagination = some_pagination_object %}
{% include "components/_pagination.html" %}
```

---

## JavaScript in Templates

### AJAX with Flask Routes

```javascript
fetch('{{ url_for("some.route", id=item.id) }}', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': '{{ csrf_token() }}'
    },
    body: JSON.stringify(data)
});
```

### Passing Python Data to JS

```javascript
// For simple values
const garaId = {{ gara.id }};

// For strings (use tojson!)
const message = {{ _("Some message")|tojson }};

// For objects/arrays
const config = {{ some_dict|tojson }};
```

---

## i18n Guidelines

- Wrap all user-visible strings: `{{ _("Text") }}`
- Use named placeholders: `{{ _("Hello %(name)s", name=user.username) }}`
- Run `pybabel extract/update/compile` after adding strings
- Italian is the primary language; English is fallback
