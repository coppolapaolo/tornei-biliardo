#!/usr/bin/env python3
"""I pacchetti di requirements.txt sono installati, alla versione giusta?

Uso: venv/bin/python scripts/requirements_check.py requirements.txt

Esce con 0 se e' tutto installato, con 1 se manca qualcosa (una riga per
pacchetto su stdout), con 2 se il controllo non ha potuto rispondere. Lo lancia
`auto_deploy.deps_in_sync` **con l'interprete del venv**: i pacchetti che contano
sono quelli da cui importa la web app, e `importlib.metadata` vede solo quelli
dell'interprete che lo esegue.

Perche' non `pip install --dry-run`: la risposta dipendeva da cosa pip stampa,
e ha sbagliato in entrambe le direzioni. pip 22 non conosceva l'opzione, il
comando falliva e ogni notte si reinstallava tutto; pip 26 la conosce ma con
`-q` zittisce «Would install», quindi un pacchetto mancante risultava
installato (2026-09-14). Qui la grammatica dei requisiti e' quella di
`packaging`, la stessa che usa pip, e l'installato si legge dai metadati.

Non importa nulla del progetto: deve girare prima che le dipendenze ci siano.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set

_COMMENTO = re.compile(r"(^|\s+)#.*$")


def _righe_logiche(righe: Iterable[str]) -> List[str]:
    """Unisce le continuazioni con `\\`, toglie commenti e righe vuote."""
    logiche: List[str] = []
    in_corso = ""
    for grezza in righe:
        riga = _COMMENTO.sub("", grezza.rstrip("\n"))
        if riga.endswith("\\"):
            in_corso += riga[:-1] + " "
            continue
        riga = (in_corso + riga).strip()
        in_corso = ""
        if riga:
            logiche.append(riga)
    if in_corso.strip():
        logiche.append(in_corso.strip())
    return logiche


def missing_requirements(
    righe: Iterable[str],
    installati: Mapping[str, str],
    ambiente: Optional[Mapping[str, str]] = None,
) -> List[str]:
    """I requisiti non soddisfatti, uno per riga con il motivo.

    `installati` e' nome → versione; i nomi si confrontano normalizzati, quindi
    `Flask_SQLAlchemy` e `flask-sqlalchemy` coincidono. Le opzioni di pip
    (`-r`, `-e`, `--index-url` …) si saltano: i file inclusi li espande
    `read_requirement_lines`. Una riga che non si riesce a interpretare conta
    come mancante, perche' darla per installata sarebbe il difetto di prima.
    """
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import InvalidVersion, Version

    per_nome = {canonicalize_name(nome): ver for nome, ver in installati.items()}
    ambiente_marker = dict(ambiente) if ambiente is not None else None
    mancanti: List[str] = []

    for riga in _righe_logiche(righe):
        if riga.startswith("-"):
            continue
        # `pkg==1.0 --hash=sha256:...`: le opzioni in coda non sono il requisito.
        requisito = re.split(r"\s+--", riga, maxsplit=1)[0].strip()
        try:
            req = Requirement(requisito)
        except InvalidRequirement:
            mancanti.append(f"{riga}: riga non interpretabile")
            continue

        if req.marker is not None and not req.marker.evaluate(ambiente_marker):
            continue

        versione = per_nome.get(canonicalize_name(req.name))
        if versione is None:
            mancanti.append(f"{requisito}: non installato")
            continue
        # Un riferimento diretto (`pkg @ url`) non porta una versione da confrontare.
        if req.url or not req.specifier:
            continue
        try:
            soddisfatto = req.specifier.contains(Version(versione), prereleases=True)
        except InvalidVersion:
            soddisfatto = False
        if not soddisfatto:
            mancanti.append(f"{requisito}: installato {versione}")

    return mancanti


def read_requirement_lines(
    percorso: Path, _visti: Optional[Set[Path]] = None
) -> List[str]:
    """Le righe del file, con gli `-r altro.txt` espansi nel punto in cui compaiono."""
    visti = _visti if _visti is not None else set()
    percorso = percorso.resolve()
    if percorso in visti:
        return []
    visti.add(percorso)

    righe: List[str] = []
    for riga in _righe_logiche(percorso.read_text(encoding="utf-8").splitlines()):
        incluso = re.match(r"^(?:-r|--requirement)(?:\s+|=)?(\S+)$", riga)
        if incluso:
            righe.extend(
                read_requirement_lines(percorso.parent / incluso.group(1), visti)
            )
        else:
            righe.append(riga)
    return righe


def installed_distributions() -> Dict[str, str]:
    """Nome → versione dei pacchetti visibili a questo interprete."""
    from importlib.metadata import distributions

    installati: Dict[str, str] = {}
    for dist in distributions():
        nome = dist.metadata["Name"]
        if nome:
            installati[nome] = dist.version
    return installati


def main(argv: List[str]) -> int:
    if len(argv) != 1:
        print("uso: requirements_check.py <requirements.txt>")
        return 2
    try:
        righe = read_requirement_lines(Path(argv[0]))
        mancanti = missing_requirements(righe, installed_distributions())
    except ImportError as e:
        print(
            "controllo non riuscito, `packaging` non importabile in "
            f"{sys.executable}: {e}"
        )
        return 2
    except OSError as e:
        print(f"controllo non riuscito, file dei requisiti non leggibile: {e}")
        return 2
    except Exception as e:  # prudenza: chi chiama deve installare, non tacere
        print(f"controllo non riuscito: {e!r}")
        return 2

    for mancante in mancanti:
        print(mancante)
    return 1 if mancanti else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
