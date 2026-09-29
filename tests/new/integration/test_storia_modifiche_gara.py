"""La gara si corregge anche con gli iscritti, e la correzione resta scritta.

ADR-075, primo passo. Nasce dalla finale dei playoff del 28/09/2026: creata
con gli iscritti dentro, non se ne poteva cambiare né la sala né chi spacca,
perché `Gara.can_be_modified()` chiudeva il modulo al primo iscritto.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, time, timedelta

import pytest

from models import Gara, Inscription, User
from models.competition.services import GaraService
from models.exceptions import ConflictError
from models.status_enum import GaraStatus
from models.storia.models import SettingsChange
from models.storia.service import StoriaModificheService, serializza
from models.user.role_enum import UserRole
from routes.admin.competition.form_parser import GaraFormParser

pytestmark = pytest.mark.integration


def _utente(db_session, ruolo=UserRole.PLAYER.value) -> User:
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@test.com",
        role=ruolo,
        onboarding_completed=True,
    )
    user.set_password("director123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def direttore(db_session):
    return _utente(db_session, UserRole.DIRECTOR.value)


@pytest.fixture
def gara_con_iscritti(db_session, direttore):
    gara = Gara(
        number=1,
        name="Finale",
        date=date.today() + timedelta(days=10),
        time=time(20, 0),
        discipline="palla_9",
        distance=5,
        is_race_to=True,
        location="Biliardo Centrale",
        status=GaraStatus.SETUP.value,
        director_id=direttore.id,
        rounds_count=3,
        min_participants=2,
        max_participants=8,
    )
    db_session.add(gara)
    db_session.commit()
    for _ in range(4):
        giocatore = _utente(db_session)
        db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
    db_session.commit()
    return gara


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


def _modulo(gara: Gara, **cambi) -> dict:
    """I campi che il modulo di modifica manda, con i valori attuali."""
    dati = {
        "name": gara.name,
        "location": gara.location or "",
        "date": gara.date.isoformat(),
        "time": gara.time.strftime("%H:%M"),
        "available_tables": "",
        "description": gara.description or "",
        "rounds_count": str(gara.rounds_count),
        "min_participants": str(gara.min_participants),
        "max_participants": str(gara.max_participants or ""),
        "entry_fee": str(gara.entry_fee or 0),
        "discipline": gara.discipline,
        "distance": str(gara.distance),
        "withdraw_policy": gara.withdraw_policy or "",
        "has_handicap": "",
        "start_rule": gara.start_rule or "",
        "break_rule": gara.break_rule or "",
        "matchmaking_strategy": gara.matchmaking_strategy,
        "first_round_policy": gara.first_round_policy or "random",
        "odd_number_policy": gara.odd_number_policy or "bye",
        "classification_system": gara.classification_system or "WINS",
        "tiebreaker_until_position": str(gara.tiebreaker_until_position or 3),
        "stato_iniziale": json.dumps(GaraFormParser.valori_attuali(gara)),
    }
    # Le caselle spuntate, come le manda la pagina vera.
    for casella in (
        "anti_rematch_enabled",
        "tiebreaker_enabled",
        "is_race_to_sets",
        "is_multi_set",
        "separate_teammates",
        "third_place_match",
    ):
        if getattr(gara, casella):
            dati[casella] = "on"
    if not gara.is_race_to:
        dati["exact_number"] = "on"
    dati.update(cambi)
    return dati


class TestLaFinaleSiCorregge:
    def test_il_modulo_si_apre_con_gli_iscritti(
        self, client, direttore, gara_con_iscritti
    ):
        _login(client, direttore)
        risposta = client.get(f"/admin/gara/{gara_con_iscritti.id}/edit")
        assert risposta.status_code == 200
        pagina = risposta.get_data(as_text=True)
        assert 'name="stato_iniziale"' in pagina
        assert 'name="motivo"' in pagina
        assert "Storia delle modifiche" in pagina

    def test_sala_e_chi_spacca_cambiano_e_restano_scritti(
        self, client, db_session, direttore, gara_con_iscritti
    ):
        _login(client, direttore)
        gara_id = gara_con_iscritti.id
        client.post(
            f"/admin/gara/{gara_id}/edit",
            data=_modulo(
                gara_con_iscritti,
                location="Sala Nuova",
                break_rule="winner_breaks",
                motivo="La sala centrale è chiusa per lavori",
            ),
        )

        gara = db_session.get(Gara, gara_id)
        assert gara.location == "Sala Nuova"
        assert gara.break_rule == "winner_breaks"

        voci = StoriaModificheService.voci_della_gara(gara_id)
        assert len(voci) == 1
        voce = voci[0]
        assert voce.author_id == direttore.id
        assert voce.author_role == "direttore"
        assert voce.reason == "La sala centrale è chiusa per lavori"
        righe = {r.field: (r.old_value, r.new_value) for r in voce.fields}
        assert righe["location"] == ("Biliardo Centrale", "Sala Nuova")
        assert righe["break_rule"] == ("", "winner_breaks")
        # Solo ciò che il direttore ha cambiato: il nome, la data, la
        # distanza non compaiono.
        assert set(righe) <= {"location", "break_rule", "billiard_hall_id"}

    def test_la_storia_si_vede_in_fondo_alla_pagina(
        self, client, direttore, gara_con_iscritti
    ):
        _login(client, direttore)
        gara_id = gara_con_iscritti.id
        client.post(
            f"/admin/gara/{gara_id}/edit",
            data=_modulo(gara_con_iscritti, location="Sala Nuova"),
        )
        pagina = client.get(f"/admin/gara/{gara_id}/edit").get_data(as_text=True)
        storia = pagina[pagina.index('id="storia-modifiche"') :]
        assert "Sala" in storia and "Sala Nuova" in storia
        assert direttore.username in storia

    def test_salvare_senza_cambiare_non_lascia_traccia(
        self, client, direttore, gara_con_iscritti
    ):
        _login(client, direttore)
        client.post(
            f"/admin/gara/{gara_con_iscritti.id}/edit",
            data=_modulo(gara_con_iscritti),
        )
        assert StoriaModificheService.voci_della_gara(gara_con_iscritti.id) == []

    def test_un_campo_che_il_modulo_non_manda_non_si_tocca(
        self, client, db_session, direttore, gara_con_iscritti
    ):
        """Il criterio di sorteggio non è nel modulo: prima tornava a «elo»."""
        gara_con_iscritti.seeding_rating = "fargo"
        db_session.commit()
        _login(client, direttore)
        client.post(
            f"/admin/gara/{gara_con_iscritti.id}/edit",
            data=_modulo(gara_con_iscritti, name="Finalissima"),
        )
        gara = db_session.get(Gara, gara_con_iscritti.id)
        assert gara.name == "Finalissima"
        assert gara.seeding_rating == "fargo"


class TestDueDirettori:
    def test_il_campo_cambiato_da_un_altro_ferma_il_salvataggio(
        self, client, db_session, direttore, gara_con_iscritti
    ):
        _login(client, direttore)
        gara_id = gara_con_iscritti.id
        modulo = _modulo(gara_con_iscritti, location="Sala del direttore")

        # Mentre il modulo è aperto, un co-direttore sposta la gara altrove.
        GaraService.update_gara(gara_id, location="Sala del co-direttore")

        client.post(f"/admin/gara/{gara_id}/edit", data=modulo)
        assert db_session.get(Gara, gara_id).location == "Sala del co-direttore"

    def test_un_campo_diverso_passa(
        self, client, db_session, direttore, gara_con_iscritti
    ):
        _login(client, direttore)
        gara_id = gara_con_iscritti.id
        modulo = _modulo(gara_con_iscritti, name="Nome del direttore")

        GaraService.update_gara(gara_id, location="Sala del co-direttore")

        client.post(f"/admin/gara/{gara_id}/edit", data=modulo)
        gara = db_session.get(Gara, gara_id)
        assert gara.name == "Nome del direttore"
        # E la sala dell'altro non viene riportata indietro.
        assert gara.location == "Sala del co-direttore"


class TestIlServizio:
    def test_con_gli_iscritti_prima_dell_avvio_si_modifica(
        self, db_session, gara_con_iscritti
    ):
        GaraService.update_gara(gara_con_iscritti.id, distance=7)
        assert db_session.get(Gara, gara_con_iscritti.id).distance == 7

    def test_a_gara_avviata_la_struttura_no(self, db_session, gara_con_iscritti):
        gara_con_iscritti.status = GaraStatus.PLAYING.value
        gara_con_iscritti.current_round = 1
        db_session.commit()
        with pytest.raises(ConflictError):
            GaraService.update_gara(gara_con_iscritti.id, rounds_count=9)
        db_session.rollback()

    def test_dopo_annulla_l_avvio_si_torna_a_modificare(
        self, db_session, gara_con_iscritti
    ):
        gara_con_iscritti.status = GaraStatus.INSCRIPTION.value
        gara_con_iscritti.current_round = 0
        db_session.commit()
        GaraService.update_gara(gara_con_iscritti.id, name="Rinviata")
        assert db_session.get(Gara, gara_con_iscritti.id).name == "Rinviata"

    def test_la_capienza_non_scende_sotto_gli_iscritti(
        self, db_session, gara_con_iscritti
    ):
        with pytest.raises(ValueError, match="4 iscritti"):
            GaraService.update_gara(gara_con_iscritti.id, max_participants=3)
        db_session.rollback()
        GaraService.update_gara(gara_con_iscritti.id, max_participants=4)
        assert db_session.get(Gara, gara_con_iscritti.id).max_participants == 4

    def test_la_voce_porta_autore_e_motivo(
        self, db_session, direttore, gara_con_iscritti
    ):
        GaraService.update_gara(
            gara_con_iscritti.id,
            autore=direttore,
            motivo="  rinviata per pioggia  ",
            date=gara_con_iscritti.date + timedelta(days=7),
        )
        voce = SettingsChange.query.filter_by(gara_id=gara_con_iscritti.id).one()
        assert voce.reason == "rinviata per pioggia"
        assert voce.fields[0].field == "date"

    def test_serializza_una_forma_sola(self):
        assert serializza(None) == ""
        assert serializza(True) == "true"
        assert serializza(date(2026, 10, 1)) == "2026-10-01"
        assert serializza(time(20, 5)) == "20:05"
        assert serializza(10.0) == "10"
        assert serializza(["3", "1"]) == "3,1"
