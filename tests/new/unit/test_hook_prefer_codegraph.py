"""L'hook che manda le ricerche nel codice Python al grafo (`prefer-codegraph.sh`).

Due difetti presidiati:

- dove `.codegraph/` non esiste (clone fresco, sessione nel cloud) l'hook
  rifiutava lo stesso, mandando a uno strumento che lì non c'è;
- spezzava il comando anche sui `\\|` delle regex, staccando il pattern dal
  percorso: `grep "a\\|b" models/x.py` passava, `grep "scripts/\\|y" doc.md`
  veniva bloccato.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "prefer-codegraph.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="l'hook richiede bash e jq",
)


def _decisione(comando: str, progetto: Path) -> str:
    risultato = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_input": {"command": comando}}),
        capture_output=True,
        text=True,
        env={
            "CLAUDE_PROJECT_DIR": str(progetto),
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        },
        check=True,
    )
    if not risultato.stdout.strip():
        return "allow"
    return json.loads(risultato.stdout)["hookSpecificOutput"]["permissionDecision"]


@pytest.fixture
def con_grafo(tmp_path: Path) -> Path:
    (tmp_path / ".codegraph").mkdir()
    return tmp_path


@pytest.mark.parametrize(
    "comando, attesa",
    [
        ('grep -rn "x" models/', "deny"),
        ('ls && grep -rn "y" routes/', "deny"),
        ('grep -n "foo\\|bar" models/base.py', "deny"),
        ('grep -n "python scripts/x\\|y" models/a/CLAUDE.md', "allow"),
        ('grep "x\\|y" README.md', "allow"),
        ("pytest tests/new -q | grep -c passed", "allow"),
        ('grep -rn "x" models/ # codegraph-checked', "allow"),
    ],
)
def test_decisione_con_il_grafo(con_grafo: Path, comando: str, attesa: str) -> None:
    assert _decisione(comando, con_grafo) == attesa


def test_senza_grafo_non_blocca_niente(tmp_path: Path) -> None:
    assert _decisione('grep -rn "x" models/', tmp_path) == "allow"
