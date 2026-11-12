"""Una squadra nuova nasce solo se chi la chiede può assegnarla (2026-11-10).

La route che assegna la squadra a un'iscrizione crea la voce nuova quando il
nome non è in elenco. La creava **prima** del controllo dei permessi, che
avveniva dopo nell'assegnazione, e la creazione si salvava da sola: un utente
collegato qualsiasi lasciava voci nell'elenco squadre di una gara non sua, e
lo stesso succedeva a finestra chiusa o con le squadre spente. Ora il
controllo — titolare dell'iscrizione o chi dirige la gara, a squadre ancora
modificabili — precede la creazione.
"""

import uuid
from datetime import date, timedelta

from models import Gara, User
from models.competition.models import Inscription
from models.squadra.models import Squadra
from models.status_enum import Discipline, GaraStatus
from models.user.role_enum import UserRole


def _gara(db_session, status=GaraStatus.INSCRIPTION.value, current_round=0):
    gara = Gara(
        name=f"G{uuid.uuid4().hex[:6]}",
        number=1,
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
        status=status,
        current_round=current_round,
        separate_teammates=True,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _iscrizione_di_un_altro(db_session, gara):
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"isc_{sigla}",
        email=f"isc_{sigla}@test.com",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("test123")
    db_session.add(utente)
    db_session.flush()
    iscrizione = Inscription(user_id=utente.id, gara_id=gara.id)
    db_session.add(iscrizione)
    db_session.commit()
    return iscrizione


def _chiedi_squadra_nuova(client, gara, iscrizione, nome):
    return client.post(
        f"/admin/gara/{gara.id}/inscription/{iscrizione.id}/squadra",
        data={"squadra_id": "__new__", "new_name": nome},
    )


def test_un_estraneo_non_lascia_squadre_in_elenco(db_session, logged_in_client):
    gara = _gara(db_session)
    iscrizione = _iscrizione_di_un_altro(db_session, gara)
    client, _estraneo = logged_in_client(role="player", username_prefix="estraneo")

    _chiedi_squadra_nuova(client, gara, iscrizione, "Squadra intrusa")

    db_session.expire_all()
    assert Squadra.query.count() == 0
    assert db_session.get(Inscription, iscrizione.id).squadra_id is None


def test_a_finestra_chiusa_la_squadra_non_nasce(db_session, logged_in_client):
    gara = _gara(db_session, status=GaraStatus.PLAYING.value, current_round=1)
    client, io = logged_in_client(role="player", username_prefix="io")
    iscrizione = Inscription(user_id=io.id, gara_id=gara.id)
    db_session.add(iscrizione)
    db_session.commit()

    _chiedi_squadra_nuova(client, gara, iscrizione, "Fuori tempo")

    db_session.expire_all()
    assert Squadra.query.count() == 0


def test_il_titolare_crea_la_squadra_e_la_sceglie(db_session, logged_in_client):
    gara = _gara(db_session)
    client, io = logged_in_client(role="player", username_prefix="io")
    iscrizione = Inscription(user_id=io.id, gara_id=gara.id)
    db_session.add(iscrizione)
    db_session.commit()

    risposta = _chiedi_squadra_nuova(client, gara, iscrizione, "Circolo Nord")

    assert risposta.status_code == 302
    db_session.expire_all()
    squadra = Squadra.query.one()
    assert squadra.name == "Circolo Nord"
    assert db_session.get(Inscription, iscrizione.id).squadra_id == squadra.id


def test_chi_dirige_crea_la_squadra_per_un_iscritto(db_session, logged_in_client):
    gara = _gara(db_session)
    iscrizione = _iscrizione_di_un_altro(db_session, gara)
    client, _admin = logged_in_client(role="admin", username_prefix="adm")

    _chiedi_squadra_nuova(client, gara, iscrizione, "Circolo Sud")

    db_session.expire_all()
    squadra = Squadra.query.one()
    assert db_session.get(Inscription, iscrizione.id).squadra_id == squadra.id
