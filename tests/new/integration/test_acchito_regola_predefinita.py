"""La regola di inizio proposta a chi crea è l'acchito, non il primo giocatore.

Rilievo della gara del 2026-09-23: nei tornei si tira l'acchito, e il
direttore doveva ricordarsi ogni volta di cambiarla. Il default vale per ciò
che **nasce** — i moduli di creazione e le colonne delle righe nuove. Non
cambia ciò che esiste già: una gara senza campionato nata prima dell'ADR-056
ha `start_rule` NULL, e per lei NULL ha sempre voluto dire «apre il primo
giocatore». Spostare quel ripiego avrebbe fatto comparire le domande
dell'acchito su gare già cominciate.
"""

import re
from datetime import date
from pathlib import Path

import pytest

from models.competition.models import Gara
from models.match.break_rules import DEFAULT_START_RULE, StartRule
from models.status_enum import Discipline, GaraStatus

pytestmark = pytest.mark.integration

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


def test_il_default_e_l_acchito():
    assert DEFAULT_START_RULE is StartRule.LAG


def test_la_gara_storica_senza_regola_resta_al_primo_giocatore(db_session):
    gara = Gara(
        number=1,
        name="Gara nata prima dell'ADR-056",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        status=GaraStatus.PLAYING.value,
    )
    db_session.add(gara)
    db_session.commit()
    assert gara.start_rule is None
    assert gara.effective_start_rule is StartRule.FIRST_PLAYER


@pytest.mark.parametrize(
    "template",
    [
        "admin/campionato_wizard_step2.html",
        "admin/gara_create_standalone.html",
        "individual_match/create_proposal.html",
    ],
)
def test_i_moduli_di_creazione_propongono_il_default(template):
    """La preselezione si legge dal default, non da un membro scritto a mano.

    Scritto a mano, cambiare il default non cambiava i moduli: è così che
    tre schermate su quattro avrebbero continuato a proporre «Primo
    giocatore».
    """
    testo = (TEMPLATES / template).read_text(encoding="utf-8")
    assert "StartRule.FIRST_PLAYER" not in testo
    assert "DEFAULT_START_RULE" in testo


def test_la_gara_singola_nuova_preseleziona_l_acchito(client, db_session):
    from models.user.models import User
    from models.user.role_enum import UserRole

    admin = User(
        username="acchito_admin",
        email="acchito_admin@test.local",
        role=UserRole.ADMIN.value,
    )
    admin.set_password("pw12345")
    db_session.add(admin)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = admin.get_id()

    risposta = client.get("/admin/gara/create_standalone")
    assert risposta.status_code == 200
    select = re.search(
        r'<select[^>]*name="start_rule".*?</select>',
        risposta.get_data(as_text=True),
        re.S,
    )
    assert select is not None
    assert re.search(r'value="lag"\s+selected', select.group(0))
    assert not re.search(r'value="first_player"\s+selected', select.group(0))
