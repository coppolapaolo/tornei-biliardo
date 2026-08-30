"""La vetrina di una gara: quello che vede chi arriva da un post (issue #235).

Tre cose che il direttore decide una volta e che poi vivono nel link che
incolla su WhatsApp o Facebook: la **locandina**, un **link esterno** (il
regolamento, la pagina della sala) e un **indirizzo leggibile**.

Perché un modulo a parte e non due metodi in `GaraService`: sono le uniche
regole di scrittura che questa funzione porta con sé, e sono tre — normalizzare
uno slug, garantirne l'unicità *contro entrambi i modi di indirizzare una
gara*, e rifiutare un link che non è un link. Tenerle insieme è quello che le
rende verificabili senza toccare il database (`normalize_slug` e
`normalize_external_url` sono funzioni pure).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional
from urllib.parse import urlsplit

from models.base import db
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.transaction.manager import transactional

from .models import Gara

#: Un indirizzo più corto non si legge come un nome («`/g/x`» non dice niente e
#: sarebbe solo un modo peggiore di scrivere il token), e uno più lungo non sta
#: su una locandina. Il massimo combacia con la colonna.
SLUG_MIN_LEN = 3
SLUG_MAX_LEN = 60

#: Gli unici schemi che un browser apre come pagina. Senza questo controllo un
#: `javascript:` scritto nel campo diventerebbe codice eseguito nel browser di
#: chiunque apra la vetrina: il link lo mette il direttore, ma un direttore è
#: un utente qualsiasi con un ruolo, non una fonte fidata.
SCHEMI_AMMESSI = ("http", "https")


def normalize_slug(raw: Optional[str]) -> Optional[str]:
    """Da quello che il direttore scrive all'indirizzo che finisce nell'URL.

    «Open di Natale 2026» → `open-di-natale-2026`. Si normalizza invece di
    rifiutare perché chi scrive sta pensando al nome della gara, non a un
    identificatore: chiedergli di digitare i trattini a mano è una richiesta
    che non aggiunge niente.

    Gli accenti si riducono alla lettera base (`città` → `citta`): un URL con
    caratteri non ASCII funziona, ma viaggia percentuato — dettato al telefono
    o stampato su una locandina diventa illeggibile, che è esattamente ciò da
    cui questo campo doveva salvare.

    Restituisce `None` per una stringa vuota: "nessuno slug" è una risposta
    valida, ed è il caso normale.
    """
    if not raw:
        return None

    senza_accenti = (
        unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    )
    ridotto = re.sub(r"[^a-zA-Z0-9]+", "-", senza_accenti).strip("-").lower()
    if not ridotto:
        return None

    if len(ridotto) < SLUG_MIN_LEN:
        raise ValidationError(
            f"L'indirizzo personalizzato deve avere almeno {SLUG_MIN_LEN} caratteri."
        )
    return ridotto[:SLUG_MAX_LEN]


def normalize_external_url(raw: Optional[str]) -> Optional[str]:
    """Il link esterno, o `None`. Solleva se non è un indirizzo web.

    A chi incolla `torneibiliardo.it/regolamento` senza schema lo si aggiunge:
    è quello che fa qualunque browser, e rifiutare sarebbe pedanteria. Tutto
    il resto — `javascript:`, `data:`, `file:` — si rifiuta e si dice perché.
    """
    if not raw or not raw.strip():
        return None

    candidato = raw.strip()
    parti = urlsplit(candidato)

    if not parti.scheme:
        candidato = f"https://{candidato}"
        parti = urlsplit(candidato)

    if parti.scheme not in SCHEMI_AMMESSI:
        raise ValidationError(
            "Il link deve cominciare per http:// o https://: "
            f"«{parti.scheme}:» non è un indirizzo web."
        )
    if not parti.netloc:
        raise ValidationError("Il link non sembra un indirizzo valido.")

    return candidato[:500]


def slug_is_taken(slug: str, gara_id: Optional[int] = None) -> bool:
    """Quello slug è già il nome pubblico di un'altra gara?

    Guarda **entrambe** le colonne che indirizzano una gara. Un token è otto
    caratteri url-safe e può capitare che siano tutti minuscoli: senza questo
    controllo uno slug potrebbe coincidere con il token di un'altra gara, e da
    quel momento lo stesso indirizzo aprirebbe due gare diverse a seconda di
    quale query vince — un difetto che si manifesta una volta ogni molte, cioè
    nel modo peggiore.
    """
    query = Gara.query.filter(db.or_(Gara.slug == slug, Gara.public_token == slug))
    if gara_id is not None:
        query = query.filter(Gara.id != gara_id)
    return db.session.query(query.exists()).scalar()


def resolve_public_identifier(identificatore: str) -> Optional[Gara]:
    """La gara che risponde a `/g/<identificatore>`, per slug o per token.

    Lo slug si cerca per primo perché è quello che il direttore ha scelto di
    pubblicare, ma i due sono mutuamente esclusivi per costruzione (vedi
    `slug_is_taken`), quindi l'ordine non cambia il risultato: cambia solo
    quale delle due query si evita nel caso frequente.
    """
    if not identificatore:
        return None
    per_slug = Gara.query.filter_by(slug=identificatore).first()
    if per_slug is not None:
        return per_slug
    return Gara.query.filter_by(public_token=identificatore).first()


def classifica_gia_calcolata(gara_id: int) -> list:
    """La classifica più recente **già scritta**, senza ricalcolare niente.

    La pagina di gestione, per mostrare la classifica, la ricalcola e la
    salva (`RoundClassification.calculate_classification_after_round`). Qui
    non si può: la vetrina la aprono i crawler dei social e chiunque abbia il
    link, e un ricalcolo per ogni passaggio significherebbe scritture sul
    database innescate da richieste anonime.

    Se nessun turno è ancora stato calcolato la lista è vuota, e la vetrina
    semplicemente non mostra la classifica: è la risposta giusta per una gara
    che non ha ancora prodotto un risultato.

    Si legge `RoundClassification` e non `GaraClassification` perché è quella
    che la pagina della gara mostra davvero — la seconda resta vuota su gare
    che pure hanno una classifica completa, e un podio vuoto sulla vetrina
    sarebbe un difetto senza sintomi.
    """
    from models.classification.models import RoundClassification

    ultimo_turno = (
        db.session.query(db.func.max(RoundClassification.round_number))
        .filter(RoundClassification.gara_id == gara_id)
        .scalar()
    )
    if ultimo_turno is None:
        return []
    return RoundClassification.ordered_for_display(gara_id, ultimo_turno)


@transactional(domain="competition")
def update_gara_showcase(
    gara_id: int,
    slug: Optional[str] = None,
    external_url: Optional[str] = None,
    external_label: Optional[str] = None,
) -> Gara:
    """Salva i campi della vetrina di una gara.

    Un campo vuoto **cancella** il valore: è l'unico modo che il direttore ha
    per togliere un link o rinunciare all'indirizzo personalizzato, e una
    schermata che salva senza toccare nulla riscrive gli stessi valori.
    """
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        raise NotFoundError(f"Gara {gara_id} non trovata")

    nuovo_slug = normalize_slug(slug)
    if nuovo_slug and slug_is_taken(nuovo_slug, gara_id=gara_id):
        raise ConflictError(
            f"L'indirizzo «{nuovo_slug}» è già usato da un'altra gara. "
            "Scegline un altro."
        )

    gara.slug = nuovo_slug
    gara.external_url = normalize_external_url(external_url)
    etichetta = (external_label or "").strip()
    # Un'etichetta senza link non ha dove andare: si scarta invece di
    # persisterla, altrimenti resterebbe in colonna a comparire il giorno in
    # cui qualcuno rimette un indirizzo, con il nome di una pagina diversa.
    gara.external_label = etichetta[:60] if (etichetta and gara.external_url) else None
    return gara


@transactional(domain="competition")
def set_gara_banner(gara_id: int, banner_path: Optional[str]) -> Gara:
    """Attacca (o stacca) la locandina di una gara.

    `None` non lascia la gara senza immagine: la fa **tornare a ereditare**
    quella del campionato, che è ciò che un direttore si aspetta quando toglie
    una grafica speciale da una tappa.
    """
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        raise NotFoundError(f"Gara {gara_id} non trovata")
    gara.banner_path = banner_path
    return gara


@transactional(domain="campionato")
def update_campionato_showcase(
    campionato_id: int,
    external_url: Optional[str] = None,
    external_label: Optional[str] = None,
):
    """Link esterno del campionato, ereditato dalle sue gare."""
    from models.campionato.models import Campionato

    campionato = db.session.get(Campionato, campionato_id)
    if campionato is None:
        raise NotFoundError(f"Campionato {campionato_id} non trovato")

    campionato.external_url = normalize_external_url(external_url)
    etichetta = (external_label or "").strip()
    campionato.external_label = (
        etichetta[:60] if (etichetta and campionato.external_url) else None
    )
    return campionato


@transactional(domain="campionato")
def set_campionato_banner(campionato_id: int, banner_path: Optional[str]):
    """Locandina del campionato: vale per tutte le gare che non ne hanno una."""
    from models.campionato.models import Campionato

    campionato = db.session.get(Campionato, campionato_id)
    if campionato is None:
        raise NotFoundError(f"Campionato {campionato_id} non trovato")
    campionato.banner_path = banner_path
    return campionato
