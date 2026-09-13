"""La gara dentro un campionato offre il ritorno al campionato.

Su mobile la freccia della testata c'era gia' (`_gara_header.back`), ma
sopra i 992px il tema nasconde `.c7-head__back` e la barra laterale porta
solo agli elenchi: dal dettaglio di una gara non si risaliva al campionato
che la contiene se non con il tasto indietro del browser.
"""

import pytest
from datetime import date

from models import Campionato, Gara
from models.status_enum import GaraStatus, Discipline


def _gara(db_session, campionato_id=None):
    gara = Gara(
        number=1,
        name="Gara con testata",
        date=date.today(),
        discipline=Discipline.NINE_BALL.value,
        distance=4,
        matchmaking_strategy="random",
        status=GaraStatus.INSCRIPTION.value,
        rounds_count=3,
        min_participants=6,
        campionato_id=campionato_id,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


@pytest.mark.integration
class TestRitornoAlCampionato:

    def test_gara_di_campionato_mostra_il_ritorno(self, logged_in_client, db_session):
        client, _ = logged_in_client(role="admin")
        campionato = Campionato(name="Campionato di prova", planned_gare_count=2)
        db_session.add(campionato)
        db_session.commit()
        gara = _gara(db_session, campionato_id=campionato.id)

        html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

        url = f"/admin/campionato/{campionato.id}"
        # Tre volte: la freccia sotto lg, il pulsante da lg in su e, per chi
        # dirige, il kicker «Gara N di M · Campionato» sopra la striscia.
        assert html.count(f'href="{url}"') == 3
        assert 'class="c7-gara-campionato"' in html
        assert "Campionato di prova" in html

    def test_gara_standalone_non_lo_mostra(self, logged_in_client, db_session):
        client, _ = logged_in_client(role="admin")
        gara = _gara(db_session)

        html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

        # Il JS di eliminazione gara cita comunque l'URL: qui conta il link.
        assert 'href="/admin/campionato/' not in html
