"""Un achievement creato da interfaccia deve poter davvero sbloccarsi.

`AchievementService.create_achievement` salva sempre la forma
`{"type": ..., "count": N}`, perche' il form ha un solo campo numerico. Solo i
requisiti *conteggiabili* (`AchievementMetrics.COUNTABLE_TYPES`) usano `count`:

- un tipo **senza resolver** (era il caso di `matches_played`,
  `tournaments_played`, `xp_total`, tutti offerti dal form e mai esistiti come
  metrica) fa tornare `None` a `AchievementMetrics.current_value`, quindi
  l'idoneita' non e' calcolabile e l'achievement non si sblocca **mai**, senza
  errori da nessuna parte;
- un tipo **a logica propria** (`level_reached`, `win_rate`, `weekly_streak`,
  `category_reached`) legge da `requirements` chiavi su misura — `level`,
  `percentage`+`min_matches`, `weeks`, `category` — che quella forma non
  contiene: `level_reached` era offerto dal form e avrebbe fatto `KeyError` al
  primo controllo.

Questi tipi vanno dichiarati nei seed, dove la forma dei requisiti si scrive per
esteso. Il form offre solo cio' che il form sa esprimere.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from models.exceptions import ValidationError
from models.gamification.achievement_metrics import AchievementMetrics
from models.gamification.achievement_service import AchievementService

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FORM = PROJECT_ROOT / "templates/gamification/admin/achievement_form.html"


@pytest.fixture
def utente_senza_storia(db_session):
    """Un utente reale che non ha ancora fatto nulla.

    Serve un utente *esistente*: alcuni resolver passano da
    `UserStatsService.get_user_stats`, che solleva su un id inventato. Ogni
    metrica vale quindi 0 — il che e' il punto: 0 e' un valore, `None` no.
    """
    from models.user.models import User

    utente = User(
        username="senza_storia",
        email="senza_storia@example.test",
        role="player",
    )
    utente.set_password("password")
    db_session.add(utente)
    db_session.flush()
    return utente


def test_ogni_tipo_conteggiabile_ha_un_resolver(utente_senza_storia):
    """COUNTABLE_TYPES e i resolver non devono divergere.

    `None` significa «nessun resolver», ed e' esattamente la condizione che
    rende un achievement impossibile da sbloccare.
    """
    for tipo in sorted(AchievementMetrics.COUNTABLE_TYPES):
        valore = AchievementMetrics.current_value(utente_senza_storia.id, tipo, {})
        assert valore is not None, (
            f"«{tipo}» e' dichiarato conteggiabile ma non ha resolver: "
            "gli achievement con questo requisito non si sbloccherebbero mai."
        )


def test_il_form_offre_solo_tipi_conteggiabili():
    """Il select non deve piu' contenere un elenco scritto a mano."""
    testo = FORM.read_text(encoding="utf-8")
    cablati = re.findall(r'<option value="([a-z_]+)"', testo)
    assert not cablati, (
        "Il form dichiara di nuovo i requirement type a mano: "
        f"{sorted(set(cablati))}. Devono venire da "
        "AchievementMetrics.COUNTABLE_TYPES via la route."
    )
    assert "requirement_types" in testo, "Il form non cicla il vocabolario."


def test_creare_con_un_tipo_non_conteggiabile_viene_rifiutato(db_session):
    """Il servizio rifiuta cio' che non potrebbe mai sbloccarsi."""
    for tipo in ("matches_played", "xp_total", "level_reached", "win_rate"):
        with pytest.raises(ValidationError) as errore:
            AchievementService.create_achievement(
                slug=f"prova_{tipo}",
                name="Prova",
                description="",
                category="match",
                difficulty="common",
                icon_path=None,
                xp_reward=10,
                is_hidden=False,
                is_progressive=False,
                requirement_type=tipo,
                requirement_value=3,
            )
        assert tipo in str(errore.value)


def test_creare_con_un_tipo_conteggiabile_funziona(db_session):
    """Il percorso buono resta percorribile, e salva la forma attesa."""
    achievement = AchievementService.create_achievement(
        slug="prova_conteggiabile",
        name="Prova",
        description="",
        category="match",
        difficulty="common",
        icon_path=None,
        xp_reward=10,
        is_hidden=False,
        is_progressive=False,
        requirement_type="match_wins",
        requirement_value=3,
    )
    requisiti = json.loads(achievement.requirements)
    assert requisiti == {"type": "match_wins", "count": 3}
