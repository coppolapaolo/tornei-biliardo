"""«Valida il risultato» aspetta tre secondi con «Annulla», come il tocco che chiude.

Rilievo della gara del 2026-09-23: segnando i punteggi dalla card il
direttore aveva tre secondi per ripensarci, validando no — eppure validare
chiude la partita quanto l'ultimo +. Il comportamento dell'attesa è provato in
jsdom (`tests/frontend/test_card_partita.cjs`); qui si prova che la pagina
vera la usa, e che il suo JavaScript inline resta valido: un errore di
sintassi lì spegne l'intera pagina del direttore.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole
from tests.new.integration.test_chiusura_gara_direttore import _gara_a_un_turno

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user("attesa_admin", "attesa_admin@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "attesa_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def _pagina_con_partita_da_validare(admin_client, db_session):
    gara = _gara_a_un_turno(db_session, GaraStatus.PLAYING.value, spareggio=False)
    partita = db_session.query(Match).filter_by(gara_id=gara.id).first()
    # Alla distanza ma non chiusa: chiusa dal segnapunti senza le due firme.
    partita.status = MatchStatus.PLAYING.value
    partita.winner_id = None
    db_session.commit()
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    return partita.id, html


def test_valida_passa_dall_attesa(admin_client, db_session):
    match_id, html = _pagina_con_partita_da_validare(admin_client, db_session)
    assert f"validaDallaCard({match_id}, this)" in html
    corpo = html[html.index("function validaDallaCard(") :]
    corpo = corpo[: corpo.index("function spedisciValidazione(")]
    assert "CardPartita.attendi(" in corpo
    assert "/validate" not in corpo, "la richiesta parte solo dopo l'attesa"


@pytest.mark.skipif(shutil.which("node") is None, reason="serve node")
def test_il_javascript_della_pagina_resta_valido(admin_client, db_session, tmp_path):
    _, html = _pagina_con_partita_da_validare(admin_client, db_session)
    # Solo il JavaScript: i blocchi `type="application/json"` sono dati.
    inline = re.findall(
        r"<script(?![^>]*\b(?:src|type)=)[^>]*>(.*?)</script>", html, re.S
    )
    assert inline
    for n, codice in enumerate(inline):
        file = tmp_path / f"s{n}.js"
        file.write_text(codice, encoding="utf-8")
        esito = subprocess.run(
            ["node", "--check", str(file)], capture_output=True, text=True
        )
        assert esito.returncode == 0, esito.stderr
