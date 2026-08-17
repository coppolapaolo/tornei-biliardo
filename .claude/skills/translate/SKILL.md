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
pybabel extract -F babel.cfg --ignore-dirs 'venv .* _* node_modules' -o messages.pot .
```

**IMPORTANTE**: `--ignore-dirs` è obbligatorio. Senza, `pybabel` scansiona
anche `venv/` ed estrae migliaia di stringhe di librerie terze (click,
networkx, ecc.); `update` poi le riattiva generando **duplicati** che fanno
fallire la compilazione. Babel non supporta esclusioni in `babel.cfg`, quindi vanno
passate qui. (`.* _*` sono i default di Babel da preservare.)

### 2. Update catalogs

```bash
pybabel update -i messages.pot -d translations --ignore-obsolete
```

`--ignore-obsolete` rimuove le entry `#~` non più presenti nel sorgente
(incl. eventuale cruft venv pregresso), mantenendo i `.po` puliti.

### 3. Find new untranslated EN strings

Dopo l'update, cerca nel file `translations/en/LC_MESSAGES/messages.po` le entry con `msgstr ""` (non tradotte) o marcate `#, fuzzy`.

Per ogni stringa **nuova** (non fuzzy, solo untranslated con msgstr vuoto):
- Il `msgid` è in italiano
- Genera la traduzione inglese appropriata
- Scrivi il `msgstr` nel file .po

Per le stringhe **fuzzy**:
- **Riscrivile a mano, una per una.** `pybabel update` non traduce: copia il
  `msgstr` di una voce che *somiglia* al `msgid` nuovo, e la somiglianza è sul
  testo. Casi realmente prodotti: «Nessuna Gara Configurata» → *No features
  configured*, «Dispari» → *Tiebreakers*. Mostrare la proposta e chiedere
  conferma in blocco significa far approvare all'utente traduzioni sbagliate.
- **Controlla i placeholder**, che il fuzzy-matching ignora: «%(position)s°
  Posto» era diventato «%(num)s slots». Un `%(nome)s` che il `msgid` non ha
  è un `KeyError` al primo rendering in quella lingua — non un refuso.
- Conta vuote e fuzzy **col parser di Babel**
  (`babel.messages.pofile.read_po` + `msg.fuzzy` / `msg.string`), mai con
  `grep`: un `.po` ha stringhe su più righe e commenti che contengono la
  parola «fuzzy».

### 3-bis. Ripulisci i fuzzy del catalogo italiano

`pybabel update` marca fuzzy anche le voci **italiane**, che hanno `msgstr`
vuoto per scelta (in italiano il `msgid` *è* la traduzione). Sono innocue —
`pybabel compile` ripiega sul `msgid` — ma restano rumore nel catalogo, e chi
lo apre non sa distinguerle da un lavoro lasciato a metà.

Togli il flag **solo** dalle voci a `msgstr` vuoto: una fuzzy con dentro una
traduzione va letta, non sbandierata via. Verificato una volta (agosto 2026,
3317 confronti su tutte le voci, `gettext`/`ngettext` a confronto prima e
dopo): la rimozione non cambia **nessuna** stringa resa. Il `.mo` cresce —
entrano le forme plurali, che da fuzzy erano escluse — ma il testo è identico,
perché il valore compilato coincide col `msgid` e la `Plural-Forms` italiana
(`n != 1`) è la stessa regola che `gettext` applica quando la voce non c'è.

### 4. Compile

```bash
pybabel compile -d translations --statistics
```

`--statistics` compila **e** stampa il conteggio per catalogo, così
compilazione e report sono un'unica operazione.

**Usa sempre `pybabel compile`, mai GNU `msgfmt`, per compilare/verificare.**
I due compiler hanno semantiche diverse sulle entry plurali con `msgstr`
vuoto: `msgfmt` le scarta, `pybabel` le mantiene (col `msgid` come fallback).
Mischiare i due fa sembrare il `.mo` "disallineato" dal `.po` quando in realtà
è corretto. Per validare la coerenza `.mo`/`.po` usa lo stesso compiler della
toolchain (`pybabel`).

### 5. Report

Riporta le statistiche già stampate dallo step 4 (messaggi tradotti per
catalogo: EN dovrebbe essere 100%, IT volutamente basso perché i `msgstr`
sono vuoti by-design).

## Regole

- **NON tradurre il file IT**: per l'italiano il msgid È la traduzione (fallback di Flask-Babel). Lasciare msgstr vuoti.
- **Contesto UI**: le traduzioni EN devono essere brevi e appropriate per bottoni, flash messages, titoli. Non tradurre in modo letterale se il risultato è innaturale.
- **Placeholder**: preservare `%(name)s` e simili senza modificarli.
- **Plural forms**: usare `ngettext` dove appropriato (già gestito da pybabel).
- **Non modificare** le entry già tradotte (msgstr non vuoto e non fuzzy) a meno che l'utente non lo chieda esplicitamente.
- Dopo aver scritto le traduzioni, **sempre** compilare e verificare con `pybabel compile -d translations --statistics` (mai GNU `msgfmt`: semantica diversa sui plurali, vedi step 4).
