#!/bin/bash
# audit_deprecated.sh - Trova e analizza metodi deprecati
# Usage: ./scripts/audit/audit_deprecated.sh

set -e
cd "$(dirname "$0")/../.."

echo "=============================================="
echo "AUDIT METODI DEPRECATI"
echo "Data: $(date)"
echo "=============================================="
echo ""

echo "=== 1. DEFINIZIONI METODI DEPRECATI ==="
echo "Metodi marcati come DEPRECATED nel codice:"
echo ""
grep -rn "DEPRECATED" models/ routes/ --include="*.py" -B 1 -A 5 2>/dev/null | head -100 || echo "Nessuno trovato"

echo ""
echo "=== 2. CONTEGGIO UTILIZZI PER METODO ==="
echo ""

deprecated_methods=(
    "reset_to_pending"
    "get_table_count_for_gara"
    "get_winning_score"
    "is_match_finished"
)

for method in "${deprecated_methods[@]}"; do
    echo "--- $method ---"
    # Conta utilizzi escludendo definizioni, commenti e test
    count=$(grep -rn "$method" --include="*.py" 2>/dev/null | \
            grep -v "def $method\|DEPRECATED\|#.*$method\|test_\|tests/" | wc -l)
    echo "Utilizzi in produzione: $count"
    
    if [ "$count" -gt 0 ]; then
        echo "Dettaglio:"
        grep -rn "$method" --include="*.py" 2>/dev/null | \
            grep -v "def $method\|DEPRECATED\|#.*$method\|test_\|tests/" | head -10
    fi
    echo ""
done

echo "=== 3. WARNINGS DEPRECATION ==="
echo "File che usano warnings.warn per deprecation:"
grep -rln "DeprecationWarning\|warnings.warn" models/ routes/ --include="*.py" 2>/dev/null || echo "Nessuno"

echo ""
echo "=== 4. SUMMARY ==="
total_deprecated=$(grep -rn "DEPRECATED" models/ routes/ --include="*.py" 2>/dev/null | grep "def " | wc -l)
echo "Totale metodi deprecati definiti: $total_deprecated"

echo ""
echo "=============================================="
echo "AUDIT COMPLETATO"
echo "=============================================="
