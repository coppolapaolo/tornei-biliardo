"""Il selettore di certificazione nel profilo (ADR-083, UC6).

In testa al profilo, proprio e altrui, un selettore **Tornei · Confermate ·
Tutte** cambia insieme ELO, vittorie, sconfitte, pareggi, TPA e runout, e fra
le partite recenti mostra o nasconde le sfide in attesa.

Il server rende **i tre valori**, ciascuno in un blocco con ``data-vista``; il
selettore li alterna nel browser senza ricaricare (``static/js/
vista_certificazione.js``, provato in ``tests/frontend/
test_vista_certificazione.cjs``). Qui si controlla la metà del server: che
ogni blocco porti i numeri della sua vista, calcolati dalle stesse voci.

Caso d'uso in ``docs/usecases/sfide-e-certificazione.md``, UC6.
"""

import uuid
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple

import pytest
from flask import g

from models import User, db
from models.base import utc_now
from models.campionato.models import Campionato
from models.competition.models import Gara
from models.individual_match.models import IndividualMatch
from models.match.models import Match
from models.rating.models import PlayerRating, RatingSystem
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


# ──────────────────────────────────────────────────────────────────────────
# Lettura della pagina
# ──────────────────────────────────────────────────────────────────────────

_VUOTI = {
    "area",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "wbr",
}


class _Pagina(HTMLParser):
    """Legge i numeri marcati ``data-stat`` e i link, con la vista in cui stanno.

    La vista si eredita dal blocco ``data-vista`` più vicino: è così che il
    selettore decide cosa mostrare, e così la legge il test.
    """

    def __init__(self):
        super().__init__()
        self._pila: List[Tuple[str, Optional[str]]] = []
        self._stat: Optional[Tuple[Optional[str], str, int]] = None
        self._testo: List[str] = []
        #: (vista, nome) → testo
        self.numeri: Dict[Tuple[Optional[str], str], str] = {}
        #: href → viste dei blocchi in cui compare
        self.link: Dict[str, Set[Optional[str]]] = {}
        #: vista → testo visibile del blocco (per le frasi)
        self.testi: Dict[Optional[str], List[str]] = {}
        self.scelte: List[str] = []

    def _vista(self) -> Optional[str]:
        for _, vista in reversed(self._pila):
            if vista is not None:
                return vista
        return None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "data-vista-scelta" in a:
            self.scelte.append(a["data-vista-scelta"])
        if tag == "a" and a.get("href"):
            self.link.setdefault(a["href"], set()).add(self._vista())
        if tag in _VUOTI:
            return
        self._pila.append((tag, a.get("data-vista")))
        if "data-stat" in a and self._stat is None:
            self._stat = (self._vista(), a["data-stat"], len(self._pila))
            self._testo = []

    def handle_endtag(self, tag):
        if tag in _VUOTI or not self._pila:
            return
        if self._stat is not None and len(self._pila) == self._stat[2]:
            vista, nome, _ = self._stat
            self.numeri[(vista, nome)] = " ".join("".join(self._testo).split())
            self._stat = None
        self._pila.pop()

    def handle_data(self, data):
        if self._stat is not None:
            self._testo.append(data)
        self.testi.setdefault(self._vista(), []).append(data)

    def testo(self, vista: str) -> str:
        return " ".join(" ".join(self.testi.get(vista, [])).split())


def _leggi(body: str) -> _Pagina:
    pagina = _Pagina()
    pagina.feed(body)
    return pagina


# ──────────────────────────────────────────────────────────────────────────
# Dati
# ──────────────────────────────────────────────────────────────────────────


def _player(**kw):
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"v_{uid}",
        email=f"v_{uid}@test.com",
        role=UserRole.PLAYER.value,
        gamification_override=True,
        **kw,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _sfida(p1, p2, ore_fa, **kw):
    valori = dict(
        player1_id=p1.id,
        player2_id=p2.id,
        location="Sala Test",
        scheduled_at=utc_now() - timedelta(hours=ore_fa),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
    )
    valori.update(kw)
    sfida = IndividualMatch(**valori)
    db.session.add(sfida)
    db.session.commit()
    return sfida


def _confermata(p1, p2, ore_fa=30):
    return _sfida(
        p1,
        p2,
        ore_fa,
        status=MatchStatus.CONFIRMED_BY_BOTH,
        player1_confirmed=True,
        player2_confirmed=True,
        player1_score=3,
        player2_score=1,
        winner_id=p1.id,
    )


def _in_attesa(p1, p2, ore_fa=2):
    """Firmata da ``p1`` soltanto: il risultato è quello che ha dichiarato."""
    return _sfida(
        p1,
        p2,
        ore_fa,
        status=MatchStatus.IN_PROGRESS,
        player1_confirmed=True,
        player2_confirmed=False,
        player1_score=3,
        player2_score=2,
    )


def _forfait_perso(p1, p2, ore_fa=20):
    """``p1`` abbandona: vince ``p2``. È confermata, ma non muove l'ELO."""
    return _sfida(
        p1,
        p2,
        ore_fa,
        status=MatchStatus.CLOSED_UNILATERALLY,
        player1_score=1,
        player2_score=2,
        winner_id=p2.id,
    )


def _partita_di_torneo(p1, p2, giorni_fa=3):
    campionato = Campionato(name=f"Camp {uuid.uuid4().hex[:6]}")
    db.session.add(campionato)
    db.session.commit()
    gara = Gara(
        campionato_id=campionato.id,
        name="Gara 1",
        number=1,
        date=date.today() - timedelta(days=giorni_fa),
        status=GaraStatus.COMPLETED.value,
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
    )
    db.session.add(gara)
    db.session.commit()
    match = Match(
        gara_id=gara.id,
        player1_id=p1.id,
        player2_id=p2.id,
        round_number=1,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        player1_score=5,
        player2_score=1,
        winner_id=p1.id,
    )
    db.session.add(match)
    db.session.commit()
    return match


def _imposta_elo(user, sistema, valore):
    """Valori distinti per i tre pool, così un pool scambiato si vede."""
    rating = PlayerRating.get_user_rating(user.id, sistema)
    if rating is None:
        rating = PlayerRating(
            user_id=user.id, rating_system=sistema, rating_value=valore, robustness=1
        )
        db.session.add(rating)
    else:
        rating.rating_value = valore
    if sistema is RatingSystem.ELO:
        user.elo_rating = valore
    db.session.commit()


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
    return client


def _get(client, url):
    g.pop("_login_user", None)
    return client.get(url).get_data(as_text=True)


@pytest.fixture
def paolo_e_pietro(app):
    """Paolo: un torneo vinto, una sfida confermata vinta, un forfait perso,
    una sfida vinta e firmata solo da lui."""
    paolo, pietro, gianni = _player(), _player(), _player()
    torneo = _partita_di_torneo(paolo, gianni)
    confermata = _confermata(paolo, pietro)
    forfait = _forfait_perso(paolo, gianni)
    attesa = _in_attesa(paolo, pietro)
    _imposta_elo(paolo, RatingSystem.ELO, 1510)
    _imposta_elo(paolo, RatingSystem.ELO_GLOBAL, 1530)
    _imposta_elo(paolo, RatingSystem.ELO_ALL, 1545)
    return {
        "paolo": paolo,
        "pietro": pietro,
        "gianni": gianni,
        "torneo": torneo,
        "confermata": confermata,
        "forfait": forfait,
        "attesa": attesa,
    }


def _link_sfida(sfida):
    return f"/match/matches/{sfida.id}"


def _link_partita(match):
    return f"/admin/match/{match.id}"


# ──────────────────────────────────────────────────────────────────────────
# UC6 — Paolo apre il proprio profilo
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestIlProfiloRendeLeTreViste:
    def test_il_selettore_ha_le_tre_posizioni_in_ordine(self, app, paolo_e_pietro):
        pagina = _leggi(
            _get(_client_for(app, paolo_e_pietro["paolo"]), "/player/profile")
        )

        assert pagina.scelte == ["tornei", "confermate", "tutte"]

    def test_vittorie_sconfitte_e_pareggi_per_vista(self, app, paolo_e_pietro):
        pagina = _leggi(
            _get(_client_for(app, paolo_e_pietro["paolo"]), "/player/profile")
        )
        n = pagina.numeri

        # Tornei: la sola partita di gara.
        assert n[("tornei", "totali")] == "1"
        assert n[("tornei", "vittorie")] == "1"
        assert n[("tornei", "sconfitte")] == "0"
        # Confermate: più la sfida firmata da entrambi e il forfait (UC7).
        assert n[("confermate", "totali")] == "3"
        assert n[("confermate", "vittorie")] == "2"
        assert n[("confermate", "sconfitte")] == "1"
        # Tutte: più la sfida firmata da Paolo soltanto.
        assert n[("tutte", "totali")] == "4"
        assert n[("tutte", "vittorie")] == "3"
        assert n[("tutte", "sconfitte")] == "1"
        for vista in ("tornei", "confermate", "tutte"):
            assert n[(vista, "pareggi")] == "0"

    def test_un_pareggio_si_conta(self, app):
        """«Esattamente 4» chiusa 2-2: pareggio, non una partita sparita."""
        paolo, pietro = _player(), _player()
        _sfida(
            paolo,
            pietro,
            5,
            status=MatchStatus.CONFIRMED_BY_BOTH,
            player1_confirmed=True,
            player2_confirmed=True,
            player1_score=2,
            player2_score=2,
            distance=4,
            is_race_to=False,
        )

        n = _leggi(_get(_client_for(app, paolo), "/player/profile")).numeri

        assert n[("confermate", "pareggi")] == "1"
        assert n[("confermate", "totali")] == "1"

    def test_ogni_vista_ha_il_suo_elo(self, app, paolo_e_pietro):
        n = _leggi(
            _get(_client_for(app, paolo_e_pietro["paolo"]), "/player/profile")
        ).numeri

        assert n[("tornei", "elo")] == "1510"
        assert n[("confermate", "elo")] == "1530"
        assert n[("tutte", "elo")] == "1545"

    def test_le_sfide_in_attesa_compaiono_solo_in_tutte(self, app, paolo_e_pietro):
        body = _get(_client_for(app, paolo_e_pietro["paolo"]), "/player/profile")
        link = _leggi(body).link

        assert link[_link_sfida(paolo_e_pietro["attesa"])] == {"tutte"}
        assert link[_link_sfida(paolo_e_pietro["confermata"])] == {
            "confermate",
            "tutte",
        }
        assert link[_link_partita(paolo_e_pietro["torneo"])] == {
            "tornei",
            "confermate",
            "tutte",
        }

    def test_la_sfida_in_attesa_porta_il_suo_segno(self, app, paolo_e_pietro):
        body = _get(_client_for(app, paolo_e_pietro["paolo"]), "/player/profile")

        assert body.count("data-in-attesa") == 1


@pytest.mark.integration
class TestTpaERunout:
    def test_in_vista_tornei_il_tpa_e_una_lineetta_spiegata(self, app, paolo_e_pietro):
        pagina = _leggi(
            _get(_client_for(app, paolo_e_pietro["paolo"]), "/player/profile")
        )

        assert pagina.numeri[("tornei", "tpa")] == "—"
        assert "solo nelle sfide" in pagina.testo("tornei")

    def test_il_runout_segue_la_vista(self, app):
        """Un runout marcato su una sfida in attesa conta solo in *Tutte*."""
        from models.individual_match.match_models import IndividualRack

        paolo, pietro = _player(), _player()
        _partita_di_torneo(paolo, pietro)
        attesa = _in_attesa(paolo, pietro)
        db.session.add(
            IndividualRack(
                match_id=attesa.id,
                rack_number=1,
                winner_id=paolo.id,
                is_run_out=True,
            )
        )
        db.session.commit()

        n = _leggi(_get(_client_for(app, paolo), "/player/profile")).numeri

        assert n.get(("tutte", "runout")) == "1"
        assert ("confermate", "runout") not in n
        assert ("tornei", "runout") not in n


@pytest.mark.integration
class TestSoloSfide:
    """Variante di UC6: chi ha solo sfide, in vista *Tornei*."""

    def test_nessuna_partita_di_torneo_invece_di_una_fila_di_zeri(self, app):
        gianni, pietro = _player(), _player()
        _confermata(gianni, pietro)

        pagina = _leggi(_get(_client_for(app, gianni), "/player/profile"))

        assert "Nessuna partita di torneo" in pagina.testo("tornei")
        assert ("tornei", "vittorie") not in pagina.numeri
        assert pagina.numeri[("confermate", "vittorie")] == "1"


# ──────────────────────────────────────────────────────────────────────────
# Il profilo di un altro: stessa vista, stessa privacy
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestProfiloAltrui:
    def _apri(self, owner):
        from models.user.privacy_service import PrivacyService

        PrivacyService.update_privacy_settings(
            owner.id, show_recent_matches=True, show_statistics=True
        )

    def test_ha_lo_stesso_selettore_e_gli_stessi_numeri(self, app, paolo_e_pietro):
        paolo = paolo_e_pietro["paolo"]
        self._apri(paolo)

        pagina = _leggi(
            _get(
                _client_for(app, paolo_e_pietro["gianni"]),
                f"/player/profile/{paolo.id}",
            )
        )

        assert pagina.scelte == ["tornei", "confermate", "tutte"]
        assert pagina.numeri[("tornei", "totali")] == "1"
        assert pagina.numeri[("confermate", "totali")] == "3"
        assert pagina.numeri[("tutte", "totali")] == "4"

    def test_la_partita_nascosta_resta_fuori_da_tutte_le_viste(
        self, app, paolo_e_pietro
    ):
        from models.user.privacy_service import PrivacyService

        paolo, torneo = paolo_e_pietro["paolo"], paolo_e_pietro["torneo"]
        self._apri(paolo)
        PrivacyService.hide_match(paolo.id, torneo.id)

        body = _get(
            _client_for(app, paolo_e_pietro["gianni"]), f"/player/profile/{paolo.id}"
        )
        pagina = _leggi(body)

        assert _link_partita(torneo) not in pagina.link
        assert "Nessuna partita di torneo" in pagina.testo("tornei")
        assert pagina.numeri[("confermate", "totali")] == "2"
        assert pagina.numeri[("tutte", "totali")] == "3"

    def test_l_ospite_vede_il_selettore(self, app, paolo_e_pietro):
        """Variante di UC6: Luca, da ospite. La scelta la ricorda il browser,
        e senza preferenze si parte da *Confermate* — lo prova il test
        frontend; qui basta che il selettore e i tre blocchi ci siano."""
        paolo = paolo_e_pietro["paolo"]
        self._apri(paolo)

        pagina = _leggi(_get(app.test_client(), f"/player/profile/{paolo.id}"))

        assert pagina.scelte == ["tornei", "confermate", "tutte"]
        assert pagina.numeri[("confermate", "totali")] == "3"


# ──────────────────────────────────────────────────────────────────────────
# I ripieghi dell'ELO
# ──────────────────────────────────────────────────────────────────────────


def _stats(confermate: int, tutte: int):
    from dataclasses import replace

    from models.certificazione import Vista
    from models.player.history_service import PlayerHistoryService

    vuote = PlayerHistoryService.stats_of([])
    return {
        Vista.TORNEI: vuote,
        Vista.CONFERMATE: replace(vuote, total_matches=confermate),
        Vista.TUTTE: replace(vuote, total_matches=tutte),
    }


class TestIRipieghiDellElo:
    """Quale numero si mostra quando un pool non ha ancora un valore."""

    def test_senza_nessun_pool_si_parte_da_1200(self, app):
        """Come il profilo ha sempre fatto per il competitivo."""
        from types import SimpleNamespace

        from models.certificazione import Vista
        from routes.player.profile import _elo_per_vista

        nessuno = SimpleNamespace(
            elo_rating=None, elo_global_rating=None, elo_all_rating=None
        )

        assert _elo_per_vista(nessuno, _stats(0, 0)) == {
            Vista.TORNEI: 1200,
            Vista.CONFERMATE: 1200,
            Vista.TUTTE: 1200,
        }

    def test_tutte_non_calcolato_con_sfide_in_attesa_e_una_lineetta(self, app):
        """Prima del ricalcolo in produzione (UC9) il pool *Tutte* può
        mancare: con sfide in attesa l'ELO di *Confermate* sarebbe un numero
        che quelle sfide non hanno mai mosso."""
        from types import SimpleNamespace

        from models.certificazione import Vista
        from routes.player.profile import _elo_per_vista

        giocatore = SimpleNamespace(
            elo_rating=1500, elo_global_rating=1520, elo_all_rating=None
        )

        assert _elo_per_vista(giocatore, _stats(3, 3))[Vista.TUTTE] == 1520
        assert _elo_per_vista(giocatore, _stats(3, 4))[Vista.TUTTE] is None
