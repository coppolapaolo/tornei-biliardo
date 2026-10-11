"""Ciò che l'editor della catena degli spareggi deve sapere (ADR-078).

L'editor è JavaScript (`static/js/catena_spareggi.js`) e compone sotto la
lista la stessa frase del regolamento che il server scrive con
`ordinamento.descrivi_catena`. Per non tradurre due volte, le parole arrivano
da qui già tradotte: i nomi dei criteri, i pezzi della frase e i criteri
ammessi per ciascun sistema. Le regole (cosa è ammesso, il sorteggio sempre
in fondo, lo SSR una volta sola) sono quelle di `criteri_ammessi` e
`normalizza_catena`: il server le riapplica comunque al salvataggio.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from flask_babel import gettext as _

from models.status_enum import ClassificationSystem

from .ordinamento import (
    NOMI,
    SSR_FINO_AL_DEFAULT,
    SSR_FINO_AL_MASSIMO,
    Criterio,
    Livello,
    Voce,
    _a_pari,
    _nella_frase,
    catena_completa,
    catena_di_default,
    criteri_ammessi,
    criterio_principale,
    normalizza_catena,
    serializza_catena,
)

_SISTEMI = (
    ClassificationSystem.WINS,
    ClassificationSystem.RACK,
    ClassificationSystem.POINTS,
)


def _sistemi(livello: Livello) -> tuple:
    """I sistemi che un editor di quel livello conosce.

    La classifica generale anche POSITION: il campionato a piazzamenti ha la
    sua catena (ADR-080, emendamento del 2026-10-11).
    """
    if livello is Livello.CAMPIONATO:
        return _SISTEMI + (ClassificationSystem.POSITION,)
    return _SISTEMI


def _sistema(valore: Any, livello: Livello = Livello.GARA) -> ClassificationSystem:
    sistema = ClassificationSystem.resolve(valore)
    return sistema if sistema in _sistemi(livello) else ClassificationSystem.WINS


def _descrizioni(livello: Livello) -> Dict[str, str]:
    """Una riga sotto ogni criterio dell'editor: cosa guarda."""
    campionato = livello is Livello.CAMPIONATO
    return {
        Criterio.SCONTRI_DIRETTI.value: _(
            "fra i pari sta davanti chi vince lo scontro; chi si batte in giro "
            "resta pari"
        ),
        Criterio.PIAZZAMENTI.value: _(
            "più primi posti nelle gare, poi più secondi, e così via"
        ),
        Criterio.DIFFERENZA_RACK.value: _("triangoli vinti meno triangoli persi"),
        Criterio.RACK_VINTI.value: _("triangoli vinti in tutto"),
        Criterio.VITTORIE.value: _("partite vinte"),
        Criterio.SPAREGGIO_SSR.value: (
            _("la somma degli spareggi delle gare")
            if campionato
            else _("una prova a punti, giocata a gara finita")
        ),
        Criterio.POSIZIONE_PRECEDENTE.value: (
            _("chi era davanti dopo la gara precedente")
            if campionato
            else _("chi era davanti al turno precedente")
        ),
    }


def config_editor(
    livello: str, catena: Optional[Iterable[Voce]], sistema: Any
) -> Dict[str, Any]:
    """La configurazione di un editor: livello, voci di partenza, parole."""
    liv = Livello(livello)
    sis = _sistema(sistema, liv)
    sistemi = _sistemi(liv)
    if catena is None:
        catena = catena_di_default(liv, sis)
    voci = normalizza_catena(catena, liv, sis)
    frasi = {c.value: _nella_frase(Voce(c), liv) for c in Criterio}
    frasi["ssr_n"] = _nella_frase(Voce(Criterio.SPAREGGIO_SSR, 999), liv).replace(
        "999", "{n}"
    )
    return {
        "livello": liv.value,
        "sistema": sis.value,
        "voci": serializza_catena(voci),
        # A turno e campionato l'ordine dev'essere completo: il sorteggio
        # chiude sempre la catena e non si toglie.
        "completa": catena_completa(liv),
        "ssrConPosto": liv is Livello.GARA,
        "ssrDefault": SSR_FINO_AL_DEFAULT,
        "ssrMassimo": SSR_FINO_AL_MASSIMO,
        "ammessi": {
            s.value: [c.value for c in criteri_ammessi(liv, s)] for s in sistemi
        },
        "principale": {
            s.value: str(NOMI[criterio_principale(s, liv)]) for s in sistemi
        },
        "default": {
            s.value: serializza_catena(
                normalizza_catena(catena_di_default(liv, s), liv, s)
            )
            for s in sistemi
        },
        "nomi": {c.value: str(nome) for c, nome in NOMI.items()},
        "descrizioni": _descrizioni(liv),
        "frasi": frasi,
        "aPari": {s.value: _a_pari(s) for s in sistemi},
        "testi": {
            # I segnaposto `{…}` li riempie il JavaScript.
            "conta": _(
                "%(a_pari)s conta %(elenco)s.", a_pari="{a_pari}", elenco="{elenco}"
            ),
            "poi": _(", poi %(x)s", x="{x}"),
            "vuota": _(
                "%(a_pari)s i giocatori restano a pari merito.", a_pari="{a_pari}"
            ),
            "finoAl": _("fino al %(n)s°", n="{n}"),
            "su": _("Sposta prima"),
            "giu": _("Sposta dopo"),
            "togli": _("Togli"),
            "meno": _("Un posto in meno"),
            "piu": _("Un posto in più"),
            "aggiungi": _("Aggiungi un criterio"),
            "principaleNota": _("criterio principale"),
            "sorteggioNota": _("sempre ultimo: chiude l'ordine"),
            "nessunAltro": _("Non restano criteri da aggiungere."),
        },
    }


def editor_della_gara(
    livello: str, gara: Any = None, campionato: Any = None, sistema: Any = None
) -> Dict[str, Any]:
    """L'editor di una catena della gara: quella che vale, o la proposta.

    Con la gara, la sua catena (gara → campionato → default); senza, in
    creazione, quella che il campionato propone o il default dell'app.
    """
    from . import catene

    liv = Livello(livello)
    if gara is not None:
        sistema = sistema or getattr(gara, "classification_system", None)
        catena = (
            catene.catena_di_turno(gara)
            if liv is Livello.TURNO
            else catene.catena_di_gara(gara)
        )
    elif campionato is not None:
        from models.campionato.piazzamenti import sistema_delle_gare

        sistema = sistema or sistema_delle_gare(campionato)
        catena = catene.catena_proposta(campionato, liv)
    else:
        catena = None
    return config_editor(livello, catena, sistema)


def editor_del_campionato(
    livello: str, campionato: Any = None, sistema: Any = None
) -> Dict[str, Any]:
    """L'editor di una catena del campionato: le due proposte e la generale."""
    from . import catene

    liv = Livello(livello)
    if campionato is None:
        return config_editor(livello, None, sistema)
    if liv is Livello.CAMPIONATO:
        if not sistema:
            # Un campionato a tabellone è a piazzamenti anche col sistema
            # scritto diverso (ADR-080).
            from models.campionato.piazzamenti import e_a_piazzamenti

            sistema = (
                ClassificationSystem.POSITION.value
                if e_a_piazzamenti(campionato)
                else getattr(campionato, "default_classification_system", None)
            )
        catena = catene.catena_generale(campionato, _sistema(sistema, liv))
    else:
        # Le catene proposte alle gare seguono il sistema delle gare: in un
        # campionato a piazzamenti quello delle serate (ADR-080).
        from models.campionato.piazzamenti import sistema_delle_gare

        sistema = sistema or sistema_delle_gare(campionato)
        catena = catene.catena_proposta(campionato, liv)
    return config_editor(livello, catena, sistema)


__all__ = ["config_editor", "editor_del_campionato", "editor_della_gara"]
