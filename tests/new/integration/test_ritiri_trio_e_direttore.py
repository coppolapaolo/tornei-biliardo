"""Il ritiro vale uguale su ogni strada: trio, giocatore, direttore.

Tre decisioni del 2026-09-13:

* **il ritiro nel trio applica la regola della gara sui ritiri**, come quello
  in una partita a due: chi si ritira resta negli abbinamenti perdendo a
  tavolino, oppure esce dalla gara, e le sue altre partite aperte si chiudono;
* **il direttore ritira un iscritto anche a gara in corso**, per chi se ne va
  senza dirlo all'app. Quella cancellazione *e'* un forfait del giocatore: la
  stessa strada di dominio, e in piu' una notifica che gli dice chi l'ha
  ritirato e cosa comporta la regola;
* **un turno superato non si tocca da nessuna strada**: il forfait dichiarato
  dal giocatore e il ritiro nel trio rifiutano come gia' faceva il ritiro del
  direttore dal menu della partita.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, Match, User
from models.competition.models import WithdrawPolicy
from models.match.models import TrioMatch, TrioRack
from models.notification.models import Notification
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
def direttore(db_session):
    return _utente(db_session, "rtd_admin", role=UserRole.ADMIN.value)


@pytest.fixture
def admin_client(client, direttore):
    return _entra(client, direttore)


def _gara(db_session, policy=WithdrawPolicy.FORFEIT.value, **kw):
    gara = Gara(
        number=1,
        name=kw.pop("name", "Gara ritiri"),
        date=date.today() + timedelta(days=3),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        matchmaking_strategy=kw.pop("strategy", "amalfi"),
        status=kw.pop("status", GaraStatus.PLAYING.value),
        current_round=kw.pop("current_round", 1),
        rounds_count=3,
        min_participants=2,
        withdraw_policy=policy,
        **kw,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _iscritti(db_session, gara, n, **kw):
    giocatori = []
    for i in range(n):
        user = _utente(db_session, f"rtd_p{i}")
        db_session.add(Inscription(gara_id=gara.id, user_id=user.id, **kw))
        giocatori.append(user)
    db_session.commit()
    return giocatori


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


def _trio(db_session, gara, giocatori, round_number=1):
    p1, p2, p3 = giocatori
    match = Match(
        gara_id=gara.id,
        round_number=round_number,
        player1_id=p1.id,
        player2_id=p2.id,
        is_trio=True,
        status=MatchStatus.PLAYING.value,
    )
    db_session.add(match)
    db_session.flush()
    trio = TrioMatch(
        match_id=match.id, player1_id=p1.id, player2_id=p2.id, player3_id=p3.id
    )
    db_session.add(trio)
    db_session.commit()
    return match, trio


def _iscrizione(gara, user):
    return Inscription.query.filter_by(
        gara_id=gara.id, user_id=user.id, is_withdrawn=False
    ).first()


def _notifiche(user):
    return Notification.query.filter_by(user_id=user.id).all()


# ── Il ritiro nel trio applica la regola della gara ─────────────────────────


def test_il_ritiro_nel_trio_con_la_regola_a_tavolino_lo_marca_e_chiude_il_resto(
    admin_client, db_session
):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value, strategy="random")
    a, b, c, d = _iscritti(db_session, gara, 4)
    _match, trio = _trio(db_session, gara, (a, b, c))
    # La strategia casuale ha gia' creato il turno dopo: quella partita di C
    # e' aperta e si deve chiudere a tavolino.
    altra = _partita(db_session, gara, c, d, round_number=2, status="pending")

    resp = admin_client.post(
        f"/admin/gara/trio/{trio.id}/forfeit", data={"player_id": str(c.id)}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    assert db_session.get(TrioMatch, trio.id).forfeit_player_id == c.id
    assert _iscrizione(gara, c).is_forfeit is True
    altra = db_session.get(Match, altra.id)
    assert MatchStatus.is_finished(altra.status)
    assert altra.winner_id == d.id


def test_il_ritiro_nel_trio_con_la_regola_di_esclusione_toglie_l_iscrizione(
    admin_client, db_session
):
    gara = _gara(db_session, WithdrawPolicy.EXCLUDE.value)
    a, b, c = _iscritti(db_session, gara, 3)
    _match, trio = _trio(db_session, gara, (a, b, c))

    resp = admin_client.post(
        f"/admin/gara/trio/{trio.id}/forfeit", data={"player_id": str(a.id)}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _iscrizione(gara, a) is None


def test_il_ritiro_nel_trio_non_si_applica_due_volte(admin_client, db_session):
    """La regola della gara richiude i trii aperti di chi si ritira: il trio
    da cui si parte non deve ricevere un secondo giro di triangoli a
    tavolino."""
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b, c = _iscritti(db_session, gara, 3)
    _match, trio = _trio(db_session, gara, (a, b, c))

    resp = admin_client.post(
        f"/admin/gara/trio/{trio.id}/forfeit", data={"player_id": str(a.id)}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    numeri = [
        r.rack_number for r in TrioRack.query.filter_by(trio_match_id=trio.id).all()
    ]
    assert len(numeri) == len(set(numeri))
    trio = db_session.get(TrioMatch, trio.id)
    assert len(numeri) <= trio.trio_config.total_played_racks


def test_il_giocatore_che_si_ritira_dal_trio_segue_la_regola_della_gara(
    client, db_session
):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b, c = _iscritti(db_session, gara, 3)
    match, _trio_ = _trio(db_session, gara, (a, b, c))
    _entra(client, c)

    resp = client.post(f"/player/match/{match.id}/trio/forfeit")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _iscrizione(gara, c).is_forfeit is True


def test_il_foglio_del_ritiro_nel_trio_dice_la_regola_della_gara(
    admin_client, db_session
):
    gara = _gara(db_session, WithdrawPolicy.EXCLUDE.value)
    a, b, c = _iscritti(db_session, gara, 3)
    _trio(db_session, gara, (a, b, c))
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    foglio = html.split('id="ritiroModal"', 1)[1]
    assert "la regola della gara sui ritiri non si applica" not in foglio
    assert "Esce dalla gara" in foglio


# ── Un turno superato non si tocca da nessuna strada ────────────────────────


def _turno_superato(db_session, gara, *giocatori):
    """Avvia il turno 2 di una gara Amalfi: il turno 1 resta alle spalle."""
    gara.current_round = 2
    db_session.commit()
    extra = _utente(db_session, "rtd_t2")
    return _partita(db_session, gara, giocatori[0], extra, round_number=2)


def test_il_forfait_del_giocatore_non_tocca_un_turno_superato(client, db_session):
    gara = _gara(db_session)
    a, b = _iscritti(db_session, gara, 2)
    match = _partita(db_session, gara, a, b)
    _turno_superato(db_session, gara, b)
    _entra(client, a)

    resp = client.post(f"/player/match/{match.id}/forfeit")
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert not MatchStatus.is_finished(db_session.get(Match, match.id).status)
    assert _iscrizione(gara, a).is_forfeit is not True


def test_il_ritiro_nel_trio_del_direttore_non_tocca_un_turno_superato(
    admin_client, db_session
):
    gara = _gara(db_session)
    a, b, c = _iscritti(db_session, gara, 3)
    _match, trio = _trio(db_session, gara, (a, b, c))
    _turno_superato(db_session, gara, a)

    resp = admin_client.post(
        f"/admin/gara/trio/{trio.id}/forfeit", data={"player_id": str(c.id)}
    )
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert db_session.get(TrioMatch, trio.id).forfeit_player_id is None


def test_il_ritiro_nel_trio_del_giocatore_non_tocca_un_turno_superato(
    client, db_session
):
    gara = _gara(db_session)
    a, b, c = _iscritti(db_session, gara, 3)
    match, trio = _trio(db_session, gara, (a, b, c))
    _turno_superato(db_session, gara, a)
    _entra(client, c)

    resp = client.post(f"/player/match/{match.id}/trio/forfeit")
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert db_session.get(TrioMatch, trio.id).forfeit_player_id is None


def test_con_la_strategia_casuale_nessun_turno_e_superato(client, db_session):
    """Col casuale i turni nascono tutti insieme e si giocano in qualunque
    ordine: il blocco non esiste, e il forfait resta possibile."""
    gara = _gara(db_session, strategy="random")
    a, b = _iscritti(db_session, gara, 2)
    match = _partita(db_session, gara, a, b)
    _partita(db_session, gara, b, a, round_number=2, status="pending")
    _entra(client, a)

    resp = client.post(f"/player/match/{match.id}/forfeit")
    assert resp.status_code == 200, resp.get_data(as_text=True)


# ── Il direttore ritira un iscritto a gara in corso ─────────────────────────


def _ritira(client, gara, user):
    return client.post(f"/admin/gara/{gara.id}/ritira/{user.id}")


def test_ritirare_un_iscritto_in_gioco_e_il_suo_forfait(
    admin_client, db_session, direttore
):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b = _iscritti(db_session, gara, 2)
    match = _partita(db_session, gara, a, b, player1_score=1)

    resp = _ritira(admin_client, gara, a)
    assert resp.status_code == 302, resp.get_data(as_text=True)

    match = db_session.get(Match, match.id)
    assert MatchStatus.is_finished(match.status)
    assert match.winner_id == b.id
    assert match.player2_score == 3
    # Come nel forfait dal menu della partita: i triangoli vinti restano suoi.
    assert match.player1_score == 1
    assert _iscrizione(gara, a).is_forfeit is True

    notifiche = _notifiche(a)
    assert len(notifiche) == 1
    testo = notifiche[0].message
    assert direttore.username in testo
    assert "tavolino" in testo


def test_ritirare_un_iscritto_con_la_regola_di_esclusione_lo_toglie_e_lo_dice(
    admin_client, db_session
):
    gara = _gara(db_session, WithdrawPolicy.EXCLUDE.value)
    a, b = _iscritti(db_session, gara, 2)
    _partita(db_session, gara, a, b)

    resp = _ritira(admin_client, gara, b)
    assert resp.status_code == 302
    assert _iscrizione(gara, b) is None
    assert "abbinamenti" in _notifiche(b)[0].message


def test_ritirare_chi_ha_la_x_applica_solo_la_regola(admin_client, db_session):
    """Fra un turno e l'altro, o con la X, non c'e' niente da chiudere: resta
    la regola per i turni dopo."""
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    (a,) = _iscritti(db_session, gara, 1)
    x = _partita(
        db_session,
        gara,
        a,
        None,
        is_bye=True,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        player1_score=0,
    )

    resp = _ritira(admin_client, gara, a)
    assert resp.status_code == 302
    assert _iscrizione(gara, a).is_forfeit is True
    assert db_session.get(Match, x.id).winner_id is None


def test_ritirare_un_iscritto_che_gioca_un_trio(admin_client, db_session):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b, c = _iscritti(db_session, gara, 3)
    _match, trio = _trio(db_session, gara, (a, b, c))

    resp = _ritira(admin_client, gara, b)
    assert resp.status_code == 302
    assert db_session.get(TrioMatch, trio.id).forfeit_player_id == b.id
    assert _iscrizione(gara, b).is_forfeit is True


def test_in_un_tabellone_la_notifica_parla_del_tabellone(admin_client, db_session):
    gara = _gara(
        db_session, WithdrawPolicy.FORFEIT.value, strategy="direct_elimination"
    )
    a, b = _iscritti(db_session, gara, 2)
    _partita(db_session, gara, a, b)

    resp = _ritira(admin_client, gara, a)
    assert resp.status_code == 302
    assert "tabellone" in _notifiche(a)[0].message


def test_non_si_ritira_due_volte(admin_client, db_session):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b = _iscritti(db_session, gara, 2)
    _partita(db_session, gara, a, b)
    assert _ritira(admin_client, gara, a).status_code == 302

    resp = admin_client.post(
        f"/admin/gara/{gara.id}/ritira/{a.id}", follow_redirects=True
    )
    assert "già ritirato" in resp.get_data(as_text=True)
    assert len(_notifiche(a)) == 1


def test_la_lista_d_attesa_non_si_ritira_a_gara_in_corso(admin_client, db_session):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    (attesa,) = _iscritti(db_session, gara, 1, is_waitlist=True)

    admin_client.post(f"/admin/gara/{gara.id}/ritira/{attesa.id}")
    iscrizione = Inscription.query.filter_by(gara_id=gara.id, user_id=attesa.id).one()
    assert iscrizione.is_forfeit is not True
    assert _notifiche(attesa) == []


@pytest.mark.parametrize(
    "stato",
    [GaraStatus.INSCRIPTION.value, GaraStatus.COMPLETED.value],
)
def test_il_ritiro_dell_iscritto_vale_solo_a_gara_in_corso(
    admin_client, db_session, stato
):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value, status=stato)
    (a,) = _iscritti(db_session, gara, 1)

    _ritira(admin_client, gara, a)
    iscrizione = _iscrizione(gara, a)
    assert iscrizione is not None
    assert iscrizione.is_forfeit is not True


def test_il_ritiro_dell_iscritto_e_negato_a_chi_non_dirige(client, db_session):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b = _iscritti(db_session, gara, 2)
    _entra(client, b)

    resp = _ritira(client, gara, a)
    assert resp.status_code in (302, 403)
    assert _iscrizione(gara, a).is_forfeit is not True


def test_in_gioco_la_riga_dell_iscritto_propone_il_ritiro_con_il_foglio(
    admin_client, db_session
):
    gara = _gara(db_session, WithdrawPolicy.EXCLUDE.value)
    a, b = _iscritti(db_session, gara, 2)
    _partita(db_session, gara, a, b)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert f'data-ritira-url="/admin/gara/{gara.id}/ritira/{a.id}"' in html
    foglio = html.split('id="ritiroIscrittoModal"', 1)[1]
    assert "Esce dalla gara" in foglio
    assert "notifica" in foglio


def test_la_riga_di_chi_si_e_gia_ritirato_non_propone_il_ritiro(
    admin_client, db_session
):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b = _iscritti(db_session, gara, 2)
    _partita(db_session, gara, a, b)
    ins = _iscrizione(gara, a)
    ins.is_forfeit = True
    db_session.commit()

    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert f"/ritira/{a.id}" not in html
    assert f"/ritira/{b.id}" in html


def test_a_iscrizioni_aperte_resta_la_disiscrizione(admin_client, db_session):
    gara = _gara(db_session, status=GaraStatus.INSCRIPTION.value, current_round=0)
    (a,) = _iscritti(db_session, gara, 1)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert f"/admin_uninscribe/{a.id}" in html
    assert "/ritira/" not in html


def _guasto_alla_notifica(monkeypatch):
    """Fa fallire l'ultimo passo del ritiro, dopo che gli altri hanno scritto."""
    from models.competition.inscription_service import InscriptionService

    def guasto(*_args, **_kwargs):
        raise RuntimeError("guasto simulato alla notifica")

    monkeypatch.setattr(InscriptionService, "notifica_di_gara", guasto)


def test_il_ritiro_dell_iscritto_e_tutto_o_niente(db_session, direttore, monkeypatch):
    """Se un passo fallisce dopo che la partita e la regola hanno scritto, non
    resta scritto niente: partita aperta, iscrizione intatta, nessuna
    notifica. Si rilegge il database dopo aver annullato la sessione.

    Dipende dalla #385: prima un servizio annidato salvava da solo, e la
    partita restava chiusa a tavolino con il giocatore marcato."""
    from models.competition.withdraw_policy_service import WithdrawPolicyService

    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b = _iscritti(db_session, gara, 2)
    match = _partita(db_session, gara, a, b, player1_score=1)
    ids = (gara.id, a.id, match.id)
    _guasto_alla_notifica(monkeypatch)

    with pytest.raises(RuntimeError):
        WithdrawPolicyService.ritira_iscritto(gara.id, a.id, direttore.id)
    db_session.rollback()
    db_session.expire_all()

    gara_id, a_id, match_id = ids
    riletta = db_session.get(Match, match_id)
    assert not MatchStatus.is_finished(riletta.status)
    assert riletta.winner_id is None
    assert riletta.player2_score == 0
    iscrizione = Inscription.query.filter_by(gara_id=gara_id, user_id=a_id).one()
    assert iscrizione.is_forfeit is not True
    assert Notification.query.filter_by(user_id=a_id).count() == 0


def test_il_ritiro_dell_iscritto_nel_trio_e_tutto_o_niente(
    db_session, direttore, monkeypatch
):
    """Stessa garanzia sulla strada del trio: triangoli a tavolino, ritiro del
    trio e regola della gara si annullano insieme."""
    from models.competition.withdraw_policy_service import WithdrawPolicyService

    gara = _gara(db_session, WithdrawPolicy.EXCLUDE.value)
    a, b, c = _iscritti(db_session, gara, 3)
    _match, trio = _trio(db_session, gara, (a, b, c))
    ids = (gara.id, a.id, trio.id)
    _guasto_alla_notifica(monkeypatch)

    with pytest.raises(RuntimeError):
        WithdrawPolicyService.ritira_iscritto(gara.id, a.id, direttore.id)
    db_session.rollback()
    db_session.expire_all()

    gara_id, a_id, trio_id = ids
    assert db_session.get(TrioMatch, trio_id).forfeit_player_id is None
    assert TrioRack.query.filter_by(trio_match_id=trio_id).count() == 0
    iscrizione = Inscription.query.filter_by(
        gara_id=gara_id, user_id=a_id, is_withdrawn=False
    ).first()
    assert iscrizione is not None
    assert iscrizione.is_forfeit is not True


@pytest.mark.parametrize("strada", ["partita", "trio"])
def test_il_ritiro_dal_menu_del_direttore_e_tutto_o_niente(
    db_session, direttore, monkeypatch, strada
):
    """Il ritiro dal menu della partita e quello nel trio registrato dal
    direttore: se la notifica fallisce, non resta scritto niente."""
    from models.competition.withdraw_policy_service import WithdrawPolicyService

    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    if strada == "partita":
        a, b = _iscritti(db_session, gara, 2)
        match = _partita(db_session, gara, a, b)
        operazione = WithdrawPolicyService.ritira_dalla_partita
        bersaglio = match.id
    else:
        a, b, c = _iscritti(db_session, gara, 3)
        match, trio = _trio(db_session, gara, (a, b, c))
        operazione = WithdrawPolicyService.ritira_dal_trio
        bersaglio = trio.id
    ids = (gara.id, a.id, match.id)
    _guasto_alla_notifica(monkeypatch)

    with pytest.raises(RuntimeError):
        operazione(bersaglio, a.id, direttore.id)
    db_session.rollback()
    db_session.expire_all()

    gara_id, a_id, match_id = ids
    riletta = db_session.get(Match, match_id)
    assert not MatchStatus.is_finished(riletta.status)
    if strada == "trio":
        assert riletta.trio_match.forfeit_player_id is None
        assert (
            TrioRack.query.filter_by(trio_match_id=riletta.trio_match.id).count() == 0
        )
    iscrizione = Inscription.query.filter_by(gara_id=gara_id, user_id=a_id).one()
    assert iscrizione.is_forfeit is not True
    assert Notification.query.filter_by(user_id=a_id).count() == 0


# ── La notifica arriva per ogni ritiro deciso dal direttore ─────────────────


def _notifiche_di_ritiro(user):
    return [n for n in _notifiche(user) if "ti ha ritirato" in n.message]


def test_il_ritiro_dal_menu_della_partita_avvisa_il_giocatore(
    admin_client, db_session, direttore
):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b = _iscritti(db_session, gara, 2)
    match = _partita(db_session, gara, a, b)

    resp = admin_client.post(
        f"/admin/match/{match.id}/forfeit", data={"player_id": str(a.id)}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    notifiche = _notifiche_di_ritiro(a)
    assert len(notifiche) == 1
    assert direttore.username in notifiche[0].message
    assert "tavolino" in notifiche[0].message
    assert _notifiche_di_ritiro(b) == []


def test_il_ritiro_nel_trio_del_direttore_avvisa_il_giocatore(
    admin_client, db_session, direttore
):
    gara = _gara(db_session, WithdrawPolicy.EXCLUDE.value)
    a, b, c = _iscritti(db_session, gara, 3)
    _match, trio = _trio(db_session, gara, (a, b, c))

    resp = admin_client.post(
        f"/admin/gara/trio/{trio.id}/forfeit", data={"player_id": str(c.id)}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    notifiche = _notifiche_di_ritiro(c)
    assert len(notifiche) == 1
    assert direttore.username in notifiche[0].message
    assert "abbinamenti" in notifiche[0].message


def test_il_ritiro_dalla_lista_manda_una_notifica_sola(admin_client, db_session):
    """La lista compone il ritiro dalla partita: la notifica non si ripete."""
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b = _iscritti(db_session, gara, 2)
    _partita(db_session, gara, a, b)

    assert _ritira(admin_client, gara, a).status_code == 302
    assert len(_notifiche_di_ritiro(a)) == 1


def test_il_forfait_dichiarato_dal_giocatore_non_manda_notifiche(client, db_session):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b = _iscritti(db_session, gara, 2)
    match = _partita(db_session, gara, a, b)
    _entra(client, a)

    resp = client.post(f"/player/match/{match.id}/forfeit")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _notifiche_di_ritiro(a) == []
    assert _notifiche_di_ritiro(b) == []


def test_il_ritiro_dal_trio_dichiarato_dal_giocatore_non_manda_notifiche(
    client, db_session
):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b, c = _iscritti(db_session, gara, 3)
    match, _trio_ = _trio(db_session, gara, (a, b, c))
    _entra(client, c)

    resp = client.post(f"/player/match/{match.id}/trio/forfeit")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _notifiche_di_ritiro(c) == []


def test_il_foglio_del_ritiro_dal_menu_dice_la_notifica(admin_client, db_session):
    gara = _gara(db_session, WithdrawPolicy.FORFEIT.value)
    a, b = _iscritti(db_session, gara, 2)
    _partita(db_session, gara, a, b)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    foglio = html.split('id="ritiroModal"', 1)[1].split('id="ritiroIscrittoModal"')[0]
    assert "Riceve una notifica" in foglio


def test_la_notifica_della_disiscrizione_parla_bene_del_direttore(
    admin_client, db_session
):
    """Regressione: la f-string scriveva «L'direttore di gara» e non si
    traduceva."""
    gara = _gara(db_session, status=GaraStatus.INSCRIPTION.value, current_round=0)
    (a,) = _iscritti(db_session, gara, 1)

    resp = admin_client.post(f"/admin/gara/{gara.id}/admin_uninscribe/{a.id}")
    assert resp.status_code == 302
    notifiche = _notifiche(a)
    assert len(notifiche) == 1
    assert "L'direttore" not in notifiche[0].message
    assert "L'admin " not in notifiche[0].message
    assert gara.name in notifiche[0].message
