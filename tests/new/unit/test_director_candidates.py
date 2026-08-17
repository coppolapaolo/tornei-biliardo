"""Chi si può proporre come co-direttore di una gara.

Il filtro di zona non si vede nei test end-to-end, perché quelli girano su un
database senza sale geolocalizzate e lì la regola dice — giustamente — «senza
zona non si filtra». Le sue decisioni si verificano qui.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db
from models.competition.director_candidates import direttori_candidati
from models.competition.services import GaraService
from models.location.models import BilliardHall
from models.user.models import User
from models.user.role_enum import UserRole

# Due città lontane ~570 km: qualunque raggio ammesso le separa.
MILANO = (45.4642, 9.1900)
NAPOLI = (40.8518, 14.2681)
# Bergamo dista ~45 km da Milano: fuori dal raggio predefinito (30 km),
# dentro a uno più largo. Serve a mostrare che il raggio conta davvero.
BERGAMO = (45.6983, 9.6773)


def _direttore(db_session, citta: str | None = None, raggio: int | None = None):
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"dir_{sigla}",
        email=f"dir_{sigla}@example.test",
        role=UserRole.DIRECTOR.value,
        home_city=citta,
    )
    if raggio:
        utente.signal_radius_km = raggio
    utente.set_password("x")
    db_session.add(utente)
    db_session.commit()
    return utente


def _sala(db_session, citta: str, punto: tuple[float, float]):
    sala = BilliardHall(
        name=f"Sala {citta} {uuid.uuid4().hex[:4]}",
        city=citta,
        latitude=punto[0],
        longitude=punto[1],
        is_active=True,
    )
    db_session.add(sala)
    db_session.commit()
    return sala


def _gara_di(db_session, proprietario):
    return GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Gara {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        location="Sala di prova",
        rounds_count=3,
        min_participants=4,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=proprietario.id,
        matchmaking_strategy="amalfi",
    )


@pytest.mark.unit
class TestZonaDelProprietario:

    def test_chi_e_lontano_resta_fuori(self, db_session):
        _sala(db_session, "Milano", MILANO)
        _sala(db_session, "Napoli", NAPOLI)
        proprietario = _direttore(db_session, "Milano")
        vicino = _direttore(db_session, "Milano")
        lontano = _direttore(db_session, "Napoli")

        candidati = direttori_candidati(
            _gara_di(db_session, proprietario), richiedente_id=proprietario.id
        )

        assert vicino in candidati
        assert lontano not in candidati

    def test_senza_citta_del_proprietario_si_elencano_tutti(self, db_session):
        """«Chi c'è qui intorno» non ha risposta se non c'è un "qui".

        Elencare nessuno sarebbe la lettura letterale, e renderebbe la funzione
        inutilizzabile per chi non ha mai compilato la città.
        """
        _sala(db_session, "Milano", MILANO)
        _sala(db_session, "Napoli", NAPOLI)
        proprietario = _direttore(db_session, citta=None)
        lontano = _direttore(db_session, "Napoli")

        candidati = direttori_candidati(
            _gara_di(db_session, proprietario), richiedente_id=proprietario.id
        )

        assert lontano in candidati

    def test_chi_non_ha_dichiarato_la_citta_resta_in_elenco(self, db_session):
        """Non sappiamo se è vicino: escluderlo lo renderebbe inaggiungibile.

        Va però **dopo** chi risulta in zona: l'ordine è l'unico modo onesto di
        dire "di questi lo so, di quelli no".
        """
        _sala(db_session, "Milano", MILANO)
        proprietario = _direttore(db_session, "Milano")
        in_zona = _direttore(db_session, "Milano")
        ignoto = _direttore(db_session, citta=None)

        candidati = direttori_candidati(
            _gara_di(db_session, proprietario), richiedente_id=proprietario.id
        )

        assert ignoto in candidati
        assert candidati.index(in_zona) < candidati.index(ignoto)

    def test_il_raggio_del_proprietario_decide_quanto_e_larga_la_zona(self, db_session):
        """La zona è quella che il direttore si è dato, non una costante.

        Bergamo dista ~45 km da Milano: fuori dai 30 km predefiniti, dentro a
        90. `clamp_radius` taglia comunque a 100 km, quindi «tutta Italia» non
        è una zona ottenibile alzando il numero.
        """
        _sala(db_session, "Milano", MILANO)
        _sala(db_session, "Bergamo", BERGAMO)

        stretto = _direttore(db_session, "Milano", raggio=30)
        bergamasco_1 = _direttore(db_session, "Bergamo")
        assert bergamasco_1 not in direttori_candidati(
            _gara_di(db_session, stretto), richiedente_id=stretto.id
        )

        largo = _direttore(db_session, "Milano", raggio=90)
        assert bergamasco_1 in direttori_candidati(
            _gara_di(db_session, largo), richiedente_id=largo.id
        )

    def test_chi_dirige_gia_non_e_un_candidato(self, db_session):
        proprietario = _direttore(db_session, citta=None)
        gia_dentro = _direttore(db_session, citta=None)

        candidati = direttori_candidati(
            _gara_di(db_session, proprietario),
            escludi_ids=[gia_dentro.id],
            richiedente_id=proprietario.id,
        )

        assert gia_dentro not in candidati
        assert proprietario not in candidati

    def test_la_sede_della_gara_batte_la_citta_di_chi_l_ha_creata(self, db_session):
        """Si cerca chi è vicino al tavolo, non chi è vicino all'organizzatore.

        Un direttore milanese che organizza a Napoli ha bisogno di qualcuno che
        quella sera sia a Napoli.
        """
        sala_napoli = _sala(db_session, "Napoli", NAPOLI)
        _sala(db_session, "Milano", MILANO)
        proprietario = _direttore(db_session, "Milano")
        napoletano = _direttore(db_session, "Napoli")
        milanese = _direttore(db_session, "Milano")

        gara = _gara_di(db_session, proprietario)
        gara.billiard_hall_id = sala_napoli.id
        db.session.commit()

        candidati = direttori_candidati(gara, richiedente_id=proprietario.id)

        assert napoletano in candidati
        assert milanese not in candidati
