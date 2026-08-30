"""Issue #235 — la vetrina da condividere sui social.

Il link che il direttore incolla su WhatsApp o Facebook deve produrre
un'anteprima: immagine, titolo, una riga di descrizione. Perché ci riesca
servono due cose insieme, e **è la coppia** che va difesa qui:

1. lo scraper è un client **anonimo senza cookie**, quindi la pagina gli deve
   rispondere 200 — non un redirect al login, non un 404 dell'allowlist di
   produzione (ADR-028);
2. i meta devono esserci e portare indirizzi **assoluti**: uno scraper non
   risolve un `/static/...` relativo, e il risultato è un'anteprima senza
   immagine, senza errori e invisibile in sviluppo.

Il resto sono le tre decisioni prese nella issue: solo il conteggio degli
iscritti (mai i nomi), il banner ereditato dal campionato, l'indirizzo
leggibile accanto al token — che continua a funzionare.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

import pytest

from models import Campionato, Gara, Inscription, User
from models.base import db, utc_now
from models.competition.services import GaraService
from models.competition.showcase_service import (
    set_campionato_banner,
    set_gara_banner,
    update_gara_showcase,
)
from models.exceptions import ConflictError
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole


def _user(role: str = UserRole.PLAYER.value) -> User:
    unique = str(uuid.uuid4())[:8]
    user = User(
        username=f"{role}_{unique}",
        email=f"{role}_{unique}@test.local",
        role=role,
    )
    user.set_password("secret123")
    db.session.add(user)
    db.session.commit()
    return user


def _gara(director: User, **overrides) -> Gara:
    now = utc_now()
    params = dict(
        campionato_id=None,
        number=1,
        name="Trofeo della Locandina",
        date=date.today() + timedelta(days=10),
        location="Sala Test",
        rounds_count=3,
        min_participants=2,
        max_participants=16,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy="random",
        inscription_start=now - timedelta(days=1),
        inscription_end=now + timedelta(days=5),
    )
    params.update(overrides)
    gara = GaraService.create_gara(**params)
    gara.status = GaraStatus.INSCRIPTION.value
    db.session.commit()
    return gara


def _meta(body: str, proprieta: str) -> str | None:
    """Il contenuto di un meta Open Graph, o None se manca."""
    trovato = re.search(
        rf'<meta (?:property|name)="{re.escape(proprieta)}" content="([^"]*)"', body
    )
    return trovato.group(1) if trovato else None


@pytest.mark.integration
class TestAnteprimaSocial:
    """Quello che lo scraper di WhatsApp o Facebook trova seguendo il link."""

    def test_lo_scraper_anonimo_riceve_la_pagina(self, client, db_session):
        gara = _gara(_user(UserRole.DIRECTOR.value))

        risposta = client.get(f"/g/{gara.public_token}")

        assert risposta.status_code == 200

    def test_i_meta_ci_sono_e_parlano_di_questa_gara(self, client, db_session):
        gara = _gara(_user(UserRole.DIRECTOR.value), name="Open di Primavera")

        body = client.get(f"/g/{gara.public_token}").get_data(as_text=True)

        assert "Open di Primavera" in (_meta(body, "og:title") or "")
        descrizione = _meta(body, "og:description") or ""
        assert descrizione, "senza descrizione l'anteprima mostra solo il titolo"
        assert _meta(body, "twitter:card") == "summary_large_image"

    def test_gli_indirizzi_dei_meta_sono_assoluti(self, client, db_session):
        """Il difetto invisibile: un `/static/…` relativo lo scraper lo ignora.

        Non produce errori né in pagina né nei log — l'anteprima esce senza
        immagine e basta. È il motivo per cui questo test guarda il **prefisso**
        e non la presenza del tag.
        """
        gara = _gara(_user(UserRole.DIRECTOR.value))

        body = client.get(f"/g/{gara.public_token}").get_data(as_text=True)

        for proprieta in ("og:image", "og:url"):
            valore = _meta(body, proprieta) or ""
            assert valore.startswith(
                "http"
            ), f"{proprieta} deve essere assoluto: {valore!r}"

    def test_una_gara_zombie_non_finisce_sui_motori_di_ricerca(
        self, client, db_session
    ):
        """SETUP con data passata: la lista pubblica la nasconde (ADR-030).

        Il link continua a funzionare — gliel'ha dato il direttore — ma la
        pagina si dichiara non indicizzabile.
        """
        gara = _gara(_user(UserRole.DIRECTOR.value))
        # `create_gara` rifiuta una data passata, e fa bene: una gara zombie
        # non nasce così, ci diventa col tempo. Si retrodata dopo, che è
        # esattamente ciò che succede a una gara mai avviata.
        gara.status = GaraStatus.SETUP.value
        gara.date = date.today() - timedelta(days=30)
        db.session.commit()

        body = client.get(f"/g/{gara.public_token}").get_data(as_text=True)

        assert _meta(body, "robots") == "noindex"


@pytest.mark.integration
class TestCosaMostraLaVetrina:
    def test_mostra_il_conteggio_degli_iscritti_non_i_nomi(self, client, db_session):
        """Decisione della issue: la pagina è pubblica, i nomi no.

        Chi si iscrive a una gara non sta scegliendo di comparire in un elenco
        che chiunque abbia il link può leggere.
        """
        gara = _gara(_user(UserRole.DIRECTOR.value))
        giocatore = _user()
        db.session.add(
            Inscription(gara_id=gara.id, user_id=giocatore.id, initial_order=1)
        )
        db.session.commit()

        body = client.get(f"/g/{gara.public_token}").get_data(as_text=True)
        # Il pannello di debug in fondo a `base.html` elenca ogni utente per
        # il login rapido: si guarda la pagina, non il guscio, altrimenti il
        # test fallisce per una ragione che non c'entra con la vetrina.
        pagina = body.split("debug-footer")[0]

        assert giocatore.username not in pagina, "la vetrina non elenca gli iscritti"
        assert "1" in pagina, "il conteggio invece si mostra"

    def test_la_via_per_iscriversi_c_e_anche_per_chi_non_ha_un_account(
        self, client, db_session
    ):
        gara = _gara(_user(UserRole.DIRECTOR.value))

        body = client.get(f"/g/{gara.public_token}").get_data(as_text=True)

        assert "/auth/login" in body
        assert f"/g/{gara.public_token}" in body, "dopo il login si torna qui"

    def test_non_ricalcola_la_classifica(self, client, db_session, monkeypatch):
        """Una pagina pubblica non scrive sul database.

        La pagina di gestione, per mostrare la classifica, la ricalcola e la
        salva. Qui non si può: la vetrina la aprono i crawler, e ogni loro
        passaggio innescherebbe scritture su una richiesta anonima.
        """
        from models.classification.models import RoundClassification

        gara = _gara(_user(UserRole.DIRECTOR.value))
        gara.status = GaraStatus.COMPLETED.value
        db.session.commit()

        chiamate = []
        monkeypatch.setattr(
            RoundClassification,
            "calculate_classification_after_round",
            staticmethod(lambda *a, **k: chiamate.append(a)),
        )

        client.get(f"/g/{gara.public_token}")

        assert chiamate == [], "la vetrina deve leggere, non ricalcolare"


@pytest.mark.integration
class TestBannerEreditato:
    def test_la_gara_usa_la_locandina_del_campionato(self, db_session):
        """Una grafica sola per tutte le tappe: è il caso normale."""
        campionato = Campionato(name=f"Camp {uuid.uuid4().hex[:6]}")
        db.session.add(campionato)
        db.session.commit()
        gara = _gara(_user(UserRole.DIRECTOR.value), campionato_id=campionato.id)

        set_campionato_banner(campionato.id, "static/uploads/banners/camp.png")
        db.session.commit()

        assert gara.effective_banner_path == "static/uploads/banners/camp.png"

    def test_la_gara_puo_scavalcare_quella_del_campionato(self, db_session):
        campionato = Campionato(name=f"Camp {uuid.uuid4().hex[:6]}")
        db.session.add(campionato)
        db.session.commit()
        gara = _gara(_user(UserRole.DIRECTOR.value), campionato_id=campionato.id)
        set_campionato_banner(campionato.id, "static/uploads/banners/camp.png")
        set_gara_banner(gara.id, "static/uploads/banners/gara.png")
        db.session.commit()

        assert gara.effective_banner_path == "static/uploads/banners/gara.png"

    def test_togliere_la_propria_fa_tornare_a_quella_del_campionato(self, db_session):
        """«Rimuovi» non lascia la gara senza immagine: la fa tornare a ereditare."""
        campionato = Campionato(name=f"Camp {uuid.uuid4().hex[:6]}")
        db.session.add(campionato)
        db.session.commit()
        gara = _gara(_user(UserRole.DIRECTOR.value), campionato_id=campionato.id)
        set_campionato_banner(campionato.id, "static/uploads/banners/camp.png")
        set_gara_banner(gara.id, "static/uploads/banners/gara.png")
        db.session.commit()

        set_gara_banner(gara.id, None)
        db.session.commit()

        assert gara.effective_banner_path == "static/uploads/banners/camp.png"

    def test_una_gara_standalone_senza_locandina_non_ne_ha(self, db_session):
        gara = _gara(_user(UserRole.DIRECTOR.value))

        assert gara.effective_banner_path is None


@pytest.mark.integration
class TestIndirizzoLeggibile:
    def test_lo_slug_apre_la_stessa_pagina_del_token(self, client, db_session):
        gara = _gara(_user(UserRole.DIRECTOR.value))
        update_gara_showcase(gara.id, slug="Open di Natale 2026")
        db.session.commit()

        assert client.get("/g/open-di-natale-2026").status_code == 200

    def test_il_token_continua_a_funzionare_dopo_lo_slug(self, client, db_session):
        """Le locandine già stampate non diventano carta straccia."""
        gara = _gara(_user(UserRole.DIRECTOR.value))
        update_gara_showcase(gara.id, slug="Open di Natale 2026")
        db.session.commit()

        assert client.get(f"/g/{gara.public_token}").status_code == 200

    def test_uno_slug_non_puo_coincidere_col_token_di_un_altra_gara(self, db_session):
        """Il token è url-safe e può essere tutto minuscolo, cioè indistinguibile
        da uno slug: senza questo controllo lo stesso indirizzo aprirebbe due
        gare diverse a seconda di quale query vince.
        """
        direttore = _user(UserRole.DIRECTOR.value)
        prima = _gara(direttore)
        seconda = _gara(direttore, number=2, date=date.today() + timedelta(days=20))
        # Un token con maiuscole non collide mai: la normalizzazione lo
        # abbassa e ne fa un'altra stringa. Il caso che conta è il token già
        # tutto minuscolo, che capita in circa una gara su cento — abbastanza
        # da succedere davvero, abbastanza di rado da non vederlo arrivare.
        prima.public_token = "abc12xyz"
        db.session.commit()

        with pytest.raises(ConflictError):
            update_gara_showcase(seconda.id, slug="abc12xyz")

    def test_un_indirizzo_inesistente_resta_un_404(self, client, db_session):
        assert client.get("/g/non-esiste-questa-gara").status_code == 404
