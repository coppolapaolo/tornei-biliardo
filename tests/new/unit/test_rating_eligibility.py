"""Quali partite entrano nell'Elo: la tabella di verità, riga per riga.

Regola (ADR-049): una gara con handicap non spegne più l'Elo in blocco. Lo
spegne la **differenza di categoria** — fra due giocatori della stessa
categoria l'handicap non è in gioco, quindi il risultato dice davvero qualcosa
sulla loro forza.

Il test che vale di più è `test_handicap_senza_categorie_si_comporta_come_prima`:
finché nessuno assegna le categorie, il comportamento è identico a quello
storico. È la proprietà che rende il deploy innocuo sulle gare già esistenti.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.categoria.models import Categoria
from models.competition.models import Gara, Inscription
from models.match.models import Match, TrioMatch
from models.rating.eligibility import RatingEligibility, RatingExclusion
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User


def _user(suffix):
    u = User(username=f"cat_{suffix}", email=f"cat_{suffix}@t.com", role="player")
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    return u


def _gara(suffix, **overrides):
    base = dict(
        number=1,
        name=f"Gara {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
    )
    base.update(overrides)
    gara = Gara(**base)
    db.session.add(gara)
    db.session.flush()
    return gara


def _categoria(gara, name):
    categoria = Categoria(name=name, gara_id=gara.id)
    db.session.add(categoria)
    db.session.flush()
    return categoria


def _iscrivi(gara, user, categoria=None):
    ins = Inscription(
        gara_id=gara.id,
        user_id=user.id,
        categoria_id=categoria.id if categoria else None,
    )
    db.session.add(ins)
    db.session.flush()
    return ins


def _match(gara, p1, p2, **overrides):
    base = dict(
        gara_id=gara.id,
        round_number=1,
        player1_id=p1.id if p1 else None,
        player2_id=p2.id if p2 else None,
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
    )
    base.update(overrides)
    match = Match(**base)
    db.session.add(match)
    db.session.flush()
    return match


def _scenario(handicap, cat1, cat2):
    """Costruisce gara + due iscritti + un match. `cat*` sono nomi o None."""
    suffix = uuid.uuid4().hex[:8]
    gara = _gara(suffix, has_handicap=handicap)
    nomi = {n for n in (cat1, cat2) if n}
    categorie = {n: _categoria(gara, n) for n in nomi}
    p1, p2 = _user(f"{suffix}a"), _user(f"{suffix}b")
    _iscrivi(gara, p1, categorie.get(cat1))
    _iscrivi(gara, p2, categorie.get(cat2))
    return _match(gara, p1, p2)


# ── La tabella di verità ────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "handicap, cat1, cat2, atteso",
    [
        # Fuori dall'handicap la policy non cambia: si conta sempre.
        (False, None, None, None),
        (False, "A", "B", None),
        (False, "B", "B", None),
        # Con l'handicap decide la categoria.
        (True, "B", "B", None),
        (True, "B", "A", RatingExclusion.HANDICAP_DIFFERENT_CATEGORY),
        (True, "B", None, RatingExclusion.HANDICAP_CATEGORY_MISSING),
        (True, None, "B", RatingExclusion.HANDICAP_CATEGORY_MISSING),
        (True, None, None, RatingExclusion.HANDICAP_CATEGORY_MISSING),
    ],
)
def test_tabella_di_verita(db_session, handicap, cat1, cat2, atteso):
    match = _scenario(handicap, cat1, cat2)
    assert RatingEligibility.exclusion_reason(match) == atteso
    assert RatingEligibility.counts_for_rating(match) is (atteso is None)


@pytest.mark.unit
def test_handicap_senza_categorie_si_comporta_come_prima(db_session):
    """Non-regressione: il deploy non cambia nulla sulle gare esistenti.

    Nessuno ha ancora assegnato categorie, e una gara con handicap continua a
    restare fuori dall'Elo esattamente come prima di ADR-049.
    """
    match = _scenario(True, None, None)
    assert match.counts_for_rating is False


# ── Walkover: precede tutto ─────────────────────────────────────────────


@pytest.mark.unit
def test_il_walkover_vince_anche_sulla_stessa_categoria(db_session):
    match = _scenario(True, "B", "B")
    assert RatingEligibility.exclusion_reason(match, is_walkover=True) == (
        RatingExclusion.WALKOVER
    )


# ── Trii: servono tutti e tre ───────────────────────────────────────────


def _scenario_trio(nomi):
    suffix = uuid.uuid4().hex[:8]
    gara = _gara(suffix, has_handicap=True)
    categorie = {n: _categoria(gara, n) for n in {n for n in nomi if n}}
    players = [_user(f"{suffix}{i}") for i in range(3)]
    for player, nome in zip(players, nomi):
        _iscrivi(gara, player, categorie.get(nome))
    match = _match(gara, players[0], players[1], is_trio=True)
    trio = TrioMatch(
        match_id=match.id,
        player1_id=players[0].id,
        player2_id=players[1].id,
        player3_id=players[2].id,
    )
    db.session.add(trio)
    db.session.flush()
    return match


@pytest.mark.unit
def test_trio_conta_solo_se_tutti_e_tre_condividono_la_categoria(db_session):
    assert RatingEligibility.exclusion_reason(_scenario_trio(["B", "B", "B"])) is None


@pytest.mark.unit
def test_trio_due_su_tre_non_basta(db_session):
    """Nel girone interno si incontrano tutti: due su tre non è «ad armi pari»."""
    assert RatingEligibility.exclusion_reason(_scenario_trio(["B", "B", "A"])) == (
        RatingExclusion.HANDICAP_DIFFERENT_CATEGORY
    )


@pytest.mark.unit
def test_trio_uno_senza_categoria_esclude(db_session):
    assert RatingEligibility.exclusion_reason(_scenario_trio(["B", "B", None])) == (
        RatingExclusion.HANDICAP_CATEGORY_MISSING
    )


# ── Casi ai bordi ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_match_senza_gara_con_handicap_forzato_non_conta(db_session):
    """Non ci sono iscrizioni, quindi non esiste una categoria da confrontare."""
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(f"{suffix}a"), _user(f"{suffix}b")
    match = Match(
        gara_id=None,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
        has_handicap=True,
    )
    db.session.add(match)
    db.session.flush()

    assert RatingEligibility.exclusion_reason(match) == (
        RatingExclusion.HANDICAP_CATEGORY_MISSING
    )


@pytest.mark.unit
def test_match_senza_gara_senza_handicap_conta(db_session):
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(f"{suffix}a"), _user(f"{suffix}b")
    match = Match(
        gara_id=None,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
    )
    db.session.add(match)
    db.session.flush()

    assert RatingEligibility.exclusion_reason(match) is None


@pytest.mark.unit
def test_bye_senza_avversario_non_conta(db_session):
    suffix = uuid.uuid4().hex[:8]
    gara = _gara(suffix, has_handicap=True)
    categoria = _categoria(gara, "B")
    p1 = _user(suffix)
    _iscrivi(gara, p1, categoria)
    match = _match(gara, p1, None)

    assert RatingEligibility.exclusion_reason(match) == (
        RatingExclusion.HANDICAP_CATEGORY_MISSING
    )


@pytest.mark.unit
def test_giocatore_senza_iscrizione_non_conta(db_session):
    """Può capitare su dati storici: nessuna iscrizione, nessuna categoria."""
    suffix = uuid.uuid4().hex[:8]
    gara = _gara(suffix, has_handicap=True)
    categoria = _categoria(gara, "B")
    p1, p2 = _user(f"{suffix}a"), _user(f"{suffix}b")
    _iscrivi(gara, p1, categoria)  # p2 non è iscritto

    match = _match(gara, p1, p2)
    assert RatingEligibility.exclusion_reason(match) == (
        RatingExclusion.HANDICAP_CATEGORY_MISSING
    )


@pytest.mark.unit
def test_categoria_disattivata_conta_lo_stesso(db_session):
    """Ritirare una categoria dall'elenco non riscrive le gare già giocate."""
    match = _scenario(True, "B", "B")
    for categoria in Categoria.query.filter_by(gara_id=match.gara_id).all():
        categoria.is_active = False
    db.session.flush()

    assert RatingEligibility.exclusion_reason(match) is None


@pytest.mark.unit
def test_handicap_ereditato_dal_campionato(db_session):
    """Il flag può stare sul campionato: la regola non cambia."""
    suffix = uuid.uuid4().hex[:8]
    campionato = Campionato(
        name=f"Camp {suffix}", campionato_type="amalfi", has_handicap=True
    )
    db.session.add(campionato)
    db.session.flush()
    gara = _gara(suffix, has_handicap=None, campionato_id=campionato.id)

    categoria = Categoria(name="B", campionato_id=campionato.id)
    db.session.add(categoria)
    db.session.flush()

    p1, p2 = _user(f"{suffix}a"), _user(f"{suffix}b")
    _iscrivi(gara, p1, categoria)
    _iscrivi(gara, p2, categoria)
    match = _match(gara, p1, p2)

    assert match.effective_has_handicap is True
    assert RatingEligibility.exclusion_reason(match) is None


# ── L'indice dei ricalcoli deve dire le stesse cose ─────────────────────


@pytest.mark.unit
def test_l_indice_da_lo_stesso_verdetto_delle_query_singole(db_session):
    """Il prefetch è un'ottimizzazione, non una seconda implementazione."""
    matches = [
        _scenario(True, "B", "B"),
        _scenario(True, "B", "A"),
        _scenario(True, None, None),
        _scenario(False, "A", "B"),
    ]
    index = RatingEligibility.build_index(matches)

    for match in matches:
        assert RatingEligibility.exclusion_reason(
            match, index
        ) == RatingEligibility.exclusion_reason(match)


@pytest.mark.unit
def test_l_indice_legge_la_categoria_dell_iscrizione(db_session):
    """La categoria che l'indice riporta è quella scritta sull'iscrizione.

    Questo test verificava un tie-break fra **due** iscrizioni dello stesso
    giocatore alla stessa gara, una ritirata e una attiva. Da settembre 2026
    quel dato non esiste più: `uq_inscription_gara_user` lo rifiuta, e il test
    non riusciva nemmeno a costruirlo. L'ordinamento in `build_index` resta —
    difende la finestra fra il codice nuovo e la migration — ma non è più
    raggiungibile da qui; il presidio dell'invariante è in
    `tests/new/unit/test_iscrizione_unica_per_gara.py`.
    """
    suffix = uuid.uuid4().hex[:8]
    gara = _gara(suffix, has_handicap=True)
    cat_b = _categoria(gara, "B")
    p1, p2 = _user(f"{suffix}a"), _user(f"{suffix}b")

    _iscrivi(gara, p1, cat_b)
    _iscrivi(gara, p2, cat_b)
    db.session.flush()

    match = _match(gara, p1, p2)
    index = RatingEligibility.build_index([match])
    assert index[(gara.id, p1.id)] == cat_b.id
    assert RatingEligibility.exclusion_reason(match, index) is None
