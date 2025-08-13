# utils/jinja.py — aggiunta di un helper per render accattivante
from markupsafe import Markup, escape


def display_user_handle(user) -> Markup:
    if getattr(user, "is_deleted", False):
        date = user.deleted_at.strftime("%d/%m/%Y") if user.deleted_at else ""
        prev = escape(user.previous_username or user.username)
        return Markup(f"🗑️ <s>{prev}</s> <small class='text-muted'>· {date}</small>")
    return Markup(escape(user.username))
