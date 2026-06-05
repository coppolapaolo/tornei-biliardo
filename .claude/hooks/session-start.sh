#!/bin/bash
# SessionStart hook — prepara l'ambiente per test e linter su Claude Code on the web.
#
# Perché un venv dedicato: l'immagine remota ha setuptools di sistema rotto
# (build wheel fallisce, es. Flask-Mail). Un venv pulito ha build-tools sani.
set -euo pipefail

# Solo nell'ambiente remoto (web). In locale l'utente ha il suo setup.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

VENV="$HOME/.venv-tornei"

# Idempotente: ricostruisce solo se pytest non c'è già (state cache del container).
if [ ! -x "$VENV/bin/pytest" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip setuptools wheel
  "$VENV/bin/pip" install --quiet -r "$CLAUDE_PROJECT_DIR/requirements.txt"
  "$VENV/bin/pip" install --quiet -r "$CLAUDE_PROJECT_DIR/requirements-dev.txt"
fi

# Espone i tool del venv (pytest/pyright/black/flake8/python) e PYTHONPATH
# per tutta la sessione.
echo "export PATH=\"$VENV/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
echo "export PYTHONPATH=\".\"" >> "$CLAUDE_ENV_FILE"
echo "export VIRTUAL_ENV=\"$VENV\"" >> "$CLAUDE_ENV_FILE"
