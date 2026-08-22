"""Nessun file tracciato può essere un symlink che esce dal repository.

Un symlink versionato porta con sé il percorso della macchina di chi lo ha
creato, e `git checkout` lo **materializza ovunque**: se nella destinazione
c'era una directory vera, git la rimuove per farci stare il link.

È successo il 2026-08-22. Un `venv -> /Users/<tizio>/.../tornei-biliardo/venv`
è finito in `main` (PR #212): `.gitignore` aveva `venv/`, che con lo slash
finale copre solo la *directory* e lascia passare un symlink con lo stesso
nome. Su PythonAnywhere lo scheduled task ha fatto `git pull` e il virtualenv
della web app è stato sostituito dal link — che lì non punta a niente:

    bash: venv/bin/python: No such file or directory

Il deploy si è fermato da solo prima del reload (per questo il sito è rimasto
in piedi: il worker già avviato serviva ancora il codice precedente), ma la
venv era da ricostruire a mano. Sulla macchina di partenza il danno è stato
peggiore e meno evidente: lì il link punta alla cartella che lo contiene,
quindi diventa **circolare** e il virtualenv locale sparisce lo stesso.

Il presidio guarda i symlink *tracciati*, non i file sul disco: un link
dentro `.gitignore` non fa male a nessuno — è la versione in indice quella che
viaggia. Un symlink **relativo e interno** al repository resta lecito: quello
punta a qualcosa che il repository stesso contiene, e vale su ogni macchina.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]


def _symlink_tracciati() -> list[tuple[str, str]]:
    """(percorso, destinazione) di ogni symlink presente nell'indice git."""
    righe = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=RADICE,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    trovati = []
    for riga in righe:
        meta, _, percorso = riga.partition("\t")
        # mode 120000 = symlink; il blob contiene la destinazione, non un file
        if not meta.startswith("120000"):
            continue
        blob = meta.split()[1]
        destinazione = subprocess.run(
            ["git", "cat-file", "-p", blob],
            cwd=RADICE,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        trovati.append((percorso, destinazione))
    return trovati


def test_nessun_symlink_tracciato_esce_dal_repository():
    colpevoli = []

    for percorso, destinazione in _symlink_tracciati():
        if os.path.isabs(destinazione):
            colpevoli.append(f"{percorso} -> {destinazione}  (percorso assoluto)")
            continue
        # Relativo: deve restare dentro il repository anche dopo la risoluzione
        partenza = (RADICE / percorso).parent
        risolto = os.path.normpath(partenza / destinazione)
        if not str(risolto).startswith(str(RADICE)):
            colpevoli.append(f"{percorso} -> {destinazione}  (esce dal repository)")

    assert not colpevoli, (
        "Symlink tracciati che puntano fuori dal repository: `git checkout` li "
        "ricrea su ogni macchina, cancellando quel che trova al loro posto.\n"
        "Toglili dall'indice (`git rm --cached <percorso>`) e mettili in "
        "`.gitignore` senza slash finale.\n  " + "\n  ".join(colpevoli)
    )
