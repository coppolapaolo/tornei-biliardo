# routes/i18n.py
from urllib.parse import urljoin, urlparse

from flask import Blueprint, request, session, redirect, url_for

i18n_bp = Blueprint("i18n", __name__)


def _is_safe_redirect_target(target: str | None) -> bool:
    """True solo se `target` punta allo stesso host dell'app.

    Evita open redirect: il vecchio check `request.host in next_page` era un
    match di sottostringa, superato p.es. da
    `https://evil.com/?x=www.torneibiliardo.it` o
    `https://www.torneibiliardo.it.evil.com/`. Qui si confronta il netloc del
    target risolto (via urljoin sull'host dell'app) con quello dell'app.
    """
    if not target:
        return False
    host_url = request.host_url
    resolved = urlparse(urljoin(host_url, target))
    if resolved.scheme not in ("http", "https"):
        return False
    return resolved.netloc == urlparse(host_url).netloc


@i18n_bp.route("/set_language/<language>")
def set_language(language):
    if language in ["it", "en"]:
        session["language"] = language

    # Redirect back to the previous page, or home if not available/unsafe.
    next_page = request.referrer
    if _is_safe_redirect_target(next_page):
        return redirect(next_page)
    return redirect(url_for("main.index"))
