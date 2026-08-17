"""Categoria e difficolta' di un achievement si leggono, e si leggono tradotte.

Due guasti gemelli, entrambi invisibili a chi non apra la pagina:

- la colonna «Difficolta'» dell'elenco amministrativo era **sempre vuota**: i
  rami confrontavano `bronze`/`silver`/`gold`/`platinum`/`diamond`, un
  vocabolario che `AchievementDifficulty` non ha mai avuto
  (`common`/`uncommon`/`rare`/`epic`/`legendary`). Nessun `{% else %}`, quindi
  nessun errore: solo una cella bianca;
- le tendine del form di creazione mostravano il **valore grezzo** dell'enum
  (`skill`, `legendary`), fuori da `_()` e quindi in inglese anche per chi
  legge in italiano.

Le etichette esistevano gia', in un posto solo:
`templates/components/_gamification_labels.html`. Il test verifica che le
pagine le usino davvero, cosi' un domani chi rinomina un membro dell'enum vede
fallire questo invece di scoprire una cella vuota in produzione.
"""

from __future__ import annotations

import uuid

import pytest

from models import User
from models.gamification.models import (
    Achievement,
    AchievementCategory,
    AchievementDifficulty,
)
from models.user.role_enum import UserRole


@pytest.fixture
def amministratore(db_session) -> User:
    codice = str(uuid.uuid4())[:8]
    utente = User(
        username=f"admin_{codice}",
        email=f"admin_{codice}@test.com",
        role=UserRole.ADMIN.value,
    )
    utente.set_password("admin123")
    db_session.add(utente)
    db_session.commit()
    return utente


@pytest.fixture
def achievement_leggendario(db_session) -> Achievement:
    achievement = Achievement(
        slug=f"prova_{str(uuid.uuid4())[:8]}",
        name="Prova di difficolta'",
        description="Serve solo a comparire nell'elenco amministrativo",
        category=AchievementCategory.SKILL,
        difficulty=AchievementDifficulty.LEGENDARY,
        xp_reward=100,
        requirements='{"type": "match_wins", "count": 1}',
    )
    db_session.add(achievement)
    db_session.commit()
    return achievement


def _entra(client, utente: User) -> None:
    client.post(
        "/auth/login",
        data={"username": utente.username, "password": "admin123"},
        follow_redirects=True,
    )


@pytest.mark.integration
def test_elenco_mostra_categoria_e_difficolta_tradotte(
    client, amministratore, achievement_leggendario
):
    """La riga dell'elenco non deve avere celle vuote ne' parole inglesi."""
    _entra(client, amministratore)

    risposta = client.get("/gamification/admin/achievements")
    assert risposta.status_code == 200
    pagina = risposta.get_data(as_text=True)

    assert "Leggendario" in pagina, (
        "La colonna «Difficolta'» e' di nuovo vuota: i rami del template non "
        "corrispondono ai valori di AchievementDifficulty."
    )
    assert "Abilità" in pagina, "La categoria e' mostrata col valore grezzo dell'enum."
    assert ">legendary<" not in pagina and ">skill<" not in pagina


@pytest.mark.integration
def test_form_mostra_le_tendine_tradotte(client, amministratore):
    """Le opzioni si leggono in italiano, i valori inviati restano quelli."""
    _entra(client, amministratore)

    risposta = client.get("/gamification/admin/achievements/create")
    assert risposta.status_code == 200
    pagina = risposta.get_data(as_text=True)

    # Etichette visibili tradotte...
    for etichetta in ("Partite", "Traguardi", "Comune", "Leggendario"):
        assert etichetta in pagina, f"Etichetta mancante nelle tendine: {etichetta}"

    # ...e valori inviati invariati: la route legge `category`/`difficulty`
    # come nomi minuscoli dei membri dell'enum.
    assert 'value="milestone"' in pagina
    assert 'value="legendary"' in pagina
