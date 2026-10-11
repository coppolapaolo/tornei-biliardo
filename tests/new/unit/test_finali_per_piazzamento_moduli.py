"""Le finali per piazzamento nei moduli, nei nomi, nel foglio di avvio e nelle frasi.

Il dominio ha i suoi test (`test_finali_per_piazzamento_regole.py`,
`test_gironi_finali_per_piazzamento.py`); qui il passaggio interfaccia↔server
(PR 6 del piano dei gironi, seconda metà; ADR-081, emendamento «le finali per
piazzamento»):

* il modulo della gara e quello del campionato accettano «piazzamento» solo
  con «Gironi: fino a 2», e con quella voce non leggono qualificati per
  girone e finalina (restano le regole della fase finale e della finale);
* le partite e il turno delle finali hanno un nome: «Finale 3°/4° posto»,
  «Finali per piazzamento», «Avvia le finali»;
* il foglio di avvio conta il turno delle finali e dice che con un girone
  solo non si giocano;
* la frase del regolamento le racconta.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.competition.gironi_service import Anteprima
from models.competition.tabellone_della_gara import nomi_del_turno_delle_finali
from models.competition.tabellone_view import NomeRound
from models.exceptions import ValidationError
from routes.admin.campionato_form_parser import CampionatoFormParser
from routes.admin.competition.form_parser import GaraFormParser

BASE = {
    "date": "2026-12-01",
    "time": "20:00",
    "discipline": "8_ball",
    "distance": "3",
    "rounds_count": "3",
    "min_participants": "2",
    "matchmaking_strategy": "round_robin",
    "first_round_policy": "random",
    "odd_number_policy": "bye",
    "max_groups": "2",
}

PIAZZAMENTO = {
    "final_phase_mode": "piazzamento",
    "qualifiers_per_group": "3",
    "third_place_match": "on",
    "final_phase_time_limit": "nessuno",
    "final_phase_distance_mode": "altra",
    "final_phase_distance": "4",
    "final_distance_mode": "altra",
    "final_distance": "5",
}


def _direttore():
    from models import User
    from models.user.role_enum import UserRole

    uid = uuid.uuid4().hex[:8]
    user = User(username=f"fpm_{uid}", email=f"fpm_{uid}@test.com")
    user.role = UserRole.DIRECTOR.value
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


def _parse(app, **extra):
    with app.test_request_context(method="POST", data={**BASE, **extra}):
        return GaraFormParser(campionato=None, gara=None).parse()


@pytest.mark.unit
class TestModuloGara:
    def test_con_due_gironi_si_sceglie(self, app):
        dati = _parse(app, **PIAZZAMENTO)
        assert dati["final_phase_mode"] == "piazzamento"
        # La finalina è del tabellone: con le finali ogni posto ha la sua.
        assert dati["third_place_match"] is False
        # Chi gioca le finali sono tutti: i qualificati non si leggono.
        assert "qualifiers_per_group" not in dati
        # Le regole della fase finale e della finale valgono anche qui.
        assert dati["final_phase_time_limit_minutes"] == 0
        assert dati["final_phase_distance"] == 4
        assert dati["final_distance"] == 5

    @pytest.mark.parametrize("tetto", ["3", "4"])
    def test_con_piu_di_due_gironi_si_rifiuta(self, app, tetto):
        with pytest.raises(ValueError, match="due gironi"):
            _parse(app, **{**PIAZZAMENTO, "max_groups": tetto})

    def test_col_girone_unico_nessuna_fase_finale(self, app):
        dati = _parse(app, **{**PIAZZAMENTO, "max_groups": "1"})
        assert dati["final_phase_mode"] == "nessuna"


@pytest.mark.unit
class TestModuloCampionato:
    def _gironi(self, app, **dati):
        with app.test_request_context(method="POST", data=dati):
            from flask import request

            return CampionatoFormParser.parse_gironi(request.form)

    def test_con_due_gironi_si_propone(self, app):
        valori = self._gironi(
            app,
            default_max_groups="2",
            default_final_phase_mode="piazzamento",
            default_qualifiers_per_group="2",
            default_third_place_match="on",
            default_final_phase_time_limit="minuti",
            default_final_phase_time_limit_minutes="40",
        )
        assert valori["default_final_phase_mode"] == "piazzamento"
        assert valori["default_third_place_match"] is False
        assert "default_qualifiers_per_group" not in valori
        assert valori["default_final_phase_time_limit_minutes"] == 40

    def test_con_tre_gironi_si_rifiuta(self, app):
        with pytest.raises(ValueError, match="due gironi"):
            self._gironi(
                app, default_max_groups="3", default_final_phase_mode="piazzamento"
            )

    def test_il_servizio_rifiuta_il_campionato_con_tre_gironi(self, app, db_session):
        """Il garante resta il servizio: il modulo può essere aggirato."""
        from models.campionato.tournament_service import TournamentService

        with pytest.raises(ValidationError, match="due gironi"):
            TournamentService().create_campionato_with_director(
                f"Piazzamenti {uuid.uuid4().hex[:6]}",
                creator_user_id=_direttore().id,
                campionato_type="round_robin",
                default_classification_system="POSITION",
                default_max_groups=3,
                default_final_phase_mode="piazzamento",
            )

    def test_il_servizio_rifiuta_la_modifica_a_tre_gironi(self, app, db_session):
        from models.campionato.tournament_service import TournamentService

        camp = Campionato(
            name=f"Piazzamenti {uuid.uuid4().hex[:6]}",
            campionato_type="round_robin",
            default_classification_system="POSITION",
            is_active=True,
            default_max_groups=2,
            default_final_phase_mode="piazzamento",
        )
        db.session.add(camp)
        db.session.commit()
        with pytest.raises(ValidationError, match="due gironi"):
            TournamentService().update_campionato(camp.id, default_max_groups=3)


@pytest.mark.unit
class TestNomi:
    def _macro(self, app):
        return app.jinja_env.get_template(
            "components/_tabellone_macros.html"
        ).make_module({})

    def test_la_partita(self, app):
        t = self._macro(app)
        with app.test_request_context():
            assert str(t.nome_partita(NomeRound("piazzamento", 1), 4)) == (
                "Finale 1°/2° posto"
            )
            assert str(t.nome_partita(NomeRound("piazzamento", 2), 4)) == (
                "Finale 3°/4° posto"
            )
            assert str(t.nome_round(NomeRound("piazzamento", 3))) == (
                "Finale 5°/6° posto"
            )

    def test_il_turno(self, app):
        t = self._macro(app)
        finali = [NomeRound("finali_piazzamento")]
        with app.test_request_context():
            assert str(t.nome_turno(finali)) == "Finali per piazzamento"
            assert str(t.turno_pronto(finali, 4)) == "Finali pronte"
            assert str(t.avvia_turno(finali, 4)) == "Avvia le finali"


def _partita(turno, girone=None, tipo=None, coppia=None, id_=None):
    return SimpleNamespace(
        id=id_,
        round_number=turno,
        bracket_group=girone,
        bracket_type=tipo,
        bracket_slot=coppia,
    )


def _gara(modo="piazzamento", turni=4):
    return SimpleNamespace(
        matchmaking_strategy="round_robin",
        ha_finali_per_piazzamento=modo == "piazzamento",
        ha_tabellone_finale=modo == "tabellone",
        rounds_count=turni,
        third_place_match=False,
    )


@pytest.mark.unit
class TestIlTurnoDelleFinali:
    """Il turno delle finali si nomina dalle partite, senza database."""

    def test_a_gironi_in_corso_e_l_ultimo_turno(self):
        partite = [_partita(1, 0), _partita(1, 1), _partita(2, 0), _partita(2, 1)]
        nomi = nomi_del_turno_delle_finali(_gara(), partite)
        assert nomi == {4: [NomeRound("finali_piazzamento")]}

    def test_dalle_partite_delle_finali(self):
        partite = [_partita(3, 0), _partita(3, 1), _partita(4, None, "PP", 0, 9)]
        assert nomi_del_turno_delle_finali(_gara(turni=6), partite) == {
            4: [NomeRound("finali_piazzamento")]
        }

    def test_con_un_girone_solo_non_ci_sono(self):
        partite = [_partita(1), _partita(2)]
        assert nomi_del_turno_delle_finali(_gara(), partite) == {}

    def test_senza_finali_per_piazzamento_niente(self):
        partite = [_partita(1, 0), _partita(1, 1)]
        assert nomi_del_turno_delle_finali(_gara("tabellone"), partite) == {}
        assert nomi_del_turno_delle_finali(_gara("nessuna"), partite) == {}


@pytest.mark.unit
class TestFoglioDiAvvio:
    def _anteprima(self, **extra):
        valori = dict(
            iscritti=8,
            tetto=2,
            massimo=2,
            proposta=2,
            taglie={1: [8], 2: [4, 4]},
            finali_per_piazzamento=True,
        )
        valori.update(extra)
        return Anteprima(**valori)

    def test_il_turno_delle_finali_si_conta(self):
        anteprima = self._anteprima()
        assert anteprima.turni == {1: 7, 2: 4}

    def test_col_girone_unico_le_finali_non_si_giocano(self):
        assert self._anteprima().girone_unico_senza_fase_finale
        assert (
            Anteprima(
                iscritti=8, tetto=2, massimo=2, proposta=2, taglie={1: [8]}
            ).girone_unico_senza_fase_finale
            is False
        )


@pytest.mark.unit
class TestParole:
    def test_la_frase_delle_finali(self, app):
        from models.competition.gironi_service import descrivi_finali_per_piazzamento

        with app.test_request_context():
            frase = descrivi_finali_per_piazzamento()
        assert frase.startswith("Poi le finali per piazzamento")
        assert "1° del girone A contro il 1° del girone B" in frase
        assert "tabellone" not in frase

    def test_la_frase_dice_le_regole_diverse(self, app):
        from models.competition.gironi_service import descrivi_finali_per_piazzamento

        with app.test_request_context():
            frase = descrivi_finali_per_piazzamento(
                45, distanza=4, minuti_finale=0, distanza_finale=7
            )
        assert "nelle finali al 4, 45 minuti a partita" in frase
        assert "la finale per il 1° posto al 7, senza limite di tempo" in frase

    def test_la_frase_dei_gironi_porta_le_finali(self, app, db_session):
        from datetime import date, timedelta

        from models.competition.gironi_service import GironiService
        from models.competition.services import GaraService

        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Lunedì al 74",
            date=date.today() + timedelta(days=7),
            discipline="8_ball",
            distance=3,
            is_race_to=True,
            matchmaking_strategy="round_robin",
            first_round_policy="random",
            odd_number_policy="bye",
            rounds_count=3,
            max_groups=2,
            final_phase_mode="piazzamento",
            director_id=_direttore().id,
        )
        with app.test_request_context():
            frase = GironiService.frase(gara)
        assert frase is not None
        assert "finali per piazzamento" in frase


@pytest.mark.unit
class TestRegolamentoDelCampionato:
    def test_qualificati_e_finalina_tacciono(self, app, db_session):
        from models.storia.regolamento import CAMPI_DEL_CAMPIONATO, _impostazioni

        camp = Campionato(
            name=f"Piazzamenti {uuid.uuid4().hex[:6]}",
            campionato_type="round_robin",
            default_classification_system="POSITION",
            is_active=True,
            default_max_groups=2,
            default_final_phase_mode="piazzamento",
            default_third_place_match=True,
        )
        db.session.add(camp)
        db.session.commit()
        campi = {i.campo for i in _impostazioni(camp, CAMPI_DEL_CAMPIONATO, [])}
        assert "default_final_phase_mode" in campi
        assert "default_qualifiers_per_group" not in campi
        assert "default_third_place_match" not in campi
        assert "default_final_phase_time_limit_minutes" in campi


def _foglio(client, iscritti: int) -> str:
    """Il foglio «Avvia la gara» di una gara singola con le finali."""
    from datetime import date, timedelta

    from models import User
    from models.base import utc_now
    from models.competition.inscription_service import InscriptionService
    from models.competition.services import GaraService
    from models.user.role_enum import UserRole

    director = _direttore()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Foglio",
        date=date.today() + timedelta(days=7),
        rounds_count=3,
        min_participants=3,
        max_participants=32,
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy="round_robin",
        first_round_policy="random",
        odd_number_policy="bye",
        max_groups=2,
        final_phase_mode="piazzamento",
    )
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for _i in range(iscritti):
        uid = uuid.uuid4().hex[:8]
        player = User(username=f"fpf_{uid}", email=f"fpf_{uid}@test.com")
        player.role = UserRole.PLAYER.value
        player.set_password("x")
        db.session.add(player)
        db.session.commit()
        InscriptionService.inscribe_user(player.id, gara.id)
    client.post("/auth/login", data={"username": director.username, "password": "x"})
    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    return html[html.index('id="avviaGaraModal"') :]


@pytest.mark.unit
class TestIlFoglioDice:
    def test_le_finali_e_il_loro_turno(self, client):
        foglio = _foglio(client, 8)
        assert "Poi le finali per piazzamento" in foglio
        assert "2 gironi · 4 turni" in foglio
        assert "poi le finali" in foglio
        assert "le finali non si giocano: la gara finisce col girone" in foglio
        assert "il tabellone non si gioca" not in foglio
        assert "Poi il tabellone" not in foglio
