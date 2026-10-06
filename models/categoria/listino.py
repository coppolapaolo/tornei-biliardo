"""Il listino delle quote per categoria (ADR-079).

«Serie A 30 € · B e C 20 € · Amatori 15 €»: le voci sono le categorie della
competizione con una quota accanto. Il listino appartiene a chi possiede le
categorie — il **campionato**, e allora vale per tutte le sue serate, oppure la
**gara singola** — e si compila nella configurazione dell'uno o dell'altra.

È **solo informazione**. La categoria la assegna il direttore, quindi il
giocatore non vede «la sua» quota: vede il listino. Niente incasso, niente
«ha pagato». Senza listino la gara mostra la quota unica di sempre
(`Gara.entry_fee`).

Tre regole stanno qui:

- **scrivere una voce crea la categoria** (o ritrova, a meno di maiuscole e
  spazi, quella già scritta accanto a un iscritto);
- **togliere una voce non cancella la categoria**: può essere già assegnata a
  qualcuno, quindi esce dal listino (quota a NULL) e resta dov'è;
- **ogni cambio resta nella storia delle modifiche** (ADR-075), con un campo
  solo, ``listino``, che porta prima e dopo per intero.

L'ordine è dalla quota più alta alla più bassa, a parità in ordine alfabetico:
stabile, e leggibile come una locandina.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from models.base import db
from models.exceptions import NotFoundError, ValidationError
from models.shared.naming import clean_display_name, normalize_list_name
from models.transaction.manager import transactional

from .models import MAX_NAME_LENGTH, Categoria

#: Il campo con cui il listino compare nella storia delle modifiche.
CAMPO_STORIA = "listino"

#: Il campo nascosto che dice «questo modulo porta il listino». Senza, un
#: modulo che non mostra l'editor svuoterebbe il listino a ogni salvataggio.
MARCATORE_MODULO = "listino_presente"


@dataclass(frozen=True)
class VoceListino:
    """Una riga del listino come arriva dal modulo."""

    nome: str
    quota: Optional[float]
    #: La categoria già esistente che la riga mostrava: serve a rinominarla.
    categoria_id: Optional[int] = None


@dataclass(frozen=True)
class GruppoListino:
    """Le categorie che pagano la stessa quota: «B e C 20 €»."""

    quota: float
    nomi: Tuple[str, ...]


# ── Di chi è il listino ──────────────────────────────────────────────────


def _proprietario_di(entita: Any) -> Tuple[str, int]:
    """``("campionato", id)`` o ``("gara", id)`` per una gara o un campionato."""
    from models.campionato.models import Campionato

    if isinstance(entita, Campionato):
        return ("campionato", entita.id)
    if getattr(entita, "campionato_id", None):
        return ("campionato", entita.campionato_id)
    return ("gara", entita.id)


def _query(kind: str, owner_id: int):
    if kind == "campionato":
        return Categoria.query.filter_by(campionato_id=owner_id)
    return Categoria.query.filter_by(gara_id=owner_id)


def _del_listino(kind: str, owner_id: int) -> List[Categoria]:
    return (
        _query(kind, owner_id)
        .filter(Categoria.is_active.is_(True), Categoria.entry_fee.isnot(None))
        .order_by(Categoria.entry_fee.desc(), Categoria.normalized_name)
        .all()
    )


def listino_di(entita: Any) -> List[Categoria]:
    """Le voci del listino di una gara (quello del suo campionato) o di un
    campionato, dalla quota più alta. Vuoto se non c'è listino."""
    if entita is None or getattr(entita, "id", None) is None:
        return []
    return _del_listino(*_proprietario_di(entita))


def ha_listino(entita: Any) -> bool:
    if entita is None or getattr(entita, "id", None) is None:
        return False
    kind, owner_id = _proprietario_di(entita)
    return (
        _query(kind, owner_id)
        .filter(Categoria.is_active.is_(True), Categoria.entry_fee.isnot(None))
        .first()
        is not None
    )


def gruppi(voci: Sequence[Categoria]) -> List[GruppoListino]:
    """Le voci raggruppate per quota, nell'ordine del listino."""
    risultato: List[GruppoListino] = []
    for categoria in voci:
        quota = float(categoria.entry_fee or 0)
        if risultato and risultato[-1].quota == quota:
            ultimo = risultato[-1]
            risultato[-1] = GruppoListino(quota, ultimo.nomi + (categoria.name,))
        else:
            risultato.append(GruppoListino(quota, (categoria.name,)))
    return risultato


def gruppi_di(entita: Any) -> List[GruppoListino]:
    """Scorciatoia per i template: il listino di una gara o di un campionato."""
    return gruppi(listino_di(entita))


def formatta_quota(quota: float) -> str:
    """«30», «12.5»: la quota senza decimali inutili."""
    return f"{quota:g}"


# ── La forma nella storia ────────────────────────────────────────────────


def serializza(voci: Sequence[Categoria]) -> str:
    """Il listino come testo per la storia: JSON, nell'ordine del listino.

    Valori grezzi, come ogni riga della storia: si traducono in lettura
    (``models.storia.etichette``).
    """
    if not voci:
        return ""
    return json.dumps(
        [[c.name, float(c.entry_fee or 0)] for c in voci], ensure_ascii=False
    )


def in_parole(grezzo: str) -> str:
    """«Serie A 30 € · Serie B 20 €» dalla forma salvata nella storia."""
    try:
        righe = json.loads(grezzo)
    except (TypeError, ValueError):
        return grezzo
    return " · ".join(
        f"{nome} {formatta_quota(float(quota))} €" for nome, quota in righe
    )


# ── Lettura del modulo ───────────────────────────────────────────────────


def _quota(grezza: str) -> Optional[float]:
    testo = (grezza or "").strip().replace(",", ".")
    if not testo:
        return None
    try:
        quota = float(testo)
    except ValueError:
        raise ValidationError(f"«{grezza}» non è una quota valida")
    if quota < 0:
        raise ValidationError("Una quota non può essere negativa")
    return quota


def leggi_dal_modulo(form: Mapping[str, Any]) -> Optional[List[VoceListino]]:
    """Le righe del listino dal modulo, o ``None`` se il modulo non lo porta.

    Tre liste parallele (``listino_id``, ``listino_nome``, ``listino_quota``):
    le righe senza nome si saltano, la virgola decimale si accetta.
    """
    if not form.get(MARCATORE_MODULO):
        return None
    getlist = getattr(form, "getlist")
    ids = getlist("listino_id")
    nomi = getlist("listino_nome")
    quote = getlist("listino_quota")
    voci: List[VoceListino] = []
    for indice, nome in enumerate(nomi):
        pulito = clean_display_name(nome or "")
        if not pulito:
            continue
        grezzo_id = ids[indice] if indice < len(ids) else ""
        grezza_quota = quote[indice] if indice < len(quote) else ""
        voci.append(
            VoceListino(
                nome=pulito,
                quota=_quota(grezza_quota),
                categoria_id=int(grezzo_id) if str(grezzo_id).isdigit() else None,
            )
        )
    return voci


# ── Scrittura ────────────────────────────────────────────────────────────


class ListinoService:
    """Il listino di una competizione: salvataggio intero o quota di una voce."""

    @staticmethod
    def _registra(kind: str, owner_id: int, prima: str, dopo: str, autore, motivo):
        if prima == dopo:
            return
        from models.storia.models import SettingsChangeSource
        from models.storia.service import StoriaModificheService

        StoriaModificheService.registra(
            cambi={CAMPO_STORIA: (prima, dopo)},
            gara_id=owner_id if kind == "gara" else None,
            campionato_id=owner_id if kind == "campionato" else None,
            autore=autore,
            motivo=motivo,
            provenienza=(
                SettingsChangeSource.CAMPIONATO
                if kind == "campionato"
                else SettingsChangeSource.GARA
            ),
        )

    @staticmethod
    @transactional(domain="categoria")
    def salva(
        *,
        voci: Sequence[VoceListino],
        gara_id: Optional[int] = None,
        campionato_id: Optional[int] = None,
        autore: Any = None,
        motivo: Optional[str] = None,
        nella_storia: bool = True,
    ) -> bool:
        """Sostituisce il listino con queste voci. Torna se è cambiato.

        Le voci con ``categoria_id`` rinominano e riprezzano quella categoria;
        le altre la ritrovano per nome o la creano. Le categorie del listino
        che non compaiono più escono dal listino senza essere cancellate.

        ``nella_storia=False`` alla creazione della gara o del campionato: la
        storia racconta le modifiche, non la nascita.
        """
        if (gara_id is None) == (campionato_id is None):
            raise ValueError("Il listino è di una gara singola o di un campionato")
        if campionato_id is not None:
            kind, owner_id = "campionato", int(campionato_id)
        else:
            kind, owner_id = "gara", int(gara_id or 0)

        visti: Dict[str, VoceListino] = {}
        for voce in voci:
            nome = clean_display_name(voce.nome)
            if not nome:
                continue
            if len(nome) > MAX_NAME_LENGTH:
                raise ValidationError(
                    f"Il nome della categoria supera i {MAX_NAME_LENGTH} caratteri"
                )
            if voce.quota is not None and voce.quota < 0:
                raise ValidationError("Una quota non può essere negativa")
            chiave = normalize_list_name(nome)
            if chiave in visti:
                raise ValidationError(f"«{nome}» compare due volte nel listino")
            visti[chiave] = VoceListino(nome, voce.quota, voce.categoria_id)

        prima = serializza(_del_listino(kind, owner_id))
        tutte = {c.id: c for c in _query(kind, owner_id).all()}
        per_nome = {c.normalized_name: c for c in tutte.values()}
        toccate = set()

        for chiave, voce in visti.items():
            categoria: Optional[Categoria]
            if voce.categoria_id is not None:
                categoria = tutte.get(voce.categoria_id)
                if categoria is None:
                    raise NotFoundError("Categoria non trovata in questa competizione")
                omonima = per_nome.get(chiave)
                if omonima is not None and omonima.id != categoria.id:
                    raise ValidationError(
                        f"La categoria «{omonima.name}» è già in elenco"
                    )
                if categoria.normalized_name != chiave or categoria.name != voce.nome:
                    per_nome.pop(categoria.normalized_name, None)
                    categoria.rename(voce.nome)
                    per_nome[chiave] = categoria
            else:
                categoria = per_nome.get(chiave)
                if categoria is None:
                    categoria = Categoria(
                        name=voce.nome,
                        campionato_id=owner_id if kind == "campionato" else None,
                        gara_id=owner_id if kind == "gara" else None,
                    )
                    db.session.add(categoria)
                    db.session.flush()
                    tutte[categoria.id] = categoria
                    per_nome[chiave] = categoria
            categoria.entry_fee = voce.quota
            categoria.is_active = True
            toccate.add(categoria.id)

        for categoria in tutte.values():
            if categoria.id not in toccate and categoria.entry_fee is not None:
                categoria.entry_fee = None
        db.session.flush()

        dopo = serializza(_del_listino(kind, owner_id))
        if nella_storia:
            ListinoService._registra(kind, owner_id, prima, dopo, autore, motivo)
        return prima != dopo

    @staticmethod
    @transactional(domain="categoria")
    def imposta_quota(
        categoria_id: int, quota: Optional[float], autore: Any = None
    ) -> Categoria:
        """Cambia la quota di una voce sola: è il campo del foglio categorie."""
        categoria = db.session.get(Categoria, categoria_id)
        if categoria is None:
            raise NotFoundError("Categoria non trovata")
        if quota is not None and quota < 0:
            raise ValidationError("Una quota non può essere negativa")
        kind, owner_id = (
            ("campionato", categoria.campionato_id)
            if categoria.campionato_id
            else ("gara", categoria.gara_id)
        )
        prima = serializza(_del_listino(kind, owner_id))
        categoria.entry_fee = quota
        db.session.flush()
        dopo = serializza(_del_listino(kind, owner_id))
        ListinoService._registra(kind, owner_id, prima, dopo, autore, None)
        return categoria


def quota_dal_testo(grezza: Optional[str]) -> Optional[float]:
    """La quota scritta in un campo singolo (il foglio delle categorie)."""
    return _quota(grezza or "")
