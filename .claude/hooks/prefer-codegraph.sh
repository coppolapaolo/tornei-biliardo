#!/usr/bin/env bash
# Ricerche di codice Python: passa dal grafo, non da grep.
#
# La regola è già scritta in CLAUDE.md e in memoria; questo hook esiste perché
# leggerla non basta — il primo `grep` costa zero e da lì si prosegue per
# inerzia. Un rifiuto rompe l'inerzia, un promemoria no.
#
# Il grafo non è esaustivo (non segue gli import dentro le funzioni, che qui
# sono ovunque per via degli import circolari): dice DOVE guardare, e l'elenco
# completo si chiude comunque con grep. Per quel momento, e per template, guida,
# traduzioni e testi, c'è la via d'uscita `# codegraph-checked`.

set -uo pipefail

cmd=$(jq -r '.tool_input.command // ""')
[ -z "$cmd" ] && exit 0
case "$cmd" in *codegraph-checked*) exit 0 ;; esac

# Ogni segmento della riga, non solo il primo: `ls x && grep y` è comunque un
# grep, e `pytest | grep -c passed` non lo è. Si guarda l'inizio di ciascun
# comando, quindi la pipe scarta il filtro ma non il primo elemento.
mentre_cerca=0
while IFS= read -r seg; do
  seg=$(printf '%s' "$seg" | sed 's/^[[:space:]()]*//')
  case "$seg" in
    grep\ *|rg\ *|find\ *|"git grep "*|ugrep\ *) ;;
    *) continue ;;
  esac
  # Dove il grafo non arriva, grep è lo strumento giusto.
  case "$seg" in
    *templates/*|*help_content/*|*docs/*|*translations/*|*static/*|\
    *.md*|*.yaml*|*.yml*|*.po*|*.html*|*.css*|*.js*) continue ;;
  esac
  case "$seg" in
    *.py*|*models/*|*routes/*|*utils/*|*migrations/*|*scripts/*|*tests/*|\
    *--include=*py*) mentre_cerca=1 ;;
  esac
done < <(printf '%s\n' "$cmd" | sed 's/&&/\n/g; s/||/\n/g; s/;/\n/g; s/|/\n/g')

[ "$mentre_cerca" -eq 0 ] && exit 0

# Il messaggio via heredoc e non dentro `jq -n '...'`: in italiano ha apostrofi
# («l'elenco»), e un apostrofo chiude la stringa a virgoletta singola di bash.
motivo=$(cat <<'FINE'
Ricerca nel codice Python, e il progetto ha `.codegraph/`: il grafo risponde in un colpo solo a ciò che grep ricostruisce a forza di passate.

Dalla 1.5.0 lo strumento è uno solo:
  "select:mcp__codegraph__codegraph_explore"

Gli si passa la domanda in linguaggio naturale, oppure i nomi di simboli/file: risponde con il sorgente verbatim numerato per riga (pronto da passare a Edit), il percorso delle chiamate fra quei simboli e chi dipende da loro. Una chiamata sola copre trovare un simbolo, seguire il flusso e vedere il raggio d'impatto prima di cambiare.

Il grafo dice DOVE guardare e non è esaustivo: quando ti serve l'elenco completo, o cerchi in template/guida/traduzioni, aggiungi `# codegraph-checked` al comando e passa.
FINE
)

jq -n --arg motivo "$motivo" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $motivo
  }
}'
