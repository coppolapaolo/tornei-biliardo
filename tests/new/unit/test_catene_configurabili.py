"""Le catene degli spareggi si configurano (ADR-078, parte configurabile).

Tre livelli, tre catene: la classifica di turno e quella di gara stanno sulla
gara (`catena_turno`, `catena_gara`), il campionato le **propone** alle sue
gare (ADR-075) e ha in più la catena della classifica generale. Fuori da un
campionato vale il default dell'app.

Lo spareggio SSR non è più un interruttore: è il criterio `ssr:N` della
catena di gara. La migration 20261007 ha scritto su ogni gara la catena che
riproduce il comportamento di prima.

Qui si difende, per la CI che esegue solo i test unitari:

* da dove si legge una catena (gara → campionato → default);
* cosa l'editor può salvare (il principale, lo SSR nel turno, il sorteggio);
* la migration, che deve riprodurre esattamente le due colonne di prima;
* la gara che nasce con le catene del campionato, o con quelle di default;
* le regole di modifica: la catena di turno vale dal turno successivo, anche
  quando la classifica di un turno già nato si ricalcola; quella di gara si
  cambia finché lo spareggio non è cominciato;
* il cambio di sistema, che porta con sé le catene di default;
* le parole: storia, regolamento, editor.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import uuid
from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.classification import catene
from models.classification.ordinamento import (
    Criterio,
    Livello,
    Voce,
    catena_dal_testo,
    catena_di_default,
    normalizza_catena,
    testo_della_catena as _in_colonna,
)
from models.competition.models import Gara
from models.status_enum import ClassificationSystem, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole

WINS = ClassificationSystem.WINS
RACK = ClassificationSystem.RACK
D = Voce(Criterio.DIFFERENZA_RACK)
SD = Voce(Criterio.SCONTRI_DIRETTI)
PREC = Voce(Criterio.POSIZIONE_PRECEDENTE)
SORT = Voce(Criterio.SORTEGGIO)


def _testo(*voci: str) -> str:
    return json.dumps(list(voci))


def _gara_finta(**campi) -> SimpleNamespace:
    base = dict(
        classification_system="WINS",
        catena_turno=None,
        catena_gara=None,
        campionato=None,
    )
    base.update(campi)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Il testo in colonna
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIlTesto:
    def test_andata_e_ritorno(self):
        catena = (SD, Voce(Criterio.SPAREGGIO_SSR, 2), SORT)
        assert catena_dal_testo(_in_colonna(catena)) == catena

    def test_la_catena_vuota_non_e_null(self):
        """`[]` è una scelta («si resta pari»), NULL vuol dire «come il
        campionato»: devono restare due valori diversi."""
        assert catena_dal_testo("[]") == ()
        assert catena_dal_testo(None) is None
        assert catena_dal_testo("") is None

    def test_la_forma_del_modulo(self):
        assert catena_dal_testo("scontri_diretti,ssr:3") == (
            SD,
            Voce(Criterio.SPAREGGIO_SSR, 3),
        )

    def test_voci_illeggibili_scartate(self):
        assert catena_dal_testo('["inventato", "ssr:0", "differenza_rack"]') == (D,)

    def test_lo_spareggio_ha_un_posto_massimo(self):
        assert catena_dal_testo("ssr:100") == ()


# ---------------------------------------------------------------------------
# Da dove si legge
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDaDoveSiLegge:
    def test_gara_singola_senza_catena_ha_il_default(self):
        gara = _gara_finta()
        assert catene.catena_di_turno(gara) == (D, PREC, SORT)
        assert catene.catena_di_gara(gara) == (
            D,
            Voce(Criterio.SPAREGGIO_SSR, 3),
        )

    def test_la_catena_della_gara_vince(self):
        gara = _gara_finta(catena_gara=_testo("scontri_diretti"))
        assert catene.catena_di_gara(gara) == (SD,)

    def test_senza_catena_la_gara_legge_quella_proposta(self):
        campionato = SimpleNamespace(
            default_catena_gara=_testo("scontri_diretti", "sorteggio"),
            default_catena_turno=None,
        )
        gara = _gara_finta(campionato=campionato)
        assert catene.catena_di_gara(gara) == (SD, SORT)

    def test_il_principale_non_entra_mai(self):
        """Nel sistema a triangoli i triangoli vinti sono il principale."""
        gara = _gara_finta(
            classification_system="RACK", catena_gara=_testo("rack_vinti", "ssr:2")
        )
        assert catene.catena_di_gara(gara) == (Voce(Criterio.SPAREGGIO_SSR, 2),)

    def test_senza_spareggio_non_si_spareggia(self):
        from models.competition.spareggio_service import SpareggioService

        gara = _gara_finta(catena_gara=_testo("differenza_rack"))
        assert catene.ssr_fino_al_della_gara(gara) is None
        assert SpareggioService.tiebreakers_apply_to(gara) is False
        # Il podio resta di tre.
        assert SpareggioService.ssr_fino_al(gara) == 3

    def test_il_posto_dello_spareggio(self):
        from models.competition.spareggio_service import SpareggioService

        gara = _gara_finta(catena_gara=_testo("differenza_rack", "ssr:5"))
        assert SpareggioService.ssr_fino_al(gara) == 5

    def test_la_catena_generale(self):
        campionato = SimpleNamespace(catena_generale=None)
        assert catene.catena_generale(campionato, WINS) == (
            D,
            Voce(Criterio.SPAREGGIO_SSR),
            PREC,
            SORT,
        )
        campionato.catena_generale = _testo("scontri_diretti")
        # Nel campionato l'ordine è sempre completo.
        assert catene.catena_generale(campionato, WINS) == (SD, SORT)


# ---------------------------------------------------------------------------
# Cosa l'editor salva
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDalModulo:
    def test_nel_turno_niente_spareggio_e_sorteggio_in_fondo(self):
        testo = catene.testo_dal_modulo(
            "sorteggio,ssr:3,scontri_diretti", Livello.TURNO, WINS
        )
        assert json.loads(testo) == ["scontri_diretti", "sorteggio"]

    def test_nella_gara_il_sorteggio_non_e_obbligatorio(self):
        assert catene.testo_dal_modulo("", Livello.GARA, WINS) == "[]"

    def test_lo_spareggio_una_volta_sola(self):
        testo = catene.testo_dal_modulo("ssr:2,ssr:3", Livello.GARA, WINS)
        assert json.loads(testo) == ["ssr:2"]

    def test_il_principale_si_toglie(self):
        testo = catene.testo_dal_modulo("vittorie,differenza_rack", Livello.GARA, WINS)
        assert json.loads(testo) == ["differenza_rack"]

    def test_nel_campionato_lo_spareggio_e_la_somma(self):
        testo = catene.testo_dal_modulo("ssr:2", Livello.CAMPIONATO, WINS)
        assert json.loads(testo) == ["ssr", "sorteggio"]


# ---------------------------------------------------------------------------
# La migration
# ---------------------------------------------------------------------------


def _migration():
    spec = importlib.util.spec_from_file_location(
        "m", "migrations/20261007_catene_degli_spareggi.py"
    )
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.unit
class TestLaMigration:
    def test_riproduce_lo_spareggio_di_prima(self, tmp_path):
        percorso = tmp_path / "vecchio.db"
        conn = sqlite3.connect(percorso)
        conn.executescript("""
            CREATE TABLE campionato (
                id INTEGER PRIMARY KEY, default_classification_system TEXT);
            CREATE TABLE gara (
                id INTEGER PRIMARY KEY, classification_system TEXT,
                tiebreaker_enabled BOOLEAN DEFAULT 1 NOT NULL,
                tiebreaker_until_position INTEGER DEFAULT 3);
            INSERT INTO campionato VALUES (1, 'WINS'), (2, 'RACK');
            INSERT INTO gara VALUES
                (1, 'WINS', 1, 3), (2, 'WINS', 1, 1), (3, 'WINS', 0, 3),
                (4, 'RACK', 1, NULL), (5, 'RACK', 0, 2), (6, 'POSITION', 1, 3);
            """)
        conn.commit()
        conn.close()

        modulo = _migration()
        modulo.upgrade_sqlite(str(percorso))
        modulo.upgrade_sqlite(str(percorso))  # rilanciata non fa niente

        conn = sqlite3.connect(percorso)
        gare = dict(
            conn.execute("SELECT id, catena_gara FROM gara ORDER BY id").fetchall()
        )
        turni = dict(
            conn.execute("SELECT id, catena_turno FROM gara ORDER BY id").fetchall()
        )
        campionati = conn.execute(
            "SELECT default_catena_turno, default_catena_gara, catena_generale "
            "FROM campionato ORDER BY id"
        ).fetchall()
        conn.close()

        assert json.loads(gare[1]) == ["differenza_rack", "ssr:3"]
        assert json.loads(gare[2]) == ["differenza_rack", "ssr:1"]
        assert json.loads(gare[3]) == ["differenza_rack"]
        assert json.loads(gare[4]) == ["ssr:3"]
        assert json.loads(gare[5]) == []
        assert json.loads(gare[6]) == ["differenza_rack", "ssr:3"]
        assert json.loads(turni[1]) == [
            "differenza_rack",
            "posizione_precedente",
            "sorteggio",
        ]
        assert json.loads(turni[4]) == ["posizione_precedente", "sorteggio"]
        assert [json.loads(c) for c in campionati[1]] == [
            ["posizione_precedente", "sorteggio"],
            ["ssr:3"],
            ["ssr", "posizione_precedente", "sorteggio"],
        ]

    @pytest.mark.parametrize("sistema", [WINS, RACK])
    def test_le_catene_scritte_sono_quelle_del_motore(self, sistema):
        """La migration non importa l'app: le sue catene vanno tenute uguali
        a `catena_di_default` (e normalizzate come le si salva)."""
        modulo = _migration()

        def motore(livello, **kw):
            return [
                v.serializza()
                for v in normalizza_catena(
                    catena_di_default(livello, sistema, **kw), livello, sistema
                )
            ]

        assert modulo.catena_di_turno(sistema.value) == motore(Livello.TURNO)
        assert modulo.catena_di_gara(sistema.value, 2) == motore(
            Livello.GARA, ssr_fino_al=2
        )
        assert modulo.catena_di_gara(sistema.value, None) == motore(
            Livello.GARA, ssr_fino_al=None
        )
        assert modulo.catena_generale(sistema.value) == motore(Livello.CAMPIONATO)

    def test_la_forma_e_quella_del_codice(self):
        """Stesso testo di `testo_della_catena`: la storia non vede cambi finti."""
        modulo = _migration()
        assert json.dumps(modulo.catena_di_gara("WINS", 3)) == _in_colonna(
            (D, Voce(Criterio.SPAREGGIO_SSR, 3))
        )


# ---------------------------------------------------------------------------
# Il cambio di sistema
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIlCambioDiSistema:
    def test_la_catena_di_default_segue_il_sistema(self):
        prima = _in_colonna((D, PREC, SORT))
        dopo = catene.adegua_al_sistema(prima, Livello.TURNO, WINS, RACK)
        assert json.loads(dopo) == ["posizione_precedente", "sorteggio"]

    def test_lo_spareggio_conserva_il_suo_posto(self):
        prima = _testo("differenza_rack", "ssr:5")
        dopo = catene.adegua_al_sistema(prima, Livello.GARA, WINS, RACK)
        assert json.loads(dopo) == ["ssr:5"]

    def test_una_catena_scelta_resta(self):
        prima = _testo("scontri_diretti", "sorteggio")
        assert catene.adegua_al_sistema(prima, Livello.TURNO, WINS, RACK) is None


# ---------------------------------------------------------------------------
# Sul database: nascita, proposta, modifiche
# ---------------------------------------------------------------------------


def _direttore():
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"dir_{sigla}", email=f"dir_{sigla}@t.it", role=UserRole.DIRECTOR.value
    )
    utente.set_password("x123456")
    db.session.add(utente)
    db.session.commit()
    return utente


def _crea(campionato_id=None, **campi):
    from models.competition.services import GaraService

    direttore = _direttore()
    return GaraService.create_gara(
        number=1,
        name=f"G {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=30),
        discipline="8_ball",
        distance=3,
        campionato_id=campionato_id,
        director_id=direttore.id,
        rounds_count=4,
        matchmaking_strategy="amalfi",
        **campi,
    )


@pytest.mark.unit
class TestLaGaraNasce:
    def test_una_gara_singola_nasce_col_default_scritto(self, db_session):
        gara = _crea(classification_system="RACK", odd_number_policy="no")
        assert json.loads(gara.catena_turno) == ["posizione_precedente", "sorteggio"]
        assert json.loads(gara.catena_gara) == ["ssr:3"]

    def test_nel_campionato_nasce_con_la_proposta(self, db_session):
        campionato = Campionato(
            name=f"C {uuid.uuid4().hex[:6]}",
            default_catena_turno=_testo("scontri_diretti", "sorteggio"),
            default_catena_gara=_testo("scontri_diretti", "ssr:2"),
        )
        db.session.add(campionato)
        db.session.commit()
        gara = _crea(campionato_id=campionato.id)
        assert json.loads(gara.catena_turno) == ["scontri_diretti", "sorteggio"]
        assert json.loads(gara.catena_gara) == ["scontri_diretti", "ssr:2"]

    def test_la_scelta_del_modulo_vince(self, db_session):
        gara = _crea(catena_gara="[]")
        assert gara.catena_gara == "[]"


@pytest.mark.unit
def test_il_campionato_propone_le_catene():
    from models.campionato.proposte import CAMPI_PROPOSTI, _valore_da_scrivere

    assert CAMPI_PROPOSTI["default_catena_turno"] == "catena_turno"
    assert CAMPI_PROPOSTI["default_catena_gara"] == "catena_gara"
    # La catena vuota resta una catena, non diventa NULL.
    assert _valore_da_scrivere("catena_gara", "[]") == {"catena_gara": "[]"}


@pytest.mark.unit
def test_le_regole_di_modifica():
    from models.competition.campi_modificabili import (
        REGOLE,
        REGOLE_DEL_TABELLONE,
        SPAREGGIO,
    )

    assert "catena_turno" in REGOLE
    assert "catena_turno" in REGOLE_DEL_TABELLONE
    assert SPAREGGIO == frozenset({"catena_gara"})


def _gara_avviata(**campi):
    base = dict(
        number=1,
        name=f"Avviata {uuid.uuid4().hex[:6]}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="8_ball",
        distance=3,
        rounds_count=4,
        current_round=2,
        min_participants=2,
        matchmaking_strategy="amalfi",
        classification_system="WINS",
        status=GaraStatus.PLAYING.value,
        catena_turno=_in_colonna((D, PREC, SORT)),
        catena_gara=_in_colonna((D, Voce(Criterio.SPAREGGIO_SSR, 3))),
    )
    base.update(campi)
    gara = Gara(**base)
    db.session.add(gara)
    db.session.commit()
    return gara


@pytest.mark.unit
class TestDalTurnoSuccessivo:
    """Cambiata durante il turno 2, la catena di turno vale dal turno 3: la
    classifica dei turni 1 e 2 si fa con quella di prima, anche ricalcolata."""

    def test_i_turni_gia_nati_tengono_la_loro(self, db_session):
        from models.competition.services import GaraService

        gara = _gara_avviata()
        nuova = _in_colonna((SD, SORT))
        GaraService.update_gara(gara.id, catena_turno=nuova)

        gara = db.session.get(Gara, gara.id)
        assert gara.catena_turno == nuova
        assert catene.catena_di_turno(gara, 1) == (D, PREC, SORT)
        assert catene.catena_di_turno(gara, 2) == (D, PREC, SORT)
        assert catene.catena_di_turno(gara, 3) == (SD, SORT)
        assert catene.catena_di_turno(gara, 4) == (SD, SORT)

    def test_due_cambi_in_due_turni(self, db_session):
        from models.competition.services import GaraService

        gara = _gara_avviata()
        GaraService.update_gara(gara.id, catena_turno=_in_colonna((SD, SORT)))
        gara.current_round = 3
        db.session.commit()
        GaraService.update_gara(gara.id, catena_turno=_in_colonna((SORT,)))

        gara = db.session.get(Gara, gara.id)
        assert catene.catena_di_turno(gara, 2) == (D, PREC, SORT)
        assert catene.catena_di_turno(gara, 3) == (SD, SORT)
        assert catene.catena_di_turno(gara, 4) == (SORT,)

    def test_la_catena_di_gara_vale_subito(self, db_session):
        from models.competition.campi_modificabili import campi_bloccati
        from models.competition.services import GaraService

        gara = _gara_avviata()
        GaraService.update_gara(gara.id, catena_gara="[]")
        assert catene.catena_di_gara(db.session.get(Gara, gara.id)) == ()
        gara.status = GaraStatus.AWAITING_SSR.value
        db.session.commit()
        assert "catena_gara" in campi_bloccati(gara)


@pytest.mark.unit
def test_il_campionato_cambia_sistema_e_le_catene_di_default_seguono(db_session):
    from models.campionato.tournament_service import TournamentService

    campionato = Campionato(
        name=f"C {uuid.uuid4().hex[:6]}",
        default_classification_system="WINS",
        default_odd_policy="no",
        default_catena_turno=_in_colonna((D, PREC, SORT)),
        default_catena_gara=_in_colonna((D, Voce(Criterio.SPAREGGIO_SSR, 3))),
        catena_generale=_in_colonna((D, Voce(Criterio.SPAREGGIO_SSR), PREC, SORT)),
    )
    db.session.add(campionato)
    db.session.commit()
    gara = _crea(campionato_id=campionato.id, odd_number_policy="no")
    scelta = _crea(campionato_id=None, catena_gara=_testo("scontri_diretti", "ssr:2"))
    scelta.campionato_id = campionato.id
    scelta.number = 2
    scelta.odd_number_policy = "no"
    db.session.commit()

    TournamentService().update_campionato(
        campionato.id, default_classification_system="RACK"
    )

    gara = db.session.get(Gara, gara.id)
    assert json.loads(gara.catena_turno) == ["posizione_precedente", "sorteggio"]
    assert json.loads(gara.catena_gara) == ["ssr:3"]
    # La catena scelta dal direttore resta sua.
    assert json.loads(db.session.get(Gara, scelta.id).catena_gara) == [
        "scontri_diretti",
        "ssr:2",
    ]
    campionato = db.session.get(Campionato, campionato.id)
    assert json.loads(campionato.catena_generale) == [
        "ssr",
        "posizione_precedente",
        "sorteggio",
    ]


# ---------------------------------------------------------------------------
# Le parole
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLeParole:
    def test_la_storia(self, app):
        from models.storia.etichette import etichetta, valore

        with app.test_request_context():
            assert str(etichetta("catena_gara")) == (
                "Pari merito nella classifica di gara"
            )
            assert (
                valore("catena_gara", _testo("differenza_rack", "ssr:3"))
                == "Differenza triangoli → Spareggio SSR fino al 3°"
            )
            assert valore("catena_gara", "[]") == (
                "nessun criterio: i pari merito restano tali"
            )
            assert valore("catena_turno", "") == "come il campionato"
            assert valore("default_catena_gara", "") == "come l'app"

    def test_la_frase_del_regolamento(self, app):
        from models.storia.regolamento import frase_della_catena

        with app.test_request_context():
            gara = _gara_finta(catena_turno=_testo("scontri_diretti", "sorteggio"))
            assert frase_della_catena(gara, "catena_turno") == (
                "A pari vittorie conta lo scontro diretto, poi il sorteggio."
            )
            assert frase_della_catena(gara, "catena_gara") == (
                "A pari vittorie conta la differenza triangoli, poi lo "
                "spareggio SSR fino al 3° posto."
            )
            campionato = SimpleNamespace(
                default_classification_system="WINS", catena_generale=None
            )
            assert frase_della_catena(campionato, "catena_generale") == (
                "A pari vittorie conta la differenza triangoli, poi lo "
                "spareggio SSR, poi la posizione dopo la gara precedente, poi "
                "il sorteggio."
            )

    def test_nel_tabellone_niente_frase(self, app):
        from models.storia.regolamento import frase_della_catena

        with app.test_request_context():
            gara = _gara_finta(classification_system="POSITION")
            assert frase_della_catena(gara, "catena_gara") is None

    def test_l_editor(self, app):
        from models.classification.editor_catena import config_editor

        with app.test_request_context():
            cfg = config_editor("turno", None, "RACK")
            assert cfg["voci"] == ["posizione_precedente", "sorteggio"]
            assert cfg["completa"] is True
            assert "ssr" not in cfg["ammessi"]["WINS"]
            assert "rack_vinti" not in cfg["ammessi"]["RACK"]
            assert "vittorie" not in cfg["ammessi"]["WINS"]
            assert cfg["frasi"]["ssr_n"] == "lo spareggio SSR fino al {n}° posto"
            gara = config_editor("gara", None, "WINS")
            assert gara["completa"] is False and gara["ssrConPosto"] is True
            # Le parole visibili dicono «triangoli», mai «rack».
            assert all("rack" not in nome.lower() for nome in cfg["nomi"].values())
