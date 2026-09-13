"""La pagina della gara per chi la dirige: la striscia di fase e la fascia.

Canvas «Pagina gara del direttore» (docs/redesign-7c/canvas-gara-direttore/,
approvato il 13/09/2026), decisione 2: niente linguette per il direttore,
una striscia mostra il ciclo della gara e la pagina e' la fase in corso. Chi
non dirige continua a vedere la pagina a linguette.

Qui si verifica la scelta del template dal permesso, la striscia per ogni
stato persistito, la tacca dello spareggio solo dove serve, la fascia con il
comando giusto, la pagina «Impostazioni gara» e il menu del turno.
"""

from __future__ import annotations

from datetime import date

import pytest

from models import Gara, Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user("fasi_admin", "fasi_admin@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "fasi_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def _gara(db_session, status, *, strategy="amalfi", rounds_count=3, current_round=0):
    gara = Gara(
        number=1,
        name="Gara a fasi",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        matchmaking_strategy=strategy,
        status=status,
        current_round=current_round,
        rounds_count=rounds_count,
        min_participants=4,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _match(db_session, gara, p1_score, p2_score, status, suffix=""):
    from models.user.services import UserService

    p1 = UserService.create_user(
        f"fasi_p1{suffix}", f"fasi_p1{suffix}@test.local", "pw12345"
    )
    p2 = UserService.create_user(
        f"fasi_p2{suffix}", f"fasi_p2{suffix}@test.local", "pw12345"
    )
    match = Match(
        gara_id=gara.id,
        round_number=gara.current_round,
        player1_id=p1.id,
        player2_id=p2.id,
        player1_score=p1_score,
        player2_score=p2_score,
        status=status,
    )
    if status == MatchStatus.CLOSED_UNILATERALLY.value:
        match.winner_id = p1.id if p1_score > p2_score else p2.id
    db_session.add(match)
    db_session.commit()
    return match


def _tacche(html: str) -> list[str]:
    """Le tacche della striscia, nell'ordine, dal loro stato."""
    import re

    return re.findall(
        r'c7-fasi__tacca--(fatta|attiva|da_fare)"\s+title="([^"]+)"', html
    )


# ── La scelta del template ────────────────────────────────────────────────────


def test_chi_dirige_vede_la_striscia_e_non_le_linguette(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.SETUP.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'class="c7-fasi"' in html
    assert "c7-vtabs" not in html
    assert 'id="garaDirettore"' in html


def test_chi_guarda_vede_le_linguette_e_non_la_striscia(client, db_session):
    from models.user.services import UserService

    UserService.create_user("fasi_player", "fasi_player@test.local", "pw12345")
    db_session.commit()
    client.post("/auth/login", data={"username": "fasi_player", "password": "pw12345"})
    gara = _gara(db_session, GaraStatus.PLAYING.value, current_round=1)
    _match(db_session, gara, 2, 1, MatchStatus.PLAYING.value)

    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'class="c7-fasi"' not in html
    assert 'id="garaDirettore"' not in html
    assert "c7-fascia" not in html
    # Niente comandi del direttore nella pagina di chi guarda.
    assert "apriMenuPartita" not in html
    assert 'id="menuTurnoModal"' not in html


# ── La striscia ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status, attiva",
    [
        (GaraStatus.SETUP.value, "Preparazione"),
        (GaraStatus.INSCRIPTION.value, "Iscrizioni"),
        (GaraStatus.COMPLETED.value, "Chiusura"),
    ],
)
def test_la_tacca_attiva_segue_lo_stato(admin_client, db_session, status, attiva):
    gara = _gara(db_session, status)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    tacche = _tacche(html)
    assert [t for s, t in tacche if s == "attiva"] == [attiva]
    # Senza spareggio la striscia ha quattro tacche.
    assert [t for _, t in tacche] == [
        "Preparazione",
        "Iscrizioni",
        "In gioco",
        "Chiusura",
    ]


def test_in_gioco_le_fasi_prima_sono_fatte(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.PLAYING.value, current_round=1)
    _match(db_session, gara, 2, 1, MatchStatus.PLAYING.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert _tacche(html) == [
        ("fatta", "Preparazione"),
        ("fatta", "Iscrizioni"),
        ("attiva", "In gioco"),
        ("da_fare", "Chiusura"),
    ]


def test_nello_spareggio_la_striscia_ha_la_sua_tacca(admin_client, db_session):
    gara = _gara(
        db_session, GaraStatus.AWAITING_SSR.value, rounds_count=1, current_round=1
    )
    _match(db_session, gara, 5, 3, MatchStatus.CLOSED_UNILATERALLY.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert [t for _, t in _tacche(html)] == [
        "Preparazione",
        "Iscrizioni",
        "In gioco",
        "Spareggio",
        "Chiusura",
    ]
    assert ("attiva", "Spareggio") in _tacche(html)


# ── La fascia ─────────────────────────────────────────────────────────────────


def test_in_preparazione_la_fascia_apre_le_iscrizioni(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.SETUP.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "Nessuno vede ancora la gara" in html
    assert 'data-bs-target="#openInscriptionsModal"' in html
    assert "Da preparare" in html


def test_a_iscrizioni_aperte_l_avvio_e_spento_finche_manca_il_minimo(
    admin_client, db_session
):
    gara = _gara(db_session, GaraStatus.INSCRIPTION.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "Iscrizioni aperte" in html
    assert "Mancano 4 iscritti" in html
    # Il pulsante c'e', spento: il direttore deve sapere che la gara aspetta lui.
    assert "startFirstRound(" in html
    assert "disabled" in html.split("startFirstRound(")[1].split(">")[0]


def test_a_gara_conclusa_la_fascia_dice_chi_ha_vinto(admin_client, db_session):
    gara = _gara(
        db_session, GaraStatus.COMPLETED.value, rounds_count=1, current_round=1
    )
    m = _match(db_session, gara, 5, 3, MatchStatus.CLOSED_UNILATERALLY.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "Gara conclusa" in html
    assert f"Ha vinto {m.player1.username}" in html
    assert "Resta bloccato" in html
    # Niente comandi di gioco a gara conclusa.
    assert "Termina la gara" not in html
    assert 'id="menuTurnoModal"' not in html


# ── Il menu del turno ─────────────────────────────────────────────────────────


def test_il_menu_del_turno_annulla_l_avvio_solo_senza_triangoli(
    admin_client, db_session
):
    gara = _gara(db_session, GaraStatus.PLAYING.value, current_round=1)
    _match(db_session, gara, 0, 0, MatchStatus.PENDING.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'id="menuTurnoModal"' in html
    assert "apriMenuTurno()" in html
    assert "Annulla l'avvio del turno 1" in html
    assert "Non si può più" not in html


def test_il_menu_del_turno_dice_perche_non_si_annulla_piu(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.PLAYING.value, current_round=1)
    _match(db_session, gara, 2, 1, MatchStatus.PLAYING.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'id="menuTurnoModal"' in html
    assert "Non si può più" in html


def test_la_card_della_partita_porta_il_suo_menu(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.PLAYING.value, current_round=1)
    m = _match(db_session, gara, 2, 1, MatchStatus.PLAYING.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'id="menuPartitaModal"' in html
    assert f'data-match-id="{m.id}"' in html
    assert 'data-has-scores="1"' in html


# ── Impostazioni gara ─────────────────────────────────────────────────────────


def test_impostazioni_gara_per_chi_dirige(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.PLAYING.value, current_round=1)
    resp = admin_client.get(f"/admin/gara/{gara.id}/impostazioni")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Si modifica anche adesso" in html
    assert "Direzione di gara" in html
    assert "Fissato all'avvio" in html
    assert 'id="sezioneTavoli"' in html


def test_impostazioni_gara_in_preparazione_rimanda_ai_turni(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.SETUP.value)
    html = admin_client.get(f"/admin/gara/{gara.id}/impostazioni").get_data(
        as_text=True
    )
    assert "Fissato all'avvio" not in html
    assert "#sezioneTurni" in html


def test_impostazioni_gara_negate_a_chi_non_dirige(client, db_session):
    from models.user.services import UserService

    UserService.create_user("fasi_player2", "fasi_player2@test.local", "pw12345")
    db_session.commit()
    client.post("/auth/login", data={"username": "fasi_player2", "password": "pw12345"})
    gara = _gara(db_session, GaraStatus.SETUP.value)
    assert client.get(f"/admin/gara/{gara.id}/impostazioni").status_code in (302, 403)


def test_la_pagina_del_direttore_porta_alle_impostazioni(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.SETUP.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert f"/admin/gara/{gara.id}/impostazioni" in html


# ── Rilievi della revisione automatica (PR #343) ──────────────────────────────


def test_il_menu_del_turno_segue_il_turno_che_si_vede_con_i_turni_pregenerati(
    admin_client, db_session
):
    """Nella formula casuale i turni nascono tutti insieme: chiuso il turno 1,
    `current_round` resta 1 mentre si gioca il 2. Il menu sta accanto al
    turno che si vede, e l'annullamento e' quello dell'avvio della gara."""
    gara = _gara(
        db_session, GaraStatus.PLAYING.value, strategy="random", current_round=1
    )
    _match(db_session, gara, 5, 3, MatchStatus.CLOSED_UNILATERALLY.value, suffix="r1")
    gara.current_round = 2
    m2 = _match(db_session, gara, 0, 0, MatchStatus.PENDING.value, suffix="r2")
    gara.current_round = 1
    db_session.commit()
    assert m2.round_number == 2

    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'id="menuTurnoModal"' in html
    assert "apriMenuTurno()" in html
    # Il foglio e' del turno 2 (quello in gioco), e propone l'annullamento
    # della gara — spento, perche' il turno 1 ha gia' dei triangoli.
    assert ">Turno 2</h3>" in html
    assert (
        "Annulla l&#39;avvio della gara" in html or "Annulla l'avvio della gara" in html
    )
    assert "Non si può più" in html


def test_a_gara_conclusa_il_vincitore_c_e_anche_con_le_partite_confermate_dai_due(
    admin_client, db_session
):
    """Nella formula casuale la classifica si calcola sulle partite finite:
    confermata dai due giocatori (`CONFIRMED_BY_BOTH`) e' finita quanto
    chiusa dal direttore."""
    gara = _gara(
        db_session,
        GaraStatus.COMPLETED.value,
        strategy="random",
        rounds_count=1,
        current_round=1,
    )
    m = _match(db_session, gara, 5, 3, MatchStatus.CONFIRMED_BY_BOTH.value)
    m.winner_id = m.player1_id
    db_session.commit()

    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert f"Ha vinto {m.player1.username}" in html


# ── Fase 2, le iscrizioni (canvas 2.1–2.6) ────────────────────────────────────


def test_il_campo_per_iscrivere_sta_in_cima_e_i_candidati_sono_righe(
    admin_client, db_session
):
    """2.2: si scrive in cima, i candidati compaiono sotto con «Iscrivi» sulla
    riga; niente tendina."""
    from models.user.services import UserService

    UserService.create_user("fasi_cand", "fasi_cand@test.local", "pw12345")
    db_session.commit()
    gara = _gara(db_session, GaraStatus.INSCRIPTION.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "data-iscrivibili" in html
    assert 'js-iscrivibile"' in html
    assert 'name="user_id"' in html
    assert "<select" not in html.split("data-iscrivibili")[1].split("c7-sechead")[0]
    # Il campo precede l'elenco.
    assert html.index("data-iscrivibili") < html.index("c7-sechead")


def test_a_iscrizioni_scadute_senza_il_minimo_la_fascia_propone_di_estendere(
    admin_client, db_session
):
    """2.4: lo stato e' derivato dalla scadenza, non persistito."""
    from datetime import timedelta

    from models.base import utc_now

    gara = _gara(db_session, GaraStatus.INSCRIPTION.value)
    gara.inscription_start = utc_now() - timedelta(days=3)
    gara.inscription_end = utc_now() - timedelta(hours=1)
    db_session.commit()
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "Iscrizioni scadute" in html
    assert "Estendi le iscrizioni" in html
    assert "Annulla la gara" in html
    assert (
        "startFirstRound("
        not in html.split("c7-fascia__azione")[1].split("</section>")[0]
    )


def test_il_foglio_di_avvio_dice_i_tavoli_nell_ordine_scelto(admin_client, db_session):
    """2.5: prima di avviare si legge cosa succede, tavoli compresi."""
    import json

    gara = _gara(db_session, GaraStatus.INSCRIPTION.value)
    gara.available_tables = json.dumps(["3", "1", "2"])
    db_session.commit()
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    foglio = html.split('id="avviaGaraModal"')[1].split("</form>")[0]
    assert "Tavoli 3, 1, 2" in foglio
    assert "in quest’ordine" in foglio
    assert "Il turno 1 si sorteggia adesso" in foglio
    assert "Da qui le iscrizioni si chiudono" in foglio


# ── Fase 3, il gioco (canvas 3C, 3.2–3.4, 3.7) ────────────────────────────────


def _gara_in_gioco(db_session, *, distance=5):
    """Una gara al turno 1, con due tavoli."""
    gara = _gara(db_session, GaraStatus.PLAYING.value, current_round=1)
    gara.distance = distance
    gara.available_tables = '["1", "2"]'
    db_session.commit()
    return gara


def test_la_card_in_corso_ha_gli_stepper_con_la_distanza_del_turno(
    admin_client, db_session
):
    """ADR-027: il + si spegne alla distanza del **turno**, non della gara.

    La distanza del turno la porta `match.match_distance`, scritta alla
    creazione del turno dall'override di `RoundConfiguration`.
    """
    gara = _gara_in_gioco(db_session, distance=5)
    match = _match(db_session, gara, 1, 0, MatchStatus.PLAYING.value, suffix="_st")
    match.table_assignment = "1"
    match.match_distance = 3
    db_session.commit()
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    card = html.split(f'id="partita{match.id}"')[1].split("</article>")[0]
    assert 'data-max="3"' in card
    assert "passoPunteggio(this, 1)" in card
    assert "si vince a 3" in card
    assert "Inserisci risultato" not in html


def test_la_partita_alla_distanza_senza_doppia_conferma_e_da_validare(
    admin_client, db_session
):
    gara = _gara_in_gioco(db_session, distance=5)
    match = _match(db_session, gara, 5, 1, MatchStatus.PLAYING.value, suffix="_dv")
    match.table_assignment = "1"
    db_session.commit()
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    card = html.split(f'id="partita{match.id}"')[1].split("</article>")[0]
    assert 'data-stato="da_validare"' in card
    assert "Valida il risultato" in card
    assert "correggilo con − e + prima di validare" in card


def test_la_partita_conclusa_e_in_sola_lettura_con_correggi(admin_client, db_session):
    gara = _gara_in_gioco(db_session, distance=5)
    match = _match(
        db_session, gara, 5, 2, MatchStatus.CLOSED_UNILATERALLY.value, suffix="_cc"
    )
    altra = _match(db_session, gara, 1, 1, MatchStatus.PLAYING.value, suffix="_cc2")
    altra.table_assignment = "2"
    db_session.commit()
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    card = html.split(f'id="partita{match.id}"')[1].split("</article>")[0]
    assert 'data-stato="conclusa"' in card
    assert "passoPunteggio" not in card
    assert "apriCorrezione(this)" in card
    assert "fa-crown" in card
    assert 'id="correggiRisultatoModal"' in html


def test_a_turno_concluso_le_partite_sono_righe_da_toccare(admin_client, db_session):
    """3.7: solo «Avvia il turno 2»; le partite del turno sono righe."""
    gara = _gara_in_gioco(db_session, distance=5)
    match = _match(
        db_session, gara, 5, 2, MatchStatus.CLOSED_UNILATERALLY.value, suffix="_tc"
    )
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "Puoi avviare il turno 2" in html
    assert f'id="partita{match.id}"' not in html
    assert "c7-riga-partita" in html
    assert "si tocca la sua riga" in html


def test_il_punteggio_dalla_card_salva_e_alla_distanza_chiude(admin_client, db_session):
    """L'endpoint degli stepper: JSON, rifiuta l'eccesso, alla distanza chiude."""
    gara = _gara_in_gioco(db_session, distance=5)
    match = _match(db_session, gara, 3, 1, MatchStatus.PLAYING.value, suffix="_ep")
    match.table_assignment = "1"
    db_session.commit()
    url = f"/admin/match/{match.id}/punteggio"

    r = admin_client.post(url, data={"player1_score": 9, "player2_score": 1})
    assert r.status_code == 400
    assert r.get_json()["success"] is False

    r = admin_client.post(url, data={"player1_score": 4, "player2_score": 1})
    assert r.status_code == 200
    assert r.get_json()["finished"] is False
    assert r.get_json()["player1_score"] == 4

    r = admin_client.post(url, data={"player1_score": 5, "player2_score": 1})
    assert r.get_json()["finished"] is True
    riletta = db_session.get(Match, match.id)
    assert MatchStatus.is_finished(riletta.status)
    assert riletta.winner_id == match.player1_id


def test_il_punteggio_dalla_card_non_riscrive_una_partita_chiusa(
    admin_client, db_session
):
    """Rilievo della revisione automatica sulla PR #349: una partita chiusa si
    cambia solo con la correzione, che ne lascia traccia (issue #90)."""
    gara = _gara_in_gioco(db_session, distance=5)
    match = _match(
        db_session, gara, 5, 2, MatchStatus.CLOSED_UNILATERALLY.value, suffix="_ch"
    )
    r = admin_client.post(
        f"/admin/match/{match.id}/punteggio",
        data={"player1_score": 2, "player2_score": 5},
    )
    assert r.status_code == 409
    riletta = db_session.get(Match, match.id)
    assert (riletta.player1_score, riletta.player2_score) == (5, 2)
    assert not riletta.corrections


def test_il_multi_set_non_passa_dalla_card_degli_stepper(admin_client, db_session):
    """Rilievo della revisione automatica sulla PR #349: gli stepper ragionano
    su un set solo, il multi-set ha il suo segnapunti."""
    gara = _gara_in_gioco(db_session, distance=5)
    match = _match(db_session, gara, 1, 0, MatchStatus.PLAYING.value, suffix="_ms")
    match.table_assignment = "1"
    match.is_multi_set = True
    db_session.commit()
    r = admin_client.post(
        f"/admin/match/{match.id}/punteggio",
        data={"player1_score": 2, "player2_score": 0},
    )
    assert r.status_code == 400
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert f'id="partita{match.id}"' not in html


def test_la_correzione_dalla_pagina_della_gara_torna_alla_gara(
    admin_client, db_session
):
    gara = _gara_in_gioco(db_session, distance=5)
    match = _match(
        db_session, gara, 5, 2, MatchStatus.CLOSED_UNILATERALLY.value, suffix="_cx"
    )
    r = admin_client.post(
        f"/admin/match/{match.id}/correct",
        data={
            "player1_score": 2,
            "player2_score": 5,
            "note": "invertito",
            "next": f"/admin/gara/{gara.id}",
        },
    )
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/admin/gara/{gara.id}")
    riletta = db_session.get(Match, match.id)
    assert (riletta.player1_score, riletta.player2_score) == (2, 5)
    assert riletta.corrections

    # Un `next` esterno non si segue.
    r = admin_client.post(
        f"/admin/match/{match.id}/correct",
        data={
            "player1_score": 5,
            "player2_score": 2,
            "next": "https://altrove.example",
        },
    )
    assert "altrove" not in r.headers["Location"]
