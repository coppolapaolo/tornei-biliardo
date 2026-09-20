"""«Per oggi»: le quattro regole del consiglio, e cosa non si consiglia mai (#175).

Un consiglio che non si capisce non si segue: ogni regola porta con sé la frase
che la spiega, e i test guardano **quale regola ha parlato**, non solo che un
esercizio sia uscito.

Le regole si verificano una per una, isolandole — perché in ordine di priorità
la prima che ha presa copre le altre, ed è esattamente il comportamento voluto.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from models.base import utc_now
from models.challenge.consigli import FERMO_DA, QUANTI, build_advice
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.profile_service import ChallengeProfileService
from models.challenge.vocabulary import Abilita, CategoryAxis
from models.obiettivo import GoalKind, TrainingGoalService
from models.user.models import User
from models.user.role_enum import UserRole


# ── allestimento ────────────────────────────────────────────────────────────
def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"cs_{uid}", email=f"cs_{uid}@test.local", role=UserRole.PLAYER.value
    )
    user.set_password("p")
    db_session.add(user)
    db_session.flush()
    return user


def _challenge(db_session, titolo, *, max_score=10, abilita=()):
    challenge = Challenge(
        title=titolo,
        description=f"{titolo}: istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=False,
        max_score=max_score,
    )
    db_session.add(challenge)
    db_session.flush()
    if abilita:
        ChallengeProfileService.set_profile(
            challenge.id, abilita=[a.value for a in abilita]
        )
        db_session.flush()
    return challenge


def _prova(db_session, user, challenge, *, score, giorni_fa=1):
    db_session.add(
        ChallengeAttempt(
            challenge_id=challenge.id,
            user_id=user.id,
            score=score,
            completed=True,
            attempted_at=utc_now() - timedelta(days=giorni_fa),
        )
    )
    db_session.flush()


def _titoli(consigli):
    return [c.challenge.get_display_name() for c in consigli]


def _kickers(consigli):
    return [c.kicker for c in consigli]


# ── la regola più forte: il tuo obiettivo ───────────────────────────────────
def test_un_obiettivo_su_un_esercizio_porta_quell_esercizio_in_cima(db_session):
    user = _user(db_session)
    scelto = _challenge(db_session, "Con obiettivo", max_score=10)
    _challenge(db_session, "Un altro", max_score=10)
    _prova(db_session, user, scelto, score=5, giorni_fa=2)
    TrainingGoalService.create(
        user.id, GoalKind.ESERCIZIO, challenge_id=scelto.id, target=8
    )

    consigli = build_advice(user.id)
    assert consigli, "con un obiettivo aperto qualcosa si deve poter dire"
    assert consigli[0].challenge.id == scelto.id
    assert "traguardo" in consigli[0].reason


def test_un_obiettivo_su_un_abilita_porta_un_esercizio_di_quell_abilita(db_session):
    user = _user(db_session)
    _challenge(db_session, "Di posizione", max_score=10, abilita=[Abilita.POSIZIONE])
    _challenge(db_session, "Di tiro", max_score=10, abilita=[Abilita.TIRO])
    TrainingGoalService.create(
        user.id,
        GoalKind.ABILITA,
        axis=CategoryAxis.ABILITA,
        axis_value=Abilita.POSIZIONE.value,
        target=70,
    )

    consigli = build_advice(user.id)
    assert consigli[0].challenge.get_display_name() == "Di posizione"
    assert "Posizione" in consigli[0].reason


# ── dove sei indietro ───────────────────────────────────────────────────────
def test_la_banda_piu_bassa_porta_un_esercizio_di_quella_categoria(db_session):
    """Con cinque prove per asse l'andamento può parlare, e il consiglio segue."""
    user = _user(db_session)
    forte = _challenge(db_session, "Di tiro", max_score=10, abilita=[Abilita.TIRO])
    debole = _challenge(db_session, "Di sponde", max_score=10, abilita=[Abilita.SPONDE])
    altro_debole = _challenge(
        db_session, "Di sponde 2", max_score=10, abilita=[Abilita.SPONDE]
    )
    for _volta in range(5):
        _prova(db_session, user, forte, score=9, giorni_fa=10)
        _prova(db_session, user, debole, score=3, giorni_fa=10)

    consigli = build_advice(user.id)
    indietro = [c for c in consigli if "banda più bassa" in c.reason]
    assert indietro, f"nessuna regola «dove sei indietro» fra {_kickers(consigli)}"
    assert indietro[0].challenge.id in (debole.id, altro_debole.id)
    assert "Sponde" in indietro[0].reason


# ── fermo da tempo ──────────────────────────────────────────────────────────
def test_quello_che_non_tocchi_da_un_mese_torna_a_galla(db_session):
    user = _user(db_session)
    dimenticato = _challenge(db_session, "Dimenticato", max_score=10)
    _prova(db_session, user, dimenticato, score=5, giorni_fa=FERMO_DA + 20)

    consigli = build_advice(user.id)
    fermi = [c for c in consigli if "Non lo provi da" in c.reason]
    assert fermi and fermi[0].challenge.id == dimenticato.id


def test_quello_di_ieri_non_e_fermo(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Di ieri", max_score=10)
    _prova(db_session, user, challenge, score=5, giorni_fa=1)

    assert not [c for c in build_advice(user.id) if "Non lo provi da" in c.reason]


# ── mai provato, alla tua portata ───────────────────────────────────────────
def _community(db_session, challenge, punteggi):
    for punteggio in punteggi:
        _prova(db_session, _user(db_session), challenge, score=punteggio, giorni_fa=3)


def test_un_esercizio_alla_tua_portata_si_propone(db_session):
    user = _user(db_session)
    giusto = _challenge(db_session, "Giusto", max_score=10)
    _community(db_session, giusto, [6, 5, 6, 5, 6])

    consigli = build_advice(user.id)
    mai = [c for c in consigli if "la tua forza" in c.reason]
    assert mai and mai[0].challenge.id == giusto.id


def test_un_muro_non_si_propone(db_session):
    """Un esercizio troppo difficile allontana chi sta cominciando."""
    user = _user(db_session)
    muro = _challenge(db_session, "Muro", max_score=10)
    _community(db_session, muro, [1, 1, 1, 1, 1])

    assert not [c for c in build_advice(user.id) if "la tua forza" in c.reason]


def test_un_esercizio_senza_stima_non_si_propone(db_session):
    """Sotto le soglie non si sa niente, e un consiglio a caso è peggio di niente."""
    user = _user(db_session)
    ignoto = _challenge(db_session, "Ignoto", max_score=10)
    _community(db_session, ignoto, [6, 6])

    assert not [c for c in build_advice(user.id) if "la tua forza" in c.reason]


# ── quello che non si consiglia mai ─────────────────────────────────────────
def test_un_esercizio_gia_saputo_non_si_consiglia(db_session):
    """Insistere dove si è al massimo non serve, e lo dice la issue."""
    user = _user(db_session)
    saputo = _challenge(db_session, "Saputo", max_score=10)
    for _volta in range(4):
        _prova(db_session, user, saputo, score=10, giorni_fa=FERMO_DA + 10)

    assert "Saputo" not in _titoli(build_advice(user.id))


def test_senza_catalogo_non_si_consiglia_niente(db_session):
    assert build_advice(_user(db_session).id) == []


# ── la forma dell'elenco ────────────────────────────────────────────────────
def test_non_si_ripete_lo_stesso_esercizio(db_session):
    """Lo stesso esercizio può vincere due regole: compare una volta."""
    user = _user(db_session)
    uno = _challenge(db_session, "Uno", max_score=10, abilita=[Abilita.SPONDE])
    for _volta in range(5):
        _prova(db_session, user, uno, score=3, giorni_fa=FERMO_DA + 5)
    TrainingGoalService.create(
        user.id, GoalKind.ESERCIZIO, challenge_id=uno.id, target=8
    )

    titoli = _titoli(build_advice(user.id))
    assert titoli.count("Uno") <= 1


def test_non_se_ne_danno_piu_di_tre(db_session):
    user = _user(db_session)
    for numero in range(6):
        challenge = _challenge(db_session, f"E{numero}", max_score=10)
        _prova(db_session, user, challenge, score=4, giorni_fa=FERMO_DA + numero + 1)

    assert len(build_advice(user.id)) <= QUANTI


def test_ogni_consiglio_porta_il_suo_motivo(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Qualcosa", max_score=10)
    _prova(db_session, user, challenge, score=4, giorni_fa=FERMO_DA + 5)

    for consiglio in build_advice(user.id):
        assert consiglio.kicker, "un consiglio senza titoletto"
        assert consiglio.reason, "un consiglio senza motivo non si segue"
