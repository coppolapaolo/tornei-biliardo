# Changelog

Tutte le modifiche degne di nota a questo progetto sono annotate qui.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il
versionamento segue [Semantic Versioning](https://semver.org/lang/it/).

## [Non rilasciato]

## [1.0.0] — 2026-08-13

Prima release numerata. L'applicazione era già in produzione su
[torneibiliardo.it](https://www.torneibiliardo.it) da mesi: questa versione non
segna l'inizio del progetto ma il momento in cui i rilasci diventano
tracciabili. La storia precedente resta nei commit e nelle PR #1–#93.

Il contenuto che caratterizza la 1.0.0 è il **redesign 7c** (PR #93, 32
commit), che porta l'intera interfaccia sotto un unico design system.

### Aggiunto

- Design system **7c**: `static/css/theme-7c.css` e `tokens-7c.css`, con
  impaginazione mobile first verificata anche su desktop.
- Pagina di errore **403**, che non esisteva: un permesso negato mostrava la
  pagina grezza di Werkzeug, in inglese e fuori dal design.
- Le tabelle larghe si impaginano a card sotto i 992px (`.c7-table-cards`)
  mantenendo un solo DOM, quindi filtri e ordinamento in JavaScript continuano
  a funzionare.
- `Discipline.normalize()` per ricondurre i dati storici al vocabolario unico
  delle discipline, con la migration
  `20260811_normalize_discipline_vocabulary.py`.
- Due test che presidiano classi di guasto invece dei singoli casi:
  `test_template_integrity.py` compila ogni template e verifica ogni `url_for`
  letterale; `test_single_page_header.py` impedisce il ritorno delle testate
  doppie.
- La versione dell'applicazione è mostrata nel footer.

### Rinominato

- L'applicazione si chiama **Tornei Biliardo**, come il dominio
  torneibiliardo.it, e non più "Campionato Biliardo". Il nome era scritto a
  mano in 28 punti (titoli di scheda, oggetti delle email, informativa
  privacy): ora arriva tutto da `Config.APP_NAME`. Era anche dentro `_()` in
  dieci template, cioè dato in traduzione: un nome proprio non si traduce.

### Modificato

- Il punto di rottura del layout passa da `md` (768px) a `lg` (992px), dove il
  guscio cambia davvero impaginazione.
- Le utility `bg-*` di Bootstrap sono ridefinite dal tema: anche le pagine non
  ancora convertite restano in palette.
- Le discipline hanno un solo vocabolario (`Discipline.*.value`), con il nome
  mostrato tradotto tramite `display_name`.
- Catalogo di traduzione inglese completo: 2151 stringhe, 100%.

### Corretto

- `_pagination.html` non compilava (un esempio d'uso dentro un commento HTML,
  che non nasconde i tag a Jinja): le tre pagine admin di gamification che lo
  includono rispondevano **500**.
- Tre endpoint inesistenti nei template (`player.match_proposals` e altri due):
  le proposte di match stanno nel blueprint `individual_match`. Dashboard
  direttore e header dashboard rispondevano 500.
- `_player_challenges.html` puntava a `challenge.attempt_challenge`, che non
  esiste, e perdeva il contesto gara.
- Le route di debug leggevano `Config.DEBUG_MODE` invece di
  `current_app.config`: in produzione il guard non scattava.
- La Content Security Policy non consentiva Google Fonts, quindi la tipografia
  cadeva sul fallback.
- Dodici template disegnavano una seconda testata dentro `content`.
- Il messaggio del 403 restituito in JSON non era tradotto.

[Non rilasciato]: https://github.com/coppolapaolo/tornei-biliardo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/coppolapaolo/tornei-biliardo/releases/tag/v1.0.0
