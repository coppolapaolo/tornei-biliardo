"""Su `Match` non esiste nessun `validated_by_admin`, e nessuno può fingere che ci sia.

Quel nome è una colonna di `Rack` (e di `Set`), dove indica «questo rack l'ha
messo a verbale il direttore». Su `Match` non c'è mai stata — ma sei punti del
codice gliela assegnavano lo stesso. SQLAlchemy non protesta: un attributo non
mappato diventa un normale attributo d'istanza, vive quanto la richiesta e non
tocca il database.

Due dei sei erano davvero inerti (`MatchResultService.validate_by_admin`, il
reset in `RackService`): il corpo era dentro un `if hasattr(...)` sempre falso,
quindi non è mai stato eseguito. Gli altri quattro invece **funzionavano**, ed
è la parte insidiosa: `MatchStateService.to_completed` rileggeva l'attributo
con `getattr(match, "validated_by_admin", False)` per decidere se lasciar
chiudere una partita ancora PENDING. Era un parametro passato di nascosto
attraverso l'oggetto invece che per argomento — invisibile nella firma,
invisibile nel modello, al punto che `round_creation.py` aveva dovuto zittire
il type checker con un `# type: ignore[attr-defined]`.

Toglierlo e basta avrebbe rotto una funzione vera (il direttore che chiude una
partita mai iniziata). Ora quel permesso è il parametro `closed_by_director`, e
questi test presidiano le due metà: che la funzione ci sia ancora, e che la
scorciatoia non ci sia più.
"""

from __future__ import annotations

import pytest

from models.base import db
from models.match.models import Match, Rack
from models.match.state_service import MatchStateService
from models.match.services import InvalidTransitionError
from models.status_enum import MatchStatus

# ══ Il modello ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_match_non_ha_la_colonna_validated_by_admin():
    """Se un giorno la colonna venisse aggiunta davvero, questo test cade — ed
    è il momento giusto per rileggere `closed_by_director`, che a quel punto
    avrebbe un doppione persistito."""
    assert "validated_by_admin" not in Match.__table__.columns


@pytest.mark.unit
def test_la_colonna_esiste_invece_su_rack():
    """Il nome non è sbagliato in sé: è sbagliato l'oggetto a cui veniva
    attaccato. Sul rack significa «messo a verbale dal direttore»."""
    assert "validated_by_admin" in Rack.__table__.columns


# ══ Il permesso del direttore, ora dichiarato ═══════════════════════════════


@pytest.fixture
def partita(db_session) -> Match:
    """Una partita fra due giocatori, dentro una gara: il minimo che serve.

    `to_completed` non tocca solo lo stato — registra l'incontro per
    l'anti-reincontro, libera il tavolo, emette l'evento — quindi la gara
    serve davvero e non si può usare un `Match` scollegato.
    """
    from models.competition.models import Gara
    from models.status_enum import GaraStatus
    from models.user.models import User
    from models.base import utc_now

    giocatori = []
    for numero in (1, 2):
        utente = User(
            username=f"fantasma{numero}",
            email=f"fantasma{numero}@example.test",
            role="player",
        )
        utente.set_password("password")
        db_session.add(utente)
        giocatori.append(utente)

    gara = Gara(
        number=1,
        name="Gara del flag fantasma",
        date=utc_now().date(),
        time=utc_now().time(),
        discipline="8_ball",
        distance=5,
        is_race_to=True,
        status=GaraStatus.PLAYING.value,
    )
    db_session.add(gara)
    db_session.flush()

    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=giocatori[0].id,
        player2_id=giocatori[1].id,
        player1_score=5,
        player2_score=3,
        status=MatchStatus.PLAYING.value,
        is_bye=False,
        is_trio=False,
    )
    db_session.add(match)
    db_session.commit()
    return match


@pytest.fixture
def partita_mai_iniziata(db_session, partita) -> Match:
    """La stessa partita, ma ancora PENDING: non un bye, non un trio."""
    partita.status = MatchStatus.PENDING.value
    db.session.commit()
    return partita


@pytest.mark.unit
def test_una_partita_mai_iniziata_non_si_chiude_da_sola(partita_mai_iniziata):
    with pytest.raises(InvalidTransitionError, match="non è ancora iniziata"):
        MatchStateService.to_completed(partita_mai_iniziata.id)


@pytest.mark.unit
def test_il_direttore_puo_chiudere_una_partita_mai_iniziata(partita_mai_iniziata):
    """Il caso d'uso da non perdere: risultato inserito a mano, turno
    importato, partita chiusa d'ufficio. Prima passava dall'attributo
    fantasma, ora dal parametro."""
    aggiornata = MatchStateService.to_completed(
        partita_mai_iniziata.id, closed_by_director=True
    )

    assert aggiornata.status == MatchStatus.CLOSED_UNILATERALLY.value


@pytest.mark.unit
def test_appiccicare_l_attributo_non_apre_piu_il_varco(partita_mai_iniziata):
    """Il presidio che chiude il canale nascosto.

    Scrivere `match.validated_by_admin = True` su un'istanza non deve più
    ottenere niente: se lo ottenesse, il vecchio schema sarebbe ancora in
    piedi e qualcuno lo riscoprirebbe copiando una riga da un altro file — che
    è esattamente come si era propagato a sei punti diversi.
    """
    setattr(partita_mai_iniziata, "validated_by_admin", True)

    with pytest.raises(InvalidTransitionError, match="non è ancora iniziata"):
        MatchStateService.to_completed(partita_mai_iniziata.id)


@pytest.mark.unit
def test_una_partita_in_corso_si_chiude_senza_bisogno_del_direttore(partita):
    """Il parametro serve solo a scavalcare PENDING: da PLAYING non c'entra
    nulla, e il suo valore di default non deve aver cambiato niente."""
    aggiornata = MatchStateService.to_completed(partita.id)

    assert aggiornata.status == MatchStatus.CLOSED_UNILATERALLY.value
