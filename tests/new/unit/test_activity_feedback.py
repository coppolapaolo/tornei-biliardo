"""Il blocco «Come stai andando» della home del giocatore.

Quello che questi test difendono non e' l'aspetto della card ma la promessa
che ci sta sotto: **nessun numero inventato**. Un giocatore senza attivita' non
riceve un blocco pieno di zeri, due partite non diventano un andamento, e una
metrica che non esiste non lascia uno slot vuoto — se ne va e basta.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models import db
from models.base import utc_now
from models.challenge.models import Challenge, ChallengeAttempt
from models.dashboard.activity_feedback import (
    MIN_POINTS_FOR_CHART,
    RETURNING_AFTER_DAYS,
    WINDOW,
    ActivityFeedbackService,
)
from models.individual_match.match_models import IndividualMatch
from models.rating.models import MatchRatingHistory, RatingSystem
from models.status_enum import MatchStatus
from models.user.models import User


def _user(role: str = "player") -> User:
    tag = uuid.uuid4().hex[:8]
    user = User(username=f"u_{tag}", email=f"{tag}@example.test", role=role)
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


def _casual_match(player: User, opponent: User, mine: int, theirs: int, *, days_ago=0):
    when = utc_now() - timedelta(days=days_ago)
    match = IndividualMatch(
        player1_id=player.id,
        player2_id=opponent.id,
        scheduled_at=when,
        ended_at=when,
        status=MatchStatus.CONFIRMED_BY_BOTH,
        discipline="palla_9",
        distance=5,
        player1_score=mine,
        player2_score=theirs,
        winner_id=(
            player.id if mine > theirs else opponent.id if theirs > mine else None
        ),
    )
    db.session.add(match)
    db.session.commit()
    return match


def _elo_step(user: User, old: int, new: int, match: IndividualMatch):
    row = MatchRatingHistory(
        individual_match_id=match.id,
        user_id=user.id,
        rating_system=RatingSystem.ELO_GLOBAL,
        old_rating=old,
        new_rating=new,
        delta=new - old,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _drill(user: User, score=None, passed=None, *, pass_fail=False, days_ago=0):
    challenge = Challenge(
        description="Disponi le bilie in fila",
        image_path="x.png",
        pass_fail_only=pass_fail,
    )
    db.session.add(challenge)
    db.session.commit()
    attempt = ChallengeAttempt(
        challenge_id=challenge.id,
        user_id=user.id,
        score=score,
        passed=passed,
        completed=True,
        attempted_at=utc_now() - timedelta(days=days_ago),
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


class TestNessunaAttivita:
    def test_giocatore_appena_iscritto_non_riceve_il_blocco(self, app):
        """Zero attivita' non e' «tutto a zero»: il blocco non si disegna."""
        user = _user()
        assert ActivityFeedbackService.for_player(user.id, user=user) is None

    def test_al_suo_posto_arriva_la_card_di_setup(self, app):
        user = _user()
        card = ActivityFeedbackService.setup_card(user.id, user=user)

        assert card["done"] == 1  # l'account esiste, il resto no
        assert card["total"] == 3
        assert [step["done"] for step in card["steps"]] == [True, False, False]

    def test_il_primo_match_spunta_il_secondo_passo(self, app):
        user, other = _user(), _user()
        _casual_match(user, other, 5, 3)

        card = ActivityFeedbackService.setup_card(user.id, user=user)
        assert [step["done"] for step in card["steps"]] == [True, True, False]


class TestFinestraDelleUltimeDieci:
    def test_la_finestra_si_ferma_a_dieci_attivita(self, app):
        user, other = _user(), _user()
        for i in range(14):
            _casual_match(user, other, 5, 2, days_ago=14 - i)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        assert len(block["strip"]["items"]) == WINDOW

    def test_le_tessere_vanno_dalla_piu_vecchia_alla_piu_recente(self, app):
        user, other = _user(), _user()
        _casual_match(user, other, 1, 5, days_ago=3)
        _casual_match(user, other, 3, 3, days_ago=2)
        _casual_match(user, other, 5, 0, days_ago=1)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        assert [t["outcome"] for t in block["strip"]["items"]] == [
            "loss",
            "draw",
            "win",
        ]

    def test_ogni_tessera_porta_il_dato_oltre_al_colore(self, app):
        """Il colore non puo' essere l'unico veicolo dell'informazione."""
        user, other = _user(), _user()
        _casual_match(user, other, 5, 3)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        tile = block["strip"]["items"][0]
        assert tile["text"] == "5–3"
        assert tile["title"]


class TestGrafico:
    def test_sotto_tre_attivita_la_sparkline_non_si_disegna(self, app):
        user, other = _user(), _user()
        for i, (old, new) in enumerate([(1200, 1210), (1210, 1218)]):
            match = _casual_match(user, other, 5, 2, days_ago=5 - i)
            _elo_step(user, old, new, match)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        # Due passaggi di Elo fanno tre punti (old del primo + i due new), ma
        # la soglia vale sulla serie: qui ci siamo appena.
        assert len(block["primary"]["value"]) > 0
        assert (block["chart"] is None) == (3 < MIN_POINTS_FOR_CHART)

    def test_con_abbastanza_punti_la_linea_esiste_e_finisce_a_destra(self, app):
        user, other = _user(), _user()
        for i, (old, new) in enumerate([(1200, 1206), (1206, 1201), (1201, 1218)]):
            match = _casual_match(user, other, 5, 2, days_ago=5 - i)
            _elo_step(user, old, new, match)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        chart = block["chart"]
        assert chart is not None and chart["kind"] == "line"
        assert chart["main"].endswith(("130.0,4.0", "130.0,4"))
        # L'area e' la stessa linea chiusa sul fondo del viewBox.
        assert chart["area"].endswith("130.0,34.0 0.0,34.0")


class TestProfili:
    def test_solo_partite_senza_referti_e_elo_only(self, app):
        user, other = _user(), _user()
        for i in range(3):
            match = _casual_match(user, other, 5, 2, days_ago=3 - i)
            _elo_step(user, 1200 + i * 5, 1205 + i * 5, match)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        assert block["profile"] == "elo_only"
        # La seconda cella e' la torta degli esiti, non un numero inventato.
        assert block["secondary"]["kind"] == "donut"

    def test_solo_drill_e_drill_only(self, app):
        user = _user()
        for i, score in enumerate([60, 70, 78]):
            _drill(user, score=score, days_ago=3 - i)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        assert block["profile"] == "drill_only"
        assert block["chart"]["kind"] == "bars"

    def test_elo_in_calo_e_declining_col_delta_in_ambra(self, app):
        user, other = _user(), _user()
        for i, (old, new) in enumerate([(1375, 1360), (1360, 1352), (1352, 1348)]):
            match = _casual_match(user, other, 2, 5, days_ago=5 - i)
            _elo_step(user, old, new, match)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        assert block["profile"] == "declining"
        assert block["primary"]["delta_tone"] == "down"
        # Il calo si mostra in chiaro: la linea di base diventa grigia.
        assert block["chart"]["muted"] is not None
        assert block["chart"]["main"] is None

    def test_dopo_quattro_settimane_di_pausa_e_returning(self, app):
        user, other = _user(), _user()
        for i in range(3):
            match = _casual_match(
                user, other, 5, 2, days_ago=RETURNING_AFTER_DAYS + 10 - i
            )
            _elo_step(user, 1300 + i, 1301 + i, match)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        assert block["profile"] == "returning"
        # La linea si ferma dove il giocatore si e' fermato e prosegue
        # tratteggiata, con un cerchio vuoto sull'ultimo punto.
        assert block["chart"]["projection"] is not None
        assert any(d["kind"] == "ghost" for d in block["chart"]["dots"])

    def test_direttore_vede_le_sue_gare_non_il_suo_elo(self, app):
        from datetime import date

        from models.competition.models import Gara

        director = _user(role="director")
        for n in range(1, 4):
            db.session.add(
                Gara(
                    campionato_id=None,
                    director_id=director.id,
                    number=n,
                    name=f"Open {n}",
                    date=date(2026, 1, n),
                    discipline="palla_9",
                    distance=5,
                    max_participants=24,
                )
            )
        db.session.commit()

        block = ActivityFeedbackService.for_player(director.id, user=director)
        assert block is not None
        assert block["profile"] == "director"
        assert block["primary"]["value"] == "3"


class TestStrisciaDensa:
    def test_oltre_sei_partite_il_testo_lascia_il_posto_alla_legenda(self, app):
        user, other = _user(), _user()
        for i in range(8):
            _casual_match(
                user, other, 5 if i % 2 else 1, 1 if i % 2 else 5, days_ago=8 - i
            )

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        strip = block["strip"]
        assert strip["dense"] is True
        # I conteggi restano leggibili: il colore non resta solo.
        assert sum(int(k["label"].split()[0]) for k in strip["legend"]) == 8

    def test_i_drill_non_diventano_mai_tessere_mute(self, app):
        """Un drill numerico non ha un esito: una legenda di esiti mentirebbe.

        Meglio sei tessere col nome del drill che dieci rettangoli identici e
        una riga che dice «10 pari».
        """
        user = _user()
        for i, score in enumerate([60, 62, 65, 68, 70, 72, 75, 78]):
            _drill(user, score=score, days_ago=8 - i)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        strip = block["strip"]
        assert strip["dense"] is False
        assert len(strip["items"]) == 6
        assert all(item["text"] for item in strip["items"])
        # L'icona del bersaglio serve solo a distinguere in una striscia mista.
        assert all(item["icon"] is None for item in strip["items"])

    def test_nel_misto_il_drill_si_riconosce_dall_icona(self, app):
        user, other = _user(), _user()
        _casual_match(user, other, 5, 2, days_ago=3)
        _drill(user, score=70, days_ago=2)
        _casual_match(user, other, 3, 5, days_ago=1)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        icons = [item["icon"] for item in block["strip"]["items"]]
        assert icons == [None, "fa-bullseye", None]


class TestSenzaElo:
    """Un giocatore che ha giocato ma di cui l'Elo non e' mai stato calcolato.

    Succede a chi ha partite chiuse senza passare dal motore di rating. La card
    non deve ne' inventare 1200, ne' riempire la prima cella con il numero di
    attivita' — che sarebbe solo la lunghezza della striscia disegnata sotto.
    """

    def test_al_posto_dell_elo_va_un_fatto_vero(self, app):
        user, other = _user(), _user()
        _casual_match(user, other, 5, 3, days_ago=3)
        _casual_match(user, other, 1, 5, days_ago=2)
        _casual_match(user, other, 2, 5, days_ago=1)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        primary = block["primary"]
        assert primary["value"] == "1"
        assert primary["label"] == "Partite vinte"
        assert "3" in primary["delta"]

    def test_senza_serie_non_si_disegna_nessun_andamento(self, app):
        """Un valore solo non e' un trend: la sparkline resta fuori."""
        user, other = _user(), _user()
        for i in range(4):
            _casual_match(user, other, 5, 3, days_ago=4 - i)
        user.elo_rating = 1284
        db.session.commit()

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        # L'Elo esiste sulla colonna sincronizzata: si mostra, senza delta.
        assert block["primary"]["label"] == "Elo"
        assert block["primary"]["value"] == "1284"
        assert block["primary"]["delta"] is None
        assert block["chart"] is None

    def test_con_la_serie_l_andamento_dell_elo_c_e(self, app):
        user, other = _user(), _user()
        for i, (old, new) in enumerate([(1200, 1206), (1206, 1201), (1201, 1218)]):
            match = _casual_match(user, other, 5, 2, days_ago=5 - i)
            _elo_step(user, old, new, match)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        assert block["primary"]["label"] == "Elo"
        assert block["chart"] is not None
        assert block["chart"]["kind"] == "line"


class TestSuperAttivo:
    def test_il_profilo_super_attivo_e_raggiungibile(self, app):
        """La soglia e' «piu' di 30 attivita' nel mese».

        Contarle dentro la finestra — tappata a 10 — renderebbe la condizione
        impossibile, e il profilo resterebbe dichiarato ma morto.
        """
        user, other = _user(), _user()
        for i in range(32):
            _casual_match(user, other, 5, 2, days_ago=(i % 25) + 1)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        assert block["profile"] == "hyperactive"
        assert block["context_badge"]["text"].startswith("32")

    def test_massimo_si_scrive_solo_se_e_davvero_il_massimo(self, app):
        """«Massimo di sempre» e' una affermazione, e va verificata su tutto lo
        storico: sulla sola finestra la direbbe chiunque stia risalendo."""
        user, other = _user(), _user()
        # Un picco vecchio, fuori dalla finestra, piu' alto di dove si e' ora.
        picco = _casual_match(user, other, 5, 0, days_ago=25)
        _elo_step(user, 1500, 1700, picco)
        for i in range(31):
            match = _casual_match(user, other, 5, 2, days_ago=(i % 20) + 1)
            _elo_step(user, 1600 + i, 1601 + i, match)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        assert block["profile"] == "hyperactive"
        assert "massimo" not in block["primary"]["delta"]


class TestPannelloEspanso:
    def test_le_righe_esistono_solo_se_hanno_un_dato_dietro(self, app):
        user, other = _user(), _user()
        _casual_match(user, other, 5, 3)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        # Nessuna streak, nessun campionato, nessun drill: non si inventa una
        # riga per riempire il pannello.
        assert all(row["title"] for row in block["expanded_rows"])
        assert block["toggle_label"]

    def test_i_drill_completati_diventano_una_riga(self, app):
        user, other = _user(), _user()
        _casual_match(user, other, 5, 3)
        _drill(user, score=74)
        _drill(user, score=80)

        block = ActivityFeedbackService.for_player(user.id, user=user)
        assert block is not None
        titles = [row["title"] for row in block["expanded_rows"]]
        assert any("2" in t for t in titles)


def test_il_blocco_si_costruisce_anche_in_inglese(app):
    """Un placeholder di troppo nella traduzione e' un KeyError, non un refuso.

    `pybabel update` riempie le voci nuove copiando il msgstr di stringhe che
    *somigliano*, e quelle portano dentro i loro `%(nome)s`. Il danno non si
    vede in italiano: si vede solo qui.
    """
    from flask_babel import force_locale

    user, other = _user(), _user()
    for i, (old, new) in enumerate([(1200, 1206), (1206, 1201), (1201, 1218)]):
        match = _casual_match(user, other, 5, 2, days_ago=5 - i)
        _elo_step(user, old, new, match)
    _drill(user, score=70, days_ago=1)

    with force_locale("en"):
        block = ActivityFeedbackService.for_player(user.id, user=user)
        setup = ActivityFeedbackService.setup_card(user.id, user=user)

    assert block is not None
    assert block["title"] == "How you are doing"
    assert setup["title"] == "Your profile is ready"


@pytest.mark.parametrize("role", ["player", "director"])
def test_il_blocco_non_contiene_mai_una_chiamata_all_azione(app, role):
    """E' feedback: i bottoni restano nelle sezioni sotto."""
    user, other = _user(role=role), _user()
    _casual_match(user, other, 5, 3)

    block = ActivityFeedbackService.for_player(user.id, user=user)
    assert block is not None
    assert "cta" not in block and "action" not in block
    assert "url" not in repr(block)
