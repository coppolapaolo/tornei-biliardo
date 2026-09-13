"""Il turno dopo aspetta la prova della X convalidata e gli esercizi registrati.

`SPECIFICHE.md`, «Cosa deve essere chiuso prima del turno successivo»
(2026-09-13): con le strategie che costruiscono ogni turno sulla classifica il
turno successivo non parte finche' il turno prima non e' chiuso davvero:

* tutte le partite concluse — fino a oggi lo controllavano solo le due route,
  non il servizio che crea il turno;
* la prova giocata al posto della X **convalidata** dal direttore: il suo
  punteggio e' la differenza triangoli di quel turno, e un turno Amalfi
  calcolato senza di lui abbina su una classifica che non c'e';
* ogni esercizio fra i turni agganciato a quel turno con almeno un tentativo
  per ogni iscritto ancora in gara. Chi ha dato forfait non conta.

Con la strategia casuale, dove i turni nascono tutti all'avvio, niente di
questo blocca niente.

La regola sta nel dominio (`RoundCreationService.start_next_round`), quindi
vale per ogni strada che avvia un turno; la fascia del direttore la annuncia
col comando bloccato e il conto di cosa manca.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.competition.gara_challenge_service import GaraChallengeService
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara, Inscription
from models.competition.pendenze_turno import pendenze_del_turno
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.dashboard.comandi import ComandoDirezione, comando_per
from models.exceptions import ConflictError
from models.match.models import Match
from models.status_enum import MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(db_session, prefisso, ruolo=UserRole.PLAYER.value):
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}",
        email=f"{prefisso}_{s}@test.com",
        role=ruolo,
        onboarding_completed=True,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, utente):
    client.post(
        "/auth/login",
        data={"username": utente.username, "password": "test1234"},
        follow_redirects=True,
    )


def _esercizio(db_session, autore, *, a_esito=False):
    sfida = Challenge(
        description="Spot Shot Rally",
        image_path="test.jpg",
        pass_fail_only=a_esito,
        created_by_id=autore.id,
        is_active=True,
    )
    db_session.add(sfida)
    db_session.commit()
    return sfida


def _gara(db_session, *, giocatori, strategia="amalfi", dispari="bye", x=None):
    """Una gara standalone avviata al turno 1, con `giocatori` iscritti."""
    direttore = _utente(db_session, "dir", UserRole.DIRECTOR.value)
    iscritti = [_utente(db_session, f"p{i}") for i in range(giocatori)]
    extra = {}
    if x is not None:
        extra["x_challenge_id"] = _esercizio(db_session, direttore).id
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Gara turno {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        location="Test",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=8,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=direttore.id,
        matchmaking_strategy=strategia,
        first_round_policy="random",
        odd_number_policy=dispari,
        anti_rematch_enabled=True,
        **extra,
    )
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(days=5)
    )
    for g in iscritti:
        InscriptionService.inscribe_user(g.id, gara.id)
    db_session.commit()
    RoundService.start_first_round(gara.id)
    db_session.commit()
    return gara, direttore, iscritti


def _chiudi_turno(gara_id, turno=1):
    """Chiude le partite giocate del turno, come dal segnapunti."""
    for m in Match.query.filter_by(gara_id=gara_id, round_number=turno).all():
        if m.is_bye or MatchStatus.is_finished(m.status):
            continue
        m.player1_score = 5
        m.player2_score = 2
        m.winner_id = m.player1_id
        m.status = MatchStatus.CLOSED_UNILATERALLY.value
    db.session.commit()
    # Come la route del punteggio: la classifica del turno, su cui Amalfi abbina.
    RoundService.update_round_progression(gara_id)
    db.session.commit()


def _gara_letta(gara_id) -> Gara:
    db.session.expire_all()
    gara = db.session.get(Gara, gara_id)
    assert gara is not None
    return gara


class TestLaProvaDellaX:
    def test_senza_convalida_il_turno_dopo_non_parte(self, db_session):
        gara, _dir, _g = _gara(
            db_session, giocatori=5, dispari="bye_with_challenge", x=True
        )
        _chiudi_turno(gara.id)

        pendenze = pendenze_del_turno(_gara_letta(gara.id), 1)
        assert (pendenze.prove_x, pendenze.esercizi) == (1, 0)
        assert pendenze.bloccano

        with pytest.raises(ConflictError):
            RoundService.start_next_round(gara.id, 2)
        db.session.rollback()
        assert Match.query.filter_by(gara_id=gara.id, round_number=2).count() == 0

    def test_convalidata_il_turno_dopo_parte(self, db_session):
        gara, direttore, _g = _gara(
            db_session, giocatori=5, dispari="bye_with_challenge", x=True
        )
        _chiudi_turno(gara.id)
        x = Match.query.filter_by(gara_id=gara.id, round_number=1, is_bye=True).one()

        ChallengeService.validate_x_replacement(
            gara_id=gara.id,
            round_number=1,
            user_id=x.player1_id,
            actor_id=direttore.id,
            score=3,
        )
        db_session.commit()

        assert not pendenze_del_turno(_gara_letta(gara.id), 1).bloccano
        RoundService.start_next_round(gara.id, 2)
        db_session.commit()
        assert Match.query.filter_by(gara_id=gara.id, round_number=2).count() > 0

    def test_la_x_semplice_non_aspetta_niente(self, db_session):
        gara, _dir, _g = _gara(db_session, giocatori=5, dispari="bye")
        _chiudi_turno(gara.id)
        assert not pendenze_del_turno(_gara_letta(gara.id), 1).bloccano
        RoundService.start_next_round(gara.id, 2)


class TestGliEserciziFraITurni:
    def _con_esercizio(self, db_session, **kw):
        gara, direttore, giocatori = _gara(db_session, giocatori=4, **kw)
        sfida = _esercizio(db_session, direttore)
        gc = GaraChallengeService.add_challenge_to_gara(
            gara_id=gara.id,
            challenge_id=sfida.id,
            round_number=1,
            added_by_id=direttore.id,
            max_attempts=2,
        )
        db_session.commit()
        return gara, direttore, giocatori, gc

    def test_un_giocatore_senza_tentativi_blocca_il_turno(self, db_session):
        gara, _dir, giocatori, gc = self._con_esercizio(db_session)
        _chiudi_turno(gara.id)
        for g in giocatori[:3]:
            GaraChallengeService.record_challenge_attempt(gc.id, g.id, score=4)
        db_session.commit()

        assert pendenze_del_turno(_gara_letta(gara.id), 1).esercizi == 1
        with pytest.raises(ConflictError):
            RoundService.start_next_round(gara.id, 2)
        db.session.rollback()

        GaraChallengeService.record_challenge_attempt(gc.id, giocatori[3].id, score=0)
        db_session.commit()
        assert not pendenze_del_turno(_gara_letta(gara.id), 1).bloccano
        RoundService.start_next_round(gara.id, 2)

    def test_chi_ha_dato_forfait_non_ha_esercizi_da_registrare(self, db_session):
        gara, _dir, giocatori, gc = self._con_esercizio(db_session)
        _chiudi_turno(gara.id)
        for g in giocatori[:3]:
            GaraChallengeService.record_challenge_attempt(gc.id, g.id, score=4)
        iscrizione = Inscription.query.filter_by(
            gara_id=gara.id, user_id=giocatori[3].id
        ).one()
        iscrizione.is_forfeit = True
        db_session.commit()

        assert pendenze_del_turno(_gara_letta(gara.id), 1).esercizi == 0

    def test_l_esercizio_di_un_altro_turno_non_c_entra(self, db_session):
        gara, direttore, _giocatori = _gara(db_session, giocatori=4)
        sfida = _esercizio(db_session, direttore)
        GaraChallengeService.add_challenge_to_gara(
            gara_id=gara.id,
            challenge_id=sfida.id,
            round_number=2,
            added_by_id=direttore.id,
        )
        db_session.commit()
        _chiudi_turno(gara.id)
        assert not pendenze_del_turno(_gara_letta(gara.id), 1).bloccano

    def test_col_casuale_non_blocca_niente(self, db_session):
        gara, _dir, _giocatori, _gc = self._con_esercizio(
            db_session, strategia="random"
        )
        _chiudi_turno(gara.id)
        pendenze = pendenze_del_turno(_gara_letta(gara.id), 1)
        assert (pendenze.prove_x, pendenze.esercizi, pendenze.bloccano) == (
            0,
            0,
            False,
        )


class TestLePartiteAperte:
    def test_il_servizio_non_avvia_il_turno_con_una_partita_aperta(self, db_session):
        gara, _dir, _g = _gara(db_session, giocatori=4)
        assert pendenze_del_turno(_gara_letta(gara.id), 1).partite_aperte == 2
        with pytest.raises(ConflictError):
            RoundService.start_next_round(gara.id, 2)
        db.session.rollback()
        assert Match.query.filter_by(gara_id=gara.id, round_number=2).count() == 0


class TestLaFasciaDelDirettore:
    def test_il_comando_e_bloccato_col_conto_di_cosa_manca(self, db_session):
        gara, _dir, _g = _gara(
            db_session, giocatori=5, dispari="bye_with_challenge", x=True
        )
        _chiudi_turno(gara.id)

        comando = comando_per(_gara_letta(gara.id))
        assert comando is not None
        assert comando.tipo == ComandoDirezione.AVVIA_TURNO
        assert comando.turno == 2
        assert comando.bloccato
        assert (comando.prove_x, comando.esercizi) == (1, 0)

    def test_la_pagina_spegne_il_pulsante_e_dice_perche(self, client, db_session):
        gara, direttore, _g = _gara(
            db_session, giocatori=5, dispari="bye_with_challenge", x=True
        )
        _chiudi_turno(gara.id)
        _login(client, direttore)

        html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert "Prima di avviare il turno 2" in html
        assert "1 prova della X da convalidare" in html
        inizio = html.index('onclick="startRound(2, this)"')
        pulsante = html[html.rindex("<button", 0, inizio) : html.index(">", inizio)]
        assert "disabled" in pulsante

    def test_a_turno_concluso_la_prova_da_convalidare_resta_card(
        self, client, db_session
    ):
        """A turno concluso le partite diventano righe: la X con esercizio
        ancora da convalidare no, altrimenti nessuno potrebbe sbloccare il
        turno dopo."""
        gara, direttore, _g = _gara(
            db_session, giocatori=5, dispari="bye_with_challenge", x=True
        )
        _chiudi_turno(gara.id)
        _login(client, direttore)

        html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert "c7-partita--prova" in html
        assert "validate_x_replacement" in html or "/prova-x/" in html

        x = Match.query.filter_by(gara_id=gara.id, round_number=1, is_bye=True).one()
        ChallengeService.validate_x_replacement(
            gara_id=gara.id,
            round_number=1,
            user_id=x.player1_id,
            actor_id=direttore.id,
            score=2,
        )
        db_session.commit()

        html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert "c7-partita--prova" not in html
        assert "Puoi avviare il turno 2" in html

    def test_la_route_rifiuta_con_il_motivo(self, client, db_session):
        gara, direttore, _g = _gara(
            db_session, giocatori=5, dispari="bye_with_challenge", x=True
        )
        _chiudi_turno(gara.id)
        _login(client, direttore)

        risposta = client.post(f"/admin/gara/{gara.id}/start_round/2").get_json()
        assert risposta["success"] is False
        assert "prova della X" in risposta["error"]
        assert Match.query.filter_by(gara_id=gara.id, round_number=2).count() == 0
