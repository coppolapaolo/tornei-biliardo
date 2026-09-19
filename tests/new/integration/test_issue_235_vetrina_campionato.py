"""Issue #235, secondo lotto — la vetrina del campionato, e il guscio pubblico.

Il primo lotto ha dato una pagina condivisibile a ogni **gara**. Qui si
aggiunge quella del **campionato**, e si difende la decisione strutturale che
la direzione scelta porta con sé: la vetrina **non indossa i mobili
dell'app**.

Quella parte non è estetica. Chi apre il link non ha un account, non ha una
cronologia e non ha un posto dove tornare: una freccia indietro e una barra
laterale piena di voci che portano al login sono una promessa che la pagina
non può mantenere. E siccome nessun test guarda l'aspetto, senza queste
verifiche il giorno in cui qualcuno rifacesse la vetrina estendendo di nuovo
`base.html` non se ne accorgerebbe nessuno.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Campionato, Gara, Inscription, User
from models.base import db, utc_now
from models.competition.services import GaraService
from models.competition.showcase_service import (
    resolve_public_identifier_campionato,
    update_campionato_showcase,
)
from models.exceptions import ConflictError
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole


def _user(role: str = UserRole.PLAYER.value) -> User:
    unique = str(uuid.uuid4())[:8]
    user = User(
        username=f"{role}_{unique}", email=f"{role}_{unique}@t.local", role=role
    )
    user.set_password("secret123")
    db.session.add(user)
    db.session.commit()
    return user


def _campionato(**overrides) -> Campionato:
    params = dict(name=f"Sociale {uuid.uuid4().hex[:6]}")
    params.update(overrides)
    campionato = Campionato(**params)
    db.session.add(campionato)
    db.session.commit()
    return campionato


def _gara(direttore: User, campionato=None, numero=1, **overrides) -> Gara:
    now = utc_now()
    params = dict(
        campionato_id=campionato.id if campionato is not None else None,
        number=numero,
        name=f"Prova {numero}",
        date=date.today() + timedelta(days=10 * numero),
        location="Sala Test",
        rounds_count=3,
        min_participants=2,
        max_participants=16,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=direttore.id,
        matchmaking_strategy="random",
        inscription_start=now - timedelta(days=1),
        inscription_end=now + timedelta(days=5),
    )
    params.update(overrides)
    gara = GaraService.create_gara(**params)
    gara.status = GaraStatus.INSCRIPTION.value
    db.session.commit()
    return gara


def _pagina(client, url: str) -> str:
    """Il corpo della pagina, senza il pannello di debug in fondo.

    Quel pannello elenca ogni utente per il login rapido: cercare un nome
    nell'HTML grezzo lo troverebbe sempre, e il test passerebbe per una
    ragione che non c'entra con la vetrina.

    Si taglia sul **tag**, non sulla parola: `base.html` definisce anche
    `.debug-footer` in un `<style>` dentro `<head>`, e tagliare lì lascia in
    mano la sola testa del documento. Un `assert "1" in pagina` allora passa
    sempre, e un `assert "Iscriviti" in pagina` fallisce sempre — in entrambi
    i casi senza dire niente di vero sulla pagina.
    """
    corpo = client.get(url).get_data(as_text=True)
    corpo = corpo.split('<footer class="debug-footer"')[0]
    # Il pannello di debug c'e' solo con `DEBUG_MODE` acceso, e un altro test
    # dello stesso worker puo' averlo spento: allora il taglio qui sopra non
    # avviene, e resta in pagina il blocco `polling-config` di `base.html`, che
    # porta l'indirizzo del login per conto suo. Chi cerca «/auth/login» per
    # sapere se c'e' il pulsante «Iscriviti» lo troverebbe sempre.
    return corpo.split('id="polling-config"')[0]


@pytest.mark.integration
class TestGuscioPubblico:
    """La vetrina non è una schermata dell'app, e si vede dal guscio."""

    def test_non_mostra_la_navigazione_dell_app(self, client, db_session):
        gara = _gara(_user(UserRole.DIRECTOR.value))

        pagina = _pagina(client, f"/g/{gara.public_token}")

        assert 'class="c7-public"' in pagina, "manca il guscio pubblico"
        assert "c7-side__brand" not in pagina, "la barra laterale non deve comparire"
        assert "c7-mobilenav" not in pagina, "né la nav flottante"
        assert "c7-head__back" not in pagina, "né la freccia indietro"

    def test_lo_stesso_vale_per_il_campionato(self, client, db_session):
        campionato = _campionato()
        _gara(_user(UserRole.DIRECTOR.value), campionato)

        pagina = _pagina(client, f"/c/{campionato.public_token}")

        assert 'class="c7-public"' in pagina
        assert "c7-side__brand" not in pagina
        assert "c7-mobilenav" not in pagina


@pytest.mark.integration
class TestLaChiamataAllAzioneNonMente:
    """Un pulsante che promette ciò che non si può fare svuota tutta la pagina."""

    def test_a_iscrizioni_chiuse_non_dice_iscriviti(self, client, db_session):
        gara = _gara(_user(UserRole.DIRECTOR.value))
        gara.inscription_end = utc_now() - timedelta(days=1)
        db.session.commit()

        pagina = _pagina(client, f"/g/{gara.public_token}")

        assert "Iscrizioni chiuse" in pagina
        assert "url_iscrizione" not in pagina
        assert "/auth/login" not in pagina, (
            "con le iscrizioni chiuse il pulsante «Iscriviti» non deve esserci: "
            "sotto una pastiglia «Iscrizioni chiuse» è la contraddizione che si "
            "nota per prima"
        )

    def test_ma_una_via_d_uscita_c_e_sempre(self, client, db_session):
        """Chi è arrivato fin qui da un post è chi più si interessa alle prossime."""
        gara = _gara(_user(UserRole.DIRECTOR.value))
        gara.inscription_end = utc_now() - timedelta(days=1)
        db.session.commit()

        pagina = _pagina(client, f"/g/{gara.public_token}")

        assert "/garas" in pagina, "manca la via verso le altre gare"

    def test_a_iscrizioni_aperte_invece_si_iscrive(self, client, db_session):
        gara = _gara(_user(UserRole.DIRECTOR.value))

        pagina = _pagina(client, f"/g/{gara.public_token}")

        assert "/auth/login" in pagina
        assert f"/g/{gara.public_token}" in pagina, "dopo il login si torna qui"


@pytest.mark.integration
class TestVetrinaCampionato:
    def test_lo_scraper_anonimo_riceve_la_pagina(self, client, db_session):
        campionato = _campionato()
        _gara(_user(UserRole.DIRECTOR.value), campionato)

        assert client.get(f"/c/{campionato.public_token}").status_code == 200

    def test_i_meta_portano_indirizzi_assoluti(self, client, db_session):
        """Il difetto invisibile: uno scraper non risolve un `/static/…`.

        Non produce errori né in pagina né nei log — l'anteprima esce senza
        immagine e basta.
        """
        import re

        campionato = _campionato()
        _gara(_user(UserRole.DIRECTOR.value), campionato)

        body = client.get(f"/c/{campionato.public_token}").get_data(as_text=True)

        for proprieta in ("og:image", "og:url"):
            trovato = re.search(
                rf'<meta (?:property|name)="{proprieta}" content="([^"]*)"', body
            )
            assert trovato and trovato.group(1).startswith(
                "http"
            ), f"{proprieta} deve essere assoluto"

    def test_mostra_il_calendario_delle_prove(self, client, db_session):
        campionato = _campionato()
        direttore = _user(UserRole.DIRECTOR.value)
        _gara(direttore, campionato, numero=1)
        _gara(direttore, campionato, numero=2)

        pagina = _pagina(client, f"/c/{campionato.public_token}")

        assert "Prova 1" in pagina
        assert "Prova 2" in pagina

    def test_la_chiamata_all_azione_punta_a_una_gara(self, client, db_session):
        """Non esiste «iscriviti al campionato»: ci si iscrive alla prova aperta."""
        campionato = _campionato()
        gara = _gara(_user(UserRole.DIRECTOR.value), campionato)

        pagina = _pagina(client, f"/c/{campionato.public_token}")

        assert f"/g/{gara.public_token}" in pagina

    def test_senza_prove_aperte_non_promette_un_iscrizione(self, client, db_session):
        campionato = _campionato()
        gara = _gara(_user(UserRole.DIRECTOR.value), campionato)
        gara.status = GaraStatus.COMPLETED.value
        db.session.commit()

        pagina = _pagina(client, f"/c/{campionato.public_token}")

        assert "Iscriviti alla prova" not in pagina

    def test_mostra_il_conteggio_degli_iscritti_non_i_nomi(self, client, db_session):
        campionato = _campionato()
        gara = _gara(_user(UserRole.DIRECTOR.value), campionato)
        giocatore = _user()
        db.session.add(
            Inscription(gara_id=gara.id, user_id=giocatore.id, initial_order=1)
        )
        db.session.commit()

        pagina = _pagina(client, f"/c/{campionato.public_token}")

        assert giocatore.username not in pagina
        assert "1 iscritti" in pagina or "iscritti" in pagina

    def test_un_campionato_eliminato_non_ha_vetrina(self, client, db_session):
        """Il filtro soft-delete su questa entità non è automatico: si scrive.

        Senza, il link continuerebbe a rispondere 200 mostrando una stagione
        che per l'applicazione non esiste più.
        """
        campionato = _campionato()
        _gara(_user(UserRole.DIRECTOR.value), campionato)
        campionato.is_deleted = True
        db.session.commit()

        assert client.get(f"/c/{campionato.public_token}").status_code == 404
        assert resolve_public_identifier_campionato(campionato.public_token) is None

    def test_un_indirizzo_inesistente_resta_un_404(self, client, db_session):
        assert client.get("/c/non-esiste-questo-campionato").status_code == 404

    def test_la_pagina_pubblica_non_assegna_il_token(self, client, db_session):
        """Una pagina che aprono i crawler non scrive sul database.

        Il token si assegna nella schermata di cura, che è del direttore. Farlo
        qui vorrebbe dire una scrittura per ogni passaggio di un robot.
        """
        campionato = _campionato()
        _gara(_user(UserRole.DIRECTOR.value), campionato)
        update_campionato_showcase(campionato.id, slug="sociale-di-prova")
        campionato.public_token = None
        db.session.commit()

        assert client.get("/c/sociale-di-prova").status_code == 200

        db.session.expire(campionato)
        assert campionato.public_token is None


@pytest.mark.integration
class TestIndirizzoLeggibileCampionato:
    def test_lo_slug_apre_la_stessa_pagina_del_token(self, client, db_session):
        campionato = _campionato()
        _gara(_user(UserRole.DIRECTOR.value), campionato)
        update_campionato_showcase(campionato.id, slug="Sociale di Natale 2026")
        db.session.commit()

        assert client.get("/c/sociale-di-natale-2026").status_code == 200
        assert client.get(f"/c/{campionato.public_token}").status_code == 200

    def test_due_campionati_non_possono_avere_lo_stesso_indirizzo(self, db_session):
        primo = _campionato()
        secondo = _campionato()
        update_campionato_showcase(primo.id, slug="sociale-2026")
        db.session.commit()

        with pytest.raises(ConflictError):
            update_campionato_showcase(secondo.id, slug="sociale-2026")

    def test_una_gara_e_un_campionato_possono_chiamarsi_uguale(self, db_session):
        """Vivono su due rotte diverse: `/g/` e `/c/`, nessuna ambiguità.

        Vietarlo sarebbe una restrizione senza motivo — e la più naturale da
        violare, perché il campionato di Natale contiene la gara di Natale.
        """
        from models.competition.showcase_service import update_gara_showcase

        campionato = _campionato()
        gara = _gara(_user(UserRole.DIRECTOR.value), campionato)
        update_campionato_showcase(campionato.id, slug="natale-2026")
        update_gara_showcase(gara.id, slug="natale-2026")
        db.session.commit()

        assert campionato.slug == "natale-2026"
        assert gara.slug == "natale-2026"


def _gara_che_ha_finito(direttore, campionato=None) -> Gara:
    """Una gara che ha giocato tutto, ma che in colonna è ancora `playing`.

    È lo stato in cui una gara resta davvero dopo l'ultima partita: il
    risolutore lo deriva dalle partite (`_resolve_playing`), e senza partite
    vere non lo si può riprodurre — un `current_round` alzato a mano non
    basta, e un test che ci provasse verificherebbe un'altra cosa.
    """
    from models.match.models import Match
    from models.status_enum import MatchStatus

    gara = _gara(direttore, campionato, rounds_count=1)
    uno, due = _user(), _user()
    gara.status = GaraStatus.PLAYING.value
    gara.current_round = 1
    db.session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=uno.id,
            player2_id=due.id,
            player1_score=3,
            player2_score=1,
            winner_id=uno.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
    )
    db.session.commit()
    return gara


@pytest.mark.integration
class TestUnaGaraFinitaRisultaFinita:
    """Il difetto che si vede solo con dati veri.

    Una gara che ha giocato tutti i turni resta `status='playing'` in colonna:
    `get_real_status()` risponde `campionato_completed`, **non** `completed`.
    Confrontare con il solo `GaraStatus.COMPLETED` la lasciava «da giocare»
    nel calendario del campionato, senza vincitore, mesi dopo che si era
    giocata — e sulla sua vetrina nascondeva la classifica finale.

    Trovato guardando la schermata della guida rigenerata: sul dataset
    dimostrativo tutte e quattro le gare risultavano da giocare.
    """

    def test_gara_ha_finito_riconosce_lo_stato_derivato(self, db_session):
        from models.competition.showcase_view import gara_ha_finito
        from models.status_enum import ProvaDerivedStatus

        gara = _gara_che_ha_finito(_user(UserRole.DIRECTOR.value))

        assert gara.status == GaraStatus.PLAYING.value, "in colonna resta «playing»"
        assert gara.get_real_status() == ProvaDerivedStatus.TOURNAMENT_COMPLETED.value
        assert gara_ha_finito(gara), (
            "una gara che ha giocato tutti i turni è finita, anche se in "
            "colonna risulta ancora «playing»"
        )

    def test_nel_calendario_risulta_conclusa(self, client, db_session):
        campionato = _campionato()
        _gara_che_ha_finito(_user(UserRole.DIRECTOR.value), campionato)

        pagina = _pagina(client, f"/c/{campionato.public_token}")

        assert "Conclusa" in pagina
        assert "Da giocare" not in pagina

    def test_sulla_sua_vetrina_e_conclusa(self, db_session):
        from models.competition.showcase_view import costruisci_vetrina

        gara = _gara_che_ha_finito(_user(UserRole.DIRECTOR.value))

        assert costruisci_vetrina(gara).conclusa


@pytest.mark.integration
class TestUnaGaraInCorsoRisultaInCorso:
    """Stesso difetto, un ramo più in là.

    Fra un turno e l'altro il risolutore risponde `round_completed`, non
    `playing`: una gara a metà torneo compariva nel calendario come «Da
    giocare», con sotto un «Iscrizioni dal…» per una gara già cominciata.
    """

    def test_fra_un_turno_e_l_altro_e_in_corso(self, client, db_session):
        from models.match.models import Match
        from models.status_enum import MatchStatus, ProvaDerivedStatus

        campionato = _campionato()
        gara = _gara(_user(UserRole.DIRECTOR.value), campionato, rounds_count=3)
        uno, due = _user(), _user()
        gara.status = GaraStatus.PLAYING.value
        gara.current_round = 1
        db.session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=uno.id,
                player2_id=due.id,
                player1_score=3,
                player2_score=1,
                winner_id=uno.id,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        db.session.commit()

        assert gara.get_real_status() == ProvaDerivedStatus.ROUND_COMPLETED.value

        pagina = _pagina(client, f"/c/{campionato.public_token}")

        assert "In corso" in pagina
        assert "Da giocare" not in pagina
