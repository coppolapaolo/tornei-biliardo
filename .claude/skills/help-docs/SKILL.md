---
name: help-docs
description: Tiene allineato il mini-sito di aiuto (/aiuto) quando l'app cambia — testi, schermate catturate e micro-aiuto per l'interfaccia adattiva. Attiva dopo aver aggiunto o modificato una funzione visibile all'utente, cambiato un'etichetta o un flusso, spostato una route, o quando l'utente chiede di aggiornare la guida.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Aiuto in linea: tenerlo vero

La documentazione con le schermate ha un modo di morire tutto suo: non si
rompe, **invecchia**. Continua a rispondere, con parole ragionevoli e immagini
nitide, descrivendo un'app che non esiste più. Un utente che segue una guida
sbagliata sta peggio di uno che non ne ha nessuna: la guida non lo lascia
soltanto senza risposta, gli fa cercare un pulsante che non c'è e lo convince
di aver sbagliato lui.

Questa skill esiste per quello. Non per scrivere bella prosa — per fare in modo
che, dopo una modifica all'app, la guida torni a dire il vero.

## Quando attivarla

Serve un passaggio da qui quando la modifica appena fatta:

- **aggiunge o toglie una funzione** che l'utente vede;
- **cambia un'etichetta, un flusso o la posizione di un comando** (anche solo
  spostare un pulsante da una linguetta all'altra);
- **cambia il significato di un'opzione** (valore predefinito, vincoli,
  effetti);
- **rinomina o sposta una route** citata dai contenuti (`screens:` nelle
  pagine, `screens:` nei suggerimenti);
- **cambia l'aspetto** di una schermata che compare in una figura.

Non serve per: modifiche interne senza effetti visibili, rifattorizzazioni,
correzioni di bug che ripristinano il comportamento già documentato.

## Il perimetro: tutto tranne l'esclusivo-admin

La guida copre **tutte le funzioni e tutte le opzioni** che vedono giocatore,
direttore di gara e ospite. Resta fuori solo ciò che è **esclusivo
dell'amministratore**: gestione degli account, approvazione delle richieste di
ruolo, configurazione della gamification, indicatori di piattaforma. Chi
amministra conosce già la piattaforma; chi gioca no, ed è per lui che la guida
esiste.

Per sapere se una schermata è dentro o fuori non fidarti di `ENDPOINT_ROLES`
(`utils/feature_flags.py`): quella matrice dice cosa è *raggiungibile* in
produzione, non chi ha il permesso di usarlo. Sono due strati distinti, e
quando divergono vince il decoratore: un endpoint elencato `{"director"}` ma
protetto da `@admin_required` risponde 403 a un direttore, e documentarlo
significa promettere una funzione che non esiste. È già successo — `users_list`
e `user_detail` sono stati listati per mesi come `{"director"}` mentre il
decoratore li negava, e la voce è stata corretta proprio scrivendo questa
guida. Vale anche il contrario: una route può essere fuori matrice (quindi 404
in produzione) pur essendo aperta a tutti nel codice.

**La prova sta nel provarla**: apri la schermata con `/debug/login/<direttore>`
e guarda se risponde. Se una route risulta irraggiungibile o rotta, non
aggirarla scrivendo la pagina «a memoria» — segnalalo, perché quasi sempre è un
difetto dell'app, non della guida (così è emerso `round_management`, una pagina
il cui template non è mai esistito).

Verifica del perimetro (elenca le route non-admin che nessuna pagina dichiara
in `screens:`):

```bash
python - <<'EOF'
import yaml, pathlib
from app import create_app
from utils.feature_flags import ENDPOINT_ROLES
covered = set()
for p in pathlib.Path("help_content/it/pages").glob("*.yaml"):
    covered.update((yaml.safe_load(p.read_text()) or {}).get("screens") or [])
app = create_app("development")
with app.app_context():
    for r in app.url_map.iter_rules():
        ep = r.endpoint
        roles = ENDPOINT_ROLES.get(ep)
        if not roles or ep in covered: continue
        if "GET" not in (r.methods - {"HEAD", "OPTIONS"}): continue
        print(f"{str(r):50s} {ep}")
EOF
```

Quello che resta fuori dopo il filtro sono endpoint JSON di servizio,
redirect e pagine rotte: se compare una **schermata vera**, manca una pagina.

## Com'è fatto il mini-sito

```
help_content/
  screenshots.yaml            manifest delle catture (id → route, ruolo, viewport)
  it/                         lingua di riferimento
    site.yaml                 sezioni e ordine delle pagine
    hints.yaml                micro-aiuto e presentazioni (interfaccia adattiva)
    captions.yaml             didascalie delle schermate
    pages/<slug>.yaml         una pagina per file
  en/                         stessa struttura, stessi slug

static/img/help/<lingua>/<id>.png   le catture, generate — mai ritoccate a mano
static/css/help-7c.css        stili del solo mini-sito
templates/help/               guscio, blocchi, pagine
routes/help.py                blueprint /aiuto
utils/help_content.py         caricamento, ricerca, verifica
scripts/help_docs/            seed dimostrativo e cattura schermate
```

**Le lingue hanno la stessa struttura, sempre.** Stessi id di sezione, stessi
slug di pagina: il cambio lingua tiene l'indirizzo corrente, quindi una pagina
che esiste solo in italiano manda chi passa all'inglese su un 404. Lo verifica
`test_le_lingue_hanno_la_stessa_struttura`, e non e' un formalismo — e'
esattamente l'errore che si commette aggiungendo una pagina e rimandando la
traduzione.

Il contenuto è **dato**, non markup. Le pagine sono elenchi di blocchi tipati;
i testi brevi dei suggerimenti stanno in `hints.yaml` e sono già interrogabili
per schermata. Questa separazione è ciò che permette alla futura interfaccia
adattiva di riusare i testi invece di riscriverli.

## Il ciclo di lavoro

### 1. Trova cosa è diventato falso

Parti dal diff, non dall'indice della guida:

```bash
git diff --name-only main... | grep -E '^(routes|templates|models)/'
```

Per ogni file toccato, chiediti quale pagina lo descrive. La corrispondenza
più veloce la dà il campo `screens:` dei contenuti:

```bash
grep -rn "screens:" -A 4 help_content/it/pages/ help_content/it/hints.yaml
```

Se hai cambiato `admin.competition.gara_detail`, tutto ciò che lo elenca è
sospetto.

### 2. Aggiorna i testi

Le pagine sono in `help_content/it/pages/<slug>.yaml`. Blocchi disponibili:

| `type` | Campi | Quando usarlo |
|---|---|---|
| `heading` | `id`, `title` | Sezione della pagina. `id` è l'ancora: i suggerimenti ci puntano. |
| `text` | `text` | Un paragrafo. Markup ammesso: `**grassetto**`, `` `codice` ``, `[testo](/percorso)`. |
| `steps` | `items[].title/text/shot` | Una procedura. I numeri li mette il template. |
| `shot` | `shot`, `caption`, `variant` | Una figura. `variant: desktop` per la cattura larga. |
| `note` | `tone` (`info`/`warning`/`tip`), `title`, `text` | Un avviso. |
| `list` | `title`, `items` | Elenco puntato. |
| `options` | `items[].name/values/text/hint` | Riferimento di opzioni. `hint` collega al micro-aiuto. |
| `faq` | `items[].q/a` | Domande frequenti, a fondo pagina. |

Regole di scrittura non negoziabili:

- **Linguaggio semplice**: il destinatario non è pratico di computer. Frasi
  brevi, verbi concreti, niente gergo tecnico. «Tocca», non «effettua un tap».
- **Le parole dell'app**: campionato, gara, turno, partita, rack, distanza,
  direttore di gara, X a tavolino, conclusa, da giocare. Mai *round*, *match*,
  *bye*, *director* quando esiste il termine italiano usato nell'interfaccia.
- **Ogni passaggio ha la sua figura** quando descrive dove premere.
- **Niente promesse su ciò che non esiste**: se una funzione è a metà, o non
  si documenta o si dice cosa fa oggi.

### 3. Aggiorna le schermate

Le figure sono **generate dall'app vera**. Non aprire mai un'immagine in un
editor: la modifica sopravvivrebbe al cambiamento dell'interfaccia e la
figura diventerebbe una bugia stabile.

Per aggiungere una figura, si aggiunge una voce a `help_content/screenshots.yaml`:

```yaml
  - id: nome-con-trattini
    route: /admin/gara/2
    as: Luca Bianchi          # oppure `anonimo`
    caption: "Testo alternativo: descrive cosa si vede."
    viewports: [mobile]       # aggiungi `desktop` solo se il layout cambia
    click: ['[data-c7-tab-btn="classifica"]']   # facoltativo
    clip: ".c7-rackpad"                          # facoltativo: ritaglia
    annotate: [{selector: ".btn-primary", label: "1"}]  # facoltativo
```

Poi si rigenera:

```bash
# 1. dataset dimostrativo (deterministico, azzera il DB di sviluppo!)
python scripts/help_docs/seed_demo.py

# 2. cattura: avvia e chiude l'app da sola, in tutte le lingue dichiarate
python scripts/help_docs/capture_screenshots.py --serve

# solo alcune schermate, o solo una lingua
python scripts/help_docs/capture_screenshots.py --serve --only gara-gestione
python scripts/help_docs/capture_screenshots.py --serve --lang it
```

Il seed **fissa il generatore casuale** (`SEED`): senza, il sorteggio del primo
turno cambierebbe a ogni esecuzione e ogni ricattura riscriverebbe tutte le
immagini anche a interfaccia identica. Se tocchi il seed, ricontrolla gli id
nei percorsi del manifest (gara 1/2/3, match 18): la cattura si ferma con un
errore se un percorso sparisce, ma una gara diversa da quella attesa passerebbe
inosservata.

Il seed crea sempre gli stessi dati: un campionato con tre gare (una conclusa,
una in corso con una partita viva, una con le iscrizioni aperte), un direttore
(`Luca Bianchi`) e otto giocatori (il primo è `Marco Rossi`). Se una figura
richiede uno stato che il dataset non produce, **estendi il seed** — non
truccare l'immagine.

Se hai cambiato una schermata senza aggiungere figure nuove, basta rilanciare
la cattura: i file esistenti vengono riscritti e il diff mostra esattamente
quali immagini sono cambiate.

### 4. Traduci

Ogni pagina nuova va aggiunta a **tutte** le lingue nello stesso giro di
lavoro. Cosa si traduce e cosa no:

| Si traduce | Non si traduce |
|---|---|
| `title`, `summary`, testi dei blocchi | `slug` (nome del file) |
| `title` dei `heading` | `id` dei `heading` — sono le ancore dei micro-aiuti |
| `label` e `short` dei suggerimenti | `anchor` dei suggerimenti — e' il contratto con `data-help` |
| Le didascalie (`captions.yaml`) | `screens`, `related`, `hint`, `kind`, `audience` |

La terminologia inglese segue **l'interfaccia inglese dell'app**, non una
traduzione a orecchio: `competition`, `championship`, `round`, `match`, `rack`,
`distance`, `standings`, `venue`, `competition director`, `X by walkover`. In
dubbio, cerca la stringa nel catalogo:

```bash
grep -A 1 'msgid "Classifica"' translations/en/LC_MESSAGES/messages.po
```

Le schermate sono catturate **una volta per lingua** con l'app impostata su
quella lingua (`locales:` in `screenshots.yaml`). Una guida inglese con i
pulsanti italiani manda il lettore a cercare comandi che nella sua interfaccia
non esistono: e' l'esatto contrario di cio' che deve fare.

### 5. Aggiorna il micro-aiuto

`help_content/it/hints.yaml` contiene i testi **già pronti** per l'interfaccia
adattiva prevista dal progetto: la presentazione alla prima visita di una
schermata, e la piccola «?» accanto ai comandi. Il codice che li mostra non
esiste ancora; i testi sì, e vanno tenuti veri come il resto.

Quando aggiungi un comando importante a una schermata, aggiungi anche il suo
suggerimento:

```yaml
  - id: gara.nuova_opzione        # nome puntato, area.comando
    label: "Come si chiama nell'interfaccia"
    short: "Una o due frasi. Massimo 220 caratteri: è un fumetto, non un paragrafo."
    anchor: gara-nuova-opzione    # finirà in `data-help` sull'elemento
    screens: [admin.competition.create_gara_standalone]
    page: opzioni_della_gara      # dove si legge per esteso
    section: struttura            # `heading` esistente in quella pagina
```

`anchor` è il contratto con i template dell'app: quando l'interfaccia adattiva
verrà costruita, l'elemento esporrà `data-help="gara-nuova-opzione"` e il
componente chiederà i testi a `/aiuto/api/schermata/<endpoint>`. Fino ad allora
resta una dichiarazione di intenti verificata dai test.

Per rivederli tutti insieme: `/aiuto/microaiuto` (in produzione è admin-only).

### 6. Verifica

```bash
# coerenza dei contenuti: pagine orfane, figure mancanti, ancore rotte,
# endpoint inesistenti. È il controllo che impedisce alla guida di mentire.
pytest tests/new/unit/test_help_content.py -v

# le pagine si aprono davvero
pytest tests/new/integration/test_help_site.py -v

# manifest delle catture, senza browser
python scripts/help_docs/capture_screenshots.py --check

# il resto, come per ogni modifica
black . && flake8 && pyright
pytest tests/new/unit/ -n auto
```

Se hai toccato i template o il CSS, guarda le pagine a **390px e 1512px** —
il mini-sito è mobile first ma vive anche su desktop (vedi la skill `ui-7c`).

## Errori da non ripetere

| Errore | Perché è un problema | Cosa fare |
|---|---|---|
| Ritoccare un PNG a mano | Sopravvive al cambio di interfaccia: diventa una bugia permanente | Estendi il seed e ricattura |
| Descrivere un flusso «a memoria» | Le etichette non corrispondono mai del tutto | Apri la schermata e leggi cosa c'è scritto |
| Aggiungere una pagina senza metterla in `site.yaml` | È irraggiungibile | La verifica la segnala: aggiungila alla sezione giusta |
| `short` lungo tre righe | Nel fumetto non ci sta | Sposta il dettaglio nella pagina, lascia due frasi |
| Documentare una funzione a metà | Prometti ciò che l'app non mantiene | O si documenta com'è oggi, o non si documenta |
| Rinominare una route e non toccare i contenuti | I rimandi puntano al vuoto | La verifica confronta `screens:` con `app.url_map` |
| Nuova pagina `/aiuto/...` senza entry in `ENDPOINT_ROLES` | In produzione è admin-only (ADR-028) | Le route del blueprint ci sono già; una nuova va aggiunta |
| Termini inglesi nei testi italiani | L'interfaccia dice altro: l'utente non ritrova la parola | campionato, gara, turno, partita, X a tavolino |
| Pagina aggiunta in una lingua sola | Il cambio lingua porta su un 404 | Aggiungila a tutte, nello stesso giro di lavoro |
| `anchor` tradotto | Due ancore per lo stesso comando: l'interfaccia adattiva ne trova una | `anchor` è identico in tutte le lingue |
| Guida inglese con schermate italiane | Manda a cercare pulsanti che non esistono | `locales:` nel manifest e ricattura |
| Pagina su una funzione esclusiva dell'admin | Fuori perimetro: la guida è per chi gioca e chi organizza | Vedi «Il perimetro» sopra |
| Funzione di direttore lasciata fuori perché «avanzata» | Il perimetro è *tutte* le opzioni non-admin, non le principali | Passa la verifica del perimetro prima di chiudere |

## Dove guardare per scrivere cose vere

- `docs/reference/CLASSIFICATION_SYSTEM.md` — classifiche, gestione del numero
  dispari, forfait, spareggi, handicap. È la fonte per la sezione
  «Come funziona davvero».
- `docs/reference/SPECIFICHE.md` e `docs/usecases/gare.md` — il flusso di una
  gara dall'inizio alla fine, con le varianti.
- `models/matchmaking/configuration.py` — le strategie di abbinamento e le
  opzioni ammesse per ciascuna.
- `utils/feature_flags.py` — cosa è davvero visibile in produzione e a chi.
  Documentare una schermata che in produzione dà 404 è peggio che tacerla.
- Il modulo di creazione gara (`templates/admin/gara_create_standalone.html`)
  — l'elenco autorevole delle opzioni e delle loro etichette.

## Aggiungere una lingua

1. Crea `help_content/<codice>/` con `site.yaml`, `hints.yaml`, `captions.yaml`
   e `pages/` — **stessi id di sezione e stessi slug** delle altre lingue.
2. Aggiungi il codice a `locales:` in `screenshots.yaml` e ricattura: le
   immagini finiscono in `static/img/help/<codice>/`.
3. Aggiungi la lingua al selettore dell'app (`routes/i18n.py` accetta oggi solo
   `it` e `en`) e al catalogo delle traduzioni dell'interfaccia.
4. `pytest tests/new/unit/test_help_content.py` verifica struttura, figure e
   ancore per ogni lingua trovata: non serve toccare i test.

Nei `hints.yaml` si traducono `label` e `short`, **mai** `anchor`: quello è il
valore che l'elemento dell'interfaccia esporrà in `data-help`, uguale per tutte
le lingue.
