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

_SISTEMI = (ClassificationSystem.WINS, ClassificationSystem.RACK)


def _sistema(valore: Any) -> ClassificationSystem:
    sistema = ClassificationSystem.resolve(valore)
    return sistema if sistema in _SISTEMI else ClassificationSystem.WINS


def _descrizioni(livello: Livello) -> Dict[str, str]:
    """Una riga sotto ogni criterio dell'editor: cosa guarda."""
    campionato = livello is Livello.CAMPIONATO
    return {
        Criterio.SCONTRI_DIRETTI.value: _(
            "fra i pari sta davanti chi vince lo scontro; chi si batte in giro "
            "resta pari"
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
    sis = _sistema(sistema)
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
            s.value: [c.value for c in criteri_ammessi(liv, s)] for s in _SISTEMI
        },
        "principale": {s.value: str(NOMI[criterio_principale(s)]) for s in _SISTEMI},
        "default": {
            s.value: serializza_catena(
                normalizza_catena(catena_di_default(liv, s), liv, s)
            )
            for s in _SISTEMI
        },
        "nomi": {c.value: str(nome) for c, nome in NOMI.items()},
        "descrizioni": _descrizioni(liv),
        "frasi": frasi,
        "aPari": {s.value: _a_pari(s) for s in _SISTEMI},
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
        sistema = sistema or getattr(campionato, "default_classification_system", None)
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
    sistema = sistema or getattr(campionato, "default_classification_system", None)
    if liv is Livello.CAMPIONATO:
        catena = catene.catena_generale(campionato, _sistema(sistema))
    else:
        catena = catene.catena_proposta(campionato, liv)
    return config_editor(livello, catena, sistema)


__all__ = ["config_editor", "editor_del_campionato", "editor_della_gara"]
