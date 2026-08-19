"""Il modello ``Categoria``: i vincoli che il DB impone da solo.

Sono vincoli di tabella e non controlli in Python perché una riga senza
proprietario — o due categorie con lo stesso nome nella stessa competizione —
sarebbe un guasto silenzioso: nessuna schermata la mostrerebbe come sbagliata,
si vedrebbe solo un Elo che non torna.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from models import Campionato, Categoria, Gara
from models.base import db
from models.categoria.models import MAX_NAME_LENGTH
from models.shared.naming import normalize_list_name

pytestmark = pytest.mark.unit


def _gara(db_session, suffix):
    gara = Gara(
        number=1,
        name=f"Gara {suffix}",
        date=date.today() + timedelta(days=7),
        discipline="palla_8",
        distance=5,
        rounds_count=3,
        matchmaking_strategy="direct_elimination",
    )
    db_session.add(gara)
    db_session.flush()
    return gara


class TestNormalizzazione:
    @pytest.mark.parametrize(
        "scritto, atteso",
        [("B", "b"), ("  b  ", "b"), ("Prima  Categoria", "prima categoria")],
    )
    def test_la_forma_normalizzata_collassa_maiuscole_e_spazi(self, scritto, atteso):
        assert normalize_list_name(scritto) == atteso

    def test_il_nome_mostrato_conserva_le_maiuscole(self, db_session):
        gara = _gara(db_session, "disp")
        categoria = Categoria(name="  Prima   Categoria  ", gara_id=gara.id)
        assert categoria.name == "Prima Categoria"
        assert categoria.normalized_name == "prima categoria"

    def test_rinominare_tiene_allineata_la_forma_normalizzata(self, db_session):
        gara = _gara(db_session, "ren")
        categoria = Categoria(name="B", gara_id=gara.id)
        categoria.rename("  Nazionali ")
        assert categoria.name == "Nazionali"
        assert categoria.normalized_name == "nazionali"

    def test_il_limite_di_lunghezza_e_quello_delle_sigle(self):
        assert MAX_NAME_LENGTH == 50


class TestProprietarioEsclusivo:
    def test_senza_proprietario_il_db_rifiuta(self, db_session):
        db.session.add(Categoria(name="orfana"))
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()

    def test_con_due_proprietari_il_db_rifiuta(self, db_session):
        camp = Campionato(name="Camp xor")
        db.session.add(camp)
        db.session.flush()
        gara = _gara(db_session, "xor")

        db.session.add(Categoria(name="doppia", campionato_id=camp.id, gara_id=gara.id))
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


class TestUnicita:
    def test_due_categorie_omonime_nella_stessa_gara_sono_rifiutate(self, db_session):
        gara = _gara(db_session, "uniq")
        db.session.add(Categoria(name="B", gara_id=gara.id))
        db.session.flush()

        # Stessa forma normalizzata, scritta diversamente.
        db.session.add(Categoria(name="  b ", gara_id=gara.id))
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()

    def test_lo_stesso_nome_in_due_gare_diverse_convive(self, db_session):
        una = _gara(db_session, "u1")
        altra = _gara(db_session, "u2")
        db.session.add(Categoria(name="B", gara_id=una.id))
        db.session.add(Categoria(name="B", gara_id=altra.id))
        db.session.flush()

        assert Categoria.query.filter_by(normalized_name="b").count() == 2
