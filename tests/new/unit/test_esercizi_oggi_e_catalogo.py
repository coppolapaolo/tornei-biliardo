"""«Oggi» e il catalogo che si filtra (redesign TPA ed esercizi, fase 4c).

La vista è di sola lettura e sta tutta in ``models/challenge/catalog_view.py``:
qui si fissa che cosa filtra, come ordina, e che cosa propone la porta
d'ingresso a chi ha una storia e a chi non ce l'ha.
"""

from __future__ import annotations

import uuid

from werkzeug.datastructures import MultiDict

from models.challenge.catalog_view import (
    CatalogFilter,
    CatalogScope,
    CatalogSort,
    build_catalog,
    build_today,
)
from models.challenge.models import Challenge, ChallengeFavorite, ChallengeRating
from models.challenge.profile_service import ChallengeProfileService
from models.challenge.services import ChallengeService
from models.challenge.vocabulary import Abilita, Gesto
from models.user.models import User
from models.user.role_enum import UserRole


def _utente(db_session):
    u = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _esercizio(db_session, titolo, *, autore=None, attivo=True, **profilo):
    c = Challenge(
        title=f"{titolo} {uuid.uuid4().hex[:5]}",
        description="x",
        image_path="t.jpg",
        pass_fail_only=profilo.pop("pass_fail_only", False),
        max_score=profilo.pop("max_score", 10),
        is_active=attivo,
        created_by_id=autore,
    )
    db_session.add(c)
    db_session.flush()
    if profilo:
        ChallengeProfileService.set_profile(c.id, **profilo)
    return c


def _miei(vista, esercizi):
    """Solo le card di questo test: il DB dei test è condiviso."""
    ids = {e.id for e in esercizi}
    return [c.challenge.id for c in vista.cards if c.challenge.id in ids]


class TestFiltro:
    def test_dalla_query_string(self):
        f = CatalogFilter.from_args(
            MultiDict(
                {
                    "abilita": "posizione",
                    "gesto": "draw",
                    "livello": "2",
                    "voto": "4",
                    "ordine": "voto",
                    "vista": "preferiti",
                }
            )
        )
        assert (f.abilita, f.gesto, f.level, f.min_rating) == (
            Abilita.POSIZIONE,
            Gesto.DRAW,
            2,
            4,
        )
        assert f.sort == CatalogSort.TOP_RATED
        assert f.scope == CatalogScope.FAVORITES

    def test_un_valore_ignoto_vale_nessun_filtro(self):
        f = CatalogFilter.from_args(
            MultiDict(
                {"abilita": "esordienti", "livello": "9", "voto": "1", "ordine": "boh"}
            )
        )
        assert not f.is_filtering
        assert f.sort == CatalogSort.MOST_TRIED

    def test_la_pillola_accesa_ritoccata_si_spegne(self):
        f = CatalogFilter(gesto=Gesto.DRAW, level=2)
        assert f.to_args(gesto=None) == {"livello": 2}
        assert f.to_args(gesto="stop") == {"gesto": "stop", "livello": 2}
        # i default non sporcano l'indirizzo
        assert CatalogFilter().to_args() == {}


class TestCatalogo:
    def test_filtra_per_abilita_gesto_e_livello_insieme(self, db_session):
        a = _esercizio(
            db_session, "A", abilita=["posizione"], gesti=["draw"], declared_level=2
        )
        b = _esercizio(
            db_session, "B", abilita=["posizione"], gesti=["stop"], declared_level=2
        )
        c = _esercizio(db_session, "C")  # senza profilo
        u = _utente(db_session)

        solo_posizione = build_catalog(u.id, CatalogFilter(abilita=Abilita.POSIZIONE))
        assert set(_miei(solo_posizione, [a, b, c])) == {a.id, b.id}

        col_draw = build_catalog(
            u.id, CatalogFilter(abilita=Abilita.POSIZIONE, gesto=Gesto.DRAW, level=2)
        )
        assert _miei(col_draw, [a, b, c]) == [a.id]

        tutto = build_catalog(u.id, CatalogFilter())
        assert set(_miei(tutto, [a, b, c])) == {a.id, b.id, c.id}

    def test_gli_spenti_non_compaiono(self, db_session):
        spento = _esercizio(db_session, "Spento", attivo=False)
        vista = build_catalog(_utente(db_session).id, CatalogFilter())
        assert _miei(vista, [spento]) == []

    def test_i_piu_provati_in_testa(self, db_session):
        poco = _esercizio(db_session, "Poco")
        molto = _esercizio(db_session, "Molto")
        ChallengeService.record_attempt(_utente(db_session).id, poco.id, score=1)
        for _ in range(3):
            ChallengeService.record_attempt(_utente(db_session).id, molto.id, score=1)
        vista = build_catalog(_utente(db_session).id, CatalogFilter())
        assert _miei(vista, [poco, molto]) == [molto.id, poco.id]

    def test_per_voto_chi_non_ha_voti_va_in_fondo(self, db_session):
        senza = _esercizio(db_session, "Senza")
        tre = _esercizio(db_session, "Tre")
        cinque = _esercizio(db_session, "Cinque")
        for esercizio, voto in ((tre, 3), (cinque, 5)):
            db_session.add(
                ChallengeRating(
                    challenge_id=esercizio.id,
                    user_id=_utente(db_session).id,
                    rating=voto,
                )
            )
        db_session.flush()
        u = _utente(db_session)
        vista = build_catalog(u.id, CatalogFilter(sort=CatalogSort.TOP_RATED))
        assert _miei(vista, [senza, tre, cinque]) == [cinque.id, tre.id, senza.id]

        alti = build_catalog(u.id, CatalogFilter(min_rating=4))
        assert _miei(alti, [senza, tre, cinque]) == [cinque.id]

    def test_i_miei_e_i_preferiti(self, db_session):
        u = _utente(db_session)
        mio = _esercizio(db_session, "Mio", autore=u.id)
        caro = _esercizio(db_session, "Caro")
        db_session.add(ChallengeFavorite(challenge_id=caro.id, user_id=u.id))
        db_session.flush()
        assert _miei(
            build_catalog(u.id, CatalogFilter(scope=CatalogScope.MINE)), [mio, caro]
        ) == [mio.id]
        preferiti = build_catalog(u.id, CatalogFilter(scope=CatalogScope.FAVORITES))
        assert _miei(preferiti, [mio, caro]) == [caro.id]
        assert preferiti.cards[0].is_favorite

    def test_la_riga_di_chi_guarda(self, db_session):
        u = _utente(db_session)
        c = _esercizio(db_session, "Dieci", max_score=10)
        for punti in (2, 4, 9, 9, 9):  # l'ultima registrata è la più recente
            ChallengeService.record_attempt(u.id, c.id, score=punti)
        mai = _esercizio(db_session, "Mai")
        vista = build_catalog(u.id, CatalogFilter())
        per_id = {card.challenge.id: card for card in vista.cards}
        riga = per_id[c.id].mine
        assert riga.attempts == 5 and riga.best == 9
        assert riga.average_pct == 66  # 33 su 50
        assert riga.recent_pct == 90  # le ultime tre: 27 su 30
        assert not per_id[mai.id].mine.tried

    def test_senza_massimo_niente_percentuali(self, db_session):
        u = _utente(db_session)
        c = _esercizio(db_session, "Libero", max_score=None)
        ChallengeService.record_attempt(u.id, c.id, score=14)
        riga = {x.challenge.id: x for x in build_catalog(u.id, CatalogFilter()).cards}[
            c.id
        ].mine
        assert riga.best == 14 and riga.average_pct is None


class TestOggi:
    def test_chi_non_ha_storia_non_ha_niente_da_riprendere(self, db_session):
        _esercizio(db_session, "Uno")
        oggi = build_today(_utente(db_session).id)
        assert oggi.resume is None
        assert oggi.favorites == []
        assert not oggi.is_empty

    def test_si_riprende_l_ultimo_provato(self, db_session):
        u = _utente(db_session)
        prima, dopo = _esercizio(db_session, "Prima"), _esercizio(db_session, "Dopo")
        ChallengeService.record_attempt(u.id, prima.id, score=1)
        ChallengeService.record_attempt(u.id, dopo.id, score=1)
        assert build_today(u.id).resume.challenge.id == dopo.id

    def test_niente_doppioni_fra_le_strisce(self, db_session):
        u = _utente(db_session)
        c = _esercizio(db_session, "Solo")
        ChallengeService.record_attempt(u.id, c.id, score=1)
        db_session.add(ChallengeFavorite(challenge_id=c.id, user_id=u.id))
        db_session.flush()
        oggi = build_today(u.id)
        assert oggi.resume.challenge.id == c.id
        assert c.id not in [x.challenge.id for x in oggi.favorites]
        assert c.id not in [x.challenge.id for x in oggi.most_tried]
