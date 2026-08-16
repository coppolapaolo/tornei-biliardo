"""Le opzioni del tabellone si vedono e si salvano dal form della gara (US-4/6/7).

Il parser ha i suoi unit test (`test_bracket_form_parser.py`); qui si verifica
che quei campi **esistano davvero in una schermata** e che un salvataggio
completo li porti fino al database. Erano leggibili dal parser da un commit,
ma nessun form li mandava: senza questo passaggio le due opzioni restavano
irraggiungibili come lo erano i formati stessi.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta

import pytest

from models import Gara, User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def director(db_session):
    user = User(
        username=f"dir_{uuid.uuid4().hex[:8]}",
        email=f"dir_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.DIRECTOR.value,
        onboarding_completed=True,
    )
    user.set_password("director123")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


def _form(**overrides):
    campi = {
        "name": f"Tabellone {uuid.uuid4().hex[:6]}",
        "date": (date.today() + timedelta(days=10)).isoformat(),
        "time": "20:00",
        "discipline": "9_ball",
        "distance": "5",
        "rounds_count": "3",
        "min_participants": "4",
        "max_participants": "16",
        "entry_fee": "0",
        "matchmaking_strategy": "direct_elimination",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "withdraw_policy": "forfeit",
    }
    campi.update(overrides)
    return campi


class TestFormDiCreazione:
    def test_i_campi_del_tabellone_sono_nella_pagina(self, client, director):
        _login(client, director)
        pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)

        assert 'name="separate_teammates"' in pagina
        assert 'name="third_place_match"' in pagina
        assert 'name="double_ko_rounds"' in pagina
        # Lo scoprimento è nel file condiviso fra creazione e modifica.
        assert "bracket_options.js" in pagina

    def test_salva_le_due_opzioni(self, client, db_session, director):
        """US-6 e US-7: spuntarle deve arrivare fino al database."""
        _login(client, director)
        dati = _form(separate_teammates="on", third_place_match="on")

        client.post("/admin/gara/create_standalone", data=dati, follow_redirects=True)

        gara = Gara.query.filter_by(name=dati["name"]).one()
        assert gara.matchmaking_strategy == "direct_elimination"
        assert gara.separate_teammates is True
        assert gara.third_place_match is True
        # Sul tabellone la classifica è per posizione, comunque sia arrivato
        # il campo dal browser.
        assert gara.classification_system == "POSITION"

    def test_spente_di_default(self, client, db_session, director):
        """Chi non le spunta non deve trovarsele accese."""
        _login(client, director)
        dati = _form()

        client.post("/admin/gara/create_standalone", data=dati, follow_redirects=True)

        gara = Gara.query.filter_by(name=dati["name"]).one()
        assert gara.separate_teammates is False
        assert gara.third_place_match is False

    def test_finalina_ignorata_sul_doppio_ko(self, client, db_session, director):
        """US-7: nel doppio KO il terzo posto lo decide già il tabellone."""
        _login(client, director)
        dati = _form(
            matchmaking_strategy="double_knockout",
            third_place_match="on",
            separate_teammates="on",
            rounds_count="7",
            max_participants="8",
        )

        client.post("/admin/gara/create_standalone", data=dati, follow_redirects=True)

        gara = Gara.query.filter_by(name=dati["name"]).one()
        assert gara.third_place_match is False
        assert gara.separate_teammates is True

    def test_senza_massimo_iscritti_il_tabellone_non_si_crea(
        self, client, db_session, director
    ):
        """US-4: il massimo dichiara la capienza, quindi è obbligatorio."""
        _login(client, director)
        dati = _form(max_participants="")

        client.post("/admin/gara/create_standalone", data=dati, follow_redirects=True)

        assert Gara.query.filter_by(name=dati["name"]).first() is None

    def test_fase_a_gironi(self, client, db_session, director):
        """Formula FISBB: il girone è il doppio KO fermato dopo due turni."""
        _login(client, director)
        dati = _form(
            matchmaking_strategy="double_knockout",
            double_ko_rounds="2",
            rounds_count="7",
            max_participants="24",
        )

        client.post("/admin/gara/create_standalone", data=dati, follow_redirects=True)

        gara = Gara.query.filter_by(name=dati["name"]).one()
        assert gara.double_ko_rounds == 2


class TestFormDiModifica:
    def test_i_campi_arrivano_con_lo_stato_giusto(self, client, db_session, director):
        gara = Gara(
            director_id=director.id,
            number=1,
            name=f"Modifica {uuid.uuid4().hex[:6]}",
            date=date.today() + timedelta(days=10),
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            rounds_count=3,
            min_participants=4,
            max_participants=16,
            matchmaking_strategy="direct_elimination",
            classification_system="POSITION",
            separate_teammates=True,
            third_place_match=False,
        )
        db_session.add(gara)
        db_session.commit()

        _login(client, director)
        pagina = client.get(f"/admin/gara/{gara.id}/edit").get_data(as_text=True)

        assert 'id="separate_teammates"' in pagina
        assert 'id="third_place_match"' in pagina
        # Lo stato acceso/spento deve rispecchiare la gara, non il default.
        acceso = pagina.split('id="separate_teammates"')[1][:120]
        spento = pagina.split('id="third_place_match"')[1][:120]
        assert "checked" in acceso
        assert "checked" not in spento


class TestAvvisoDistanzePari:
    def test_il_configuratore_spiega_perche_non_si_sceglie(self, client, director):
        """Sul tabellone il numero esatto non si avverte: si toglie.

        Prima qui c'era un avviso che chiedeva solo un numero **dispari**.
        Era la lettura stretta dello stesso principio, e lasciava passare una
        configurazione comunque inutile: il vincitore è deciso a metà partita
        e i rack seguenti non cambiano né il tabellone né la classifica.
        """
        _login(client, director)
        pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)

        assert 'id="bracket-distance-note"' in pagina
        assert 'id="exact_number_row"' in pagina
        # L'avviso vecchio non deve sopravvivere come codice morto.
        assert "bracket-distance-warning" not in pagina


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestMinimiDiFormatoNellAttributo:
    """I pavimenti del formato arrivano al JS come JSON in un data attribute.

    Regressione da una review: `|tojson` **non** scappa le virgolette doppie
    (scappa `< > & '`), quindi in un attributo delimitato da doppi apici il
    JSON si chiude alla prima chiave e l'HTML si rompe. Il JS leggeva un
    frammento, `JSON.parse` falliva e — con il `try/catch` — il minimo iscritti
    e la stima dei turni smettevano di funzionare **in silenzio**.

    Stessa regola degli `onclick` in `templates/CLAUDE.md`: attributo con
    apici singoli.
    """

    def test_il_json_dei_minimi_resta_leggibile(self, client, director):
        _login(client, director)
        pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)

        match = re.search(r"data-minimum-players='([^']+)'", pagina)
        assert match, "l'attributo dev'essere delimitato da apici singoli"

        minimi = json.loads(match.group(1))
        assert minimi["direct_elimination"] == 4
        assert minimi["double_knockout"] == 8

    def test_l_attributo_non_usa_i_doppi_apici(self, client, director):
        """Il caso che rompeva: `data-minimum-players="{"direct_...` ."""
        _login(client, director)
        pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)

        assert 'data-minimum-players="' not in pagina


class TestLeTreSchermateSonoCoerenti:
    """Le gare si creano e si modificano da **tre** schermate, non una.

    Creazione standalone, modifica, e il modale "nuova gara" dentro un
    campionato. Le prime due condividono il configuratore della distanza e
    `bracket_options.js`; la terza no — eredita la strategia dal campionato,
    quindi non ha il selettore da cui quello script parte, e infatti era
    rimasta indietro: mostrava turni, numero esatto, forfait, dispari,
    anti-reincontro e spareggio, tutti senza effetto.

    Il server li impone comunque, quindi non si rompeva niente: si chiedevano
    sei cose e si ignoravano sei risposte. Questo test tiene allineate le tre
    schermate, che è il punto in cui il progetto ha già avuto drift.
    """

    DERIVATI = ["rounds_count", "withdraw_policy", "odd_number_policy"]

    def _campionato_bracket(self, db_session, director):
        from models import Campionato

        campionato = Campionato(
            name=f"Camp {uuid.uuid4().hex[:6]}",
            campionato_type="direct_elimination",
            default_classification_system="POSITION",
            is_active=True,
        )
        db_session.add(campionato)
        db_session.flush()
        from models.user.models import DirectorAssignment

        db_session.add(
            DirectorAssignment(
                entity_type="campionato",
                entity_id=campionato.id,
                user_id=director.id,
                assigned_by_id=director.id,
            )
        )
        db_session.commit()
        return campionato

    def test_la_creazione_standalone_nasconde_i_derivati(self, client, director):
        _login(client, director)
        pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)

        # Il blocco c'è ma è marcato: lo nasconde il JS sulla strategia scelta.
        assert pagina.count("data-bracket-hide") >= len(self.DERIVATI)
        assert "anti_rematch_section" in pagina

    def test_la_modifica_marca_gli_stessi_campi(self, client, db_session, director):
        from models import Gara

        gara = Gara(
            director_id=director.id,
            number=db_session.query(Gara).count() + 1,
            name=f"G {uuid.uuid4().hex[:6]}",
            date=date.today() + timedelta(days=10),
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            rounds_count=4,
            min_participants=4,
            max_participants=16,
            matchmaking_strategy="direct_elimination",
        )
        db_session.add(gara)
        db_session.commit()

        _login(client, director)
        pagina = client.get(f"/admin/gara/{gara.id}/edit").get_data(as_text=True)

        assert pagina.count("data-bracket-hide") >= len(self.DERIVATI)

    def test_il_modale_del_campionato_non_chiede_i_derivati(
        self, client, db_session, director
    ):
        """La terza schermata: qui la strategia è ereditata, quindi la
        decisione la prende il template invece del JavaScript."""
        campionato = self._campionato_bracket(db_session, director)
        _login(client, director)

        pagina = client.get(f"/admin/campionato/{campionato.id}").get_data(as_text=True)

        # I campi restano nel DOM (il POST li manda), ma nascosti.
        assert 'id="create_rounds_count"' in pagina
        assert 'id="create_exact_number"' in pagina
        # Ogni blocco derivato porta il suo display:none.
        assert pagina.count('style="display:none"') >= 4

    def test_su_un_campionato_a_girone_il_modale_chiede_tutto(
        self, client, db_session, director
    ):
        """Non-regressione: fuori dal tabellone il modale non cambia."""
        from models import Campionato
        from models.user.models import DirectorAssignment

        campionato = Campionato(
            name=f"Camp {uuid.uuid4().hex[:6]}",
            campionato_type="amalfi",
            default_classification_system="WINS",
            is_active=True,
        )
        db_session.add(campionato)
        db_session.flush()
        db_session.add(
            DirectorAssignment(
                entity_type="campionato",
                entity_id=campionato.id,
                user_id=director.id,
                assigned_by_id=director.id,
            )
        )
        db_session.commit()

        _login(client, director)
        pagina = client.get(f"/admin/campionato/{campionato.id}").get_data(as_text=True)

        assert 'id="create_rounds_count"' in pagina
        assert "Gestione Forfait" in pagina
        assert "Gestione Dispari" in pagina


class TestDefaultDelCampionato:
    """Anche i default del campionato smettono di chiedere l'inutile.

    Un livello sopra ai form della gara c'era lo stesso difetto: il campionato
    a tabellone proponeva "Turni", "Giocatori dispari" e "Anti-rematch", che
    il parser della gara sovrascrive comunque — turni fissati dal sorteggio,
    bye strutturali, e nessun reincontro possibile visto che chi perde esce.
    """

    def _campionato(self, db_session, director, tipo):
        from models import Campionato
        from models.user.models import DirectorAssignment

        campionato = Campionato(
            name=f"Camp {uuid.uuid4().hex[:6]}",
            campionato_type=tipo,
            default_classification_system="POSITION" if "elim" in tipo else "WINS",
            is_active=True,
        )
        db_session.add(campionato)
        db_session.flush()
        db_session.add(
            DirectorAssignment(
                entity_type="campionato",
                entity_id=campionato.id,
                user_id=director.id,
                assigned_by_id=director.id,
            )
        )
        db_session.commit()
        return campionato

    def test_la_modifica_marca_i_campi_inerti(self, client, db_session, director):
        campionato = self._campionato(db_session, director, "direct_elimination")
        _login(client, director)

        pagina = client.get(
            f"/admin/campionato/{campionato.id}/edit"
        ).get_data(as_text=True)

        # Tre blocchi marcati, che lo script nasconde sui tipi a tabellone.
        assert pagina.count("js-bracket-inert") >= 3

    def test_su_un_campionato_a_girone_restano(self, client, db_session, director):
        """Non-regressione: fuori dal tabellone quei default servono davvero."""
        campionato = self._campionato(db_session, director, "amalfi")
        _login(client, director)

        pagina = client.get(
            f"/admin/campionato/{campionato.id}/edit"
        ).get_data(as_text=True)

        assert 'id="default_rounds_count"' in pagina
        assert 'id="default_odd_policy"' in pagina
