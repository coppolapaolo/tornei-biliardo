"""Comporre una scheda: la pagina, e il modulo che torna indietro (ADR-067).

Il contratto col browser è un modulo normale — liste parallele lette per
posizione, come per l'esame — e non JSON: l'ordine che conta è quello in cui le
voci compaiono nella pagina, e una voce manda **sempre** tutti i suoi campi,
anche vuoti. Basta un campo saltato su una voce perché da lì in poi le liste si
disallineino, e nessuno se ne accorga finché non si rilegge il registro.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask import abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.base import db
from models.challenge.models import Challenge
from models.exceptions import DomainError
from models.training_sheet import (
    MAX_AMOUNT,
    SheetItemSpec,
    SheetMeasure,
    TrainingSheetService,
)
from models.training_sheet.services import MAX_LEVEL, MAX_STREAK, MAX_WEEKS
from utils.route_helpers import http_status_for_exception

from . import sheet_bp


def _mia_o_404(sheet_id: int):
    """La scheda, se è tua. Di un altro non esiste: non è «vietata», non c'è."""
    try:
        sheet = TrainingSheetService.get_sheet(sheet_id)
    except DomainError:
        abort(404)
    if not TrainingSheetService.can_edit(sheet, current_user):
        abort(404)
    return sheet


def _catalogo() -> List[Challenge]:
    """Gli esercizi fra cui pescare: quelli attivi, in ordine di nome.

    Anche quelli con estrazione: una scheda è di una persona sola, quindi il
    motivo per cui un esame li rifiuta — a due candidati uscirebbero consegne
    diverse — qui non c'è.
    """
    esercizi = Challenge.query.filter_by(is_active=True).all()
    return sorted(esercizi, key=lambda c: c.get_display_name().lower())


def _render(sheet, items, *, form=None, status=200):
    return (
        render_template(
            "sheet/compose.html",
            sheet=sheet,
            items=items,
            form=form or {},
            available=_catalogo(),
            measures=list(SheetMeasure),
            max_amount=MAX_AMOUNT,
            max_level=MAX_LEVEL,
            max_streak=MAX_STREAK,
            max_weeks=MAX_WEEKS,
        ),
        status,
    )


@sheet_bp.route("/<int:sheet_id>/componi", methods=["GET"])
@login_required
def compose(sheet_id):
    """La pagina: nome, sequenza, e le opzioni facoltative."""
    sheet = _mia_o_404(sheet_id)
    return _render(sheet, sheet.active_items)


@sheet_bp.route("/<int:sheet_id>/componi", methods=["POST"])
@login_required
def save_composition(sheet_id):
    """Salva tutto insieme: nome, opzioni e sequenza.

    Se qualcosa non va, la pagina torna **com'era stata lasciata**: un redirect
    butterebbe via il lavoro di chi ha appena riordinato dieci voci per un
    numero scritto male.
    """
    sheet = _mia_o_404(sheet_id)
    voci = _items_from_form()
    form = {
        "name": (request.form.get("name") or "").strip(),
        "level": request.form.get("level") or "",
        "threshold": request.form.get("threshold") or "",
        "threshold_streak": request.form.get("threshold_streak") or "",
        "weeks": request.form.get("weeks") or "",
        "has_level": _acceso("has_level"),
        "has_threshold": _acceso("has_threshold"),
        "has_weeks": _acceso("has_weeks"),
        "uses_days": _acceso("uses_days"),
    }

    try:
        TrainingSheetService.save_composition(
            sheet.id,
            current_user,
            name=form["name"],
            items=voci,
            level=_int(form["level"]) if form["has_level"] else None,
            threshold=_int(form["threshold"]) if form["has_threshold"] else None,
            threshold_streak=(
                _int(form["threshold_streak"]) or 1 if form["has_threshold"] else 1
            ),
            weeks=_int(form["weeks"]) if form["has_weeks"] else None,
            uses_days=form["uses_days"],
        )
    except ValueError as errore:
        db.session.rollback()
        flash(str(errore), "error")
        sheet = TrainingSheetService.get_sheet(sheet_id)
        return _render(
            sheet,
            _come_inviate(voci),
            form=form,
            status=http_status_for_exception(errore),
        )

    flash(_("Scheda salvata."), "success")
    return redirect(url_for("sheet.index"))


def _come_inviate(voci: List[SheetItemSpec]) -> List[Dict[str, Any]]:
    """Le voci appena mandate, nella stessa forma che ha una voce salvata.

    Stessi nomi di `TrainingSheetItem` — `challenge`, `measure`, `amount` — così
    il template ne rende una sola specie e non impara che esiste un «dopo un
    errore».
    """
    esercizi = {
        c.id: c
        for c in Challenge.query.filter(
            Challenge.id.in_([voce.challenge_id for voce in voci])
        ).all()
    }
    return [
        {
            "id": voce.item_id,
            "challenge": esercizi[voce.challenge_id],
            "measure": voce.measure.value,
            "measure_kind": voce.measure,
            "amount": voce.amount,
            "per_variant": voce.per_variant,
            "section": voce.section,
            "day": voce.day,
        }
        for voce in voci
        if voce.challenge_id in esercizi
    ]


def _items_from_form() -> List[SheetItemSpec]:
    """Le voci, lette per posizione dalle liste parallele del modulo."""
    challenge_ids = request.form.getlist("challenge_id")
    item_ids = request.form.getlist("item_id")
    measures = request.form.getlist("measure")
    amounts = request.form.getlist("amount")
    per_variants = request.form.getlist("per_variant")
    sections = request.form.getlist("section")
    days = request.form.getlist("day")

    voci: List[SheetItemSpec] = []
    for posizione, grezzo in enumerate(challenge_ids):
        challenge_id = _int(grezzo)
        if challenge_id is None:
            abort(400)
        voci.append(
            SheetItemSpec(
                challenge_id=challenge_id,
                item_id=_int(_alla(item_ids, posizione)),
                measure=SheetMeasure.parse(_alla(measures, posizione)),
                amount=_int(_alla(amounts, posizione)),
                per_variant=_alla(per_variants, posizione) in ("1", "true", "on"),
                section=_alla(sections, posizione),
                day=_alla(days, posizione),
            )
        )
    return voci


def _alla(valori: List[str], posizione: int) -> Optional[str]:
    return valori[posizione] if posizione < len(valori) else None


def _int(grezzo: Optional[str]) -> Optional[int]:
    try:
        return int(str(grezzo).strip())
    except (TypeError, ValueError):
        return None


def _acceso(campo: str) -> bool:
    return request.form.get(campo) in ("1", "true", "on")
