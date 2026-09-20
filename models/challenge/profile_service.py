"""Scrivere il profilo di un esercizio: abilità, gesti, livello, varianti (ADR-065).

Sta in un servizio suo e non dentro ``ChallengeService.update_challenge`` perché
risponde a una domanda diversa. Quello cambia **come si valuta** la prova —
punteggio, tetto, istruzioni — cioè cose che riscrivono il senso dei risultati
già registrati, e per questo il modulo chiede se farne una copia. Questo cambia
**come la prova si trova**: descrivere meglio un esercizio non tocca nessun
punteggio passato, e non deve far scattare nessuna domanda.

**Non inviato ≠ vuoto.** Ogni argomento ha per default ``UNSET``: chi passa solo
``abilita`` non azzera livello e varianti. ``None`` (o la lista vuota) invece
vuol dire «toglilo». È la stessa distinzione che ``update_challenge`` fa col
titolo, qui resa esplicita con un segnaposto invece che con la stringa vuota.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Type, Union

from flask_babel import gettext as _

from ..base import db
from ..exceptions import ConflictError, NotFoundError, ValidationError
from ..transaction.manager import transactional
from .models import Challenge, ChallengeAttempt, ChallengeCategory, ChallengeVariant
from .vocabulary import (
    MAX_ABILITA,
    MAX_LEVEL,
    MIN_LEVEL,
    Abilita,
    CategoryAxis,
    Gesto,
)


class _Unset:
    """Segnaposto di «argomento non inviato». Falso, così `if value:` non inganna."""

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:  # pragma: no cover - banale
        return "UNSET"


UNSET = _Unset()

FAMILY_MAX_LENGTH = 80
VARIANT_LABEL_MAX_LENGTH = 40


class ChallengeProfileService:
    """Il profilo dell'esercizio si scrive tutto da qui."""

    @staticmethod
    @transactional(domain="challenge")
    def set_profile(
        challenge_id: int,
        *,
        abilita: Union[Iterable[Any], _Unset] = UNSET,
        gesti: Union[Iterable[Any], _Unset] = UNSET,
        declared_level: Union[Optional[int], _Unset] = UNSET,
        family: Union[Optional[str], _Unset] = UNSET,
        family_step: Union[Optional[int], _Unset] = UNSET,
        cue_ball_reset: Union[Optional[bool], _Unset] = UNSET,
        variants: Union[Sequence[Dict[str, Any]], _Unset] = UNSET,
    ) -> Challenge:
        """Scrive le parti del profilo che arrivano, e lascia stare le altre.

        Args:
            abilita: valori di ``Abilita``; **sostituisce** l'elenco. Al più
                ``MAX_ABILITA``
            gesti: valori di ``Gesto``; sostituisce l'elenco, senza tetto
            declared_level: da 1 a 5, ``None`` per toglierlo
            family: nome libero della progressione; vuoto o di soli spazi vale
                ``None``
            family_step: a che punto della progressione sta; senza famiglia non
                ha senso
            cue_ball_reset: ``True`` la bianca si rimette, ``False`` resta dove
                si ferma, ``None`` non detto
            variants: l'elenco **completo** delle varianti, nell'ordine voluto,
                come ``{"id": ..., "label": ...}``. Con ``id`` si rinomina una
                variante esistente (le sue prove restano sue), senza se ne crea
                una. Chi manca dall'elenco viene tolto — se non ha prove

        Raises:
            NotFoundError: l'esercizio non esiste
            ValidationError: voce fuori vocabolario, troppe abilità, livello
                fuori scala, passo senza famiglia, etichette ripetute
            ConflictError: si sta togliendo una variante che ha già delle prove
        """
        challenge = db.session.get(Challenge, challenge_id)
        if challenge is None:
            raise NotFoundError(_("Esercizio non trovato"))

        if not isinstance(abilita, _Unset):
            voci = _parse_voci(Abilita, abilita)
            if len(voci) > MAX_ABILITA:
                raise ValidationError(
                    _(
                        "Un esercizio allena al più %(max)s abilità",
                        max=MAX_ABILITA,
                    )
                )
            _replace_axis(challenge, CategoryAxis.ABILITA, voci)

        if not isinstance(gesti, _Unset):
            _replace_axis(challenge, CategoryAxis.GESTO, _parse_voci(Gesto, gesti))

        if not isinstance(declared_level, _Unset):
            challenge.declared_level = _parse_level(declared_level)

        if not isinstance(family, _Unset):
            challenge.family = (family or "").strip()[:FAMILY_MAX_LENGTH] or None
        if not isinstance(family_step, _Unset):
            challenge.family_step = _parse_step(family_step)
        # Si guarda lo stato **finale**, non gli argomenti: togliere la famiglia
        # a un esercizio che aveva già un passo è lo stesso errore.
        if challenge.family is None and challenge.family_step is not None:
            if isinstance(family_step, _Unset):
                challenge.family_step = None
            else:
                raise ValidationError(
                    _("Il passo ha senso solo dentro una famiglia di esercizi")
                )

        if not isinstance(cue_ball_reset, _Unset):
            challenge.cue_ball_reset = (
                None if cue_ball_reset is None else bool(cue_ball_reset)
            )

        if not isinstance(variants, _Unset):
            _replace_variants(challenge, variants)
            _refuse_mirror_with_target(challenge)

        return challenge


def copy_profile(originale: Challenge, copia: Challenge) -> None:
    """Porta sulla copia il profilo dell'originale. Le prove e i voti no.

    Una copia è lo stesso esercizio con un'altra storia: che cosa allena, quanto
    è difficile e in quali varianti si fa restano veri; quanti l'hanno provato e
    che voto gli hanno dato sono fatti dell'originale, e la copia parte pulita.

    Non apre una transazione: si chiama da dentro quella di chi sta copiando.
    """
    copia.declared_level = originale.declared_level
    copia.family = originale.family
    copia.family_step = originale.family_step
    copia.cue_ball_reset = originale.cue_ball_reset
    for categoria in originale.categories:
        copia.categories.append(
            ChallengeCategory(axis=categoria.axis, value=categoria.value)
        )
    for variante in originale.variants:
        copia.variants.append(
            ChallengeVariant(
                label=variante.label,
                position=variante.position,
                mirrored=variante.mirrored,
            )
        )


def _refuse_mirror_with_target(challenge: Challenge) -> None:
    """Lo specchio è del **disegno**, e con un bersaglio il disegno è il punteggio.

    Su un esercizio a bersaglio il panno che si tocca è uno, in un sistema di
    coordinate solo: mostrare il disegno ribaltato e chiedere di indicare dove
    si è fermata la bianca sul panno dritto è un modo tranquillo di registrare
    ogni colpo dal lato sbagliato — senza errori, senza segnali, con dei numeri
    plausibili. Meglio dirlo qui, all'autore, che è l'unico che può scegliere
    fra le due cose.

    La strada per ammetterlo c'è ed è scritta nell'ADR-066: specchiare anche il
    bersaglio e riportare il punto toccato nelle coordinate del disegno prima
    di dargli i punti. È un lavoro suo, non un effetto collaterale di questo.
    """
    from .target import target_from_scene

    if not any(v.mirrored for v in challenge.variants):
        return
    if target_from_scene(challenge.diagram_scene) is None:
        return
    raise ValidationError(
        _(
            "Con un bersaglio la variante specchiata non si può usare: "
            "il punteggio discende dal disegno, e il panno da toccare è uno solo"
        )
    )


# ────────────────────────────────────────────────────────────────────────
# Pezzi
# ────────────────────────────────────────────────────────────────────────
def _parse_voci(
    vocabolario: Union[Type[Abilita], Type[Gesto]], grezze: Iterable[Any]
) -> List[str]:
    """Valori validi, senza ripetizioni, nell'ordine del vocabolario."""
    scelte = set()
    for grezza in grezze or []:
        voce = vocabolario.normalize(grezza)
        if voce is None:
            raise ValidationError(
                _("«%(value)s» non è una voce ammessa", value=str(grezza))
            )
        scelte.add(voce.value)
    return [v.value for v in vocabolario if v.value in scelte]


def _replace_axis(challenge: Challenge, axis: CategoryAxis, valori: List[str]) -> None:
    """Porta le righe di un asse a coincidere con ``valori``.

    Si toglie ciò che non c'è più e si aggiunge ciò che manca, invece di
    cancellare tutto e riscrivere: con l'unicità su (esercizio, asse, voce)
    un delete-e-insert della stessa voce nello stesso flush dipende dall'ordine
    in cui SQLAlchemy emette le istruzioni.
    """
    voluti = set(valori)
    presenti = {c.value: c for c in challenge.categories if c.axis == axis.value}
    for valore, riga in presenti.items():
        if valore not in voluti:
            challenge.categories.remove(riga)
    for valore in valori:
        if valore not in presenti:
            challenge.categories.append(
                ChallengeCategory(axis=axis.value, value=valore)
            )


def _parse_level(grezzo: Optional[int]) -> Optional[int]:
    if grezzo is None or grezzo == "":
        return None
    try:
        livello = int(grezzo)
    except (TypeError, ValueError):
        raise ValidationError(_("Il livello deve essere un numero"))
    if not MIN_LEVEL <= livello <= MAX_LEVEL:
        raise ValidationError(
            _(
                "Il livello va da %(min)s a %(max)s",
                min=MIN_LEVEL,
                max=MAX_LEVEL,
            )
        )
    return livello


def _parse_step(grezzo: Optional[int]) -> Optional[int]:
    if grezzo is None or grezzo == "":
        return None
    try:
        passo = int(grezzo)
    except (TypeError, ValueError):
        raise ValidationError(_("Il passo deve essere un numero"))
    if passo < 1:
        raise ValidationError(_("Il passo parte da 1"))
    return passo


def _replace_variants(
    challenge: Challenge, richieste: Sequence[Dict[str, Any]]
) -> None:
    """Porta le varianti a coincidere con l'elenco richiesto, nell'ordine dato."""
    esistenti = {v.id: v for v in challenge.variants}

    etichette: List[str] = []
    viste = set()
    for richiesta in richieste or []:
        etichetta = str(richiesta.get("label") or "").strip()
        if not etichetta:
            raise ValidationError(_("Ogni variante vuole un nome"))
        if len(etichetta) > VARIANT_LABEL_MAX_LENGTH:
            raise ValidationError(
                _(
                    "Il nome di una variante ha al più %(max)s caratteri",
                    max=VARIANT_LABEL_MAX_LENGTH,
                )
            )
        if etichetta.casefold() in viste:
            raise ValidationError(
                _("Due varianti non possono chiamarsi «%(label)s»", label=etichetta)
            )
        viste.add(etichetta.casefold())
        etichette.append(etichetta)

    tenute = set()
    for richiesta in richieste or []:
        grezzo_id = richiesta.get("id")
        if grezzo_id in (None, ""):
            continue
        try:
            variant_id = int(grezzo_id)
        except (TypeError, ValueError):
            raise ValidationError(_("Variante non riconosciuta"))
        if variant_id not in esistenti:
            # L'id di una variante di un altro esercizio, o di una già tolta.
            raise ValidationError(_("Variante non riconosciuta"))
        tenute.add(variant_id)

    for variant_id, variante in esistenti.items():
        if variant_id in tenute:
            continue
        prove = (
            db.session.query(ChallengeAttempt).filter_by(variant_id=variant_id).count()
        )
        if prove:
            # Toglierla lascerebbe le sue prove senza etichetta (SET NULL): i
            # numeri resterebbero, e non si saprebbe più di che lato erano.
            raise ConflictError(
                _(
                    "La variante «%(label)s» ha già %(count)s prove: "
                    "si può rinominare, non togliere",
                    label=variante.label,
                    count=prove,
                )
            )
        challenge.variants.remove(variante)

    # Le etichette sono uniche per esercizio: scambiare «A» e «B» in un colpo
    # solo urterebbe il vincolo a metà del flush. Si passa da nomi provvisori.
    db.session.flush()
    rinominate = [
        (esistenti[int(r["id"])], etichetta)
        for r, etichetta in zip(richieste or [], etichette)
        if r.get("id") not in (None, "")
    ]
    if any(v.label != nuova for v, nuova in rinominate):
        for variante, _nuova in rinominate:
            variante.label = f"\x00{variante.id}"
        db.session.flush()

    for posizione, (richiesta, etichetta) in enumerate(
        zip(richieste or [], etichette), start=1
    ):
        specchiata = bool(richiesta.get("mirrored"))
        if richiesta.get("id") not in (None, ""):
            variante = esistenti[int(richiesta["id"])]
            variante.label = etichetta
            variante.position = posizione
            variante.mirrored = specchiata
        else:
            challenge.variants.append(
                ChallengeVariant(
                    label=etichetta, position=posizione, mirrored=specchiata
                )
            )
