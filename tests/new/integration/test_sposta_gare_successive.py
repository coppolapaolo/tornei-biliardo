"""Una data che scavalca le gare successive diventa una proposta (ADR-075).

Gare 1, 2, 3, 4 a una settimana circa l'una dall'altra; la gara 1 va avanti
di dieci giorni. Scavalca la 2, che spostata di dieci giorni scavalca la 3; la
4 è abbastanza lontana. L'app propone di spostare la 2 e la 3, e il cambio non
si salva finché il direttore non sceglie.

Nella stessa PR: alzare la capienza fa entrare chi aspetta in lista.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, time, timedelta

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService
from models.competition.spostamento import piano
from models.status_enum import GaraStatus
from models.storia.service import StoriaModificheService
from models.user.models import User

pytestmark = pytest.mark.integration

INIZIO = date.today() + timedelta(days=30)


def _utente(db_session, prefisso="p", role="player"):
    s = uuid.uuid4().hex[:8]
    u = User(username=f"{prefisso}_{s}", email=f"{prefisso}_{s}@t.com", role=role)
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture
def calendario(db_session):
    camp = Campionato(name=f"C {uuid.uuid4().hex[:6]}", campionato_type="amalfi")
    db_session.add(camp)
    db_session.commit()
    gare = [
        GaraService.create_gara(
            number=n,
            name=f"Gara {n}",
            date=INIZIO + timedelta(days=giorni),
            time=time(20, 0),
            discipline="9_ball",
            distance=5,
            campionato_id=camp.id,
        )
        for n, giorni in ((1, 0), (2, 7), (3, 14), (4, 30))
    ]
    db_session.commit()
    return camp, gare


class TestIlPiano:
    def test_si_spostano_solo_quelle_che_servono(self, calendario):
        _camp, gare = calendario
        p = piano(gare[0], INIZIO + timedelta(days=10), time(20, 0))
        assert p is not None and p.giorni == 10
        assert p.numeri == [2, 3]
        assert [s.a for s in p.spostamenti] == [
            INIZIO + timedelta(days=17),
            INIZIO + timedelta(days=24),
        ]

    def test_senza_scavalcare_niente_da_proporre(self, calendario):
        _camp, gare = calendario
        assert piano(gare[0], INIZIO + timedelta(days=3), time(20, 0)) is None

    def test_una_gara_avviata_non_si_sposta(self, db_session, calendario):
        _camp, gare = calendario
        gare[1].status = GaraStatus.PLAYING.value
        gare[1].current_round = 1
        db_session.commit()
        p = piano(gare[0], INIZIO + timedelta(days=10), time(20, 0))
        assert p is not None and p.bloccata_da.id == gare[1].id


class TestDallaPagina:
    def _modulo(self, gara, nuova_data):
        from routes.admin.competition.form_parser import GaraFormParser

        return {
            "name": gara.name,
            "date": nuova_data.isoformat(),
            "time": "20:00",
            "discipline": "9_ball",
            "distance": "5",
            "rounds_count": str(gara.rounds_count or 3),
            "min_participants": str(gara.min_participants or 4),
            "max_participants": str(gara.max_participants or 16),
            "entry_fee": "0",
            "first_round_policy": "random",
            "odd_number_policy": gara.odd_number_policy or "bye",
            "withdraw_policy": "forfeit",
            "stato_iniziale": json.dumps(GaraFormParser.valori_attuali(gara)),
            "motivo": "Sala occupata",
        }

    def test_proposta_poi_spostamento(self, client, db_session, calendario):
        _camp, gare = calendario
        admin = _utente(db_session, "admin", role="admin")
        db_session.commit()
        client.post(
            "/auth/login",
            data={"username": admin.username, "password": "test1234"},
            follow_redirects=True,
        )
        nuova = INIZIO + timedelta(days=10)
        dati = self._modulo(gare[0], nuova)

        pagina = client.post(f"/admin/gara/{gare[0].id}/edit", data=dati)
        assert pagina.status_code == 200
        assert "Sposta anche le successive" in pagina.get_data(as_text=True)
        assert db.session.get(Gara, gare[0].id).date == INIZIO

        client.post(
            f"/admin/gara/{gare[0].id}/edit", data={**dati, "sposta_successive": "1"}
        )
        date_ = [db.session.get(Gara, g.id).date for g in gare]
        assert date_ == [
            nuova,
            INIZIO + timedelta(days=17),
            INIZIO + timedelta(days=24),
            INIZIO + timedelta(days=30),
        ]
        voce = StoriaModificheService.voci_della_gara(gare[1].id)[0]
        assert voce.reason == "Sala occupata"


class TestLaCapienzaRipesca:
    def test_alzare_la_capienza_fa_entrare_chi_aspetta(self, db_session):
        direttore = _utente(db_session, "dir", role="director")
        gara = GaraService.create_gara(
            number=1,
            director_id=direttore.id,
            name="Serata",
            date=INIZIO,
            time=time(20, 0),
            discipline="9_ball",
            distance=5,
            max_participants=2,
            min_participants=2,
        )
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()
        from models.competition.inscription_service import InscriptionService

        giocatori = [_utente(db_session) for _ in range(4)]
        db_session.commit()
        for g in giocatori:
            InscriptionService.inscribe_user(user_id=g.id, gara_id=gara.id)
        in_attesa = Inscription.query.filter_by(gara_id=gara.id, is_waitlist=True)
        assert in_attesa.count() == 2

        GaraService.update_gara(gara.id, max_participants=3)
        attivi = Inscription.query.filter_by(gara_id=gara.id, is_waitlist=False)
        assert attivi.count() == 3
        assert in_attesa.count() == 1
