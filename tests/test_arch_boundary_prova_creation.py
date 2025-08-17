from __future__ import annotations

from pathlib import Path
import tokenize
import token
import io

# File dove è CONSENTITO istanziare direttamente Prova(...)
ALLOWED_FILES = {
    "models/competition/models.py",
    "models/competition/services.py",
    # Se in futuro introduci una factory interna:
    # "models/competition/factories.py",
}

IGNORED_DIR_SEGMENTS = ("/venv/", "__pycache__", "migrations/", "tests/")


def _has_prova_constructor_call(code: str) -> bool:
    """
    Rileva una chiamata a Prova(...) analizzando i token Python.
    Evita falsi positivi in commenti/docstring e in 'import'.
    """
    toks = list(tokenize.generate_tokens(io.StringIO(code).readline))
    n = len(toks)
    i = 0

    NON_SIG = {
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.COMMENT,
    }

    while i < n:
        tok = toks[i]
        if tok.type == token.NAME and tok.string == "Prova":
            # Escludi 'import Prova' o 'from ... import Prova' sulla stessa riga
            line_no = tok.start[0]
            j = i - 1
            saw_import_on_line = False
            while j >= 0 and toks[j].start[0] == line_no:
                if toks[j].type == token.NAME and toks[j].string == "import":
                    saw_import_on_line = True
                    break
                j -= 1
            if saw_import_on_line:
                i += 1
                continue

            # Cerca il prossimo token significativo
            k = i + 1
            while k < n and toks[k].type in NON_SIG:
                k += 1
            if k < n and toks[k].type == token.OP and toks[k].string == "(":
                return True
        i += 1
    return False


def test_no_direct_prova_constructor_outside_services():
    repo_root = Path(__file__).resolve().parents[1]
    violations: list[str] = []

    for path in repo_root.rglob("*.py"):
        rel = path.relative_to(repo_root).as_posix()

        # Escludi cartelle non rilevanti
        if any(seg in rel for seg in IGNORED_DIR_SEGMENTS):
            continue

        # Consenti i file esplicitamente whitelisted
        if rel in ALLOWED_FILES:
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            # Se non leggibile, salta (non blocchiamo la pipeline)
            continue

        if _has_prova_constructor_call(text):
            violations.append(rel)

    assert not violations, (
        "Creazione diretta di Prova(...) trovata fuori da models/services:\n"
        + "\n".join(f"- {v}" for v in violations)
        + "\nUsa ProvaService.create_prova(...)."
    )
