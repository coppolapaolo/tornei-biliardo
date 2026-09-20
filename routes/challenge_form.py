"""Il modulo dell'esercizio: una lettura sola per creare, modificare e duplicare.

Le tre route rendono lo stesso template e leggono gli stessi campi: tenerne tre
copie è il modo in cui `edit_challenge` aveva smesso di leggere il punteggio
massimo senza che nessuno se ne accorgesse (#252). Stessa regola di
`GaraFormParser` e `CampionatoFormParser`.

Qui si **legge e si ripulisce**; le regole — quante abilità, che livello, quali
varianti si possono togliere — stanno nei servizi, che le applicano anche a chi
non passa dal modulo.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask_babel import gettext as _

from models.challenge.authoring import (
    ChallengeDraft,
    EvidenceDecisionRequired,
    MeaningChangeKind,
)
from models.challenge.recording import RecordingMode
from models.exceptions import ValidationError


def _getlist(data: Any, key: str) -> List[str]:
    """Una lista da un MultiDict (modulo) come da un dict (JSON)."""
    if hasattr(data, "getlist"):
        return [str(v) for v in data.getlist(key)]
    raw = data.get(key) or []
    if isinstance(raw, (list, tuple)):
        return [str(v) for v in raw]
    return [str(raw)]


def _text(data: Any, key: str) -> str:
    return str(data.get(key) or "").strip()


def _optional_int(data: Any, key: str, error: str) -> Optional[int]:
    grezzo = _text(data, key)
    if not grezzo:
        return None
    try:
        return int(grezzo)
    except (TypeError, ValueError):
        raise ValidationError(error)


def _is_pass_fail(data: Any) -> bool:
    """Il tipo arriva come `scoring_type` dal modulo, `pass_fail_only` dalle API."""
    if data.get("scoring_type"):
        return _text(data, "scoring_type") == "pass_fail"
    return _text(data, "pass_fail_only").lower() == "true"


def _recording_mode(data: Any) -> RecordingMode:
    """«Come si registra» ha tre voci; la terza è un modo, non un tipo."""
    if _text(data, "scoring_type") == RecordingMode.SHOTS.value:
        return RecordingMode.SHOTS
    return RecordingMode.parse(_text(data, "recording_mode"))


def parse_challenge_draft(data: Any) -> ChallengeDraft:
    """La bozza dell'esercizio com'è scritta nel modulo."""
    pass_fail_only = _is_pass_fail(data)
    modo = _recording_mode(data)

    # La casella «attivo» c'è solo in modifica: il segnaposto dice che il campo
    # è stato inviato, così un modulo che non lo mostra non disattiva niente
    # (col vecchio default ogni salvataggio faceva sparire l'esercizio).
    is_active: Optional[bool] = None
    if data.get("is_active_sent"):
        is_active = bool(data.get("is_active"))
    elif data.get("is_active") is not None:
        is_active = _text(data, "is_active").lower() in ("true", "1", "on")

    bianca = _text(data, "cue_ball_reset")
    cue_ball_reset = {"1": True, "0": False}.get(bianca)

    labels = _getlist(data, "variant_label")
    ids = _getlist(data, "variant_id")
    variants: List[Dict[str, Any]] = []
    for posizione, label in enumerate(labels):
        if not label.strip():
            # Una riga lasciata vuota nel modulo non è una variante senza nome.
            continue
        variant_id = ids[posizione] if posizione < len(ids) else ""
        variants.append({"id": variant_id or None, "label": label.strip()})

    return ChallengeDraft(
        title=_text(data, "title"),
        description=_text(data, "description"),
        pass_fail_only=pass_fail_only,
        # Su un esercizio riuscito/non riuscito la casella è nascosta: un valore
        # che arriva lo stesso è un residuo del cambio di tipo a schermo.
        # Colpo per colpo il massimo lo deriva il servizio: anche lì la
        # casella è nascosta.
        max_score=(
            None
            if pass_fail_only or modo.is_sequence
            else _optional_int(
                data, "max_score", _("Il punteggio massimo deve essere un numero")
            )
        ),
        recording_mode=modo.value,
        shots_count=(
            _optional_int(
                data, "shots_count", _("I colpi di una prova devono essere un numero")
            )
            if modo.is_sequence
            else None
        ),
        is_active=is_active,
        abilita=tuple(_getlist(data, "abilita")),
        gesti=tuple(_getlist(data, "gesti")),
        declared_level=_optional_int(
            data, "declared_level", _("Il livello deve essere un numero")
        ),
        family=_text(data, "family") or None,
        family_step=_optional_int(
            data, "family_step", _("Il passo deve essere un numero")
        ),
        cue_ball_reset=cue_ball_reset,
        variants=tuple(variants),
    )


def draft_from_challenge(challenge: Any, *, as_copy: bool = False) -> ChallengeDraft:
    """La bozza con cui il modulo si apre in modifica — o su una copia."""
    title = challenge.title or ""
    if as_copy:
        # Un segno che è una copia, da riscrivere prima di salvare: due
        # esercizi con lo stesso nome nel catalogo non si distinguono.
        title = _("%(title)s (copia)", title=challenge.get_display_name())[:120]
    return ChallengeDraft(
        title=title,
        description=challenge.description or "",
        pass_fail_only=bool(challenge.pass_fail_only),
        max_score=challenge.max_score,
        recording_mode=RecordingMode.parse(challenge.recording_mode).value,
        shots_count=challenge.shots_count,
        is_active=None if as_copy else bool(challenge.is_active),
        abilita=tuple(a.value for a in challenge.abilita),
        gesti=tuple(g.value for g in challenge.gesti),
        declared_level=challenge.declared_level,
        family=challenge.family,
        family_step=challenge.family_step,
        cue_ball_reset=challenge.cue_ball_reset,
        variants=tuple(
            {"id": None if as_copy else v.id, "label": v.label}
            for v in challenge.variants
        ),
    )


def describe_decision(fermo: EvidenceDecisionRequired) -> Dict[str, Any]:
    """Il testo del foglio «ha già delle prove», nella lingua di chi salva."""
    from flask_babel import ngettext

    frasi: List[str] = []
    for cambio in fermo.changes:
        if cambio.kind == MeaningChangeKind.SCORING_TYPE:
            frasi.append(_("Hai cambiato come si registra la prova."))
        elif cambio.kind == MeaningChangeKind.RECORDING_MODE:
            frasi.append(
                _(
                    "Hai cambiato come si registra la prova: da «%(before)s» "
                    "a «%(after)s».",
                    before=cambio.before,
                    after=cambio.after,
                )
            )
        elif cambio.kind == MeaningChangeKind.MAX_SCORE:
            if cambio.before is None:
                frasi.append(
                    _("Hai messo un punteggio massimo: %(after)s.", after=cambio.after)
                )
            elif cambio.after is None:
                frasi.append(
                    _(
                        "Hai tolto il punteggio massimo, che era %(before)s.",
                        before=cambio.before,
                    )
                )
            else:
                frasi.append(
                    _(
                        "Hai cambiato il punteggio massimo, da %(before)s a %(after)s.",
                        before=cambio.before,
                        after=cambio.after,
                    )
                )
        elif cambio.kind == MeaningChangeKind.INSTRUCTIONS:
            frasi.append(_("Hai cambiato le istruzioni."))

    prove = fermo.evidence.attempts
    # Una frase intera per forma: comporla a pezzi («%(quante)s %(di_chi)s si
    # leggerà») non regge l'accordo del verbo, in nessuna lingua.
    conseguenza = ngettext(
        "Se modifichi questo esercizio, la prova già registrata si leggerà con "
        "regole che non sono quelle con cui è stata fatta.",
        "Se modifichi questo esercizio, le %(num)s prove già registrate si "
        "leggeranno con regole che non sono quelle con cui sono state fatte.",
        prove,
    )
    return {
        "title": ngettext(
            "Questo esercizio ha già %(num)s prova",
            "Questo esercizio ha già %(num)s prove",
            prove,
        ),
        "text": " ".join([*frasi, conseguenza]),
        "attempts": prove,
        "players": fermo.evidence.players,
    }
