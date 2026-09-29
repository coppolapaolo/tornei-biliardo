"""Playoff: chi si qualifica si blocca, il resto si corregge e resta scritto.

ADR-075, quinto passo. Fino al 2026-09-29 a inviti partiti la configurazione
dei playoff si bloccava tutta, mentre la scorciatoia del minimo di gare la
cambiava senza controlli; gli strumenti a mano (aggiungere, togliere,
rispondere per conto) non lasciavano traccia se non nel testo del motivo.
"""

import pytest

from models import db
from models.competition.models import Gara, Inscription
from models.exceptions import ConflictError
from models.playoff.models import PlayoffQualification, QualificationStatus
from models.playoff.proposta_finale import applica_alla_finale, proposta_alla_finale
from models.playoff.services import PlayoffService
from models.storia.service import StoriaModificheService
from tests.new.integration.test_avvio_playoff_route import (  # noqa: F401
    _login,
    admin_user,
    terminated_campionato_with_playoff,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def inviti_partiti(db_session, terminated_campionato_with_playoff):  # noqa: F811
    c, cfg, players, gara = terminated_campionato_with_playoff
    PlayoffService.start_playoff(c.id)
    return c, cfg, players, gara


def _voci(cfg_id):
    return StoriaModificheService.voci_dei_playoff([cfg_id])


class TestCriteriBloccati:
    @pytest.mark.parametrize(
        "campo, valore",
        [
            ("positions_to", 7),
            ("positions_from", 2),
            ("max_participants", 8),
            ("min_garas_played", 3),
        ],
    )
    def test_chi_si_qualifica_non_si_cambia(self, inviti_partiti, campo, valore):
        _c, cfg, _p, _g = inviti_partiti
        with pytest.raises(ConflictError):
            PlayoffService.update_configuration(cfg.id, **{campo: valore})

    def test_la_scorciatoia_del_minimo_passa_dagli_stessi_controlli(
        self, inviti_partiti
    ):
        from models.campionato.tournament_service import TournamentService

        c, cfg, _p, _g = inviti_partiti
        with pytest.raises(ConflictError):
            TournamentService().update_playoff_min_garas(c.id, cfg.id, 3)

    def test_prima_degli_inviti_si_cambia_e_resta_scritto(
        self, db_session, admin_user, terminated_campionato_with_playoff  # noqa: F811
    ):
        _c, cfg, _p, _g = terminated_campionato_with_playoff
        PlayoffService.update_configuration(
            cfg.id, autore=admin_user, motivo="Più posti", max_participants=8
        )
        voce = _voci(cfg.id)[0]
        assert voce.source == "playoff"
        assert voce.reason == "Più posti"
        assert [(r.field, r.old_value, r.new_value) for r in voce.fields] == [
            ("max_participants", "6", "8")
        ]

    def test_come_si_gioca_si_corregge_dopo_gli_inviti(
        self, inviti_partiti, admin_user  # noqa: F811
    ):
        _c, cfg, _p, _g = inviti_partiti
        PlayoffService.update_configuration(
            cfg.id, autore=admin_user, distance=7, name="Finale"
        )
        assert {r.field for r in _voci(cfg.id)[0].fields} == {"distance", "name"}


class TestStrumentiAMano:
    def test_aggiungere_resta_scritto_anche_sull_iscrizione(
        self, db_session, inviti_partiti, admin_user  # noqa: F811
    ):
        _c, cfg, players, _g = inviti_partiti
        finale = PlayoffService.create_playoff_gara(cfg.id)
        escluso = players[-1]
        PlayoffService.admin_add_player(
            cfg.id,
            escluso.id,
            admin_user.username,
            autore=admin_user,
            motivo="Ha vinto l'ultima gara",
        )
        voce = _voci(cfg.id)[0]
        assert voce.action == "giocatore_aggiunto"
        assert voce.reason == "Ha vinto l'ultima gara"
        assert voce.fields[0].new_value == str(escluso.id)
        iscrizione = Inscription.query.filter_by(
            gara_id=finale.id, user_id=escluso.id
        ).one()
        assert iscrizione.inscribed_by_id == admin_user.id

    def test_togliere_e_rispondere_per_conto(
        self, db_session, inviti_partiti, admin_user  # noqa: F811
    ):
        _c, cfg, _p, _g = inviti_partiti
        in_attesa = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id, status=QualificationStatus.PENDING
        ).all()
        PlayoffService.respond_on_behalf(
            in_attesa[0].id, accept=True, responded_by_id=admin_user.id
        )
        PlayoffService.admin_remove_player(
            in_attesa[1].id, admin_user.username, autore=admin_user
        )
        azioni = [v.action for v in _voci(cfg.id)]
        assert azioni[:2] == ["giocatore_tolto", "risposta_per_conto"]


class TestLaFinaleDecide:
    def test_il_cambio_si_propone_alla_finale(
        self, db_session, inviti_partiti, admin_user  # noqa: F811
    ):
        _c, cfg, _p, _g = inviti_partiti
        finale = PlayoffService.create_playoff_gara(cfg.id)
        assert finale.distance == 5
        PlayoffService.update_configuration(cfg.id, autore=admin_user, distance=7)
        # La finale ha i suoi valori: il cambio non la tocca da solo.
        assert db.session.get(Gara, finale.id).distance == 5

        cambi = {r.field: (r.old_value, r.new_value) for r in _voci(cfg.id)[0].fields}
        campi = proposta_alla_finale(cfg, cambi)
        assert [(c.campo_gara, c.nuovo, c.spuntato) for c in campi] == [
            ("distance", "7", True)
        ]
        assert applica_alla_finale(cfg, ["distance"], autore=admin_user)
        assert db.session.get(Gara, finale.id).distance == 7
        voce = StoriaModificheService.voci_della_gara(finale.id)[0]
        assert voce.source == "playoff"

    def test_dalla_pagina(
        self, client, db_session, inviti_partiti, admin_user  # noqa: F811
    ):
        c, cfg, _p, _g = inviti_partiti
        finale = PlayoffService.create_playoff_gara(cfg.id)
        _login(client, admin_user)
        risposta = client.post(
            f"/admin/campionato/{c.id}/playoff/config/{cfg.id}/edit",
            data={"name": cfg.name, "distance": "7", "motivo": "Più lunga"},
        )
        assert "/proposta/" in risposta.headers["Location"]
        pagina = client.get(risposta.headers["Location"]).get_data(as_text=True)
        assert 'value="distance" checked' in pagina

        client.post(risposta.headers["Location"], data={"scelta": ["distance"]})
        assert db.session.get(Gara, finale.id).distance == 7

        dettaglio = client.get(f"/admin/campionato/{c.id}").get_data(as_text=True)
        assert "Più lunga" in dettaglio
