"""Presidio: nessun testo di notifica arriva già tradotto (ADR-062).

Il servizio delle notifiche compone titolo, messaggio e pulsante nella lingua
del destinatario, ma solo se glieli si passa **da comporre**: una stringa pigra
(``lazy_gettext``) o una funzione senza argomenti. Una f-string, un letterale
o un ``_()`` chiamato sul posto arrivano già cotti nella lingua di chi ha
premuto il pulsante, e nessun test di comportamento se ne accorge: in sviluppo
e nei test chi preme e chi riceve parlano italiano entrambi.

Si guarda l'AST e non il testo. Oltre al valore passato direttamente, si
seguono le assegnazioni alla variabile dentro la stessa funzione: ``title =
f"..."`` seguito da ``title=title`` è lo schema più comune. Un valore che
arriva da fuori della funzione — un parametro, un attributo — non si può
giudicare da qui ed è ammesso: di solito è testo scritto da un utente, che non
si traduce.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACCHETTI = ("models", "routes", "utils")

#: Le funzioni che ricevono il testo di una notifica.
CREATORI = {
    "create_notification",
    "create_bulk_notification",
    "create_admin_notification",
    "create_system_announcement",
    "create_account_update_notification",
    "_notify",
}

#: Gli argomenti che portano testo da leggere.
ARGOMENTI_DI_TESTO = {"title", "message", "action_text", "message_template"}

#: Le traduzioni fatte sul posto: cuociono la lingua di chi preme.
TRADUZIONI_IMMEDIATE = {"_", "gettext", "ngettext", "pgettext"}


def _nome_chiamata(nodo: ast.Call) -> str:
    funzione = nodo.func
    if isinstance(funzione, ast.Attribute):
        return funzione.attr
    if isinstance(funzione, ast.Name):
        return funzione.id
    return ""


def _cotto(valore: ast.AST, assegnazioni: dict) -> bool:
    """True se il valore arriva alla notifica già tradotto o mai tradotto."""
    if isinstance(valore, ast.JoinedStr):
        return True
    if isinstance(valore, ast.Constant) and isinstance(valore.value, str):
        return bool(valore.value.strip())
    if isinstance(valore, ast.BinOp):
        return True
    if isinstance(valore, ast.Call):
        return _nome_chiamata(valore) in TRADUZIONI_IMMEDIATE
    if isinstance(valore, ast.IfExp):
        return _cotto(valore.body, assegnazioni) or _cotto(valore.orelse, assegnazioni)
    if isinstance(valore, ast.BoolOp):
        return any(_cotto(v, assegnazioni) for v in valore.values)
    if isinstance(valore, ast.Name):
        return any(_cotto(v, {}) for v in assegnazioni.get(valore.id, []))
    return False


def _assegnazioni(funzione: ast.AST) -> dict:
    trovate: dict = {}
    for nodo in ast.walk(funzione):
        if isinstance(nodo, ast.Assign):
            for bersaglio in nodo.targets:
                if isinstance(bersaglio, ast.Name):
                    trovate.setdefault(bersaglio.id, []).append(nodo.value)
        elif isinstance(nodo, ast.AugAssign) and isinstance(nodo.target, ast.Name):
            # `message += f"..."`: anche un'aggiunta cuoce il testo.
            trovate.setdefault(nodo.target.id, []).append(nodo.value)
    return trovate


def _testi_cotti() -> list:
    trovati = set()
    for pacchetto in PACCHETTI:
        for percorso in (ROOT / pacchetto).rglob("*.py"):
            albero = ast.parse(percorso.read_text(encoding="utf-8"))
            for funzione in ast.walk(albero):
                if not isinstance(funzione, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                assegnazioni = _assegnazioni(funzione)
                for nodo in ast.walk(funzione):
                    if not isinstance(nodo, ast.Call):
                        continue
                    if _nome_chiamata(nodo) not in CREATORI:
                        continue
                    for argomento in nodo.keywords:
                        if argomento.arg not in ARGOMENTI_DI_TESTO:
                            continue
                        if _cotto(argomento.value, assegnazioni):
                            trovati.add(
                                f"{percorso.relative_to(ROOT)}:{nodo.lineno} "
                                f"{argomento.arg}"
                            )
    return sorted(trovati)


def test_i_testi_delle_notifiche_si_compongono_per_chi_le_riceve():
    cotti = _testi_cotti()
    assert not cotti, (
        "testo di notifica già tradotto, o mai tradotto, nella lingua di chi "
        "preme: passa `lazy_gettext` o una funzione senza argomenti (ADR-062)\n"
        + "\n".join(cotti)
    )


def test_il_presidio_riconosce_i_casi_che_deve_fermare():
    """Il presidio stesso va provato: un controllo che non trova niente mente."""
    sorgente = """
def cattivo(user_id, event):
    title = f"Ciao {event.nome}"
    message = _("Pronto")
    message += " subito"
    create_notification(user_id=user_id, title=title, message=message)
    create_notification(user_id=user_id, title="Letterale", message=_l("ok"))

def buono(user_id, nota):
    create_notification(
        user_id=user_id, title=_l("Pronto"), message=lambda: _("Pronto"),
        action_text=nota,
    )
"""
    albero = ast.parse(sorgente)
    cotti = []
    for funzione in albero.body:
        assegnazioni = _assegnazioni(funzione)
        for nodo in ast.walk(funzione):
            if isinstance(nodo, ast.Call) and _nome_chiamata(nodo) in CREATORI:
                for argomento in nodo.keywords:
                    if argomento.arg in ARGOMENTI_DI_TESTO and _cotto(
                        argomento.value, assegnazioni
                    ):
                        cotti.append((funzione.name, argomento.arg))
    assert sorted(cotti) == [
        ("cattivo", "message"),
        ("cattivo", "title"),
        ("cattivo", "title"),
    ]
