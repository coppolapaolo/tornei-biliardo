"""L'esercizio giocato al posto della X lo sceglie il direttore (issue #267).

Fino a oggi lo sceglieva l'applicazione: `get_challenge_for_x_replacement`
prendeva dal catalogo globale gli esercizi attivi e a punteggio, contava quante
volte ciascuno era già stato usato in quella gara, e restituiva il meno usato.

Non è una questione di comodità. In una gara a numero dispari **riposa una
persona diversa a ogni turno**: se l'esercizio cambia da un turno all'altro, due
giocatori ricevono prove di difficoltà diversa, e i loro punteggi finiscono
nella stessa classifica con lo stesso peso. Per questo la scelta sta sulla
**gara** e non sul turno — un esercizio solo per tutte le X è l'unica
configurazione in cui la X è la stessa prova per tutti.

Non c'è **nessuna** selezione automatica, e non è una semplificazione: sceglie
sempre il direttore. Quando la configurazione non è utilizzabile — nessuna
scelta, esercizio disattivato o a esito booleano — la funzione restituisce
`None` invece di sostituire con un altro. Sostituire in silenzio sarebbe di
nuovo l'applicazione che sceglie al posto del direttore, per giunta in un
momento in cui nessuno sta guardando.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.competition.models import Gara
from models.status_enum import GaraStatus


def _esercizio(db_session, descrizione, *, pass_fail_only=False, attivo=True):
    c = Challenge(
        description=f"{descrizione} {uuid.uuid4().hex[:6]}",
        image_path="test.jpg",
        pass_fail_only=pass_fail_only,
        is_active=attivo,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _gara(db_session, **override):
    campi = dict(
        campionato_id=None,
        number=1,
        name=f"Gara {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=5,
        rounds_count=3,
        min_participants=3,
        max_participants=8,
        matchmaking_strategy="amalfi",
        odd_number_policy="bye_with_challenge",
        status=GaraStatus.SETUP.value,
    )
    campi.update(override)
    g = Gara(**campi)
    db_session.add(g)
    db_session.flush()
    return g


@pytest.mark.unit
def test_la_scelta_del_direttore_vince(app, db_session):
    """Lo scelto è creato per **ultimo**, di proposito.

    A parità di utilizzi la selezione automatica restituisce il primo del
    catalogo: un test in cui l'esercizio scelto è anche il primo passerebbe
    identico con la funzione vecchia, e non verificherebbe niente.
    """
    primo_del_catalogo = _esercizio(db_session, "Il primo, che verrebbe scelto")
    _esercizio(db_session, "Un altro qualsiasi")
    scelto = _esercizio(db_session, "Quello che vuole il direttore")
    gara = _gara(db_session, x_challenge_id=scelto.id)
    db_session.commit()

    trovato = ChallengeService.get_challenge_for_x_replacement(gara.id)
    assert trovato.id == scelto.id
    assert trovato.id != primo_del_catalogo.id


@pytest.mark.unit
def test_la_scelta_vale_per_tutti_i_turni(app, db_session):
    """È il punto della decisione: la X deve essere la stessa prova per tutti.

    Non c'è un parametro «turno» da nessuna parte, e il test lo fissa: chiamare
    due volte la stessa gara deve dare lo stesso esercizio, sempre.
    """
    _esercizio(db_session, "Il primo del catalogo")
    scelto = _esercizio(db_session, "Sempre questo")
    gara = _gara(db_session, x_challenge_id=scelto.id)
    db_session.commit()

    primo = ChallengeService.get_challenge_for_x_replacement(gara.id)
    secondo = ChallengeService.get_challenge_for_x_replacement(gara.id)

    assert primo.id == secondo.id == scelto.id


@pytest.mark.unit
def test_senza_scelta_non_c_e_esercizio(app, db_session):
    """Nessun ripiego: se il direttore non ha scelto, non c'è niente da giocare.

    È il caso delle gare create prima di questa regola. Pescarne uno dal
    catalogo sarebbe l'applicazione che decide al posto del direttore — cioè
    esattamente ciò che la #267 toglie.
    """
    _esercizio(db_session, "Nel catalogo, ma non scelto")
    gara = _gara(db_session)  # x_challenge_id resta None
    db_session.commit()

    assert ChallengeService.get_challenge_for_x_replacement(gara.id) is None


@pytest.mark.unit
def test_un_esercizio_disattivato_resta_giocabile(app, db_session):
    """Disattivare nel catalogo non svuota la X di una gara in corso.

    La disattivazione fa nascere una copia attiva su cui la gara viene
    ripuntata (vedi `test_esercizio_disattivato_copia.py`), quindi da qui la
    prova resta giocabile ed è la stessa. Quello che non succede — mai — è che
    l'applicazione sostituisca con un esercizio **diverso**.
    """
    altro = _esercizio(db_session, "Un altro, che non c'entra")
    scelto = _esercizio(db_session, "Poi ritirato dal catalogo")
    gara = _gara(db_session, x_challenge_id=scelto.id)
    db_session.commit()

    ChallengeService.update_challenge(scelto.id, is_active=False)
    db_session.commit()

    trovato = ChallengeService.get_challenge_for_x_replacement(gara.id)
    assert trovato is not None
    assert trovato.id != altro.id
    assert trovato.description == scelto.description


@pytest.mark.unit
def test_un_esercizio_riuscita_o_no_non_e_utilizzabile(app, db_session):
    """Il punteggio della X è una differenza triangoli: un esito booleano non la dà.

    Il modulo non lo offre nemmeno, ma un esercizio può diventare
    superato/non superato *dopo* essere stato scelto. Anche qui si segnala
    invece di rimpiazzare.
    """
    _esercizio(db_session, "A punteggio")
    booleano = _esercizio(db_session, "Superata o no", pass_fail_only=True)
    gara = _gara(db_session, x_challenge_id=booleano.id)
    db_session.commit()

    assert ChallengeService.get_challenge_for_x_replacement(gara.id) is None


# Manca di proposito un test sull'id orfano (`x_challenge_id` che punta a un
# esercizio inesistente). Su uno schema costruito dal modello la chiave esterna
# c'è e il DB rifiuta la scrittura, quindi il caso non è costruibile qui; in
# produzione invece la colonna nasce da un `ALTER TABLE ADD COLUMN`, che in
# SQLite non può creare vincoli, e lì l'id orfano è possibile. Il guard in
# `get_challenge_for_x_replacement` (che restituisce None) esiste per quella
# metà del mondo, ed è annotato lì: un test verde su un vincolo che in
# produzione non c'è sarebbe peggio di nessun test.
