"""Parole e formati trovati guardando le schermate della guida (ottobre 2026).

Quattro difetti dello stesso genere — un testo giusto in una lingua o in un
punto e sbagliato altrove:

1. **i giri del trio**: la card diceva «Trio · 2 gironi», con la stessa parola
   dei gironi multipli della gara («2 groups» in inglese). Il trio ripete le
   sue tre sfide a **giri**, come già diceva la guida («Due giri: le stesse tre
   sfide ripetute»);
2. **l'ordinale inglese**: «%(pos)s° girone» tradotto «(%(pos)s in group …)»
   dava «(1 in group B)». Il segno della posizione lo mette il filtro
   `ordinale`, nella lingua di chi legge;
3. **gli orari della partita**: il riquadro «Tempi Partita» rimetteva nei
   campi l'ora UTC grezza, e salvava come UTC l'ora che il direttore digitava
   nella sua (ADR-043);
4. **le quote**: «€30.00» in un posto e «30 €» in un altro. Una sola
   formattazione, `importo_quota`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from babel.messages.pofile import read_po
from flask_babel import refresh

from utils.ordinale import ordinale

pytestmark = pytest.mark.unit

RADICE = Path(__file__).resolve().parents[3]
TEMPLATES = RADICE / "templates"
ROMA = ZoneInfo("Europe/Rome")


@pytest.fixture(autouse=True)
def _lingua_non_resta_appesa(app):
    """Babel tiene la lingua sul contesto dell'app, che la suite lascia aperto:
    senza ripulire, l'inglese di un test passerebbe ai successivi."""
    yield
    with app.test_request_context("/"):
        refresh()


def _catalogo_inglese():
    with open(RADICE / "translations/en/LC_MESSAGES/messages.po", "rb") as f:
        return read_po(f)


def _traduzione(catalogo, msgid: str) -> str:
    messaggio = catalogo.get(msgid)
    assert messaggio is not None, f"manca nel catalogo: {msgid!r}"
    stringa = messaggio.string
    return stringa if isinstance(stringa, str) else stringa[0]


def _template(relativo: str) -> str:
    return (TEMPLATES / relativo).read_text(encoding="utf-8")


# ── 1. I giri del trio ───────────────────────────────────────────────────


TEMPLATE_DEL_TRIO = (
    "direttore/_card_partita.html",
    "direttore/_modali_gioco.html",
    "components/_unified_match_score.html",
    "components/_trio_rack_input.html",
)


@pytest.mark.parametrize("relativo", TEMPLATE_DEL_TRIO)
def test_il_trio_non_parla_di_gironi(relativo):
    """«Gironi» è la fase a gironi della gara: il trio si gioca a giri."""
    testo = _template(relativo)
    tradotti = re.findall(r"_\((['\"])(.*?)\1", testo)
    con_gironi = [s for _, s in tradotti if re.search(r"giron[ei]", s)]
    assert con_gironi == []


def test_la_scheda_del_trio_conta_i_giri():
    from models.competition.direttore_view import scheda_trio
    from models.match.trio_config import TrioConfig

    giocatori = [SimpleNamespace(username=n) for n in ("Anna", "Bruno", "Carla")]
    trio = SimpleNamespace(
        id=7,
        trio_config=TrioConfig(distance=4),
        player_racks_list=[0, 0, 0],
        player_ids=[11, 12, 13],
        player1=giocatori[0],
        player2=giocatori[1],
        player3=giocatori[2],
        winner_id=None,
    )
    partita = SimpleNamespace(is_trio=True, trio_match=trio)
    scheda = scheda_trio(partita)
    assert scheda is not None and scheda.giri == 2


def test_in_inglese_i_giri_del_trio_sono_laps():
    """Come nella guida inglese: «Two laps: the same three contests repeated»."""
    catalogo = _catalogo_inglese()
    assert "laps" in _traduzione(catalogo, "Trio · %(num)s giri")
    assert "lap" in _traduzione(catalogo, "Trio · un giro")


# ── 2. L'ordinale nella lingua di chi legge ─────────────────────────────


@pytest.mark.parametrize(
    "numero, atteso",
    [
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (22, "22nd"),
        (23, "23rd"),
        (101, "101st"),
        (111, "111th"),
    ],
)
def test_ordinale_inglese(numero, atteso):
    assert ordinale(numero, "en") == atteso


def test_ordinale_italiano():
    assert ordinale(1, "it") == "1°"
    assert ordinale("9", "it") == "9°"


def test_ordinale_di_un_valore_non_numerico_lo_lascia_com_e():
    assert ordinale("—", "en") == "—"


#: I template che stampano una posizione nel girone o il posto di una finale
#: per piazzamento: lì il segno lo mette `|ordinale`, non il testo tradotto.
TEMPLATE_CON_POSIZIONI = (
    "components/_classification_mobile.html",
    "components/_detailed_classification.html",
    "direttore/_classifica.html",
    "public/schermo_sala.html",
    "components/_taglio.html",
    "components/_tabellone_macros.html",
    "components/_tessera_gara.html",
)


@pytest.mark.parametrize("relativo", TEMPLATE_CON_POSIZIONI)
def test_nessun_segno_di_posizione_dentro_un_testo_tradotto(relativo):
    """Un «%(pos)s°» nel catalogo diventa in inglese un numero nudo."""
    testo = _template(relativo)
    tradotti = re.findall(r"_\((['\"])(.*?)\1", testo)
    con_segno = [s for _, s in tradotti if re.search(r"%\(\w+\)s[°º]", s)]
    assert con_segno == []


def test_in_inglese_la_posizione_nel_girone_ha_il_suo_ordinale():
    catalogo = _catalogo_inglese()
    assert _traduzione(catalogo, "%(pos)s girone %(nome)s") == (
        "%(pos)s in group %(nome)s"
    )
    finale = _traduzione(
        catalogo,
        "finale %(primo)s/%(secondo)s posto con %(nome)s (%(pos)s girone %(girone)s)",
    )
    assert "(%(pos)s in group %(girone)s)" in finale


def test_la_posizione_nel_girone_resa_in_inglese(app):
    """La pagina inglese dice «1st in group B», non «1 in group B»."""
    from flask import render_template_string

    with app.test_request_context("/"):
        from flask import session

        session["language"] = "en"

        refresh()
        resa = render_template_string(
            "{{ _('%(pos)s girone %(nome)s', pos=1|ordinale, nome='B') }}"
        )
    assert resa == "1st in group B"


# ── 3. Gli orari della partita nel fuso di chi legge ────────────────────


def test_l_ora_digitata_si_salva_in_utc():
    """Il direttore a Roma scrive 03:51 in ottobre (UTC+2): sul DB va 01:51."""
    from models.match.match_service import orari_della_partita

    inizio, fine = orari_della_partita(
        data_gara=date(2026, 10, 12),
        ora_gara=time(1, 0),
        inizio="03:51",
        fine="04:30",
        inizio_attuale=None,
        tz=ROMA,
    )
    assert inizio == datetime(2026, 10, 12, 1, 51)
    assert fine == datetime(2026, 10, 12, 2, 30)


def test_l_ora_di_fine_prima_dell_inizio_passa_al_giorno_dopo():
    from models.match.match_service import orari_della_partita

    inizio, fine = orari_della_partita(
        data_gara=date(2026, 10, 12),
        ora_gara=time(20, 0),
        inizio="23:30",
        fine="00:40",
        inizio_attuale=None,
        tz=ROMA,
    )
    assert inizio == datetime(2026, 10, 12, 21, 30)
    assert fine == datetime(2026, 10, 12, 22, 40)


def test_la_sola_fine_si_confronta_con_l_inizio_nell_ora_locale():
    """L'inizio salvato è UTC: il confronto con la fine digitata va fatto
    nell'ora di chi scrive, altrimenti alle 01:30 locali (23:30 UTC del
    giorno prima) la fine finirebbe sul giorno sbagliato."""
    from models.match.match_service import orari_della_partita

    inizio, fine = orari_della_partita(
        data_gara=date(2026, 10, 12),
        ora_gara=time(20, 0),
        inizio=None,
        fine="01:45",
        inizio_attuale=datetime(2026, 10, 12, 23, 30),  # 01:30 del 13 a Roma
        tz=ROMA,
    )
    assert inizio is None
    assert fine == datetime(2026, 10, 12, 23, 45)


@pytest.mark.parametrize(
    "relativo",
    (
        "components/_match_admin_controls.html",
        "components/_match_card.html",
        "components/_match_result_row.html",
    ),
)
def test_gli_orari_della_partita_non_si_stampano_in_utc(relativo):
    """`started_at`/`ended_at` sono UTC: in pagina passano da `|time_local`."""
    assert not re.search(r"(started|ended)_at\.strftime", _template(relativo))


# ── 4. Una sola formattazione delle quote ───────────────────────────────


def test_importo_quota_in_italiano(app):
    from flask import session

    from models.categoria.listino import importo_quota

    with app.test_request_context("/"):
        session["language"] = "it"
        refresh()
        assert importo_quota(30) == "30 €"
        assert importo_quota(12.5) == "12.5 €"


def test_importo_quota_in_inglese(app):
    from flask import session

    from models.categoria.listino import importo_quota

    with app.test_request_context("/"):
        session["language"] = "en"
        refresh()
        assert importo_quota(30) == "€30"


def test_nessun_template_formatta_le_quote_a_mano():
    """«€{{ "%.2f"|format(...) }}» e «€{{ x.entry_fee }}» sono la seconda
    formattazione: le quote passano da `importo_quota`."""
    colpevoli = []
    for percorso in TEMPLATES.rglob("*.html"):
        testo = percorso.read_text(encoding="utf-8")
        if re.search(r"€\{\{", testo) or re.search(
            r"%\.2f\"\|format\([^)]*(fee|quota)", testo
        ):
            colpevoli.append(str(percorso.relative_to(TEMPLATES)))
    assert colpevoli == []


def test_la_cattura_della_guida_avvia_il_browser_con_le_24_ore():
    """Il campo orario lo formatta il browser con la sua lingua di avvio: lo
    headless shell senza `--lang` scrive «01:51 AM» anche nella guida
    italiana."""
    testo = (RADICE / "scripts/help_docs/capture_screenshots.py").read_text(
        encoding="utf-8"
    )
    assert '_ARGOMENTI_DEL_BROWSER = ["--lang=en-GB"]' in testo
    assert testo.count("args=_ARGOMENTI_DEL_BROWSER") == 2
