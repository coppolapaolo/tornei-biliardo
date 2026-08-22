#!/usr/bin/env bash
# Tiene aggiornato il grafo graphify — la parte che si può tenere aggiornata.
#
# LA DISTINZIONE CHE DECIDE TUTTO
#
# graphify ha due passate, e costano in modo incomparabile:
#
#   - il **codice** si estrae dall'AST: `graphify update` — nessun LLM, 18
#     secondi misurati su 733 file (2026-08-22). Questo si automatizza.
#   - i **documenti** (markdown, YAML, immagini, paper) si estraggono con una
#     passata semantica fatta da subagenti: 1,1 milioni di token di input nella
#     sola passata incrementale del 21 agosto, 2,8 milioni alla prima. Questo
#     NON si automatizza: si fa a mano, con `/graphify --update`, quando serve.
#
# Da cui: l'hook aggiorna il codice e, se vede documenti cambiati, lo dice
# invece di provarci. Un hook che bruciasse un milione di token a ogni Stop
# sarebbe un guasto, non una comodità.
#
# QUANDO NON FA NIENTE
#
# Se nessun file di codice è più recente del grafo, esce subito: 18 secondi a
# ogni Stop, per ricostruire ciò che non è cambiato, sono 18 secondi sprecati
# a ogni Stop.
#
# `async: true` nei settings: la ricostruzione non deve far aspettare nessuno.

set -uo pipefail

progetto="${CLAUDE_PROJECT_DIR:-$PWD}"
grafo="$progetto/graphify-out/graph.json"

# Nessun grafo: non è compito di questo hook costruirne uno (è una decisione,
# e la prima passata costa milioni di token).
[ -f "$grafo" ] || exit 0

# Un solo aggiornamento per volta. `mkdir` è atomico: se la directory esiste
# già, un altro giro sta lavorando e questo si fa da parte.
lock="$progetto/graphify-out/.sync.lock"
mkdir "$lock" 2>/dev/null || exit 0
trap 'rmdir "$lock" 2>/dev/null' EXIT

cd "$progetto" || exit 0

# IL CONFRONTO SI FA CON UNA MARCA NOSTRA, NON CON graph.json
#
# Verificato il 2026-08-22: quando il codice cambia senza che il grafo cambi
# (una modifica che non aggiunge nodi, o un `touch`), `graphify update`
# ricostruisce ma **non riscrive** graph.json. La sua data resta quella vecchia,
# quindi un confronto `-newer "$grafo"` continuerebbe a trovare quel sorgente
# più recente **per sempre**: 12-18 secondi buttati a ogni Stop, per una
# ricostruzione che non ha niente da ricostruire.
#
# La marca la scriviamo noi dopo ogni giro riuscito, e registra quando abbiamo
# guardato — non quando il grafo è cambiato. Sono due cose diverse, e la prima
# è quella che serve qui.
marca="$progetto/graphify-out/.last-sync"
[ -f "$marca" ] || touch -r "$grafo" "$marca" 2>/dev/null || touch "$marca"

# Le cartelle esaminate sono quelle dei sorgenti: `find .` intero passerebbe
# per `venv/`, `node_modules/` e `.git/`, dove non c'è niente da estrarre e
# c'è sempre qualcosa di più recente.
codice_nuovo=$(find models routes utils scripts migrations app.py config.py \
  -name '*.py' -newer "$marca" -print -quit 2>/dev/null)

# E documenti? Quelli non li sappiamo aggiornare qui: si segnalano.
doc_nuovi=$(find docs help_content -type f \( -name '*.md' -o -name '*.yaml' \) \
  -newer "$marca" -print -quit 2>/dev/null)

[ -z "$codice_nuovo" ] && [ -z "$doc_nuovi" ] && exit 0

esito=""
if [ -n "$codice_nuovo" ]; then
  if graphify update . >/dev/null 2>&1; then
    touch "$marca"
    esito="Grafo graphify riallineato al codice."
  else
    esito="graphify update non è riuscito: il grafo resta indietro rispetto al codice."
  fi
fi

if [ -n "$doc_nuovi" ]; then
  coda="Documenti cambiati (docs/ o help_content/): quelli richiedono la passata semantica, che costa token veri — lanciala a mano con /graphify --update quando serve davvero."
  touch "$marca"
  esito="${esito:+$esito }$coda"
fi

[ -z "$esito" ] && exit 0

jq -n --arg m "$esito" '{ systemMessage: $m, suppressOutput: true }'
