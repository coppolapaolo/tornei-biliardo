"""
PyTest bootstrap – aggiunge la root del progetto a `sys.path`.

PyTest carica automaticamente *conftest.py* prima di cercare i test,
quindi tutti gli `import models` funzionano anche se la working-dir
durante i test è `tests/`.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent           # cartella del repo
if str(ROOT_DIR) not in sys.path:                    # evita duplicati
    sys.path.insert(0, str(ROOT_DIR))
