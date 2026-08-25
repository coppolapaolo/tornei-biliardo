"""Quale Elo mostrare accanto a un giocatore, in una partita, a chi guarda.

Tre domande che sembrano una sola e non lo sono:

1. **quale pool.** Le partite di gara muovono l'Elo *competitivo* — quello
   sincronizzato su ``User.elo_rating``, che pilota categoria e handicap. Le
   sfide individuali non lo toccano: confluiscono nel pool *globale*
   (``PlayerRating(ELO_GLOBAL)``, ``User.elo_global_rating``). Mostrare il
   competitivo su una sfida individuale significherebbe scrivere accanto alla
   partita in corso un numero che quella partita non muovera' mai;
2. **se si puo' vedere.** Lo decide la privacy del *giocatore mostrato*, non di
   chi guarda: ``show_elo`` e' l'unica preferenza opt-out, quindi si vede
   finche' non la si spegne — anche per chi la pagina privacy non l'ha mai
   aperta (vedi ``PrivacyService.OPT_OUT_FIELDS``);
3. **se esiste.** Un giocatore senza partite chiuse non ha un valore nel pool
   globale: li' non si stampa 1200 di ripiego. Un numero finto accanto a una
   partita vera e' peggio di uno spazio vuoto.

Il valore che esce di qui **non** va marcato con la classe ``elo-value``: quella
la governa ``window.EloToggle`` (base.html), che alterna competitivo/globale su
tutta la pagina. Qui il pool lo decide il tipo di partita, e un toggle lo
contraddirebbe al primo clic.
"""

from __future__ import annotations

from typing import Any, Optional


def is_competitive_pool(match: Any) -> bool:
    """True per una partita di gara, False per una sfida individuale.

    Si guarda ``gara_id``, non la relazione: leggere ``match.gara`` costerebbe
    una query in piu' per rispondere a una domanda che la colonna gia' chiude.
    ``IndividualMatch`` l'attributo non ce l'ha proprio.
    """
    return getattr(match, "gara_id", None) is not None


def elo_for_match(match: Any, player: Any, viewer: Any = None) -> Optional[int]:
    """L'Elo da scrivere accanto a ``player`` in ``match``, o ``None``.

    ``None`` copre tutti e tre i modi di non avere niente da dire: giocatore
    assente (la X a tavolino), Elo nascosto dal diretto interessato, pool senza
    un valore per lui.
    """
    if player is None:
        return None

    from models.user.privacy_service import PrivacyService

    viewer_id = (
        getattr(viewer, "id", None)
        if getattr(viewer, "is_authenticated", False)
        else None
    )
    if not PrivacyService.can_view_field(viewer_id, player.id, "elo"):
        return None

    value = (
        player.elo_rating if is_competitive_pool(match) else player.elo_global_rating
    )
    return int(value) if value is not None else None


def elo_pool_label(match: Any) -> str:
    """Come si chiama il pool mostrato: serve al `title` e agli screen reader.

    Sul tabellone la riga e' larga tre centimetri e il numero sta da solo; il
    nome per esteso vive qui, dove non ruba spazio alle cifre.
    """
    from flask_babel import gettext

    return (
        gettext("Elo competitivo")
        if is_competitive_pool(match)
        else gettext("Elo globale")
    )


def register_elo_visibility(app) -> None:
    """Espone le tre funzioni ai template."""
    app.jinja_env.globals["elo_for_match"] = elo_for_match
    app.jinja_env.globals["elo_pool_label"] = elo_pool_label
