"""Chi dirige una gara: il titolare e i co-direttori, in un elenco solo.

Rilievo del 16/10/2026: l'anteprima della vetrina mostrava come
organizzatore il solo co-direttore. `Gara.directors` restituisce le sole
assegnazioni sulla gara, cioè i co-direttori; il titolare sta altrove — su
`gara.director_id` in una gara singola, fra i direttori del campionato in una
gara di campionato. Tre schermate ricostruivano l'elenco ciascuna a modo suo;
ora lo dà `direzione_della_gara`.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara
from models.base import db
from models.campionato.models import Campionato
from models.competition.direzione import direzione_della_gara
from models.competition.showcase_view import costruisci_vetrina
from models.status_enum import EntityType, GaraStatus
from models.user.models import DirectorAssignment, User
from models.user.role_enum import UserRole


def _utente(nome: str) -> User:
    utente = User(
        username=f"{nome}_{uuid.uuid4().hex[:4]}",
        email=f"{nome}_{uuid.uuid4().hex[:6]}@test.local",
        role=UserRole.DIRECTOR.value,
    )
    utente.set_password("pwd12345")
    db.session.add(utente)
    db.session.flush()
    return utente


def _assegna(utente: User, tipo: EntityType, entita_id: int) -> None:
    db.session.add(
        DirectorAssignment(
            user_id=utente.id,
            entity_type=tipo.value,
            entity_id=entita_id,
            assigned_by_id=utente.id,
        )
    )
    db.session.flush()


def _gara(**campi) -> Gara:
    gara = Gara(
        number=1,
        name="Serata",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=5,
        status=GaraStatus.INSCRIPTION.value,
        **campi,
    )
    db.session.add(gara)
    db.session.flush()
    return gara


@pytest.mark.unit
class TestGaraSingola:
    def test_titolare_e_co_direttore(self, db_session):
        titolare, co = _utente("titolare"), _utente("co")
        gara = _gara(director_id=titolare.id)
        _assegna(co, EntityType.GARA, gara.id)

        assert [(d.utente, d.titolare) for d in direzione_della_gara(gara)] == [
            (titolare, True),
            (co, False),
        ]
        assert (
            costruisci_vetrina(gara).organizzatore
            == f"{titolare.username}, {co.username}"
        )

    def test_il_titolare_assegnato_anche_come_co_direttore_compare_una_volta(
        self, db_session
    ):
        titolare = _utente("titolare")
        gara = _gara(director_id=titolare.id)
        _assegna(titolare, EntityType.GARA, gara.id)

        assert [d.utente for d in direzione_della_gara(gara)] == [titolare]


@pytest.mark.unit
class TestGaraDiCampionato:
    def test_direttori_del_campionato_poi_co_direttori_della_gara(self, db_session):
        camp = Campionato(name=f"C {uuid.uuid4().hex[:4]}", campionato_type="amalfi")
        db.session.add(camp)
        db.session.flush()
        del_campionato, co = _utente("camp"), _utente("co")
        _assegna(del_campionato, EntityType.CAMPIONATO, camp.id)
        gara = _gara(campionato_id=camp.id)
        _assegna(co, EntityType.GARA, gara.id)

        assert [(d.utente, d.titolare) for d in direzione_della_gara(gara)] == [
            (del_campionato, True),
            (co, False),
        ]
        assert costruisci_vetrina(gara).organizzatore == (
            f"{del_campionato.username}, {co.username}"
        )

    def test_senza_direttori_nessun_organizzatore(self, db_session):
        assert costruisci_vetrina(_gara()).organizzatore is None
