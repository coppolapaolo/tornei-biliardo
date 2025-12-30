#!/bin/bash
# verify_audit_completion.sh - Verifica completamento audit
# Usage: ./scripts/audit/verify_audit_completion.sh

set -e
cd "$(dirname "$0")/../.."

echo "=============================================="
echo "VERIFICA COMPLETAMENTO AUDIT"
echo "Data: $(date)"
echo "=============================================="
echo ""

PASSED=0
FAILED=0
WARNINGS=0

check_pass() {
    echo "✅ PASS: $1"
    PASSED=$((PASSED + 1))
}

check_fail() {
    echo "❌ FAIL: $1"
    FAILED=$((FAILED + 1))
}

check_warn() {
    echo "⚠️  WARN: $1"
    WARNINGS=$((WARNINGS + 1))
}

echo "=== 1. DOCUMENTAZIONE ==="

# 1.1 ADR directory unica
if [ -d "docs/decisions" ]; then
    check_fail "docs/decisions/ esiste ancora (dovrebbe essere consolidato in docs/adr/)"
else
    check_pass "docs/decisions/ rimosso o consolidato"
fi

# 1.2 ADR-001 aggiornato
if grep -q "amalfi/" docs/adr/ADR-001-*.md 2>/dev/null; then
    if grep -q "Legacy\|removed\|migrated" docs/adr/ADR-001-*.md 2>/dev/null; then
        check_pass "ADR-001 aggiornato con nota sulla migrazione"
    else
        check_fail "ADR-001 contiene riferimento a amalfi/ senza nota sulla migrazione"
    fi
else
    check_pass "ADR-001 non contiene riferimento obsoleto a amalfi/"
fi

# 1.3 README ADR aggiornato
if [ -f "docs/adr/README.md" ] || [ -f "docs/decisions/README.md" ]; then
    readme_file=$(ls docs/adr/README.md docs/decisions/README.md 2>/dev/null | head -1)
    if grep -q "nessun ADR ancora" "$readme_file" 2>/dev/null; then
        check_fail "README ADR dice 'nessun ADR ancora' ma ci sono ADR"
    else
        check_pass "README ADR ha indice aggiornato"
    fi
else
    check_warn "Nessun README.md trovato per ADR"
fi

echo ""
echo "=== 2. FILE TRACKING ==="

# 2.1 coverage.json
if [ -d ".git" ]; then
    if git ls-files --error-unmatch coverage.json &>/dev/null 2>&1; then
        check_fail "coverage.json è ancora tracciato da Git"
    else
        check_pass "coverage.json non tracciato da Git"
    fi
else
    if [ -f "coverage.json" ]; then
        check_warn "coverage.json esiste (verificare se tracciato quando git disponibile)"
    else
        check_pass "coverage.json non presente"
    fi
fi

# 2.2 coverage.json in gitignore
if grep -q "coverage.json" .gitignore 2>/dev/null; then
    check_pass "coverage.json in .gitignore"
else
    check_fail "coverage.json non in .gitignore"
fi

echo ""
echo "=== 3. CODICE DEPRECATO ==="

# 3.1 Riferimento admin_backup.py
if grep -rq "admin_backup" routes/ --include="*.py" 2>/dev/null; then
    check_fail "Riferimento a admin_backup.py ancora presente"
else
    check_pass "Nessun riferimento a admin_backup.py"
fi

# 3.2 Utilizzi metodi deprecati in produzione
deprecated_usage=$(grep -rn "reset_to_pending\|get_table_count_for_gara" models/ routes/ --include="*.py" 2>/dev/null | \
    grep -v "def \|DEPRECATED\|#\|test_" | wc -l)
if [ "$deprecated_usage" -gt 0 ]; then
    check_warn "Trovati $deprecated_usage utilizzi di metodi deprecati"
else
    check_pass "Nessun utilizzo di metodi deprecati in produzione"
fi

echo ""
echo "=== 4. DIMENSIONI FILE ==="

# 4.1 File > 1000 linee (esclusi test)
# 1 file accettato: dashboard/services.py (alta coesione)
large_files=$(find . -name "*.py" -type f \
    ! -path "./.git/*" ! -path "./venv/*" ! -path "./tests/*" \
    -exec wc -l {} \; 2>/dev/null | awk '$1 > 1000' | wc -l)
if [ "$large_files" -gt 1 ]; then
    check_warn "$large_files file > 1000 linee (target: ≤1)"
else
    check_pass "$large_files file > 1000 linee (≤1 accettato: dashboard/services.py)"
fi

# 4.2 File > 2000 linee (critico)
very_large_files=$(find . -name "*.py" -type f \
    ! -path "./.git/*" ! -path "./venv/*" ! -path "./tests/*" \
    -exec wc -l {} \; 2>/dev/null | awk '$1 > 2000' | wc -l)
if [ "$very_large_files" -gt 0 ]; then
    check_fail "$very_large_files file > 2000 linee (critico)"
else
    check_pass "Nessun file > 2000 linee"
fi

echo ""
echo "=== 5. IMPORT CIRCOLARI ==="

circular_imports=$(grep -rn "# Local import to avoid circular" --include="*.py" 2>/dev/null | wc -l)
if [ "$circular_imports" -gt 10 ]; then
    check_warn "$circular_imports workaround per import circolari (target: <10)"
elif [ "$circular_imports" -gt 0 ]; then
    check_pass "$circular_imports workaround per import circolari (accettabile)"
else
    check_pass "Nessun workaround per import circolari"
fi

echo ""
echo "=== 6. TODO COMMENTS ==="

todo_count=$(grep -rn "TODO" models/ routes/ utils/ --include="*.py" 2>/dev/null | grep -v "__pycache__" | wc -l)
if [ "$todo_count" -gt 30 ]; then
    check_warn "$todo_count TODO comments (target: <30)"
elif [ "$todo_count" -gt 0 ]; then
    check_pass "$todo_count TODO comments (accettabile)"
else
    check_pass "Nessun TODO comment"
fi

echo ""
echo "=== 7. TYPE CHECKING ==="

if command -v pyright &>/dev/null; then
    pyright_errors=$(pyright models/ routes/ 2>&1 | grep -c "error:" || true)
    if [ "$pyright_errors" -gt 0 ]; then
        check_warn "$pyright_errors errori pyright"
    else
        check_pass "Nessun errore pyright"
    fi
else
    check_warn "pyright non installato - skip verifica"
fi

echo ""
echo "=============================================="
echo "RISULTATO FINALE"
echo "=============================================="
echo ""
echo "✅ Passati:   $PASSED"
echo "❌ Falliti:   $FAILED"
echo "⚠️  Warning:  $WARNINGS"
echo ""

if [ "$FAILED" -eq 0 ]; then
    if [ "$WARNINGS" -eq 0 ]; then
        echo "🎉 AUDIT COMPLETATO CON SUCCESSO!"
        exit 0
    else
        echo "✅ AUDIT COMPLETATO CON WARNING"
        exit 0
    fi
else
    echo "❌ AUDIT FALLITO - $FAILED CHECK NON SUPERATI"
    exit 1
fi
