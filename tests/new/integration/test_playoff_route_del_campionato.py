"""Le route dei playoff agiscono solo sui playoff del campionato dell'indirizzo.

Il permesso (`campionato_manager_required`) si controlla sul campionato
dell'indirizzo; la configurazione e l'invito arrivano invece come numeri, e
fino al 2026-09-29 sei route li usavano senza guardare a quale campionato
appartenessero. Il direttore di un campionato poteva così aggiungere, togliere,
rispondere per conto, cambiare punteggio, configurazione o disattivare i
playoff di **un altro** campionato, cambiando un numero nell'indirizzo.

Le due route che già lo controllavano (`playoff_calendario`,
`create_playoff_gara`) rispondono con «Configurazione playoff non trovata.»:
le altre fanno lo stesso.
"""

import uuid

import pytest

from models import Campionato, db
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffType,
    QualificationStatus,
)
from models.user.models import DirectorAssignment, User
from tests.new.integration.test_avvio_playoff_route import (  # noqa: F401
    _login,
    admin_user,
    terminated_campionato_with_playoff,
)


def _uid():
    return str(uuid.uuid4())[:8]


@pytest.fixture
def due_campionati(
    db_session,
    admin_user,  # noqa: F811
    terminated_campionato_with_playoff,  # noqa: F811
):
    """Il campionato B con gli inviti partiti; il campionato A del direttore."""
    from models.playoff.services import PlayoffService

    camp_b, cfg_b, giocatori_b, _gara = terminated_campionato_with_playoff
    PlayoffService.start_playoff(camp_b.id)

    direttore = User(
        username=f"dir_{_uid()}", email=f"dir_{_uid()}@t.com", role="director"
    )
    direttore.set_password("test1234")
    camp_a = Campionato(name=f"Camp A {_uid()}", campionato_type="amalfi")
    db_session.add_all([direttore, camp_a])
    db_session.flush()
    cfg_a = PlayoffConfiguration(
        campionato_id=camp_a.id,
        name="Elite A",
        playoff_type=PlayoffType.TOP_N,
        max_participants=4,
        positions_from=1,
        positions_to=4,
        is_active=True,
    )
    db_session.add(cfg_a)
    db_session.add(
        DirectorAssignment(
            user_id=direttore.id,
            entity_type="campionato",
            entity_id=camp_a.id,
            assigned_by_id=admin_user.id,
        )
    )
    db_session.commit()
    return direttore, camp_a, cfg_a, camp_b, cfg_b, giocatori_b


def _stato_b(cfg_b_id):
    cfg = db.session.get(PlayoffConfiguration, cfg_b_id)
    quals = PlayoffQualification.query.filter_by(configuration_id=cfg_b_id).all()
    return (
        cfg.name,
        cfg.is_active,
        cfg.final_ranking_mode,
        cfg.playoff_weight,
        sorted((q.user_id, q.status) for q in quals),
    )


def _messaggi(client):
    with client.session_transaction() as sessione:
        return [testo for _cat, testo in sessione.pop("_flashes", [])]


def _pending_b(cfg_b_id):
    return PlayoffQualification.query.filter_by(
        configuration_id=cfg_b_id, status=QualificationStatus.PENDING
    ).first()


def test_il_direttore_di_a_non_tocca_la_configurazione_di_b(
    client, db_session, due_campionati
):
    direttore, camp_a, _cfg_a, _camp_b, cfg_b, giocatori_b = due_campionati
    prima = _stato_b(cfg_b.id)
    qual = _pending_b(cfg_b.id)
    assert qual is not None
    _login(client, direttore)
    base = f"/admin/campionato/{camp_a.id}/playoff"

    richieste = [
        (f"{base}/{cfg_b.id}/add-player", {"user_id": giocatori_b[-1].id}),
        (f"{base}/{cfg_b.id}/remove-player", {"qualification_id": qual.id}),
        (
            f"{base}/{cfg_b.id}/respond",
            {"qualification_id": qual.id, "answer": "decline"},
        ),
        (
            f"{base}/{cfg_b.id}/scoring",
            {"final_ranking_mode": "playoff_only", "playoff_weight": 3},
        ),
        (f"{base}/config/{cfg_b.id}/edit", {"name": "Rubato"}),
        (f"{base}/config/{cfg_b.id}/deactivate", {}),
    ]
    for url, dati in richieste:
        risposta = client.post(url, data=dati)
        assert risposta.status_code == 302, url
        assert _messaggi(client) == ["Configurazione playoff non trovata."], url

    db.session.expire_all()
    assert _stato_b(cfg_b.id) == prima


def test_un_invito_di_b_non_passa_dalla_configurazione_di_a(
    client, db_session, due_campionati
):
    """La configurazione è di A, ma l'invito è di B: non si tocca."""
    direttore, camp_a, cfg_a, _camp_b, cfg_b, _giocatori_b = due_campionati
    prima = _stato_b(cfg_b.id)
    qual = _pending_b(cfg_b.id)
    _login(client, direttore)
    base = f"/admin/campionato/{camp_a.id}/playoff/{cfg_a.id}"

    for url, dati in [
        (f"{base}/remove-player", {"qualification_id": qual.id}),
        (f"{base}/respond", {"qualification_id": qual.id, "answer": "accept"}),
    ]:
        client.post(url, data=dati)
        assert _messaggi(client) == ["Invito non trovato."], url

    db.session.expire_all()
    assert _stato_b(cfg_b.id) == prima
