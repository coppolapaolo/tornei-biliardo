#!/bin/bash
# file_size_report.sh - Report file Python grandi
# Usage: ./scripts/audit/file_size_report.sh [threshold]
# Default threshold: 500 linee

set -e
cd "$(dirname "$0")/../.."

THRESHOLD=${1:-500}

echo "=============================================="
echo "REPORT DIMENSIONI FILE PYTHON"
echo "Data: $(date)"
echo "Soglia: $THRESHOLD linee"
echo "=============================================="
echo ""

echo "=== FILE PYTHON > $THRESHOLD LINEE ==="
echo ""
echo "LINEE | FILE"
echo "------|------"

find . -name "*.py" -type f \
    ! -path "./.git/*" \
    ! -path "./venv/*" \
    ! -path "./__pycache__/*" \
    -exec wc -l {} \; 2>/dev/null | \
    awk -v threshold="$THRESHOLD" '$1 > threshold {printf "%5d | %s\n", $1, $2}' | \
    sort -rn

echo ""
echo "=== STATISTICHE ==="
total_files=$(find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" | wc -l)
large_files=$(find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" -exec wc -l {} \; | awk -v t="$THRESHOLD" '$1 > t' | wc -l)
total_lines=$(find . -name "*.py" -type f ! -path "./.git/*" ! -path "./venv/*" -exec wc -l {} \; | awk '{sum+=$1} END {print sum}')

echo "File Python totali: $total_files"
echo "File > $THRESHOLD linee: $large_files"
echo "Linee totali: $total_lines"

echo ""
echo "=== TOP 10 FILE PIÙ GRANDI ==="
find . -name "*.py" -type f \
    ! -path "./.git/*" \
    ! -path "./venv/*" \
    -exec wc -l {} \; 2>/dev/null | \
    sort -rn | head -10

echo ""
echo "=== CANDIDATI PER DECOMPOSIZIONE (>1000 linee, no test) ==="
find . -name "*.py" -type f \
    ! -path "./.git/*" \
    ! -path "./venv/*" \
    ! -path "./tests/*" \
    -exec wc -l {} \; 2>/dev/null | \
    awk '$1 > 1000 {printf "%5d | %s\n", $1, $2}' | \
    sort -rn

echo ""
echo "=============================================="
echo "REPORT COMPLETATO"
echo "=============================================="
