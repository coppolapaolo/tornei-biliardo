# Stato del redesign 7c

Diario di lavoro sul branch `claude/redesign-7c`. Il piano originale
dell'handoff è in `README.md`, qui c'è cosa è stato fatto davvero e cosa
resta. Aggiornare a ogni passo.

## Fatto

**Import** (`d529554`) — `files/` copiato nel repo con `cp -R` (merge, non
sostituzione: il Finder di macOS rimpiazza l'intera cartella e cancella
quello che c'era). 61 template, `tokens-7c.css`, `theme-7c.css`,
`gamification.js`, documenti di riferimento in `docs/redesign-7c/`.

**CSP** (`d529554`) — `base.html` chiede Manrope e JetBrains Mono a Google
Fonts, che non erano fra i domini consentiti: aggiunti
`fonts.googleapis.com` a `style-src` e `fonts.gstatic.com` a `font-src`,
con test. L'header è impostato in un `after_request` non condizionato
all'ambiente, quindi senza la correzione la tipografia cadeva sul fallback
anche in sviluppo.

**Endpoint inventati** (`f53eb80`) — i template convertiti puntavano a
`player.match_proposals`, `player.accept_match_proposal` e
`player.create_match_proposal`: nomi plausibili ma mai registrati. Le
proposte di match stanno nel blueprint `individual_match`. Senza la
correzione, dashboard direttore e header dashboard davano 500.

**Due guasti preesistenti** (`bf08f69`) — `_pagination.html` non compilava
(esempio d'uso dentro un commento HTML, che non nasconde i tag a Jinja):
le tre pagine admin di gamification che lo includono davano 500.
`_player_challenges.html` puntava a `challenge.attempt_challenge`, che non
esiste, e perdeva comunque il contesto gara. Aggiunto
`tests/new/unit/test_template_integrity.py`, che copre l'intera classe:
compila ogni template e verifica ogni `url_for` letterale.

**Giro pagine** — 38 pagine visitate nei tre ruoli via test client:
**zero errori server**. Le tre pagine admin riparate rispondono 200.

**Giro visivo** (`c2dd915`, `28960e1`) — fatto in mobile **e** in desktop.
Dodici template convertiti disegnavano una seconda testata dentro
`content`: ora riempiono `page_title` / `page_sub` / `page_actions` /
`page_back`. Aggiunta la pagina 403, che non esisteva. Corretti i difetti
di testo nelle streak.

**Il desktop era stato trascurato dall'handoff.** Due difetti che sul
mobile non si vedono: nessun `max-width`, quindi su monitor larghi filtri
e tabelle si stiravano per l'intera finestra; e le utility `bg-*` di
Bootstrap non erano ridefinite, quindi le pagine non convertite mostravano
riquadri a tinta piena in mezzo alla palette. Entrambi risolti nel tema —
la seconda correzione vale per tutte le pagine non ancora convertite.
**Regola: ogni pagina va guardata in entrambe le viste prima di dirla
fatta.**

## Da fare

1. **`gara_detail.html` (85 KB) e `match_detail.html` (30 KB)** — punto 1
   della lista "da rifare a mano". A sezioni, verificando nel browser.
2. **Gamification giocatore**, poi **flusso challenge**, poi **pannelli
   admin di gamification**.
3. **Traduzioni EN — deciso: alla fine del redesign.** Oggi ci sono 76
   stringhe nuove senza traduzione e 346 fuzzy, che sono accoppiamenti
   automatici sbagliati ("amministrazione" → *Registrations*, "Persone" →
   *Lost*). Non fanno danno: `pybabel` scarta le fuzzy dal `.mo` e
   l'interfaccia inglese mostra l'italiano. Convertire le pagine restanti
   cambierà altri testi, quindi tradurre prima significherebbe ritradurre.
   A conversione finita: `/translate`, poi riscrivere le fuzzy invece di
   approvarle in blocco.
4. **Pulizia di `main.css` e `variables.css`** — solo a verifica completata.

## Rilievi aperti dal giro visivo

Visti ma non ancora affrontati, in ordine di dubbio:

- **Bottoni verdi nel catalogo challenge.** "Nuova challenge" e "Crea la
  prima" sono verde pieno, mentre in dashboard il bottone primario è
  inchiostro. Nella palette il verde è il semantico "ok", non un colore
  d'azione: **da decidere con il committente** se è voluto o va riportato
  al primario.
- **Card "Unisci utenti (merge)" in `/admin/users`.** Fondo giallo con
  sotto una striscia vuota: sembra un accordion o un alert malformato. Da
  guardare da vicino.
- **`public/garas_list.html` su mobile.** È una tabella a sei colonne
  dentro `c7-table-wrap`: i nomi delle gare vanno a capo su ogni parola.
  Il pacchetto ha `_match_cards_mobile` e `_classification_mobile` proprio
  per questo caso: valutare una resa a card sotto i 992px.

## Ambiente di lavoro locale

- L'app di sviluppo gira su **porta 5001**, non 5000 (`python app.py`).
- Per entrare senza password: `/debug/login/<username>` — utenti utili
  `admin`, `pa` (direttore), `player1`.
- La migration `20260607_onboarding` mette `onboarding_completed = 0` a
  **tutti** gli utenti esistenti, che quindi vengono dirottati sulla
  schermata di benvenuto a ogni pagina finché non la completano. In locale
  sono stati sbloccati con un UPDATE. **In produzione è già applicata**:
  gli utenti registrati vedranno l'onboarding al prossimo accesso.
- Il CSS è servito con `?v=ASSET_VERSION`: dopo averlo modificato serve un
  ricaricamento forzato del browser, altrimenti si guarda la versione
  vecchia e si crede che il fix non funzioni.

## Lavori in parallelo

Due branch procedono su altre macchine: tornei a eliminazione diretta /
doppio KO, e drill/challenge.

- **Eliminazione diretta**: nessun attrito. Nell'area bracket/playoff
  esiste un solo template (`player/playoff_invitation.html`, già
  convertito); il resto saranno file nuovi, e il grosso del lavoro è in
  `models/` e `routes/`, che il redesign non tocca.
- **Challenge**: collisione reale. Dei 19 template dell'area solo 3 sono
  convertiti; gli altri sono nella lista "da rifare a mano". **Non
  convertire l'area challenge finché quel branch non è merged** — il
  `README.md` la mette al punto 4, quindi rimandarla non costa nulla.
- Chi lavora su quei branch può ignorare le classi `.c7-*`: il tema
  ridefinisce `.card`, `.btn`, `.table`, `.badge`, quindi **markup
  Bootstrap standard eredita il design**. La regola è solo negativa:
  niente `style="..."` con colori, niente `<style>` con gradienti.
- File conteso: `base.html`. Voci di menu e script nuovi vanno aggiunti
  dopo il merge del tema.
- Attriti minori attesi: `utils/feature_flags.py` (stesso dict
  `ENDPOINT_ROLES`), `translations/*.po` (rigenerare, non risolvere a
  mano), `CLAUDE.md`. Le migration non collidono: nomi date-prefixed
  distinti e il runner traccia per nome.

Ordine di merge: **tema → eliminazione diretta → challenge**. Il tema è il
branch orizzontale, e più resta fuori più conflitti genera.
