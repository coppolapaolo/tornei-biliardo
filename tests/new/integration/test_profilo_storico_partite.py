"""Le partite recenti del profilo comprendono le sfide individuali.

Segnalato provando l'app: una sfida individuale appena conclusa non compariva
in «Storico Partite Recenti», né nelle statistiche del profilo.

Erano due errori sovrapposti, tutti e due già in `CLAUDE.md` come trappole
note:

1. le partite di un giocatore si cercavano nella sola tabella ``match``, e le
   sfide individuali stanno su ``individual_match``;
2. si contava come «giocata» la sola ``CLOSED_UNILATERALLY``, che è la
   chiusura del **direttore**: una partita chiusa dai due giocatori con la
   doppia conferma (``CONFIRMED_BY_BOTH``) non contava — ed è esattamente
   come finisce ogni sfida individuale.

Lo storico completo (`/player/history`) faceva già la cosa giusta: qui il
profilo ci si allinea, invece di tenersi la sua query.
"""

import uuid
from datetime import date, timedelta

import pytest
from flask import g

from models import User, db
from models.base import utc_now
from models.campionato.models import Campionato
from models.competition.models import Gara
from models.individual_match.models import IndividualMatch
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _player():
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"s_{uid}",
        email=f"s_{uid}@test.com",
        role=UserRole.PLAYER.value,
        gamification_override=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _sfida_individuale(player1, player2, status=MatchStatus.CONFIRMED_BY_BOTH):
    """Una sfida individuale conclusa come finiscono davvero: doppia conferma."""
    match = IndividualMatch(
        player1_id=player1.id,
        player2_id=player2.id,
        location="Sala Test",
        scheduled_at=utc_now() - timedelta(hours=1),
        status=status,
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        player1_score=5,
        player2_score=2,
        winner_id=player1.id,
    )
    match.ended_at = utc_now()
    db.session.add(match)
    db.session.commit()
    return match


def _partita_di_gara(player1, player2):
    campionato = Campionato(name=f"Camp {uuid.uuid4().hex[:6]}")
    db.session.add(campionato)
    db.session.commit()
    gara = Gara(
        campionato_id=campionato.id,
        name="Gara 1",
        number=1,
        date=date.today() - timedelta(days=3),
        status=GaraStatus.COMPLETED.value,
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
    )
    db.session.add(gara)
    db.session.commit()
    match = Match(
        gara_id=gara.id,
        player1_id=player1.id,
        player2_id=player2.id,
        round_number=1,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        player1_score=5,
        player2_score=1,
        winner_id=player1.id,
    )
    db.session.add(match)
    db.session.commit()
    return match


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
    return client


def _get(client, url, **kw):
    g.pop("_login_user", None)
    return client.get(url, **kw)


def _link_sfida(match):
    """Il collegamento alla sfida: è quello che la card delle partite disegna.

    Il nome dell'avversario da solo non basta come prova: in sviluppo la barra
    di `/debug/login` elenca tutti gli utenti, e lo si troverebbe in pagina
    anche senza nessuna partita.
    """
    return f'/match/matches/{match.id}"'


def _link_partita(match):
    return f'/admin/match/{match.id}"'


def _statistica(body: str, valore) -> bool:
    """Se `valore` compare come **numero di una statistica** del profilo.

    Prima si cercava `">1</h3>"`: il conteggio giusto dentro il tag che il
    componente usava allora. Portandolo al design system i numeri sono passati
    da `<h3 class="text-primary">` a `<div class="c7-num-lg">`, e i due test
    che ne dipendevano sono diventati rossi senza che il **conteggio** — cioè
    l'unica cosa che volevano difendere — fosse cambiato di una virgola.

    Qui si cerca la classe, non il tag: e' quella a dire «questo e' un numero
    di statistica», e sopravvive al prossimo giro di impaginazione.
    """
    import re

    numeri = re.findall(r'class="c7-num(?:-lg|-xl)?"[^>]*>\s*([^<\s][^<]*?)\s*<', body)
    return str(valore) in [n.strip() for n in numeri]


@pytest.mark.integration
class TestPartiteRecentiDelProfilo:
    def test_la_sfida_individuale_compare(self, app):
        me, avversario = _player(), _player()
        sfida = _sfida_individuale(me, avversario)

        body = _get(_client_for(app, me), "/player/profile").get_data(as_text=True)

        assert _link_sfida(sfida) in body

    def test_la_sfida_individuale_conta_nelle_statistiche(self, app):
        """Chiusa dai due giocatori, non dal direttore: è giocata lo stesso."""
        me, avversario = _player(), _player()
        _sfida_individuale(me, avversario)

        body = _get(_client_for(app, me), "/player/profile").get_data(as_text=True)

        # Una giocata e vinta: prima erano zero, perché `CONFIRMED_BY_BOTH` non
        # veniva contata e la tabella non veniva nemmeno interrogata.
        assert _statistica(body, 1)
        assert _statistica(body, "100.0%")

    def test_partite_di_gara_e_sfide_stanno_insieme(self, app):
        me, avversario = _player(), _player()
        altro = _player()
        partita = _partita_di_gara(me, altro)
        sfida = _sfida_individuale(me, avversario)

        body = _get(_client_for(app, me), "/player/profile").get_data(as_text=True)

        assert _link_sfida(sfida) in body
        assert _link_partita(partita) in body

    def test_una_sfida_ancora_in_corso_non_compare(self, app):
        """Lo storico è delle partite giocate, non di quelle in corso."""
        me, avversario = _player(), _player()
        sfida = _sfida_individuale(me, avversario, status=MatchStatus.IN_PROGRESS)

        body = _get(_client_for(app, me), "/player/profile").get_data(as_text=True)

        assert _link_sfida(sfida) not in body

    def test_il_profilo_e_lo_storico_contano_lo_stesso(self, app):
        """Due schermate che contano per conto proprio prima o poi divergono."""
        from models.player.history_service import HistoryFilters, PlayerHistoryService

        me, avversario = _player(), _player()
        altro = _player()
        _partita_di_gara(me, altro)
        _sfida_individuale(me, avversario)

        _, stats = PlayerHistoryService.get_unified_match_history(
            user_id=me.id, filters=HistoryFilters(), page=1, per_page=20
        )
        body = _get(_client_for(app, me), "/player/profile").get_data(as_text=True)

        assert stats.total_matches == 2
        assert _statistica(body, stats.total_matches)


@pytest.mark.integration
class TestProfiloDiUnAltro:
    """Il profilo pubblico contava e mostrava per conto suo: stessi difetti."""

    def _apri_le_partite(self, owner):
        """Il profilo altrui mostra le partite solo se il proprietario vuole."""
        from models.user.privacy_service import PrivacyService

        PrivacyService.update_privacy_settings(owner.id, show_recent_matches=True)

    def test_la_sfida_individuale_compare(self, app):
        owner, avversario = _player(), _player()
        visitatore = _player()
        sfida = _sfida_individuale(owner, avversario)
        self._apri_le_partite(owner)

        body = _get(
            _client_for(app, visitatore), f"/player/profile/{owner.id}"
        ).get_data(as_text=True)

        assert _link_sfida(sfida) in body

    def test_una_partita_nascosta_resta_nascosta(self, app):
        from models.user.privacy_service import PrivacyService

        owner, altro = _player(), _player()
        visitatore = _player()
        partita = _partita_di_gara(owner, altro)
        self._apri_le_partite(owner)
        PrivacyService.hide_match(owner.id, partita.id)

        body = _get(
            _client_for(app, visitatore), f"/player/profile/{owner.id}"
        ).get_data(as_text=True)

        assert _link_partita(partita) not in body

    def test_nascondere_una_partita_non_nasconde_la_sfida_con_lo_stesso_numero(
        self, app
    ):
        """Gli id delle due tabelle si sovrappongono.

        `match` e `individual_match` numerano per conto proprio: la partita di
        gara 7 e la sfida 7 esistono insieme. Un filtro che guardasse il solo
        id nasconderebbe la sfida di un altro giocatore, senza che nessuno
        l'abbia chiesto.
        """
        from models.user.privacy_service import PrivacyService

        owner, altro = _player(), _player()
        avversario = _player()
        visitatore = _player()
        partita = _partita_di_gara(owner, altro)
        sfida = _sfida_individuale(owner, avversario)
        self._apri_le_partite(owner)
        # Il caso vale solo se i due numeri coincidono davvero.
        assert partita.id == sfida.id

        # Si nasconde **la partita di gara**: è l'unica cosa che si può
        # nascondere, e il numero è quello.
        PrivacyService.hide_match(owner.id, partita.id)

        body = _get(
            _client_for(app, visitatore), f"/player/profile/{owner.id}"
        ).get_data(as_text=True)

        # La partita di gara sparisce, la sfida con lo stesso numero no.
        assert _link_partita(partita) not in body
        assert _link_sfida(sfida) in body
