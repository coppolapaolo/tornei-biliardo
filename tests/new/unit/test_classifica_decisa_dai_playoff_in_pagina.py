"""La classifica generale quando la decide la finale playoff, come la si legge.

Campionato 5 (Prima Rōnin CUP, finale del 14/10/2026): i primi otto erano in
ordine di arrivo della finale, ma la pagina mostrava solo vittorie e
differenza del **campionato**. serpico67 (5 vinte) stava sopra MARCO (7) e
PAOLO (8) senza che niente spiegasse perché. Decisioni dell'utente
(2026-10-15):

* la parte decisa dalla finale ha un colore suo e le **colonne della finale**;
  i numeri del campionato scendono sotto il nome (variante «B» del confronto);
* chi in finale è arrivato pari merito lo resta anche nella classifica del
  campionato, alla posizione più alta (SPECIFICHE.md, «Classifica», nota del
  2026-10-11), e fra i pari le righe vanno in **ordine alfabetico**: prima
  le separava l'id del giocatore;
* la colonna Gare conta anche la finale, e la nota lo dice.
"""

import re
import uuid
from datetime import date, time

from models.campionato.models import Campionato
from models.campionato.statistics_service import TournamentStatisticsService
from models.classification.models import GaraClassification
from models.competition.models import Gara
from models.match.models import Match
from models.playoff.models import PlayoffConfiguration, PlayoffRankingMode, PlayoffType
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User


def _user(db_session, nome):
    u = User(
        username=f"{nome}_{uuid.uuid4().hex[:6]}",
        email=f"{nome}_{uuid.uuid4().hex[:6]}@test.com",
        role="player",
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _gara(db_session, camp, number, day, **kwargs):
    g = Gara(
        campionato_id=camp.id,
        number=number,
        name=kwargs.pop("name", f"Gara {number}"),
        date=date(2026, 1, day),
        time=time(18, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        rounds_count=1,
        current_round=1,
        status=GaraStatus.COMPLETED.value,
        **kwargs,
    )
    db_session.add(g)
    db_session.flush()
    return g


def _partita(db_session, gara, vince, perde, score=(5, 0)):
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=vince.id,
            player2_id=perde.id,
            player1_score=score[0],
            player2_score=score[1],
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            winner_id=vince.id,
        )
    )
    db_session.flush()


def _campionato(db_session):
    """Quattro giocatori; la finale la giocano in tre, e due arrivano pari.

    In campionato l'ordine è A > Z > M > D. In finale vince D e Z e M
    arrivano **secondi pari merito**: Z è stato creato prima di M (id più
    basso), ma M viene prima in ordine alfabetico.
    """
    from models.classification.gara_classification import RoundClassificationService

    camp = Campionato(
        name=f"Camp {uuid.uuid4().hex[:6]}",
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=1,
        default_rounds_count=1,
    )
    db_session.add(camp)
    db_session.flush()
    a = _user(db_session, "alba")
    z = _user(db_session, "zeno")
    m = _user(db_session, "mara")
    d = _user(db_session, "dino")

    g1 = _gara(db_session, camp, 1, 10)
    _partita(db_session, g1, a, d, (5, 0))
    _partita(db_session, g1, z, m, (5, 1))
    RoundClassificationService.calculate_and_save_round_classification(g1.id, 1)

    cfg = PlayoffConfiguration(
        campionato_id=camp.id,
        name="Elite",
        playoff_type=PlayoffType.TOP_N,
        max_participants=3,
        positions_from=1,
        positions_to=3,
        is_active=True,
        min_garas_played=0,
        final_ranking_mode=PlayoffRankingMode.PLAYOFF_ONLY.value,
    )
    db_session.add(cfg)
    db_session.flush()
    finale = _gara(
        db_session, camp, 2, 20, playoff_config_id=cfg.id, name="Finale Elite"
    )
    _partita(db_session, finale, d, z, (5, 2))
    _partita(db_session, finale, d, m, (5, 2))
    RoundClassificationService.calculate_and_save_round_classification(finale.id, 1)
    # La classifica della finale come la scrive la chiusura: Z e M pari, il
    # sorteggio ha messo Z davanti, e la posizione mostrata è la stessa.
    db_session.add_all(
        [
            GaraClassification(
                gara_id=finale.id,
                user_id=d.id,
                position=1,
                shown_position=1,
                matches_won=2,
                rack_difference=6,
                racks_won=10,
            ),
            GaraClassification(
                gara_id=finale.id,
                user_id=z.id,
                position=2,
                shown_position=2,
                matches_won=0,
                rack_difference=-3,
                racks_won=2,
            ),
            GaraClassification(
                gara_id=finale.id,
                user_id=m.id,
                position=3,
                shown_position=2,
                matches_won=0,
                rack_difference=-3,
                racks_won=2,
            ),
        ]
    )
    db_session.commit()
    return {"campionato": camp, "a": a, "z": z, "m": m, "d": d, "finale": finale}


def _righe(camp_id):
    return [
        (pos, dati)
        for pos, dati in TournamentStatisticsService().classifica_generale(camp_id)
    ]


class TestIPariMeritoDellaFinale:
    def test_restano_pari_merito_alla_posizione_piu_alta(self, db_session):
        dati = _campionato(db_session)
        per_id = {
            r["user_id"]: r["shown_position"] for _p, r in _righe(dati["campionato"].id)
        }
        assert per_id[dati["d"].id] == 1
        assert per_id[dati["z"].id] == 2
        assert per_id[dati["m"].id] == 2
        # Chi non ha giocato la finale viene dopo, al suo posto.
        assert per_id[dati["a"].id] == 4

    def test_fra_i_pari_le_righe_vanno_in_ordine_alfabetico(self, db_session):
        """Non per id: Z ha l'id più basso, ma M viene prima nell'alfabeto."""
        dati = _campionato(db_session)
        ordine = [r["user_id"] for _p, r in _righe(dati["campionato"].id)]
        assert ordine[:3] == [dati["d"].id, dati["m"].id, dati["z"].id]


class TestINumeriDellaFinaleSulleRighe:
    def test_chi_ha_giocato_la_finale_ne_porta_i_numeri(self, db_session):
        dati = _campionato(db_session)
        per_id = {r["user_id"]: r for _p, r in _righe(dati["campionato"].id)}
        finale = per_id[dati["d"].id]["playoff"]
        assert finale["matches_won"] == 2
        assert finale["rack_difference"] == 6
        assert finale["position"] == 1
        assert finale["gara_name"] == "Finale Elite"

    def test_chi_non_l_ha_giocata_non_ne_ha(self, db_session):
        dati = _campionato(db_session)
        per_id = {r["user_id"]: r for _p, r in _righe(dati["campionato"].id)}
        assert per_id[dati["a"].id]["playoff"] is None

    def test_i_totali_restano_quelli_del_campionato(self, db_session):
        """La finale non si somma: D ha perso l'unica gara di campionato."""
        dati = _campionato(db_session)
        per_id = {r["user_id"]: r for _p, r in _righe(dati["campionato"].id)}
        assert per_id[dati["d"].id]["total_matches_won"] == 0


class TestLaPagina:
    def test_la_fascia_della_finale_ha_le_sue_colonne_e_la_nota(
        self, db_session, client
    ):
        dati = _campionato(db_session)
        html = client.get(f"/campionato/{dati['campionato'].id}/public").get_data(
            as_text=True
        )
        inizio = html.index('id="classificaGenerale"')
        sezione = html[inizio : html.index("</section>", inizio)]

        assert "c7-cg__riga--playoff" in sezione
        assert "Decisa dalla finale" in sezione
        assert "Finale Elite" in sezione
        assert "Poi l&#39;ordine del campionato" in sezione or (
            "Poi l'ordine del campionato" in sezione
        )
        # I numeri del campionato sotto il nome di chi ha giocato la finale.
        assert "Campionato:" in sezione
        # La nota spiega l'ordine e la colonna Gare.
        assert "in ordine di arrivo nella finale" in sezione
        righe_finale = re.findall(
            r'c7-classifica__riga[^"]*c7-cg__riga--playoff', sezione
        )
        assert len(righe_finale) == 3

    def test_senza_playoff_che_decide_la_pagina_e_quella_di_sempre(
        self, db_session, client
    ):
        dati = _campionato(db_session)
        cfg = PlayoffConfiguration.query.filter_by(
            campionato_id=dati["campionato"].id
        ).one()
        cfg.final_ranking_mode = PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF.value
        db_session.commit()
        html = client.get(f"/campionato/{dati['campionato'].id}/public").get_data(
            as_text=True
        )
        assert "c7-cg__riga--playoff" not in html
        assert "Decisa dalla finale" not in html
