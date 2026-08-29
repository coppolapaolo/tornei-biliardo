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

`x_challenge_id` a NULL resta legittimo e vuol dire «scegli tu»: è il
comportamento storico, ed è quello di ogni gara creata prima di oggi. Il ripiego
automatico non si toglie, si retrocede a ripiego.
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
def test_senza_scelta_resta_il_ripiego_automatico(app, db_session):
    """Le gare create prima non hanno la colonna valorizzata e devono funzionare."""
    _esercizio(db_session, "Catalogo")
    gara = _gara(db_session)  # x_challenge_id resta None
    db_session.commit()

    assert ChallengeService.get_challenge_for_x_replacement(gara.id) is not None


@pytest.mark.unit
def test_un_esercizio_disattivato_non_viene_piu_usato(app, db_session):
    """Una scelta che non è più valida ricade sul ripiego, non rompe.

    Un esercizio si può disattivare dal catalogo dopo essere stato scelto: la
    gara resterebbe con un id che punta a qualcosa che non si deve più
    proporre. Meglio un esercizio diverso che una X che non si può giocare.
    """
    ripiego = _esercizio(db_session, "Ancora buono")
    scelto = _esercizio(db_session, "Poi ritirato")
    gara = _gara(db_session, x_challenge_id=scelto.id)
    db_session.commit()

    scelto.is_active = False
    db_session.commit()

    trovato = ChallengeService.get_challenge_for_x_replacement(gara.id)
    assert trovato is not None
    assert trovato.id == ripiego.id


@pytest.mark.unit
def test_un_esercizio_riuscita_o_no_non_viene_usato(app, db_session):
    """Il punteggio della X è una differenza triangoli: un esito booleano non la dà.

    È già il filtro della selezione automatica, e deve valere anche quando è il
    direttore a scegliere — altrimenti la scelta manuale sarebbe l'unico modo di
    aggirare un vincolo di dominio.
    """
    a_punteggio = _esercizio(db_session, "A punteggio")
    booleano = _esercizio(db_session, "Superata o no", pass_fail_only=True)
    gara = _gara(db_session, x_challenge_id=booleano.id)
    db_session.commit()

    trovato = ChallengeService.get_challenge_for_x_replacement(gara.id)
    assert trovato is not None
    assert trovato.id == a_punteggio.id


# Manca di proposito un test sull'id orfano (`x_challenge_id` che punta a un
# esercizio inesistente). Su uno schema costruito dal modello la chiave esterna
# c'è e il DB rifiuta la scrittura, quindi il caso non è costruibile qui; in
# produzione invece la colonna nasce da un `ALTER TABLE ADD COLUMN`, che in
# SQLite non può creare vincoli, e lì l'id orfano è possibile. Il guard in
# `get_challenge_for_x_replacement` esiste per quella metà del mondo, ed è
# annotato lì: un test verde su un vincolo che in produzione non c'è sarebbe
# peggio di nessun test.
