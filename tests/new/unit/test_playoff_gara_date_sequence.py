"""La gara di playoff deve stare in coda al calendario del campionato.

Rilievo emerso dal percorso end-to-end `tests/new/e2e/test_campionato_e2e_playoff.py`:
`PlayoffService.create_playoff_gara` datava la gara **oggi**, ma la crea con il
numero successivo all'ultima del campionato — e `GaraService` pretende che le
gare numerate siano in ordine cronologico (ADR-016). Se l'ultima gara in
calendario è ancora nel futuro, la creazione veniva rifiutata con «La data/ora
della gara N deve essere successiva alla gara N-1», la route trasformava il
rifiuto in un messaggio in pagina e i playoff restavano irraggiungibili.

Nessun test se ne era accorto perché tutte le fixture dei playoff scrivono le
gare direttamente sul modello, con date nel passato: l'ordine era rispettato
per caso. Le due situazioni che lo rompono in produzione sono ordinarie:

* il campionato viene terminato prima della data dell'ultima gara in
  calendario (playoff anticipati, ultima tappa annullata);
* il direttore aveva pianificato più gare di quante se ne sono giocate: la
  terminazione soft-elimina quelle mai disputate, ma il controllo di sequenza
  continua a vederle, quindi la data futura di una gara *cancellata* basta a
  bloccare la finale.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

import pytest

from models.base import utc_now
from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.playoff.services import PlayoffService
from models.status_enum import GaraStatus
from models.user.models import User


def _sigla() -> str:
    return uuid.uuid4().hex[:8]


def _campionato(db_session) -> Campionato:
    campionato = Campionato(
        name=f"Camp {_sigla()}", campionato_type="amalfi", is_active=True
    )
    db_session.add(campionato)
    db_session.flush()
    campionato.terminated_at = utc_now()
    db_session.flush()
    return campionato


def _gara(
    db_session,
    campionato: Campionato,
    numero: int,
    giorno: date,
    status: str = GaraStatus.COMPLETED.value,
) -> Gara:
    gara = Gara(
        campionato_id=campionato.id,
        number=numero,
        name=f"Gara {numero}",
        date=giorno,
        time=time(20, 0),
        discipline="nine_ball",
        status=status,
        rounds_count=3,
        current_round=1,
        distance=5,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _configurazione(db_session, campionato: Campionato) -> PlayoffConfiguration:
    configurazione = PlayoffConfiguration(
        campionato_id=campionato.id,
        name="Elite",
        playoff_type=PlayoffType.TOP_N,
        max_participants=4,
        positions_from=1,
        positions_to=4,
        is_active=True,
        auto_generate=True,
    )
    db_session.add(configurazione)
    db_session.flush()
    return configurazione


def _qualificato(db_session, configurazione, gara: Gara) -> User:
    utente = User(username=f"p_{_sigla()}", email=f"{_sigla()}@test.com", role="player")
    utente.set_password("test1234")
    db_session.add(utente)
    db_session.flush()
    db_session.add(Inscription(user_id=utente.id, gara_id=gara.id))
    db_session.add(
        PlayoffQualification(
            configuration_id=configurazione.id,
            user_id=utente.id,
            qualifying_position=1,
            qualification_reason="test",
            status=QualificationStatus.CONFIRMED,
            responded_at=utc_now(),
        )
    )
    db_session.flush()
    return utente


@pytest.mark.unit
class TestDataDellaGaraDiPlayoff:
    def test_va_dopo_l_ultima_gara_anche_se_e_nel_futuro(self, db_session):
        """Il caso che rendeva i playoff irraggiungibili."""
        campionato = _campionato(db_session)
        _gara(db_session, campionato, 1, date.today())
        ultima = _gara(db_session, campionato, 2, date.today() + timedelta(days=30))
        configurazione = _configurazione(db_session, campionato)
        _qualificato(db_session, configurazione, ultima)
        db_session.commit()

        gara_playoff = PlayoffService.create_playoff_gara(configurazione.id)

        assert gara_playoff is not None
        assert gara_playoff.number == 3
        assert datetime.combine(
            gara_playoff.date, gara_playoff.time
        ) >= datetime.combine(ultima.date, ultima.time)

    def test_una_gara_futura_mai_giocata_non_blocca_la_finale(self, db_session):
        """La terminazione soft-elimina le gare mai disputate.

        Il controllo di sequenza però non filtra le cancellate, quindi la
        data di una gara che non esiste più continua a vincolare. Vincolarci
        la finale è accettabile — sposta solo la data in avanti — impedirla no.
        """
        campionato = _campionato(db_session)
        giocata = _gara(db_session, campionato, 1, date.today())
        mai_giocata = _gara(
            db_session,
            campionato,
            2,
            date.today() + timedelta(days=60),
            status=GaraStatus.SETUP.value,
        )
        mai_giocata.soft_delete("Campionato terminato")
        configurazione = _configurazione(db_session, campionato)
        _qualificato(db_session, configurazione, giocata)
        db_session.commit()

        gara_playoff = PlayoffService.create_playoff_gara(configurazione.id)

        assert gara_playoff is not None
        assert gara_playoff.campionato_id == campionato.id

    def test_col_calendario_tutto_alle_spalle_resta_oggi(self, db_session):
        """Il caso normale non cambia: la finale si crea per oggi."""
        campionato = _campionato(db_session)
        gara = _gara(db_session, campionato, 1, date.today() - timedelta(days=10))
        configurazione = _configurazione(db_session, campionato)
        _qualificato(db_session, configurazione, gara)
        db_session.commit()

        gara_playoff = PlayoffService.create_playoff_gara(configurazione.id)

        assert gara_playoff.date == date.today()
