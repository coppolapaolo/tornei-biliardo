"""Un giocatore, un'iscrizione per gara — e la regola per fondere le doppie.

La regola c'era da sempre, ma stava in un `if` di
`InscriptionService.inscribe_user`: chi scriveva in SQL diretto — l'unione di
due account — la scavalcava senza accorgersene, e in produzione (gara 39) lo
stesso giocatore compariva due volte, una con la categoria del direttore e una
senza. Qui si presidia l'invariante dove ora vive davvero, cioè nel database, e
la regola con cui si riducono a una le doppie già scritte.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from models import db
from models.competition.inscription_dedup import piano_di_fusione
from models.competition.models import Inscription


def _riga(id_, giorni_fa=0, **campi):
    """Una riga nella forma che `piano_di_fusione` legge."""
    base = {
        "id": id_,
        "created_at": datetime(2026, 8, 1) + timedelta(days=giorni_fa),
        "categoria_id": None,
        "squadra_id": None,
        "initial_order": None,
        "is_waitlist": False,
        "waitlist_position": None,
        "waitlist_reason": None,
        "is_withdrawn": False,
        "withdrawn_at": None,
        "is_forfeit": False,
        "forfeit_at": None,
    }
    base.update(campi)
    return base


# ------------------------------------------------------- l'invariante nel DB


@pytest.mark.unit
def test_il_db_rifiuta_due_iscrizioni_dello_stesso_giocatore(db_session, app):
    """È il vincolo, non il codice applicativo, a dire l'ultima parola."""
    import uuid
    from datetime import date

    from models.competition.models import Gara
    from models.user.models import User

    giocatore = User(
        username=f"iscritto_{uuid.uuid4().hex[:8]}",
        email=f"iscritto_{uuid.uuid4().hex[:8]}@example.com",
        role="player",
    )
    giocatore.set_password("secret123")
    db.session.add(giocatore)
    db.session.flush()

    gara = Gara(
        name="unica",
        number=1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="amalfi",
        status="inscription",
    )
    db.session.add(gara)
    db.session.flush()

    db.session.add(Inscription(gara_id=gara.id, user_id=giocatore.id))
    db.session.flush()

    db.session.add(Inscription(gara_id=gara.id, user_id=giocatore.id))
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()


# ----------------------------------------------------- la regola di fusione


@pytest.mark.unit
def test_niente_da_fondere_con_una_riga_sola():
    assert piano_di_fusione([_riga(1)]) is None
    assert piano_di_fusione([]) is None


@pytest.mark.unit
def test_sopravvive_la_piu_vecchia():
    piano = piano_di_fusione([_riga(2, giorni_fa=10), _riga(1, giorni_fa=0)])
    assert piano is not None
    assert piano.sopravvissuta_id == 1
    assert piano.da_cancellare == [2]


@pytest.mark.unit
def test_i_campi_vuoti_si_riempiono_dall_altra():
    """Il caso di produzione: la categoria sta sulla vecchia, e resta."""
    piano = piano_di_fusione(
        [_riga(1, categoria_id=None), _riga(2, giorni_fa=10, categoria_id=7)]
    )
    assert piano is not None
    assert piano.valori["categoria_id"] == 7


@pytest.mark.unit
def test_un_campo_gia_scritto_non_si_sovrascrive():
    """Se entrambe dicono qualcosa, vince la riga più vecchia."""
    piano = piano_di_fusione(
        [_riga(1, categoria_id=3), _riga(2, giorni_fa=10, categoria_id=7)]
    )
    assert piano is not None
    assert "categoria_id" not in piano.valori


@pytest.mark.unit
def test_lo_stato_attivo_batte_la_lista_d_attesa():
    """Il posto in gara è un fatto acquisito: l'unione non lo toglie."""
    piano = piano_di_fusione(
        [
            _riga(1, is_waitlist=True, waitlist_position=2, waitlist_reason="capacity"),
            _riga(2, giorni_fa=10),
        ]
    )
    assert piano is not None
    assert piano.sopravvissuta_id == 1
    assert piano.valori["is_waitlist"] is False
    assert piano.valori["waitlist_position"] is None
    assert piano.valori["waitlist_reason"] is None


@pytest.mark.unit
def test_lo_stato_arriva_tutto_dalla_stessa_riga():
    """Non campo per campo: `withdrawn_at` senza `is_withdrawn` è incoerente."""
    piano = piano_di_fusione(
        [
            _riga(1, is_withdrawn=True, withdrawn_at=datetime(2026, 8, 5)),
            _riga(2, giorni_fa=10, is_withdrawn=True, withdrawn_at=None),
        ]
    )
    # Entrambe ritirate: stesso rango, resta com'è la più vecchia.
    assert piano is not None
    assert "is_withdrawn" not in piano.valori
    assert "withdrawn_at" not in piano.valori


@pytest.mark.unit
def test_una_riga_attiva_recupera_chi_era_ritirato():
    piano = piano_di_fusione(
        [
            _riga(1, is_withdrawn=True, withdrawn_at=datetime(2026, 8, 5)),
            _riga(2, giorni_fa=10),
        ]
    )
    assert piano is not None
    assert piano.valori["is_withdrawn"] is False
    assert piano.valori["withdrawn_at"] is None


@pytest.mark.unit
def test_created_at_mancante_finisce_in_coda():
    """Le iscrizioni antiche non hanno la data: non devono vincere per caso."""
    piano = piano_di_fusione([_riga(5, created_at=None), _riga(9, giorni_fa=3)])
    assert piano is not None
    assert piano.sopravvissuta_id == 9
