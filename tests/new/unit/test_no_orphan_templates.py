"""Nessun template deve restare irraggiungibile.

Al momento della pulizia il repo conteneva 40 template orfani (~2.200 righe):
per lo più i resti della migrazione alla dashboard unificata, con
`templates/player/dashboard.html` che nessuna route renderizzava più e i ~20
componenti che includeva. Erano indistinguibili dai template vivi durante
una ricerca, e almeno una volta hanno fatto diagnosticare male un issue
(#56: il fix sembrava mancante perché si stava leggendo il template morto).

Un template è raggiungibile se una `render_template(...)` lo nomina, oppure
se lo include/estende un template a sua volta raggiungibile.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates"

SKIP_DIRS = {"venv", "node_modules", ".git", "__pycache__", "_archive", ".qoder"}

# `include`/`extends`/`import`/`from` con path letterale.
EDGE = re.compile(r"""(?:include|extends|import|from)\s+["']([^"']+\.html)["']""")
LITERAL_HTML = re.compile(r"""["']([^"']+\.html)["']""")


def _python_files():
    for path in ROOT.rglob("*.py"):
        if not any(part in SKIP_DIRS for part in path.parts):
            yield path


def _all_templates() -> set[str]:
    return {str(p.relative_to(TEMPLATES)) for p in TEMPLATES.rglob("*.html")}


def _roots() -> set[str]:
    """Template nominati da `render_template` o da `template=` (EmailService)."""
    roots: set[str] = set()
    for path in _python_files():
        source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name not in {"render_template", "render_template_string"}:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    roots.add(arg.value)
        # `template="email/reset"` — l'estensione è implicita.
        for match in re.finditer(r'template\s*=\s*["\']([^"\']+)["\']', source):
            value = match.group(1)
            roots.add(value if value.endswith(".html") else value + ".html")
    return roots


def _graph() -> dict[str, set[str]]:
    graph = {}
    for path in TEMPLATES.rglob("*.html"):
        rel = str(path.relative_to(TEMPLATES))
        graph[rel] = set(
            EDGE.findall(path.read_text(encoding="utf-8", errors="ignore"))
        )
    return graph


def _reachable(all_tpl: set[str]) -> set[str]:
    graph = _graph()
    seen: set[str] = set()
    stack = [r for r in _roots() if r in all_tpl]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(
            c for c in graph.get(current, ()) if c in all_tpl and c not in seen
        )
    return seen


@pytest.mark.unit
def test_no_dynamic_template_names_in_render_template():
    """Guardia del guardiano: se qualcuno introduce `render_template(f"...")`
    l'analisi statica smette di essere affidabile e questo test va rivisto
    prima di fidarsi del successivo."""
    offenders = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name != "render_template" or not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                offenders.append(f"{path.relative_to(ROOT)}:{first.lineno}")

    assert not offenders, (
        "render_template con nome non letterale: "
        + ", ".join(offenders)
        + ". L'analisi di raggiungibilità dei template non li vede."
    )


@pytest.mark.unit
def test_no_dynamic_includes_in_templates():
    """Stessa ragione, lato Jinja: `{% include var %}` sfugge al grafo."""
    offenders = []
    dynamic = re.compile(r"\{%-?\s*(?:include|extends)\s+(?!['\"])(\w+)")
    for path in TEMPLATES.rglob("*.html"):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if dynamic.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}")

    assert not offenders, "include/extends con nome dinamico: " + ", ".join(offenders)


@pytest.mark.unit
def test_every_template_is_reachable():
    all_tpl = _all_templates()
    orphans = sorted(all_tpl - _reachable(all_tpl))

    assert not orphans, (
        f"{len(orphans)} template irraggiungibili — nessuna route li rende e "
        "nessun template vivo li include:\n  " + "\n  ".join(orphans)
    )
