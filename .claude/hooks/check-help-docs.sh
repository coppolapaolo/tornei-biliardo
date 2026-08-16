#!/bin/bash
# Stop hook — la guida /aiuto non deve invecchiare in silenzio.
#
# Il problema che risolve: la guida non si *rompe* quando l'app cambia, quindi
# nessun test la coglie e nessuno se ne accorge. Continua a descrivere
# un'applicazione che non esiste più, e il danno si vede solo quando un utente
# la legge. È già successo tre volte di fila (PR #95, #102, #104): pulsanti
# rinominati, opzioni sparite, un modale nuovo — e `help_content/` fermo.
#
# Come funziona: se in questo ramo sono cambiate superfici viste dall'utente
# (templates/, routes/, static/js/) e `help_content/` no, il turno non si
# chiude finché qualcuno non ha *guardato*. "Guardato" include il caso "ho
# controllato e la guida va già bene": si registra nel marcatore e si prosegue.
#
# Uscita 2 = errore bloccante, e il testo su stderr torna al modello.
set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

MARKER=".claude/.help-docs-checked"

# Base del ramo: da dove misurare le modifiche. Se `main` non è raggiungibile
# (clone parziale, fetch mai fatto) si ripiega sulle sole modifiche non
# committate, che è comunque meglio di non controllare niente.
BASE=""
for ref in origin/main main; do
  if git rev-parse --verify --quiet "$ref" >/dev/null 2>&1; then
    BASE="$ref"
    break
  fi
done

changed() {
  {
    [ -n "$BASE" ] && git diff --name-only "$BASE"...HEAD 2>/dev/null
    git diff --name-only HEAD 2>/dev/null
    git ls-files --others --exclude-standard 2>/dev/null
  } | sort -u
}

CHANGED="$(changed)"
[ -z "$CHANGED" ] && exit 0

# Superfici che l'utente vede davvero. `models/` è di proposito fuori: cambia
# di continuo per ragioni interne che non si vedono da nessuna schermata.
VISIBLE="$(printf '%s\n' "$CHANGED" | grep -E '^(templates/|routes/|static/js/)' || true)"
[ -z "$VISIBLE" ] && exit 0

# La guida è stata toccata: si presume che chi l'ha toccata sapesse perché.
printf '%s\n' "$CHANGED" | grep -q '^help_content/' && exit 0

# Marcatore: l'impronta dell'insieme di file visibili già esaminato. Finché
# non cambia, non si richiede un secondo controllo dello stesso lavoro.
FINGERPRINT="$(printf '%s' "$VISIBLE" | sha256sum | cut -d' ' -f1)"
[ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$FINGERPRINT" ] && exit 0

FILES="$(printf '%s\n' "$VISIBLE" | head -12 | sed 's/^/  - /')"
EXTRA="$(printf '%s\n' "$VISIBLE" | wc -l)"

cat >&2 <<EOF
La guida /aiuto potrebbe essere disallineata: sono cambiate superfici viste
dall'utente e \`help_content/\` no.

File cambiati ($EXTRA in tutto, primi 12):
$FILES

Fai partire un subagente che verifichi l'allineamento, con questo compito:

  Invoca la skill \`help-docs\`. Confronta \`help_content/\` con le modifiche di
  questo ramo (\`git diff ${BASE:-HEAD}...HEAD\` più le modifiche non committate)
  e stabilisci se la guida descrive ancora l'applicazione: etichette e nomi dei
  pulsanti, opzioni comparse o sparite, flussi cambiati, schermate catturate da
  rigenerare. Allinea i testi che risultano sbagliati. Se invece la guida è già
  corretta, dillo e non toccare niente.

Poi, in base all'esito:
  - guida aggiornata  -> \`help_content/\` risulta cambiato e il controllo passa
  - guida già a posto -> registra l'esito con:
      echo "$FINGERPRINT" > $MARKER
EOF
exit 2
