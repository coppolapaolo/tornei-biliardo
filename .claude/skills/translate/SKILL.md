---
name: translate
description: Esegue il ciclo completo di traduzione i18n (extract → update → auto-translate IT→EN → compile). Attiva dopo ogni feature/bugfix che aggiunge o modifica stringhe _(), o quando l'utente chiede /translate.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
user-invocable: true
---

# Translate — i18n Pipeline

Ciclo completo di traduzione per l'app Flask con Flask-Babel. L'app è Italian-first: le stringhe sorgente nei `_()` sono in italiano. L'unico target di traduzione reale è **English (EN)**.

## Workflow

### 1. Extract

```bash
pybabel extract -F babel.cfg -o messages.pot .
```

### 2. Update catalogs

```bash
pybabel update -i messages.pot -d translations
```

### 3. Find new untranslated EN strings

Dopo l'update, cerca nel file `translations/en/LC_MESSAGES/messages.po` le entry con `msgstr ""` (non tradotte) o marcate `#, fuzzy`.

Per ogni stringa **nuova** (non fuzzy, solo untranslated con msgstr vuoto):
- Il `msgid` è in italiano
- Genera la traduzione inglese appropriata
- Scrivi il `msgstr` nel file .po

Per le stringhe **fuzzy**:
- Mostra all'utente la traduzione suggerita da pybabel e chiedi se va bene o va corretta
- Se l'utente approva, rimuovi il flag `#, fuzzy`
- Se sono tante (>20), proponi di approvare in blocco mostrando un campione

### 4. Compile

```bash
pybabel compile -d translations
```

### 5. Report

Mostra statistiche finali:
```bash
msgfmt --statistics translations/en/LC_MESSAGES/messages.po
msgfmt --statistics translations/it/LC_MESSAGES/messages.po
```

## Regole

- **NON tradurre il file IT**: per l'italiano il msgid È la traduzione (fallback di Flask-Babel). Lasciare msgstr vuoti.
- **Contesto UI**: le traduzioni EN devono essere brevi e appropriate per bottoni, flash messages, titoli. Non tradurre in modo letterale se il risultato è innaturale.
- **Placeholder**: preservare `%(name)s` e simili senza modificarli.
- **Plural forms**: usare `ngettext` dove appropriato (già gestito da pybabel).
- **Non modificare** le entry già tradotte (msgstr non vuoto e non fuzzy) a meno che l'utente non lo chieda esplicitamente.
- Dopo aver scritto le traduzioni, **sempre** compilare e verificare con `msgfmt --statistics`.
