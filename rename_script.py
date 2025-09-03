#!/usr/bin/env python3
"""
Script per rinominare sistematicamente:
- Prova -> Gara
- Tournament/Torneo -> Campionato

Gestisce sia i nomi delle classi che i riferimenti nel codice.
"""

import os
import re
import sys
from pathlib import Path

# Definizione delle sostituzioni
REPLACEMENTS = {
    # Modelli e classi Python (case-sensitive)
    r'\bProva\b': 'Gara',
    r'\bprova\b': 'gara',
    r'\bProve\b': 'Gare',
    r'\bprove\b': 'gare',
    r'\bPROVA\b': 'GARA',
    
    # Tournament -> Campionato
    r'\bTournament\b': 'Campionato',
    r'\btournament\b': 'campionato',
    r'\bTournaments\b': 'Campionati',
    r'\btournaments\b': 'campionati',
    r'\bTOURNAMENT\b': 'CAMPIONATO',
    
    # Torneo -> Campionato (italiano)
    r'\bTorneo\b': 'Campionato',
    r'\btorneo\b': 'campionato',
    r'\bTornei\b': 'Campionati',
    r'\btornei\b': 'campionati',
    r'\bTORNEO\b': 'CAMPIONATO',
    
    # ProvaService -> GaraService
    r'\bProvaService\b': 'GaraService',
    r'\bProvaStatus\b': 'GaraStatus',
    
    # Nomi di file/percorsi
    r'prova_': 'gara_',
    r'_prova': '_gara',
    r'tournament_': 'campionato_',
    r'_tournament': '_campionato',
    r'torneo_': 'campionato_',
    r'_torneo': '_campionato',
}

# File da escludere
EXCLUDE_PATTERNS = [
    'venv/', '.git/', '__pycache__/', '.pytest_cache/', 'htmlcov/',
    'rename_script.py',  # Questo script stesso
    '.pyc', '.pyo', '.db', '.sqlite'
]

def should_process_file(filepath):
    """Determina se un file deve essere processato."""
    filepath_str = str(filepath)
    
    # Escludi percorsi
    for pattern in EXCLUDE_PATTERNS:
        if pattern in filepath_str:
            return False
    
    # Includi solo file di codice e documentazione
    extensions = ['.py', '.html', '.md', '.txt', '.yml', '.yaml', '.json']
    return any(filepath_str.endswith(ext) for ext in extensions)

def rename_in_file(filepath):
    """Applica le sostituzioni nel contenuto di un file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Applica tutte le sostituzioni
        for pattern, replacement in REPLACEMENTS.items():
            content = re.sub(pattern, replacement, content)
        
        # Scrivi solo se ci sono state modifiche
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Errore nel processare {filepath}: {e}")
        return False

def rename_files_and_dirs(root_dir):
    """Rinomina file e directory che contengono i termini da sostituire."""
    renames = []
    
    # Prima raccogli tutti i rinominamenti necessari
    for root, dirs, files in os.walk(root_dir, topdown=False):
        # Salta directory escluse
        dirs[:] = [d for d in dirs if not any(excl in os.path.join(root, d) for excl in EXCLUDE_PATTERNS)]
        
        # File
        for filename in files:
            new_name = filename
            for pattern, replacement in REPLACEMENTS.items():
                new_name = re.sub(pattern, replacement, new_name)
            
            if new_name != filename:
                old_path = Path(root) / filename
                new_path = Path(root) / new_name
                if should_process_file(old_path):
                    renames.append((old_path, new_path))
        
        # Directory
        for dirname in dirs:
            new_name = dirname
            for pattern, replacement in REPLACEMENTS.items():
                new_name = re.sub(pattern, replacement, new_name)
            
            if new_name != dirname:
                old_path = Path(root) / dirname
                new_path = Path(root) / new_name
                renames.append((old_path, new_path))
    
    return renames

def main():
    """Funzione principale."""
    root_dir = Path.cwd()
    
    print("=== RINOMINAMENTO PROVA->GARA, TOURNAMENT/TORNEO->CAMPIONATO ===\n")
    
    # Fase 1: Rinomina contenuti dei file
    print("Fase 1: Aggiornamento contenuti dei file...")
    modified_count = 0
    
    for filepath in root_dir.rglob('*'):
        if filepath.is_file() and should_process_file(filepath):
            if rename_in_file(filepath):
                print(f"  ✓ {filepath.relative_to(root_dir)}")
                modified_count += 1
    
    print(f"\n  Modificati {modified_count} file")
    
    # Fase 2: Rinomina file e directory
    print("\nFase 2: Rinominamento file e directory...")
    renames = rename_files_and_dirs(root_dir)
    
    for old_path, new_path in renames:
        try:
            old_path.rename(new_path)
            print(f"  ✓ {old_path.relative_to(root_dir)} -> {new_path.name}")
        except Exception as e:
            print(f"  ✗ Errore nel rinominare {old_path}: {e}")
    
    print(f"\n  Rinominati {len(renames)} file/directory")
    
    print("\n=== COMPLETATO ===")
    print("\nNOTA: Ricordati di:")
    print("  1. Aggiornare eventuali migrazioni del database")
    print("  2. Verificare i nomi delle tabelle nel database")
    print("  3. Testare l'applicazione")
    print("  4. Committare i cambiamenti")

if __name__ == "__main__":
    main()