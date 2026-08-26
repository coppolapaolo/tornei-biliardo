# [054] La versione la decidono i titoli delle PR

**Data**: 2026-08-26
**Stato**: Accepted
**Decisori**: Paolo Coppola, Claude

## Contesto

Il footer di ogni pagina mostra `v{{ config.VERSION }}` (`templates/base.html`),
e `/health` restituisce lo stesso valore. La fonte era `Config.VERSION =
"1.0.0"`, una costante scritta a mano in `config.py`: ferma da quando fu creato
il tag `v1.0.0`, mentre nel frattempo su `main` sono arrivati 190 commit. Il
numero mostrato non era sbagliato per poco — non significava più niente.

Nello stesso file c'era già la diagnosi, scritta per un altro campo:

> `VERSION` non va bene perché è scritta a mano e nessuno si ricorderebbe di
> incrementarla dopo un ritocco al CSS.
>
> — commento di `_compute_asset_version()`, `config.py`

`ASSET_VERSION` aveva risolto il problema **calcolandosi**. La versione
dell'applicazione, un piano più su, no.

Il problema pratico che rende utile risolverlo: fra il merge su `main` e la
produzione può passare **fino a un giorno**. Il job `deploy` fa solo un reload;
il codice lo porta lo scheduled task `auto_deploy.py`, e se la PR contiene una
migration nemmeno il reload parte. Guardando il sito non c'era modo di sapere
quale codice stesse girando.

Due vincoli hanno ristretto molto lo spazio delle soluzioni:

1. **`main` è protetto con `enforce_admins=true`.** Il pattern usuale — un
   workflow che incrementa il numero e fa `git push` su `main` — è impossibile:
   il push viene rifiutato anche a un amministratore.
2. **Il codice arriva in produzione con un `git pull`.** Qualunque numero
   generato dalla CI deve quindi *stare nel repository*: un artefatto di build
   che non viene committato non raggiungerebbe mai PythonAnywhere.

## Decisione

La versione si calcola dai **titoli delle pull request**, secondo
[Conventional Commits](https://www.conventionalcommits.org/it/), e la scrive
[release-please](https://github.com/googleapis/release-please).

Il perno è che le PR si uniscono in **squash**: il titolo della PR *diventa* il
messaggio di commit su `main`. Non serve quindi disciplina sui singoli commit di
lavoro — solo sul titolo, che si scrive una volta e si può correggere fino
all'ultimo istante prima di unire.

| Titolo della PR | Effetto sulla versione |
|---|---|
| `fix: …` | patch (1.0.0 → 1.0.1) |
| `feat: …` | minor (1.0.1 → 1.1.0) |
| `feat!: …` (o `BREAKING CHANGE:` nel corpo) | major (1.1.0 → 2.0.0) |
| `chore:` `docs:` `test:` `ci:` `refactor:` `style:` `build:` | nessuno |

Il **tipo** è in inglese perché è sintassi che un programma deve leggere; la
**descrizione resta in italiano**, come tutto il resto del progetto.

Quattro conseguenze operative:

- **Il bot passa da una PR come tutti.** A ogni push su `main`, release-please
  apre — o aggiorna — una PR «chore(main): release X.Y.Z» che porta il numero
  nuovo in `config.py` e la voce in `docs/RELEASES.md`. Unendo *quella* nascono
  il tag `vX.Y.Z` e la GitHub Release. Nessun push diretto, nessuna deroga alla
  branch protection: il vincolo 1 non è aggirato, è rispettato.
- **`config.py` resta la fonte unica.** Il numero viene riscritto lì
  (`extra-files` + annotazione `# x-release-please-version`), quindi arriva in
  produzione col solito `git pull` — vincolo 2 — e footer, `/health` e chiunque
  legga `Config.VERSION` continuano a funzionare senza sapere niente di tutto
  questo. Non è stato necessario toccare né i template né `auto_deploy.py`.
- **Due changelog, due mestieri.** `CHANGELOG.md` resta scritto a mano ed è il
  racconto: cosa cambia per chi usa l'app, e perché è stato fatto così.
  `docs/RELEASES.md` è generato ed è l'indice: quali PR compongono quale
  versione. Puntare il bot su `CHANGELOG.md` non avrebbe cancellato lo storico,
  ma da quel momento le voci nuove sarebbero state righe secche — e la prosa,
  semplicemente, avrebbe smesso di essere scritta.
- **Il titolo non conforme blocca la PR** (job `pr-title` in `ci.yml`). Senza
  questo controllo, dimenticare il prefisso non produce alcun errore: la PR si
  unisce, non muove la versione e non compare nel changelog. Un guasto muto, e
  quelli in questo progetto si presidiano prima (cfr. `pip install` fallito con
  un WARNING in `auto_deploy.py`).

## Alternative Considerate

### Alternativa 1: contatore derivato da git

**Descrizione**: `MAJOR.MINOR` dal tag più recente, `PATCH` = numero di commit
dal tag (`git describe --tags --long`), più lo SHA breve. Oggi darebbe
`1.0.190+255e815`.

- **Pro**:
  - zero manutenzione e zero convenzioni: il numero si muove da sé a ogni merge;
  - nessun token, nessun bot, nessuna PR in più;
  - lo SHA identifica esattamente il codice vivo in produzione.
- **Contro**:
  - il numero non *significa* niente: 1.0.190 non dice se è arrivata una
    funzione o una correzione, e la distanza fra due versioni non è informativa;
  - richiede che la produzione sappia leggere git (o che `auto_deploy.py`
    scriva un file), quindi più parti in movimento proprio dove si guasta di più;
  - non produce nessun changelog.

### Alternativa 2: CalVer (`2026.08.26.3`)

- **Pro**: dice a colpo d'occhio quanto è vecchio ciò che gira — utile con una
  finestra di deploy che può arrivare a 24 ore.
- **Contro**: non distingue una correzione da un cambiamento rompente, che è
  esattamente ciò che si vuole leggere in un numero di versione.

### Alternativa 3: incremento a mano dentro ogni PR

- **Pro**: nessun tooling, controllo totale.
- **Contro**: è precisamente ciò che il commento di `_compute_asset_version()`
  già dichiarava inaffidabile per esperienza diretta. Si dimentica, e il
  dimenticarsene non ha sintomi.

## Conseguenze

### Positive

- Il numero nel footer torna a significare qualcosa, e lo fa da sé.
- `docs/RELEASES.md` dà gratis l'elenco di cosa è entrato in ogni rilascio.
- Il rilascio diventa un gesto esplicito — unire la PR di release — invece di
  un effetto collaterale del merge. Si può accumulare e rilasciare quando si
  vuole.
- I titoli delle PR migliorano per forza: dovendo scegliere `fix` o `feat`, si
  dichiara la natura della modifica prima di unirla.

### Negative

- Il footer resta sulla versione precedente finché non si unisce la PR di
  release. È corretto — quella è la versione che sta girando — ma va saputo,
  perché la tentazione di leggerlo come «il bot non ha funzionato» è forte.
- I 190 commit già su `main` non sono in formato Conventional: sono invisibili
  al bot. Il primo rilascio conterrà solo ciò che arriva da qui in avanti.

### Rischi

- **Il PAT è il punto fragile.** Il `GITHUB_TOKEN` di default non fa scattare
  workflow sulle PR che apre (protezione anti-loop di GitHub): la PR di release
  nascerebbe senza il check `test-and-typecheck`, che è *required* e con
  `enforce_admins=true` non si aggira — quindi non unibile, per sempre. Serve un
  token personale nei secret. Se **scade**, il sintomo non è un errore ma una PR
  di release che non si riesce a unire: il workflow ricade sul token di default
  e continua a sembrare funzionante.
- Il job `pr-title` protegge dal titolo dimenticato solo se qualcuno lo guarda:
  va aggiunto ai *required status checks* della branch protection, altrimenti
  resta un check rosso che si può ignorare.

## Note Implementative

```
.github/workflows/release-please.yml   il bot (push su main)
.github/workflows/ci.yml               job `pr-title` (solo sulle PR)
release-please-config.json             extra-files + changelog-path + sezioni in italiano
.release-please-manifest.json          la memoria del bot: da qui riparte
config.py                              VERSION = "…"  # x-release-please-version
docs/RELEASES.md                       generato
CHANGELOG.md                           a mano
tests/new/unit/test_version_single_source.py   presidio sulle convenzioni mute
```

Il presidio verifica le tre cose che, se saltano, non danno sintomi:
l'annotazione sulla riga di `VERSION`, la presenza di `config.py` fra gli
`extra-files`, e l'accordo fra manifest e `Config.VERSION`.

## Riferimenti

- [Conventional Commits](https://www.conventionalcommits.org/it/v1.0.0/)
- [release-please](https://github.com/googleapis/release-please) ·
  [action](https://github.com/googleapis/release-please-action)
- File correlati: `config.py`, `templates/base.html`, `scripts/auto_deploy.py`
- CLAUDE.md, sezione **CI/CD & Deployment**, punto 4
