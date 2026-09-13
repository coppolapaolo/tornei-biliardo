"""Squadre, categorie, ritiro ed eliminazione nella pagina del direttore.

Il canvas «Pagina gara del direttore» non disegnava queste quattro cose
(STATO, «Non ancora disegnato»): qui si verifica la forma scelta, la piu'
vicina alla sua grammatica.

* squadre (ADR-039) e categorie (ADR-049) sono **righe** che aprono un foglio
  `c7-sheet` con l'elenco e i comandi di prima; dopo il sorteggio la riga
  resta, bloccata, e il foglio si legge soltanto — le categorie non spariscono
  piu'. La squadra di un iscritto e' un chip che apre un foglio;
* il **ritiro** di un giocatore lo decide anche il direttore, dal menu della
  partita: stessa strada di dominio del forfait del giocatore, con i rifiuti
  della card (X, partita chiusa, turno bloccato);
* «Elimina la gara» sta in preparazione, finche' `Gara.can_be_deleted()`.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, Match, User
from models.competition.models import WithdrawPolicy
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


# ── Aiuti ───────────────────────────────────────────────────────────────────


def _utente(db_session, prefisso, role=UserRole.PLAYER.value, password="pw12345"):
    batch = uuid.uuid4().hex[:8]
    user = User(
        username=f"{prefisso}_{batch}",
        email=f"{prefisso}_{batch}@test.local",
        role=role,
        onboarding_completed=True,
    )
    user.set_password(password)
    db_session.add(user)
    db_session.commit()
    return user


def _entra(client, user, password="pw12345"):
    resp = client.post(
        "/auth/login", data={"username": user.username, "password": password}
    )
    assert resp.status_code in (200, 302)
    return client


@pytest.fixture
def admin_client(client, db_session):
    admin = _utente(db_session, "sre_admin", role=UserRole.ADMIN.value)
    return _entra(client, admin)


def _gara(db_session, status, **kw):
    gara = Gara(
        number=1,
        name=kw.pop("name", "Gara sre"),
        date=kw.pop("date", date.today() + timedelta(days=3)),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        matchmaking_strategy=kw.pop("strategy", "amalfi"),
        status=status,
        current_round=kw.pop("current_round", 0),
        rounds_count=kw.pop("rounds_count", 3),
        min_participants=2,
        **kw,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _iscrivi(db_session, gara, user, **kw):
    inscription = Inscription(gara_id=gara.id, user_id=user.id, **kw)
    db_session.add(inscription)
    db_session.commit()
    return inscription


def _partita(db_session, gara, p1, p2, *, round_number=1, status=None, **kw):
    match = Match(
        gara_id=gara.id,
        round_number=round_number,
        player1_id=p1.id,
        player2_id=p2.id if p2 else None,
        player1_score=kw.pop("player1_score", 0),
        player2_score=kw.pop("player2_score", 0),
        status=status or MatchStatus.PLAYING.value,
        **kw,
    )
    db_session.add(match)
    db_session.commit()
    return match


def _gara_in_gioco(db_session, policy=WithdrawPolicy.FORFEIT.value):
    gara = _gara(
        db_session, GaraStatus.PLAYING.value, current_round=1, withdraw_policy=policy
    )
    p1 = _utente(db_session, "sre_p1")
    p2 = _utente(db_session, "sre_p2")
    for p in (p1, p2):
        _iscrivi(db_session, gara, p)
    match = _partita(db_session, gara, p1, p2, player1_score=1)
    return gara, match, p1, p2


# ── Squadre e categorie in righe ────────────────────────────────────────────


def test_in_impostazioni_le_squadre_sono_una_riga_con_il_foglio(
    admin_client, db_session
):
    from models.squadra.service import SquadraService

    gara = _gara(db_session, GaraStatus.SETUP.value, separate_teammates=True)
    SquadraService.create(gara, "Circolo Nord")
    db_session.commit()

    html = admin_client.get(f"/admin/gara/{gara.id}/impostazioni").get_data(
        as_text=True
    )
    assert 'data-bs-target="#squadreModal"' in html
    assert 'id="squadreModal"' in html
    assert "Circolo Nord" in html
    assert f"/admin/gara/{gara.id}/squadre/create" in html
    # La forma di prima non c'e' piu'.
    assert "c7-subrow" not in html
    assert 'id="sezioneSquadre"' not in html


def test_in_preparazione_squadre_e_categorie_sono_righe_da_preparare(
    admin_client, db_session
):
    gara = _gara(
        db_session, GaraStatus.SETUP.value, separate_teammates=True, has_handicap=True
    )
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    da_preparare = html.split('id="daPreparare"', 1)[1].split("c7-nota", 1)[0]
    assert 'data-bs-target="#squadreModal"' in da_preparare
    assert 'data-bs-target="#categorieModal"' in da_preparare
    assert html.count('id="squadreModal"') == 1
    assert html.count('id="categorieModal"') == 1


def test_dopo_il_sorteggio_le_squadre_restano_bloccate_e_in_sola_lettura(
    admin_client, db_session
):
    from models.squadra.service import SquadraService

    gara = _gara(db_session, GaraStatus.INSCRIPTION.value, separate_teammates=True)
    squadra = SquadraService.create(gara, "Circolo Sud")
    db_session.commit()
    gara.status = GaraStatus.PLAYING.value
    gara.current_round = 1
    db_session.commit()

    html = admin_client.get(f"/admin/gara/{gara.id}/impostazioni").get_data(
        as_text=True
    )
    riga = html.split('data-bs-target="#squadreModal"', 1)[0].rsplit("<button", 1)[1]
    riga += html.split('data-bs-target="#squadreModal"', 1)[1].split("</button>", 1)[0]
    assert "c7-tile--locked" in riga
    assert 'id="squadreModal"' in html
    assert "Circolo Sud" in html
    # Sola lettura: nessun comando sull'elenco.
    assert f"/squadre/{squadra.id}/rename" not in html
    assert "/squadre/create" not in html
    assert "non si modifica più" in html


def test_le_categorie_restano_quando_non_si_modificano_piu(admin_client, db_session):
    from models.categoria.service import CategoriaService

    gara = _gara(db_session, GaraStatus.INSCRIPTION.value, has_handicap=True)
    giocatore = _utente(db_session, "sre_cat")
    inscription = _iscrivi(db_session, gara, giocatore)
    admin = User.query.filter(User.username.like("sre_admin_%")).first()
    CategoriaService.set_inscription_categoria_by_name(gara, inscription, "B", admin)
    db_session.commit()
    gara.status = GaraStatus.PLAYING.value
    gara.current_round = 1
    db_session.commit()

    html = admin_client.get(f"/admin/gara/{gara.id}/impostazioni").get_data(
        as_text=True
    )
    assert 'data-bs-target="#categorieModal"' in html
    assert 'id="categorieModal"' in html
    foglio = html.split('id="categorieModal"', 1)[1]
    assert ">B<" in foglio.replace("\n", "").replace("  ", "")
    assert "/categorie/" not in foglio.split("</form>")[0] or "rename" not in foglio
    assert 'class="c7-categoria-input"' not in html


def test_a_iscrizioni_aperte_la_fascia_dice_quanti_sono_senza_categoria(
    admin_client, db_session
):
    from models.categoria.service import CategoriaService

    gara = _gara(db_session, GaraStatus.INSCRIPTION.value, has_handicap=True)
    admin = User.query.filter(User.username.like("sre_admin_%")).first()
    con = _iscrivi(db_session, gara, _utente(db_session, "sre_con"))
    _iscrivi(db_session, gara, _utente(db_session, "sre_senza"))
    CategoriaService.set_inscription_categoria_by_name(gara, con, "A", admin)
    db_session.commit()

    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    fascia = html.split('class="c7-card c7-card--accent c7-fascia"', 1)[1].split(
        "</section>", 1
    )[0]
    assert "1 senza categoria" in fascia
    assert "Avvia la gara" in fascia
    riga = html.split('data-bs-target="#categorieModal"', 1)[1].split("</button>", 1)[0]
    assert "1 senza categoria" in riga


def test_la_squadra_dell_iscritto_e_un_chip_che_apre_un_foglio(
    admin_client, db_session
):
    from models.squadra.service import SquadraService

    gara = _gara(db_session, GaraStatus.INSCRIPTION.value, separate_teammates=True)
    SquadraService.create(gara, "Circolo Est")
    db_session.commit()
    _iscrivi(db_session, gara, _utente(db_session, "sre_sq"))

    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'onchange="this.form.submit()"' not in html
    assert "apriSquadraIscritto(this)" in html
    assert html.count('id="squadraIscrittoModal"') == 1


def test_la_squadra_dal_foglio_torna_alla_pagina_da_cui_si_e_partiti(
    admin_client, db_session
):
    from models.squadra.service import SquadraService

    gara = _gara(db_session, GaraStatus.INSCRIPTION.value, separate_teammates=True)
    squadra = SquadraService.create(gara, "Circolo Ovest")
    db_session.commit()
    giocatore = _utente(db_session, "sre_ovest")
    inscription = _iscrivi(db_session, gara, giocatore)

    ritorno = f"/admin/gara/{gara.id}/impostazioni#squadre"
    resp = admin_client.post(
        f"/admin/gara/{gara.id}/inscription/{inscription.id}/squadra",
        data={"squadra_id": str(squadra.id), "next": ritorno},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(ritorno)
    assert db_session.get(Inscription, inscription.id).squadra_id == squadra.id

    # Un indirizzo esterno non si segue: si torna alla gara.
    resp = admin_client.post(
        f"/admin/gara/{gara.id}/squadre/create",
        data={"name": "Circolo Esterno", "next": "https://esempio.test/"},
    )
    assert resp.headers["Location"].endswith(f"/admin/gara/{gara.id}")


def test_senza_squadra_il_messaggio_parla_del_giocatore_non_a_lui(
    admin_client, db_session
):
    gara = _gara(db_session, GaraStatus.INSCRIPTION.value, separate_teammates=True)
    giocatore = _utente(db_session, "sre_solo")
    inscription = _iscrivi(db_session, gara, giocatore)
    resp = admin_client.post(
        f"/admin/gara/{gara.id}/inscription/{inscription.id}/squadra",
        data={"squadra_id": ""},
        follow_redirects=True,
    )
    html = resp.get_data(as_text=True)
    assert "Giocherai senza squadra" not in html
    assert f"{giocatore.username} gioca senza squadra" in html


# ── Il ritiro deciso dal direttore ──────────────────────────────────────────


def test_il_ritiro_con_la_regola_a_tavolino_chiude_e_lascia_in_gara(
    admin_client, db_session
):
    gara, match, p1, p2 = _gara_in_gioco(db_session, WithdrawPolicy.FORFEIT.value)
    altra = _partita(
        db_session,
        gara,
        p1,
        _utente(db_session, "sre_p3"),
        status=MatchStatus.PENDING.value,
    )

    resp = admin_client.post(
        f"/admin/match/{match.id}/forfeit", data={"player_id": str(p1.id)}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True

    match = db_session.get(Match, match.id)
    assert MatchStatus.is_finished(match.status)
    assert match.winner_id == p2.id
    assert match.player2_score == 3
    # Le altre partite aperte si chiudono a tavolino anche loro.
    assert MatchStatus.is_finished(db_session.get(Match, altra.id).status)
    iscrizione = Inscription.query.filter_by(gara_id=gara.id, user_id=p1.id).one()
    assert iscrizione.is_forfeit is True


def test_il_ritiro_con_la_regola_di_esclusione_toglie_l_iscrizione(
    admin_client, db_session
):
    gara, match, p1, p2 = _gara_in_gioco(db_session, WithdrawPolicy.EXCLUDE.value)
    resp = admin_client.post(
        f"/admin/match/{match.id}/forfeit", data={"player_id": str(p2.id)}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert db_session.get(Match, match.id).winner_id == p1.id
    attiva = Inscription.query.filter_by(
        gara_id=gara.id, user_id=p2.id, is_withdrawn=False
    ).first()
    assert attiva is None


def test_il_ritiro_annuncia_la_partita_chiusa(admin_client, db_session, monkeypatch):
    import routes.admin.match.scoring as scoring
    import routes.sse as sse

    eventi = []
    # `scoring` lega `emit_gara_event` all'import: si sostituisce li'.
    monkeypatch.setattr(
        scoring,
        "emit_gara_event",
        lambda gid, tipo, dati: eventi.append((gid, tipo, dati)),
    )
    monkeypatch.setattr(sse, "emit_match_event", lambda mid, tipo, dati: None)
    gara, match, p1, _p2 = _gara_in_gioco(db_session)
    admin_client.post(
        f"/admin/match/{match.id}/forfeit", data={"player_id": str(p1.id)}
    )
    assert any(
        gid == gara.id and tipo == "match_completed" and dati.get("forfeit")
        for gid, tipo, dati in eventi
    )


def test_il_ritiro_e_negato_a_chi_non_dirige(client, db_session):
    _gara_, match, p1, _p2 = _gara_in_gioco(db_session)
    _entra(client, p1)
    resp = client.post(
        f"/admin/match/{match.id}/forfeit", data={"player_id": str(p1.id)}
    )
    assert resp.status_code == 403
    assert not MatchStatus.is_finished(db_session.get(Match, match.id).status)


def test_il_ritiro_non_vale_sulla_x(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.PLAYING.value, current_round=1)
    p1 = _utente(db_session, "sre_x")
    _iscrivi(db_session, gara, p1)
    x = _partita(db_session, gara, p1, None, is_bye=True)
    resp = admin_client.post(
        f"/admin/match/{x.id}/forfeit", data={"player_id": str(p1.id)}
    )
    assert resp.status_code == 400


def test_il_ritiro_non_riscrive_una_partita_chiusa(admin_client, db_session):
    for stato in (
        MatchStatus.CLOSED_UNILATERALLY.value,
        MatchStatus.CONFIRMED_BY_BOTH.value,
    ):
        gara, match, p1, p2 = _gara_in_gioco(db_session)
        match.status = stato
        match.player1_score, match.player2_score = 3, 1
        match.winner_id = p1.id
        db_session.commit()
        resp = admin_client.post(
            f"/admin/match/{match.id}/forfeit", data={"player_id": str(p1.id)}
        )
        assert resp.status_code == 409
        assert db_session.get(Match, match.id).winner_id == p1.id


def test_il_ritiro_non_tocca_un_turno_bloccato(admin_client, db_session):
    gara, match, p1, p2 = _gara_in_gioco(db_session)
    # Il turno 2 e' partito: il turno 1 non si tocca piu' (Amalfi).
    gara.current_round = 2
    _partita(db_session, gara, p2, _utente(db_session, "sre_t2"), round_number=2)
    resp = admin_client.post(
        f"/admin/match/{match.id}/forfeit", data={"player_id": str(p1.id)}
    )
    assert resp.status_code == 409
    assert not MatchStatus.is_finished(db_session.get(Match, match.id).status)


def test_il_ritiro_vuole_un_giocatore_della_partita(admin_client, db_session):
    _gara_, match, _p1, _p2 = _gara_in_gioco(db_session)
    estraneo = _utente(db_session, "sre_estraneo")
    resp = admin_client.post(
        f"/admin/match/{match.id}/forfeit", data={"player_id": str(estraneo.id)}
    )
    assert resp.status_code == 400
    resp = admin_client.post(f"/admin/match/{match.id}/forfeit", data={})
    assert resp.status_code == 400


def test_il_forfait_del_giocatore_non_riscrive_una_partita_confermata(db_session):
    """Regressione: `_validate_forfeit` guardava solo `CLOSED_UNILATERALLY`.

    Una partita chiusa con la doppia conferma dei giocatori (`validated`)
    lasciava passare il forfait, che riscriveva punteggio e vincitore.
    """
    from models.match.scoring_service import ScoringService

    _gara_, match, p1, p2 = _gara_in_gioco(db_session)
    match.status = MatchStatus.CONFIRMED_BY_BOTH.value
    match.player1_score, match.player2_score, match.winner_id = 3, 2, p1.id
    db_session.commit()
    with pytest.raises(ValueError):
        ScoringService._validate_forfeit(match, p1.id)


def test_il_menu_della_partita_propone_il_ritiro_e_il_foglio_dice_la_regola(
    admin_client, db_session
):
    gara, match, p1, p2 = _gara_in_gioco(db_session, WithdrawPolicy.EXCLUDE.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'id="menuPartitaRitiri"' in html
    assert f'data-ritiro-url="/admin/match/{match.id}/forfeit"' in html
    assert p1.username in html.split("data-ritiri=", 1)[1].split(">", 1)[0]
    foglio = html.split('id="ritiroModal"', 1)[1]
    assert "Esce dalla gara" in foglio
    assert "Resta negli abbinamenti" not in foglio


def test_la_partita_chiusa_non_propone_il_ritiro(admin_client, db_session):
    gara, match, p1, _p2 = _gara_in_gioco(db_session)
    match.status = MatchStatus.CLOSED_UNILATERALLY.value
    match.player1_score, match.winner_id = 3, p1.id
    db_session.commit()
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "data-ritiro-url" not in html


# ── Eliminare la gara ───────────────────────────────────────────────────────


def test_in_preparazione_senza_iscritti_si_puo_eliminare(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.SETUP.value)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'data-bs-target="#eliminaGaraModal"' in html
    foglio = html.split('id="eliminaGaraModal"', 1)[1].split("</form>", 1)[0]
    assert f'action="/admin/gara/{gara.id}/delete"' in foglio
    assert 'name="csrf_token"' in foglio
    assert "non si può annullare" in foglio.lower()


@pytest.mark.parametrize(
    "status", [GaraStatus.INSCRIPTION.value, GaraStatus.PLAYING.value]
)
def test_fuori_dalla_preparazione_non_si_elimina(admin_client, db_session, status):
    gara = _gara(db_session, status, current_round=1 if status == "playing" else 0)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'id="eliminaGaraModal"' not in html


def test_con_un_iscritto_non_si_elimina(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.SETUP.value)
    _iscrivi(db_session, gara, _utente(db_session, "sre_iscritto"))
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'id="eliminaGaraModal"' not in html


def test_la_prova_si_elimina_dal_suo_banner_non_dalla_riga(admin_client, db_session):
    gara = _gara(db_session, GaraStatus.SETUP.value, is_prova=True)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'id="eliminaGaraModal"' not in html


def test_eliminare_una_gara_singola_porta_alla_home(admin_client, db_session):
    from models.competition.round_configuration import RoundConfiguration
    from models.user.models import DirectorAssignment

    gara = _gara(db_session, GaraStatus.SETUP.value)
    gara_id = gara.id
    db_session.add(RoundConfiguration(gara_id=gara_id, round_number=2, distance=5))
    co = _utente(db_session, "sre_codir", role=UserRole.DIRECTOR.value)
    db_session.add(
        DirectorAssignment(
            entity_type="gara", entity_id=gara_id, user_id=co.id, assigned_by_id=co.id
        )
    )
    db_session.commit()

    resp = admin_client.post(f"/admin/gara/{gara_id}/delete")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")
    db_session.expire_all()
    assert db_session.get(Gara, gara_id) is None


def test_eliminare_una_gara_del_campionato_porta_al_campionato(
    admin_client, db_session
):
    from models import Campionato

    campionato = Campionato(name="Campionato sre", planned_gare_count=4)
    db_session.add(campionato)
    db_session.commit()
    gara = _gara(db_session, GaraStatus.SETUP.value, campionato_id=campionato.id)
    resp = admin_client.post(f"/admin/gara/{gara.id}/delete")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/admin/campionato/{campionato.id}")
