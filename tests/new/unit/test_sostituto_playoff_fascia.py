"""Il sostituto ai playoff di una fascia che non parte dal primo posto.

Difetto trovato il 2026-11-10. Una configurazione «Academy» sulle posizioni
5–8, quattro posti, dieci giocatori in classifica: `start_playoff` invita bene
il 5º, il 6º, il 7º e l'8º, perché passa da `candidati_per_posizione`. Ma
quando uno rifiuta, o il suo invito scade, la cascata passava da
`evaluate_qualifications`, che per il tipo `TOP_N` scorre la classifica dalla
posizione 1 e ignora `positions_from`/`positions_to`: veniva invitato il
**primo** in classifica, non il nono.

SPECIFICHE.md, «Playoff»: «se un giocatore rifiuta, la notifica passa al primo
degli esclusi e così via». Il primo degli esclusi di una fascia è il primo che
viene **dopo** la fascia, con le gare minime giocate e senza un invito a quel
playoff.

Lo stesso errore stava nella coda mostrata in dashboard («sei il primo degli
esclusi»), che usava la stessa valutazione.
"""

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, User
from models.base import utc_now
from models.campionato.models import Campionato
from models.classification.models import Classification
from models.matchmaking.configuration import MatchmakingStrategy
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
)
from models.playoff.services import PlayoffService
from models.status_enum import Discipline, GaraStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _utente(db_session):
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"pl_{sigla}",
        email=f"pl_{sigla}@t.local",
        role=UserRole.PLAYER.value,
        onboarding_completed=True,
    )
    utente.set_password("pw12345")
    db_session.add(utente)
    db_session.flush()
    return utente


def _academy(db_session, *, in_classifica=10, gare_minime=0, senza_gare=()):
    """Campionato terminato con l'Academy 5–8 e gli inviti partiti.

    Torna la configurazione e `posizione_di`, da utente a posto in classifica.
    Chi sta in `senza_gare` (posizioni) non ha gare giocate.
    """
    campionato = Campionato(
        name=f"C {uuid.uuid4().hex[:6]}",
        campionato_type=MatchmakingStrategy.AMALFI.value,
        is_active=True,
    )
    db_session.add(campionato)
    db_session.flush()
    campionato.terminated_at = utc_now()
    gara = Gara(
        number=1,
        name="G",
        date=date.today() - timedelta(days=3),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        matchmaking_strategy=MatchmakingStrategy.AMALFI.value,
        status=GaraStatus.COMPLETED.value,
        current_round=1,
        rounds_count=1,
        min_participants=2,
        campionato_id=campionato.id,
    )
    db_session.add(gara)
    configurazione = PlayoffConfiguration(
        campionato_id=campionato.id,
        name="Academy",
        playoff_type=PlayoffType.TOP_N,
        max_participants=4,
        positions_from=5,
        positions_to=8,
        min_garas_played=gare_minime,
        is_active=True,
        auto_generate=True,
    )
    db_session.add(configurazione)
    db_session.flush()
    posizione_di = {}
    for posizione in range(1, in_classifica + 1):
        utente = _utente(db_session)
        db_session.add(Inscription(user_id=utente.id, gara_id=gara.id))
        db_session.add(
            Classification(
                campionato_id=campionato.id,
                user_id=utente.id,
                position=posizione,
                total_matches_won=in_classifica - posizione,
                gare_played=0 if posizione in senza_gare else 1,
            )
        )
        posizione_di[utente.id] = posizione
    db_session.commit()
    PlayoffService.start_playoff(campionato.id)
    db_session.commit()
    return configurazione, posizione_di


def _inviti(configurazione):
    return PlayoffQualification.query.filter_by(
        configuration_id=configurazione.id
    ).all()


def _rifiuta(db_session, invito):
    sostituto = PlayoffService.decline_qualification(invito.id, invito.user_id)
    db_session.commit()
    return sostituto


def test_gli_inviti_partono_dalla_fascia(db_session):
    configurazione, posizione_di = _academy(db_session)
    assert sorted(posizione_di[q.user_id] for q in _inviti(configurazione)) == [
        5,
        6,
        7,
        8,
    ]


def test_chi_rifiuta_lascia_il_posto_al_nono_non_al_primo(db_session):
    configurazione, posizione_di = _academy(db_session)

    sostituto = _rifiuta(db_session, _inviti(configurazione)[0])

    assert sostituto is not None
    assert posizione_di[sostituto.user_id] == 9
    assert sostituto.qualifying_position == 9


def test_la_cascata_scorre_dopo_la_fascia_fino_a_finire_i_giocatori(db_session):
    """Nono, decimo, poi nessuno: mai chi sta sopra la fascia."""
    configurazione, posizione_di = _academy(db_session)
    invitati = _inviti(configurazione)

    chiamati = [_rifiuta(db_session, invito) for invito in invitati[:3]]

    assert [posizione_di[q.user_id] for q in chiamati[:2]] == [9, 10]
    assert chiamati[2] is None


def test_il_sostituto_deve_avere_le_gare_minime(db_session):
    """Il nono non ha gare giocate: tocca al decimo."""
    configurazione, posizione_di = _academy(db_session, gare_minime=1, senza_gare={9})

    sostituto = _rifiuta(db_session, _inviti(configurazione)[0])

    assert sostituto is not None
    assert posizione_di[sostituto.user_id] == 10


def test_anche_l_invito_scaduto_chiama_il_nono(db_session):
    configurazione, posizione_di = _academy(db_session)
    configurazione.response_deadline = utc_now() - timedelta(hours=1)
    scaduto = _inviti(configurazione)[0]
    scaduto.expires_at = utc_now() - timedelta(hours=1)
    for altro in _inviti(configurazione)[1:]:
        altro.expires_at = utc_now() + timedelta(days=2)
    db_session.commit()

    assert PlayoffService.expire_old_qualifications() == 1
    db_session.commit()

    nuovi = {posizione_di[q.user_id] for q in _inviti(configurazione)}
    assert nuovi == {5, 6, 7, 8, 9}


def test_la_coda_in_dashboard_e_la_stessa_della_cascata(db_session):
    from models.dashboard.playoff_cards import _coda_degli_esclusi

    configurazione, posizione_di = _academy(db_session)
    con_invito = {q.user_id for q in _inviti(configurazione)}

    coda = _coda_degli_esclusi(configurazione, con_invito)

    assert [posizione_di[user_id] for user_id in coda] == [9, 10]
