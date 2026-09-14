"""La pagina pubblica del campionato, per chi usa l'app (decisione del 2026-09-14).

Un campionato ha due pagine con ruoli diversi: la **vetrina** (`/c/<id>`) per
chi arriva da un link condiviso, fuori dall'app, e questa
(`/campionato/<id>/public`) per chi e' dentro l'app. E' l'unico posto in cui
un giocatore vede la classifica completa con la zona playoff: le tessere
campionato e playoff della dashboard portano qui apposta.

Il disegno (canvas «campionato-concluso», `Pubblica*`) la vuole come la
pagina del direttore in sola lettura: stessa fascia, stessa classifica,
stesse gare; al posto di «Gestione» la sezione «Il campionato». Qui si
controlla che nei tre stati — stagione in corso, fase playoff, concluso — ci
siano le sezioni giuste e **nessun comando** di chi dirige.

I 404 (campionato eliminato, prova vista da chi non la dirige) stanno in
`test_campionato_pagina_pubblica_casi_limite.py`.
"""

from __future__ import annotations

import re
import uuid

import pytest

from models.base import db
from models.competition.models import Gara
from models.playoff.models import PlayoffRankingMode
from models.status_enum import GaraStatus
from tests.new.integration.test_campionato_concluso_pagine import (
    _concluso,
    _fascia,
    _senza_debug,
)
from tests.new.integration.test_pagina_campionato_direttore import (
    _campionato,
    _login,
)
from tests.new.integration.test_pagina_campionato_playoff_fasi import (
    _con_gara_di_playoff,
)
from tests.new.unit.test_playoff_classifica_finale_e_peso import (
    _campionato_con_playoff,
    _righe_di_turno,
)

pytestmark = pytest.mark.integration

#: Le parole dei comandi di chi dirige: nessuna deve comparire qui.
COMANDI_DEL_DIRETTORE = (
    "Nuova gara",
    "Avvia i playoff",
    "Crea la gara playoff",
    "Vai alla gara playoff",
    "Passa ai playoff",
    "Termina",
    "Gestione",
    "Direttori",
    "Impostazioni",
    "Modifica",
    "Accetta",
    "Rifiuta",
    "Rimuovi dai playoff",
    "Aggiungi configurazione",
    "Classifica finale del campionato",
    "Controlla chi è qualificato",
    "DEBUG - Campionato",
)

#: Un link a una route di gestione: tutto `/admin/` tranne la pagina della
#: gara, che e' la vista unica per chiunque (`admin.competition.gara_detail`,
#: aperta ad anonimi e giocatori in `ENDPOINT_ROLES`).
LINK_ADMIN = re.compile(r"""href=["']/admin/(?!gara/\d+["'])""")


def _pagina(client, campionato_id) -> str:
    risposta = client.get(f"/campionato/{campionato_id}/public")
    assert risposta.status_code == 200
    return _senza_debug(risposta.get_data(as_text=True))


def _senza_comandi(html: str) -> None:
    for parola in COMANDI_DEL_DIRETTORE:
        assert parola not in html, parola
    # Nessuna route del campionato riservata a chi dirige, in tutta la pagina.
    assert "/admin/campionato/" not in html
    # I link a /admin/ si guardano nella pagina, non nel guscio: la barra
    # laterale di chi e' entrato porta per esempio all'elenco delle sale
    # (`admin.venue.venues_list`), che con questa pagina non c'entra.
    pagina = html.split("data-campionato-pubblico")[1].split("</main>")[0]
    assert not LINK_ADMIN.search(pagina), LINK_ADMIN.search(pagina)
    assert 'method="POST"' not in pagina
    assert "c7-iconbtn" not in pagina
    assert "c7-invitato" not in pagina


@pytest.fixture(params=["anonimo", "giocatore"])
def chi_guarda(request, client, db_session):
    """La stessa pagina per chi non e' entrato e per un giocatore qualsiasi."""

    def _prepara(dati_giocatore=None):
        if request.param == "giocatore" and dati_giocatore is not None:
            _login(client, dati_giocatore)
        return client

    return _prepara


class TestConcluso:
    def test_la_fascia_annuncia_il_campione(self, chi_guarda, db_session):
        dati = _concluso(db_session)
        client = chi_guarda(dati["a"])

        html = _pagina(client, dati["campionato"].id)
        fascia = _fascia(html)

        assert "Campionato concluso" in fascia
        assert dati["d"].username in fascia.split("c7-campione__nome")[1]
        assert "c7-pos--2" in fascia and "c7-pos--3" in fascia
        assert "c7-fascia__azione" not in fascia

    def test_classifica_finale_e_gare_con_chi_le_ha_vinte(self, chi_guarda, db_session):
        dati = _concluso(db_session)
        client = chi_guarda(dati["a"])

        html = _pagina(client, dati["campionato"].id)

        assert "Classifica finale" in html and "Classifica generale" not in html
        assert "Zona playoff" not in html and "c7-classifica__trend" not in html
        gare = Gara.query.filter_by(campionato_id=dati["campionato"].id).count()
        assert html.count("ha vinto ") == gare
        # Le righe portano alla pagina della gara, come prima.
        assert f'href="/admin/gara/{dati["playoff"].id}"' in html

    def test_al_posto_di_gestione_il_campionato(self, chi_guarda, db_session):
        dati = _concluso(db_session)
        client = chi_guarda(dati["a"])

        html = _pagina(client, dati["campionato"].id)

        assert 'data-c7-tab-btn="classifica"' in html
        assert 'data-c7-tab-btn="gare"' in html
        assert 'data-c7-tab-btn="campionato"' in html
        assert 'data-c7-tab-btn="gestione"' not in html
        assert "Il campionato" in html
        assert "Formula" in html and "Classifica a vittorie" in html
        # La finale non e' una delle gare previste (`conteggio_gare`).
        assert "Giocatori" in html and "2 gare + finale" in html

    def test_nessun_comando_di_gestione(self, chi_guarda, db_session):
        dati = _concluso(db_session)
        client = chi_guarda(dati["a"])

        _senza_comandi(_pagina(client, dati["campionato"].id))

    def test_neanche_per_chi_lo_dirige(self, client, db_session):
        """Chi dirige ha la sua pagina: questa resta in sola lettura."""
        dati = _concluso(db_session)
        _login(client, dati["direttore"])

        _senza_comandi(_pagina(client, dati["campionato"].id))


class TestStagioneInCorso:
    def test_fascia_informativa_e_classifica_con_la_zona(self, chi_guarda, db_session):
        from models.classification.campionato_classification import (
            ClassificationService,
        )

        dati = _campionato_con_playoff(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        _righe_di_turno(db_session, dati["campionato"])
        # Prima degli inviti la zona la decidono le righe `Classification`
        # persistite, come per `start_playoff` (`models/playoff/zona.py`).
        ClassificationService.update_campionato_classification(dati["campionato"].id)
        db_session.commit()
        client = chi_guarda(dati["a"])

        html = _pagina(client, dati["campionato"].id)
        fascia = _fascia(html)

        assert "Stagione in corso" in fascia
        assert "c7-campione" not in fascia
        assert "Classifica generale" in html and "Classifica finale" not in html
        assert "Zona playoff" in html and "c7-cg__riga--zona" in html
        _senza_comandi(html)

    def test_senza_classifica_lo_dice(self, chi_guarda, db_session):
        dati = _campionato(db_session, terminato=False)
        client = chi_guarda(dati["giocatori"][0])

        html = _pagina(client, dati["campionato"].id)

        assert "Stagione in corso" in _fascia(html)
        _senza_comandi(html)


class TestFasePlayoff:
    def test_da_avviare_senza_pulsanti(self, chi_guarda, db_session):
        dati = _campionato(db_session, terminato=True)
        client = chi_guarda(dati["giocatori"][0])

        html = _pagina(client, dati["campionato"].id)
        fascia = _fascia(html)

        assert "Fase playoff" in fascia and "Playoff da avviare" in fascia
        assert "c7-fascia__azione" not in fascia
        _senza_comandi(html)

    def test_inviti_partiti_dice_i_confermati(self, chi_guarda, db_session):
        dati, _gara = _con_gara_di_playoff(db_session, GaraStatus.SETUP.value, 0)
        client = chi_guarda(dati["giocatori"][0])

        html = _pagina(client, dati["campionato"].id)
        fascia = _fascia(html)

        assert "Fase playoff" in fascia and "Inviti chiusi" in fascia
        assert "2 confermati su 2" in fascia
        # La linguetta resta «Il campionato»: gli invitati li gestisce chi
        # dirige, qui la zona in classifica dice chi c'e'.
        assert 'data-c7-tab-btn="playoff"' not in html
        _senza_comandi(html)

    def test_a_finale_cominciata(self, chi_guarda, db_session):
        dati, gara = _con_gara_di_playoff(db_session, GaraStatus.PLAYING.value, 1)
        client = chi_guarda(dati["giocatori"][0])

        html = _pagina(client, dati["campionato"].id)

        assert "Playoff in corso" in _fascia(html)
        assert f'href="/admin/gara/{gara.id}"' in html
        _senza_comandi(html)


class TestVetrina:
    def test_c_e_col_link_pubblico(self, client, db_session):
        dati = _concluso(db_session)
        campionato = dati["campionato"]

        html = _pagina(client, campionato.id)

        assert f'href="/c/{campionato.public_slug_or_token}"' in html

    def test_senza_link_pubblico_non_c_e(self, client, db_session):
        dati = _concluso(db_session)
        campionato = dati["campionato"]
        campionato.public_token = None
        campionato.slug = None
        db.session.commit()

        html = _pagina(client, campionato.id)

        assert 'href="/c/' not in html
        assert "Vetrina" not in html

    def test_mai_per_una_prova(self, logged_in_client):
        from models.campionato.tournament_service import TournamentService
        from models.prova.service import ProvaService
        from models.prova.visibility import prova_visibili
        from models.user.role_enum import UserRole

        client_dir, direttore = logged_in_client(
            role=UserRole.DIRECTOR, username_prefix="dir"
        )
        with prova_visibili():
            campionato = TournamentService().create_campionato_with_director(
                name=f"Campionato di prova {uuid.uuid4().hex[:4]}",
                creator_user_id=direttore.id,
                **ProvaService.campi_di_creazione(),
            )
            db.session.commit()
            campionato_id = campionato.id
        db.session.expunge_all()

        html = _pagina(client_dir, campionato_id)

        assert 'href="/c/' not in html


def test_ogni_linguetta_ha_il_suo_filtro_nel_foglio_di_stile():
    """Una linguetta senza regola in `theme-7c.css` non nasconde niente: sul
    telefono «Il campionato» mostrava tutte le sezioni insieme. Il test client
    non esegue il CSS, quindi il contratto si guarda sul testo."""
    from pathlib import Path

    tema = Path("static/css/theme-7c.css").read_text(encoding="utf-8")
    pagina = Path("templates/public/campionato_detail.html").read_text(encoding="utf-8")
    viste = re.findall(r"\('(\w+)', _\('", pagina)

    assert viste == ["classifica", "gare", "campionato"]
    for vista in viste:
        regola = (
            f'[data-c7-view="{vista}"] [data-c7-tab]' f':not([data-c7-tab~="{vista}"])'
        )
        assert regola in tema, vista
