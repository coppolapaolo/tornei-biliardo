"""Acchito, chi apre e runout, dal servizio alla route (ADR-056).

Tre cose si difendono qui, e sono tre difetti diversi:

1. **Chi ha aperto si scrive sul triangolo, non si ricalcola.** Se domani il
   direttore cambia la regola di apertura della gara, i triangoli già giocati
   devono continuare a dire chi li ha aperti — altrimenti cambierebbe anche
   quali sono stati break and run, cioè un numero nel profilo dei giocatori.
2. **L'acchito sono due domande.** Chi vince può mandare al tavolo
   l'avversario: se il codice deducesse il secondo dal primo, quella scelta
   non esisterebbe.
3. **Il runout è un interruttore, e la sigla la deduce il server.** Nessun
   secondo flag da tenere allineato a mano.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Match, User
from models.base import db, utc_now
from models.campionato.models import Campionato
from models.exceptions import ConflictError, ValidationError
from models.individual_match.match_models import IndividualMatch, IndividualRack
from models.individual_match.individual_rack_service import IndividualRackService
from models.match.break_rules import BreakRule, StartRule
from models.match.models import Rack
from models.match.scoring_service import ScoringService
from models.status_enum import Discipline, MatchStatus
from models.user.role_enum import UserRole


def _giocatori(db_session, quanti=2):
    batch = str(uuid.uuid4())[:8]
    utenti = []
    for i in range(quanti):
        u = User(
            username=f"ro{i}_{batch}",
            email=f"ro{i}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        u.set_password("test123")
        utenti.append(u)
    db_session.add_all(utenti)
    db_session.commit()
    return utenti


def _match_di_gara(db_session, giocatori, *, break_rule=None, start_rule=None):
    """Un match dentro una gara, con le due regole dove le vuole l'ADR."""
    campionato = Campionato(name=f"C{uuid.uuid4().hex[:6]}")
    db_session.add(campionato)
    db_session.flush()

    gara = Gara(
        campionato_id=campionato.id,
        number=1,
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
        break_rule=break_rule.value if break_rule else None,
        start_rule=start_rule.value if start_rule else None,
    )
    db_session.add(gara)
    db_session.flush()

    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=giocatori[0].id,
        player2_id=giocatori[1].id,
        status=MatchStatus.PLAYING.value,
        table_assignment="1",
        match_distance=5,
        is_race_to=True,
    )
    db_session.add(match)
    db_session.commit()
    return campionato, gara, match


class TestChiHaApertoSiScriveSulTriangolo:
    def test_a_turno_alterna_i_triangoli(self, db_session):
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, break_rule=BreakRule.ALTERNATE)

        for _ in range(4):
            ScoringService.add_rack_for_player(
                match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
            )
        db_session.commit()

        aperture = [
            r.break_player_id
            for r in Rack.query.filter_by(match_id=match.id)
            .order_by(Rack.rack_number)
            .all()
        ]
        assert aperture == [gioc[0].id, gioc[1].id, gioc[0].id, gioc[1].id]

    def test_spacca_chi_ha_vinto_segue_i_risultati(self, db_session):
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(
            db_session, gioc, break_rule=BreakRule.WINNER_BREAKS
        )

        for vincitore in (gioc[0], gioc[1], gioc[1]):
            ScoringService.add_rack_for_player(
                match_id=match.id, user_id=gioc[0].id, winner_id=vincitore.id
            )
        db_session.commit()

        aperture = [
            r.break_player_id
            for r in Rack.query.filter_by(match_id=match.id)
            .order_by(Rack.rack_number)
            .all()
        ]
        # Primo: apre il primo giocatore. Poi apre chi ha vinto quello prima.
        assert aperture == [gioc[0].id, gioc[0].id, gioc[1].id]

    def test_cambiare_la_regola_dopo_non_riscrive_il_passato(self, db_session):
        """È il motivo per cui `break_player_id` si persiste invece di dedurlo
        a ogni lettura: un triangolo già giocato non deve cambiare padrone."""
        gioc = _giocatori(db_session)
        _, gara, match = _match_di_gara(
            db_session, gioc, break_rule=BreakRule.ALTERNATE
        )

        for _ in range(2):
            ScoringService.add_rack_for_player(
                match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
            )
        db_session.commit()
        prima = [
            r.break_player_id
            for r in Rack.query.filter_by(match_id=match.id)
            .order_by(Rack.rack_number)
            .all()
        ]

        gara.break_rule = BreakRule.LOSER_BREAKS.value
        db_session.commit()

        dopo = [
            r.break_player_id
            for r in Rack.query.filter_by(match_id=match.id)
            .order_by(Rack.rack_number)
            .all()
        ]
        assert dopo == prima

    def test_la_gara_eredita_dal_campionato(self, db_session):
        gioc = _giocatori(db_session)
        campionato, gara, match = _match_di_gara(db_session, gioc, break_rule=None)
        campionato.default_break_rule = BreakRule.ALTERNATE_TWO.value
        db_session.commit()

        assert gara.break_rule is None  # NULL = eredita
        assert match.effective_break_rule is BreakRule.ALTERNATE_TWO

    def test_con_l_acchito_non_registrato_non_si_inventa_chi_apre(self, db_session):
        """`None`, non un ripiego: è il segnale che fa comparire le domande."""
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, start_rule=StartRule.LAG)

        assert match.needs_lag is True
        assert match.breaker_of_first_rack is None

        ScoringService.add_rack_for_player(
            match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        db_session.commit()

        rack = Rack.query.filter_by(match_id=match.id).one()
        assert rack.break_player_id is None
        assert rack.is_break_and_run is False


class TestAcchito:
    def test_chi_vince_puo_mandare_al_tavolo_l_avversario(self, db_session):
        """«Regole generali pool» 1.2: chi vince l'acchito **sceglie chi** apre."""
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, start_rule=StartRule.LAG)

        ScoringService.register_lag(
            match_id=match.id,
            lag_winner_id=gioc[0].id,
            first_break_player_id=gioc[1].id,
        )
        db_session.commit()

        assert match.lag_winner_id == gioc[0].id
        assert match.breaker_of_first_rack == gioc[1].id
        assert match.needs_lag is False

    def test_non_si_registra_a_partita_cominciata(self, db_session):
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, start_rule=StartRule.LAG)

        ScoringService.add_rack_for_player(
            match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        db_session.commit()

        with pytest.raises(ConflictError):
            ScoringService.register_lag(
                match_id=match.id,
                lag_winner_id=gioc[0].id,
                first_break_player_id=gioc[0].id,
            )

    def test_senza_acchito_la_domanda_non_si_pone(self, db_session):
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(
            db_session, gioc, start_rule=StartRule.FIRST_PLAYER
        )

        assert match.needs_lag is False
        assert match.breaker_of_first_rack == gioc[0].id

        with pytest.raises(ValidationError):
            ScoringService.register_lag(
                match_id=match.id,
                lag_winner_id=gioc[0].id,
                first_break_player_id=gioc[0].id,
            )

    def test_chi_non_gioca_non_puo_aprire(self, db_session):
        gioc = _giocatori(db_session, 3)
        _, _, match = _match_di_gara(db_session, gioc[:2], start_rule=StartRule.LAG)

        with pytest.raises(ValidationError):
            ScoringService.register_lag(
                match_id=match.id,
                lag_winner_id=gioc[0].id,
                first_break_player_id=gioc[2].id,
            )


class TestRunout:
    def test_e_un_interruttore(self, db_session):
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, break_rule=BreakRule.ALTERNATE)
        rack = ScoringService.add_rack_for_player(
            match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        db_session.commit()

        assert ScoringService.toggle_run_out(match.id, rack.id)["is_run_out"] is True
        db_session.commit()
        assert ScoringService.toggle_run_out(match.id, rack.id)["is_run_out"] is False
        db_session.commit()

    def test_la_sigla_si_deduce_da_chi_apriva(self, db_session):
        """B se aveva aperto lui, R se ha chiuso rispondendo. Un flag solo."""
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, break_rule=BreakRule.ALTERNATE)

        # Triangolo 1: apre p1 (regola di inizio «primo giocatore») e vince p1.
        primo = ScoringService.add_rack_for_player(
            match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        # Triangolo 2: apre p2 (alternate) ma vince p1.
        secondo = ScoringService.add_rack_for_player(
            match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        db_session.commit()

        assert ScoringService.toggle_run_out(match.id, primo.id)["is_break_and_run"]
        db_session.commit()
        assert not ScoringService.toggle_run_out(match.id, secondo.id)[
            "is_break_and_run"
        ]

    def test_un_triangolo_annullato_non_si_marca(self, db_session):
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, break_rule=BreakRule.ALTERNATE)
        rack = ScoringService.add_rack_for_player(
            match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        db_session.commit()
        ScoringService.remove_rack_for_player(match.id, gioc[0].id, gioc[0].id)
        db_session.commit()

        from models.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            ScoringService.toggle_run_out(match.id, rack.id)


class TestSfideIndividuali:
    """Lì il match **è** la radice: nessuna gara da cui ereditare."""

    def _sfida(self, db_session, gioc, **kwargs):
        match = IndividualMatch(
            player1_id=gioc[0].id,
            player2_id=gioc[1].id,
            scheduled_at=utc_now(),
            status=MatchStatus.IN_PROGRESS,
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            is_race_to=True,
            **kwargs,
        )
        db.session.add(match)
        db.session.commit()
        return match

    def test_la_regola_la_porta_il_match(self, db_session):
        gioc = _giocatori(db_session)
        match = self._sfida(db_session, gioc, break_rule=BreakRule.ALTERNATE_TWO.value)

        assert match.effective_break_rule is BreakRule.ALTERNATE_TWO

        for _ in range(4):
            IndividualRackService.add_rack_for_player(
                match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
            )
        db_session.commit()

        aperture = [
            r.break_player_id
            for r in IndividualRack.query.filter_by(match_id=match.id)
            .order_by(IndividualRack.rack_number)
            .all()
        ]
        assert aperture == [gioc[0].id, gioc[0].id, gioc[1].id, gioc[1].id]

    def test_l_acchito_vale_anche_qui(self, db_session):
        gioc = _giocatori(db_session)
        match = self._sfida(db_session, gioc, start_rule=StartRule.LAG.value)

        assert match.needs_lag is True
        IndividualRackService.register_lag(
            match_id=match.id,
            lag_winner_id=gioc[1].id,
            first_break_player_id=gioc[0].id,
        )
        db_session.commit()

        assert match.breaker_of_first_rack == gioc[0].id


class TestRunoutNelProfilo:
    """«Runout: 26, di cui 9 break and run»: insieme e sottoinsieme."""

    def test_somma_le_due_fonti_senza_arbitrarle(self, db_session):
        from models.user.runout_stats import runout_summary

        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, break_rule=BreakRule.ALTERNATE)

        primo = ScoringService.add_rack_for_player(
            match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        secondo = ScoringService.add_rack_for_player(
            match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        db_session.commit()
        ScoringService.toggle_run_out(match.id, primo.id)  # B: apriva lui
        ScoringService.toggle_run_out(match.id, secondo.id)  # R: rispondeva
        db_session.commit()

        dal_tabellone = runout_summary(gioc[0].id)
        assert dal_tabellone == {"total": 2, "break_and_runs": 1}

        # Il tally TPA si somma: i due segnapunti non convivono mai sulla
        # stessa partita, quindi non c'è niente da arbitrare.
        con_tpa = runout_summary(gioc[0].id, {"run_outs": 17, "break_and_runs": 9})
        assert con_tpa == {"total": 2 + 26, "break_and_runs": 1 + 9}

    def test_i_due_contatori_del_tpa_sono_disgiunti(self, db_session):
        """`run_outs + break_and_runs`, non `run_outs`.

        Nel motore TPA `is_run_out = not is_break_and_run and …`: chi leggesse
        `tally.run_outs` come «runout totali» mostrerebbe 17 invece di 26.
        """
        from models.user.runout_stats import runout_summary

        gioc = _giocatori(db_session)
        somma = runout_summary(gioc[0].id, {"run_outs": 17, "break_and_runs": 9})
        assert somma["total"] == 26
        assert somma["break_and_runs"] == 9

    def test_chi_non_ha_marcato_niente_non_ha_runout(self, db_session):
        from models.user.runout_stats import runout_summary

        gioc = _giocatori(db_session)
        assert runout_summary(gioc[0].id) == {"total": 0, "break_and_runs": 0}


class TestLeRouteDelTabellone:
    """Le due route nuove: acchito e runout, dal telefono al server.

    Il livello serve perché fra il gesto e il servizio ci sono tre cose che i
    test di dominio non attraversano: il decoratore dei permessi, la matrice
    dell'ADR-028 e la forma della risposta JSON — quella che il tabellone
    legge per scrivere la sigla sul trattino senza ricaricare.
    """

    def _login(self, client, utente):
        return client.post(
            "/auth/login",
            data={"username": utente.username, "password": "test123"},
            follow_redirects=True,
        )

    def test_il_giocatore_registra_l_acchito(self, app, db_session):
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, start_rule=StartRule.LAG)

        client = app.test_client()
        self._login(client, gioc[0])
        risposta = client.post(
            f"/player/match/{match.id}/lag",
            data={
                "lag_winner_id": gioc[0].id,
                "first_break_player_id": gioc[1].id,
            },
        )

        assert risposta.status_code == 200
        assert risposta.get_json()["success"] is True
        assert db.session.get(Match, match.id).first_break_player_id == gioc[1].id

    def test_la_pagina_chiede_l_acchito_e_poi_smette(self, app, db_session):
        """Il giro intero: la domanda c'è, si risponde, e ricaricando sparisce.

        Alla gara 3 della Ronin Cup (16/09/2026) il tabellone «non andava
        avanti» dopo la prima risposta. Questo test tiene fermo il lato
        server del giro — risposta salvata, domanda che non ritorna — e i due
        agganci della pagina: il modulo che fa proseguire toccando i nomi, e
        nessun «Comincia» da cui dipendere (ADR-056, emendamento 2026-09-17).
        """
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, start_rule=StartRule.LAG)

        client = app.test_client()
        self._login(client, gioc[0])

        prima = client.get(f"/admin/match/{match.id}").get_data(as_text=True)
        assert 'id="boardLag"' in prima
        assert "js/board_acchito.js" in prima
        assert "data-lag-reset" in prima
        assert "data-lag-go" not in prima

        client.post(
            f"/player/match/{match.id}/lag",
            data={"lag_winner_id": gioc[0].id, "first_break_player_id": gioc[0].id},
        )

        dopo = client.get(f"/admin/match/{match.id}").get_data(as_text=True)
        assert 'id="boardLag"' not in dopo

    def test_chi_non_gioca_non_registra_l_acchito(self, app, db_session):
        gioc = _giocatori(db_session, 3)
        _, _, match = _match_di_gara(db_session, gioc[:2], start_rule=StartRule.LAG)

        client = app.test_client()
        self._login(client, gioc[2])
        risposta = client.post(
            f"/player/match/{match.id}/lag",
            data={
                "lag_winner_id": gioc[0].id,
                "first_break_player_id": gioc[0].id,
            },
        )

        assert risposta.status_code in (302, 403)
        assert db.session.get(Match, match.id).first_break_player_id is None

    def test_il_trattino_marca_e_la_risposta_porta_la_sigla(self, app, db_session):
        """`letter` viaggia nella risposta perché la sigla la decide il server:
        dipende da chi apriva, e dedurla nel JavaScript sarebbe la terza copia
        della regola."""
        gioc = _giocatori(db_session)
        _, _, match = _match_di_gara(db_session, gioc, break_rule=BreakRule.ALTERNATE)
        rack = ScoringService.add_rack_for_player(
            match_id=match.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        db_session.commit()
        rack_id = rack.id

        client = app.test_client()
        self._login(client, gioc[0])

        marca = client.post(f"/player/match/{match.id}/racks/{rack_id}/runout")
        assert marca.status_code == 200
        # Il primo triangolo lo apre il primo giocatore, e l'ha vinto lui.
        assert marca.get_json() == {
            "success": True,
            "is_run_out": True,
            "is_break_and_run": True,
            "letter": "B",
        }

        smarca = client.post(f"/player/match/{match.id}/racks/{rack_id}/runout")
        assert smarca.get_json()["is_run_out"] is False
        assert smarca.get_json()["letter"] == ""

    def test_un_triangolo_di_un_altra_partita_non_si_marca(self, app, db_session):
        """L'id del triangolo arriva dal client: non basta che esista."""
        gioc = _giocatori(db_session)
        _, _, mio = _match_di_gara(db_session, gioc, break_rule=BreakRule.ALTERNATE)
        _, _, altrui = _match_di_gara(db_session, gioc, break_rule=BreakRule.ALTERNATE)
        rack_altrui = ScoringService.add_rack_for_player(
            match_id=altrui.id, user_id=gioc[0].id, winner_id=gioc[0].id
        )
        db_session.commit()

        client = app.test_client()
        self._login(client, gioc[0])
        risposta = client.post(f"/player/match/{mio.id}/racks/{rack_altrui.id}/runout")

        assert risposta.status_code == 400
        assert db.session.get(Rack, rack_altrui.id).is_run_out is False
