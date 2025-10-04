#!/usr/bin/env python3
"""
Script per migrare automaticamente i formati data dai template.

Sostituisce:
- .strftime('%d/%m/%Y') → |date_local
- .strftime('%d/%m/%Y %H:%M') → |datetime_local
- .strftime('%Y-%m-%d %H:%M') → |datetime_local
- .strftime('%H:%M') → |time_local
- .strftime('%d/%m') → |date_local (formato breve)

Usage:
    python scripts/migrate_date_formatting.py [--dry-run] [--file FILEPATH]
"""

import argparse
import re
from pathlib import Path
from typing import List, Tuple


# Pattern di sostituzione (regex, replacement)
REPLACEMENTS: List[Tuple[str, str]] = [
    # Data e ora con testo (es. "alle")
    (r"\.strftime\(['\"]%d/%m/%Y alle %H:%M['\"]\)", "|datetime_local"),

    # Data e ora completa
    (r"\.strftime\(['\"]%d/%m/%Y %H:%M['\"]\)", "|datetime_local"),
    (r"\.strftime\(['\"]%Y-%m-%d %H:%M['\"]\)", "|datetime_local"),

    # Data e ora breve (solo giorno/mese e ora)
    (r"\.strftime\(['\"]%d/%m %H:%M['\"]\)", "|datetime_local"),

    # Solo data
    (r"\.strftime\(['\"]%d/%m/%Y['\"]\)", "|date_local"),
    (r"\.strftime\(['\"]%Y-%m-%d['\"]\)", "|date_local"),
    (r"\.strftime\(['\"]%d/%m['\"]\)", "|date_local"),

    # Solo ora
    (r"\.strftime\(['\"]%H:%M['\"]\)", "|time_local"),
]


def migrate_file(filepath: Path, dry_run: bool = False) -> Tuple[int, List[str]]:
    """
    Migra un singolo file template.

    Returns:
        Tuple di (numero_sostituzioni, lista_modifiche)
    """
    content = filepath.read_text(encoding='utf-8')
    original_content = content
    changes = []

    for pattern, replacement in REPLACEMENTS:
        matches = re.findall(pattern, content)
        if matches:
            content = re.sub(pattern, replacement, content)
            changes.append(f"  - {len(matches)}x '{pattern}' → '{replacement}'")

    num_changes = len(changes)

    if num_changes > 0 and not dry_run:
        filepath.write_text(content, encoding='utf-8')

    return num_changes, changes


def find_template_files(templates_dir: Path) -> List[Path]:
    """Trova tutti i file .html nella directory templates."""
    return sorted(templates_dir.rglob("*.html"))


def main():
    parser = argparse.ArgumentParser(
        description="Migra formati data nei template da strftime a filtri locali"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra le modifiche senza applicarle"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Migra solo un file specifico (path relativo da templates/)"
    )

    args = parser.parse_args()

    # Trova la directory templates
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    templates_dir = project_root / "templates"

    if not templates_dir.exists():
        print(f"❌ Directory templates non trovata: {templates_dir}")
        return 1

    # Trova i file da processare
    if args.file:
        files = [templates_dir / args.file]
        if not files[0].exists():
            print(f"❌ File non trovato: {files[0]}")
            return 1
    else:
        files = find_template_files(templates_dir)

    print(f"🔍 Trovati {len(files)} file template da analizzare\n")

    if args.dry_run:
        print("⚠️  MODALITÀ DRY-RUN - Nessuna modifica verrà applicata\n")

    total_files_changed = 0
    total_changes = 0

    for filepath in files:
        num_changes, changes = migrate_file(filepath, dry_run=args.dry_run)

        if num_changes > 0:
            total_files_changed += 1
            total_changes += num_changes

            rel_path = filepath.relative_to(templates_dir)
            status = "📋 [DRY-RUN]" if args.dry_run else "✅"
            print(f"{status} {rel_path}")
            for change in changes:
                print(change)
            print()

    # Riepilogo
    print("=" * 60)
    print(f"📊 RIEPILOGO:")
    print(f"   - File modificati: {total_files_changed}")
    print(f"   - Sostituzioni totali: {total_changes}")

    if args.dry_run and total_changes > 0:
        print("\n💡 Per applicare le modifiche, esegui senza --dry-run")
    elif total_changes > 0:
        print("\n✅ Migrazione completata con successo!")
    else:
        print("\n✨ Nessuna modifica necessaria - tutti i template sono già aggiornati!")

    return 0


if __name__ == "__main__":
    exit(main())
