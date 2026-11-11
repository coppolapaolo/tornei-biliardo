"""Sul tabellone la capienza è obbligatoria e l'anti-reincontro non esiste.

Due rilievi sulla stessa famiglia di formati, eliminazione diretta e doppio KO.

**Capienza (#238).** Il massimo iscritti dichiara quanti posti ha il tabellone,
e da lì si ricavano i turni. Senza, la gara si creava lo stesso e l'errore
arrivava più avanti parlando di turni — un campo che sul tabellone non si
chiede nemmeno. Il server ora lo rifiuta sul campo giusto: è la difesa che vale
per tutti i moduli, per il JavaScript spento e per una scheda rimasta aperta.

**Anti-reincontro (#236).** Nell'eliminazione diretta il reincontro non può
capitare, nel doppio KO è previsto dal formato: in entrambi la domanda non si
pone. I moduli nascondono la casella, ma nascosta resta spuntata e il browser
la invia: il campionato a tabellone salvava «anti-reincontro attivo», e la sua
scheda lo mostrava. Nascondere non è imporre: lo impone il parser.
"""

import pytest
from werkzeug.datastructures import MultiDict

from models.competition.services import GaraService
from models.matchmaking.configuration import MatchmakingStrategy
from routes.admin.campionato_form_parser import CampionatoFormParser

pytestmark = pytest.mark.unit

TABELLONI = [
    MatchmakingStrategy.DIRECT_ELIMINATION.value,
    MatchmakingStrategy.DOUBLE_KNOCKOUT.value,
]


def _gara(**campi):
    dati = {"name": "Gara", "discipline": "8_ball", "distance": 5}
    dati.update(campi)
    return dati


@pytest.mark.parametrize("strategia", TABELLONI)
@pytest.mark.parametrize("vuoto", [None, ""])
def test_sul_tabellone_il_massimo_iscritti_e_obbligatorio(strategia, vuoto):
    errori = GaraService.validate_gara_data(
        _gara(matchmaking_strategy=strategia, max_participants=vuoto)
    )

    assert "max_participants" in errori
    assert "turni" not in errori["max_participants"].lower()


@pytest.mark.parametrize("strategia", TABELLONI)
def test_sul_tabellone_con_la_capienza_non_c_e_errore(strategia):
    errori = GaraService.validate_gara_data(
        _gara(matchmaking_strategy=strategia, max_participants=16)
    )

    assert "max_participants" not in errori


@pytest.mark.parametrize(
    "strategia",
    [MatchmakingStrategy.AMALFI.value, MatchmakingStrategy.RANDOM.value, None],
)
def test_fuori_dal_tabellone_il_massimo_resta_facoltativo(strategia):
    errori = GaraService.validate_gara_data(_gara(matchmaking_strategy=strategia))

    assert "max_participants" not in errori


@pytest.mark.parametrize("strategia", TABELLONI)
def test_il_campionato_a_tabellone_non_salva_l_anti_reincontro(strategia):
    """La casella nascosta arriva spuntata: il parser la ignora."""
    modulo = MultiDict({"campionato_type": strategia, "default_anti_rematch": "on"})

    assert (
        CampionatoFormParser.parse_default_settings(modulo)["default_anti_rematch"]
        is False
    )
    assert (
        CampionatoFormParser.parse_configurazione(modulo, strategia)[
            "default_anti_rematch"
        ]
        is False
    )


def test_il_campionato_amalfi_tiene_l_anti_reincontro_scelto():
    modulo = MultiDict(
        {
            "campionato_type": MatchmakingStrategy.AMALFI.value,
            "default_anti_rematch": "on",
        }
    )

    assert (
        CampionatoFormParser.parse_default_settings(modulo)["default_anti_rematch"]
        is True
    )


# ── I moduli: forma dei template ─────────────────────────────────────────────


def _template(percorso: str) -> str:
    from pathlib import Path

    radice = Path(__file__).resolve().parents[3]
    return (radice / "templates" / percorso).read_text(encoding="utf-8")


def test_nel_modale_del_campionato_la_capienza_e_obbligatoria_sul_tabellone():
    """Nel modale la strategia la eredita il campionato: decide il template."""
    html = _template("components/_new_gara_modal.html")
    campo = html[html.index('name="max_participants"') :]
    campo = campo[: campo.index(">")]

    assert "{% if modal_is_bracket %}required{% else %}placeholder=" in campo


def test_la_scheda_del_campionato_a_tabellone_tace_sull_anti_reincontro():
    html = _template("components/_campionato_details_info.html")

    assert (
        "campionato.default_anti_rematch is not none and "
        "campionato.campionato_type not in bracket_minimum_players" in html
    )


def test_il_riepilogo_della_creazione_non_legge_la_casella_nascosta():
    html = _template("admin/gara_create_standalone.html")

    # `d-none`, non l'attributo `hidden`: `.badge` ha un `display` suo nel
    # tema 7c e lo vince, lasciando la pillola in vista.
    assert "summaryAntiRematch.classList.toggle('d-none', sulTabellone);" in html
    assert "summaryAntiRematch.hidden" not in html


@pytest.mark.parametrize(
    "percorso",
    ["admin/gara_create_standalone.html", "components/_gara_edit_form.html"],
)
def test_dove_la_strategia_si_sceglie_l_obbligo_si_vede(percorso):
    """Il campo bloccava già il passo, ma senza asterisco e senza dire perché.

    L'asterisco è nel template, spento; lo accende `bracket_options.js`
    quando la strategia è a tabellone.
    """
    assert "data-capienza-obbligatoria hidden" in _template(percorso)

    from pathlib import Path

    radice = Path(__file__).resolve().parents[3]
    script = (radice / "static/js/bracket_options.js").read_text(encoding="utf-8")
    assert "[data-capienza-obbligatoria]" in script
    assert "segno.hidden = !isBracket" in script


def test_il_wizard_dice_perche_il_passo_non_avanza():
    html = _template("admin/gara_create_standalone.html")
    campo = html[html.index('name="max_participants"') :]

    assert '<div class="invalid-feedback">' in campo[:400]
