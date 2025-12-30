#!/bin/bash
# todo_triage.sh - Genera report TODO per triage
# Usage: ./scripts/audit/todo_triage.sh

set -e
cd "$(dirname "$0")/../.."

OUTPUT_FILE="todo_report.csv"

echo "=============================================="
echo "TRIAGE TODO COMMENTS"
echo "Data: $(date)"
echo "=============================================="
echo ""

echo "Generando report CSV: $OUTPUT_FILE"
echo ""

# Header CSV
echo "file,line,category,priority,text" > "$OUTPUT_FILE"

# Trova tutti i TODO
grep -rn "TODO" models/ routes/ utils/ --include="*.py" 2>/dev/null | \
    grep -v "__pycache__" | \
while IFS=: read -r file linenum rest; do
    # Estrai il testo del TODO
    text=$(echo "$rest" | sed 's/.*TODO[: ]*//' | sed 's/"/""/g')
    
    # Categorizza automaticamente
    category="unknown"
    priority="medium"
    
    # Design questions
    if echo "$text" | grep -qiE "verificare|controllare|check|sicuro|giusto|corretto"; then
        category="design_question"
        priority="low"
    # Cleanup/refactor
    elif echo "$text" | grep -qiE "rimuovere|eliminare|remove|pulire|cleanup|refactor"; then
        category="cleanup"
        priority="medium"
    # Feature incomplete
    elif echo "$text" | grep -qiE "aggiungere|implementare|add|implement|creare|create"; then
        category="feature"
        priority="medium"
    # Bug/fix
    elif echo "$text" | grep -qiE "fix|bug|errore|error|problema|problem"; then
        category="bug"
        priority="high"
    # Documentation
    elif echo "$text" | grep -qiE "document|doc|comment"; then
        category="documentation"
        priority="low"
    fi
    
    echo "\"$file\",$linenum,$category,$priority,\"$text\"" >> "$OUTPUT_FILE"
done

echo "=== SUMMARY PER CATEGORIA ==="
echo ""
echo "Categoria       | Count"
echo "----------------|------"
for cat in design_question cleanup feature bug documentation unknown; do
    count=$(grep ",$cat," "$OUTPUT_FILE" 2>/dev/null | wc -l)
    printf "%-15s | %d\n" "$cat" "$count"
done

echo ""
echo "=== SUMMARY PER PRIORITÀ ==="
echo ""
echo "Priorità | Count"
echo "---------|------"
for prio in high medium low; do
    count=$(grep ",$prio," "$OUTPUT_FILE" 2>/dev/null | wc -l)
    printf "%-8s | %d\n" "$prio" "$count"
done

echo ""
echo "=== TODO AD ALTA PRIORITÀ ==="
grep ",high," "$OUTPUT_FILE" 2>/dev/null | head -10 || echo "Nessuno"

echo ""
echo "=== DETTAGLIO PER FILE ==="
echo ""
echo "File                                          | Count"
echo "----------------------------------------------|------"
cut -d',' -f1 "$OUTPUT_FILE" | tail -n +2 | sort | uniq -c | sort -rn | head -15 | \
    awk '{printf "%-45s | %d\n", $2, $1}'

echo ""
echo "=============================================="
echo "Report generato: $OUTPUT_FILE"
echo "Totale TODO: $(tail -n +2 "$OUTPUT_FILE" | wc -l)"
echo "=============================================="
