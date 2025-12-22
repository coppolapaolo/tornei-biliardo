# routes/i18n.py
from flask import Blueprint, request, session, redirect, url_for

i18n_bp = Blueprint("i18n", __name__)

@i18n_bp.route("/set_language/<language>")
def set_language(language):
    if language in ["it", "en"]:
        session["language"] = language
    
    # Redirect back to the previous page, or home if not available
    next_page = request.referrer
    if next_page and request.host in next_page:
        return redirect(next_page)
    return redirect(url_for("main.index"))
