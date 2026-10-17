"""Il link al video di una partita: cosa si accetta e in che forma si salva.

Un modulo solo, usato da ogni punto che scrive un ``video_url`` (sfida
individuale e partita di gara). Si accettano i link di YouTube nelle forme
che un giocatore copia davvero:

* ``youtube.com/watch?v=ID`` (anche ``m.`` e senza ``www.``);
* ``youtu.be/ID``, il tasto «Condividi»;
* ``youtube.com/live/ID``, la diretta rimasta come video;
* ``youtube.com/shorts/ID``;

compreso il punto d'inizio (``t=90``, ``t=1m30s``, ``start=90``). Tutte
diventano la stessa forma canonica, ``https://www.youtube.com/watch?v=ID``
più ``&t=Ns`` se c'è un inizio: chi legge la pagina trova sempre lo stesso
link, e i parametri di tracciamento (``si=``, ``feature=``) restano fuori.

Il video si mostra come **link esterno** e non incorporato: un iframe
chiederebbe di aprire la CSP a YouTube. Ed è proprio perché il sito lo
presenta come «il video della partita» che non si accetta un link qualunque.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from flask_babel import lazy_gettext as _l

from models.exceptions import ValidationError

#: Oltre questa lunghezza non è un link copiato da YouTube.
MAX_LENGTH = 300

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SECONDS = re.compile(r"^(\d+)s?$")
_HMS = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")

_WATCH_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"})
_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
_PATH_PREFIXES = ("/live/", "/shorts/")


class VideoLinkError(ValidationError):
    """Il testo scritto non è un link a un video di YouTube."""


def _invalid() -> VideoLinkError:
    return VideoLinkError(
        str(
            _l(
                "Il link al video deve essere un video di YouTube "
                "(youtube.com o youtu.be)."
            )
        )
    )


def _start_seconds(raw: Optional[str]) -> int:
    """Il punto d'inizio in secondi: ``90``, ``90s``, ``1m30s``, ``1h2m3s``."""
    if raw is None or raw == "":
        return 0
    match = _SECONDS.match(raw)
    if match:
        return int(match.group(1))
    match = _HMS.match(raw)
    if match and any(match.groups()):
        hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    raise _invalid()


def normalize_video_url(raw: Optional[str]) -> Optional[str]:
    """Restituisce il link in forma canonica, ``None`` se il campo è vuoto.

    Solleva :class:`VideoLinkError` (una ``ValidationError``) per tutto ciò
    che non è un video di YouTube.
    """
    text = (raw or "").strip()
    if not text:
        return None
    if len(text) > MAX_LENGTH:
        raise _invalid()

    # Chi incolla da un messaggio spesso perde lo schema: «youtu.be/…».
    if "://" not in text:
        text = "https://" + text

    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise _invalid()
    # `hostname` è già in minuscolo e senza porta né credenziali.
    host = parsed.hostname or ""
    query = parse_qs(parsed.query)

    video_id: Optional[str] = None
    if host in _SHORT_HOSTS:
        video_id = parsed.path.strip("/")
    elif host in _WATCH_HOSTS:
        if parsed.path == "/watch":
            video_id = (query.get("v") or [""])[0]
        else:
            for prefix in _PATH_PREFIXES:
                if parsed.path.startswith(prefix):
                    video_id = parsed.path[len(prefix) :].strip("/")
                    break

    if not video_id or not _VIDEO_ID.match(video_id):
        raise _invalid()

    start_raw = (query.get("t") or query.get("start") or [None])[0]
    seconds = _start_seconds(start_raw)

    canonical = f"https://www.youtube.com/watch?v={video_id}"
    if seconds:
        canonical += f"&t={seconds}s"
    return canonical
