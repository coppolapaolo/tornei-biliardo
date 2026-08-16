"""Regressioni dalla prova manuale di drill ed esami (2026-08-16).

Cinque rilievi, cinque presidi:

1. il modulo del drill tagliava la descrizione a 500 caratteri (1000 nel
   builder) con un `maxlength`, mentre la colonna è TEXT;
2. un drill non aveva un nome proprio: si chiamava con i primi 50 caratteri
   delle sue istruzioni, quindi venti drill che cominciano con «Disponi le
   bilie…» erano venti card indistinguibili;
3. il catalogo non si poteva cercare;
4. le richieste di ruolo esaminatore erano raggiungibili solo dalla notifica —
   admin non aveva nessuna voce di menu, né un comando nella lista utenti;
5. **ogni** POST degli esami rispondeva 400 «sessione scaduta»: nessuno dei
   form aveva il token CSRF.

Il quinto merita una nota, perché dice come sia sopravvissuto. `TestingConfig`
disattiva `WTF_CSRF_ENABLED`: nei test i form senza token funzionano
benissimo, quindi nessuna prova di integrazione poteva accorgersene, per
quante se ne scrivano. L'unico presidio possibile è **statico**, sul testo dei
template — ed è `test_ogni_form_post_ha_il_token_csrf`, qui sotto.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


def _make_user(role: str = UserRole.PLAYER.value) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{role}_{suffix}",
        email=f"{role}_{suffix}@test.local",
        role=role,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.flush()
    return user


def _login(client, user_id: int) -> None:
    """Autentica il client.

    Le richieste vanno fatte **fuori** dal `with app.app_context()` del setup:
    Flask-Login tiene l'utente corrente su `g`, e una richiesta del test client
    non spinge un nuovo app context se ce n'è già uno per la stessa app —
    quindi si porta dietro il `g._login_user` anonimo lasciato lì dai servizi
    chiamati durante il setup, e la pagina risponde 403 all'admin.
    """
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


# ────────────────────────────────────────────────────────────────────────────────
# 5. Il token CSRF in ogni form che scrive
# ────────────────────────────────────────────────────────────────────────────────
def _form_post_senza_token() -> list[str]:
    """I `<form method=POST>` privi di `csrf_token`, come `file:riga`."""
    mancanti: list[str] = []

    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"<form\b", text):
            start = match.start()
            close = text.find(">", start)
            if close == -1:
                continue
            tag = text[start : close + 1]
            # Un GET non passa dal controllo CSRF: qui interessa chi scrive.
            if not re.search(r'method\s*=\s*["\']?post', tag, re.I):
                continue
            end = text.find("</form>", close)
            body = text[close : end if end != -1 else len(text)]
            if "csrf_token" in body or "csrf_token" in tag:
                continue
            riga = text.count("\n", 0, start) + 1
            mancanti.append(f"{path.relative_to(TEMPLATES.parent)}:{riga}")

    return mancanti


def test_ogni_form_post_ha_il_token_csrf():
    """Nessun form che scrive può nascere senza token.

    Bug: tutti i 19 form di `templates/exam/` ne erano privi, quindi ogni
    azione degli esami — creare l'esame, aggiungere un drill, registrare un
    esito, certificare — rispondeva 400 «sessione scaduta». `CSRFProtect` è
    globale e fail-closed: la route non dichiara niente, e il template che si
    dimentica il token non fallisce alla build, fallisce in faccia all'utente.

    Il test è statico di proposito: con `WTF_CSRF_ENABLED = False` nei test
    non esiste nessuna prova di integrazione che possa accorgersene.
    """
    mancanti = _form_post_senza_token()
    assert not mancanti, (
        "Form POST senza token CSRF (daranno 400 «sessione scaduta»):\n  "
        + "\n  ".join(mancanti)
    )


def test_nessuna_fetch_non_get_senza_header_csrf():
    """L'altra metà della stessa regola, per le chiamate JavaScript.

    Chi invia con `fetch` non ha un campo nascosto: il token viaggia
    nell'header `X-CSRFToken`. Dimenticarlo ha lo stesso esito — 400 — solo
    con in più un errore che il codice cattura e trasforma in un generico
    «errore di rete».
    """
    root = TEMPLATES.parent
    files = list(TEMPLATES.rglob("*.html")) + list(
        (root / "static" / "js").rglob("*.js")
    )
    mancanti: list[str] = []

    for path in sorted(files):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"""method\s*:\s*['"](POST|PUT|PATCH|DELETE)['"]""", text
        ):
            finestra = text[max(0, match.start() - 600) : match.start() + 600]
            if "CSRFToken" in finestra or "csrf" in finestra.lower():
                continue
            riga = text.count("\n", 0, match.start()) + 1
            mancanti.append(f"{path.relative_to(root)}:{riga}")

    assert not mancanti, "Chiamate non-GET senza header CSRF:\n  " + "\n  ".join(
        mancanti
    )


# ────────────────────────────────────────────────────────────────────────────────
# 1. La descrizione del drill non è più tagliata dal modulo
# ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "template", ["challenge/create.html", "challenge/builder.html"]
)
def test_la_descrizione_del_drill_non_ha_un_tetto_di_caratteri(template):
    """Bug: `maxlength` sulla textarea troncava le regole dei drill lunghi.

    La colonna è TEXT, quindi il limite viveva solo nel modulo — e non lo
    diceva: si scriveva e a un certo punto i tasti smettevano di comparire.
    """
    text = (TEMPLATES / template).read_text(encoding="utf-8")
    textarea = re.search(r"<textarea[^>]*name=\"description\"[^>]*>", text)
    assert textarea is not None, f"{template}: manca la textarea della descrizione"
    assert "maxlength" not in textarea.group(0)


def test_una_descrizione_lunga_si_salva_intera(app):
    """E il giro completo: quello che si scrive è quello che resta a DB."""
    with app.app_context():
        lunga = "Disponi le bilie lungo la sponda. " * 200  # ~6800 caratteri
        challenge = ChallengeService.create_challenge(
            description=lunga, image_path="x.png"
        )
        db.session.flush()

        assert db.session.get(Challenge, challenge.id).description == lunga


# ────────────────────────────────────────────────────────────────────────────────
# 2. Il titolo del drill
# ────────────────────────────────────────────────────────────────────────────────
def test_il_titolo_scelto_e_il_nome_del_drill(app):
    with app.app_context():
        challenge = ChallengeService.create_challenge(
            title="Progressione lungo sponda",
            description="Disponi 10 bilie e imbucale in sequenza",
            image_path="x.png",
        )
        assert challenge.get_display_name() == "Progressione lungo sponda"


def test_senza_titolo_il_drill_prende_il_progressivo(app):
    """Bug: due drill con lo stesso incipit avevano lo stesso nome.

    `get_display_name()` restituiva la descrizione troncata a 50 caratteri, e
    le istruzioni cominciano quasi sempre allo stesso modo. Un numero
    distingue; mezza frase no.
    """
    with app.app_context():
        incipit = "Disponi le bilie lungo la sponda lunga e poi "
        primo = ChallengeService.create_challenge(
            description=incipit + "imbucale in sequenza", image_path="x.png"
        )
        secondo = ChallengeService.create_challenge(
            description=incipit + "gioca di sponda", image_path="y.png"
        )
        db.session.flush()

        assert primo.get_display_name() == f"Drill {primo.id}"
        assert secondo.get_display_name() == f"Drill {secondo.id}"
        assert primo.get_display_name() != secondo.get_display_name()


def test_un_titolo_di_soli_spazi_non_e_un_titolo(app):
    """Il modulo manda sempre il campo: vuoto o bianco vale «nessun titolo»."""
    with app.app_context():
        challenge = ChallengeService.create_challenge(
            title="   ", description="Istruzioni", image_path="x.png"
        )
        db.session.flush()

        assert challenge.title is None
        assert challenge.get_display_name() == f"Drill {challenge.id}"


def test_il_titolo_si_puo_togliere_dopo_averlo_messo(app):
    """`None` non tocca il titolo, la stringa vuota lo cancella.

    Senza questa distinzione un titolo, una volta scritto, sarebbe stato per
    sempre: il modulo svuotato manda `""`, che con la regola «None = non
    toccare» sarebbe stato indistinguibile dal campo assente.
    """
    with app.app_context():
        challenge = ChallengeService.create_challenge(
            title="Provvisorio", description="Istruzioni", image_path="x.png"
        )
        db.session.flush()

        ChallengeService.update_challenge(challenge.id, description="Altre istruzioni")
        assert challenge.title == "Provvisorio"  # non inviato = non toccato

        ChallengeService.update_challenge(challenge.id, title="")
        assert challenge.title is None
        assert challenge.get_display_name() == f"Drill {challenge.id}"


def test_modificare_un_drill_non_lo_disattiva(app):
    """Bug latente: `is_active` assente valeva «false», e il drill spariva.

    La rotta di modifica leggeva `data.get("is_active", "false")`, ma il
    modulo quel campo non lo manda: ogni salvataggio toglieva la challenge dal
    catalogo, senza dirlo a nessuno.
    """
    with app.app_context():
        challenge = ChallengeService.create_challenge(
            description="Istruzioni", image_path="x.png"
        )
        db.session.flush()
        assert challenge.is_active is True

        ChallengeService.update_challenge(challenge.id, description="Corrette")
        assert challenge.is_active is True


# ────────────────────────────────────────────────────────────────────────────────
# 3. La ricerca nel catalogo
# ────────────────────────────────────────────────────────────────────────────────
def test_il_catalogo_offre_la_ricerca_su_titolo_e_istruzioni(app, client):
    """La casella c'è, e ogni card porta con sé il testo su cui si cerca."""
    with app.app_context():
        player_id = _make_user().id
        ChallengeService.create_challenge(
            title="Progressione lungo sponda",
            description="Imbuca in sequenza partendo dalla corta",
            image_path="x.png",
        )
        db.session.commit()

    _login(client, player_id)
    html = client.get("/challenges/").get_data(as_text=True)

    assert 'id="challengeSearch"' in html
    # `data-search` unisce titolo e istruzioni, già minuscolo: cercare una
    # parola che sta solo nelle regole deve trovare comunque la challenge.
    assert "progressione lungo sponda" in html
    assert "imbuca in sequenza partendo dalla corta" in html


# ────────────────────────────────────────────────────────────────────────────────
# 4. Admin: menu delle richieste e comandi sugli esaminatori
# ────────────────────────────────────────────────────────────────────────────────
def test_admin_ha_la_voce_di_menu_delle_richieste_di_ruolo(app, client):
    """Bug: la coda era raggiungibile solo dalla notifica, che scade.

    Il solo ingresso era il catalogo delle challenge, e solo per chi è già
    esaminatore — cioè mai per admin, che pure le può approvare tutte.
    """
    with app.app_context():
        admin_id = _make_user(UserRole.ADMIN.value).id
        db.session.commit()

    _login(client, admin_id)
    html = client.get("/admin/users").get_data(as_text=True)

    assert "/roles/requests" in html


def test_la_lista_utenti_permette_di_nominare_e_revocare_esaminatori(app, client):
    """Bug: si poteva solo dalla scheda del singolo utente, una alla volta."""
    with app.app_context():
        admin = _make_user(UserRole.ADMIN.value)
        semplice_id = _make_user().id
        esaminatore_id = _make_user().id
        db.session.commit()
        admin_id = admin.id
        RoleGrantService.grant(esaminatore_id, GrantableRole.EXAMINER, admin)

    _login(client, admin_id)
    html = client.get("/admin/users").get_data(as_text=True)

    assert f"/roles/grant/examiner/{semplice_id}" in html
    assert f"/roles/revoke/examiner/{esaminatore_id}" in html
    # E il contrario non deve comparire: niente «promuovi» su chi lo è già.
    assert f"/roles/grant/examiner/{esaminatore_id}" not in html
    assert f"/roles/revoke/examiner/{semplice_id}" not in html


def test_holder_ids_evita_una_query_per_riga(app):
    """La colonna «Esaminatore» si legge in una query, non in N.

    `User.is_examiner` interroga il DB a ogni chiamata: in una tabella di
    cinquanta utenti sarebbero cinquanta query per stampare cinquanta badge.
    """
    with app.app_context():
        admin = _make_user(UserRole.ADMIN.value)
        esaminatore = _make_user()
        estraneo = _make_user()
        db.session.commit()
        RoleGrantService.grant(esaminatore.id, GrantableRole.EXAMINER, admin)

        ids = RoleGrantService.holder_ids(GrantableRole.EXAMINER)

        assert esaminatore.id in ids
        assert estraneo.id not in ids

        # E una revoca lo toglie dall'insieme.
        RoleGrantService.revoke(esaminatore.id, GrantableRole.EXAMINER, admin)
        assert esaminatore.id not in RoleGrantService.holder_ids(GrantableRole.EXAMINER)
