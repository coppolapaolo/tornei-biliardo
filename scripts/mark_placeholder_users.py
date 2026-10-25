"""Segna non registrati gli utenti storici che hanno giocato ma non sono mai entrati.

    venv/bin/python scripts/mark_placeholder_users.py               # prova, tutti
    venv/bin/python scripts/mark_placeholder_users.py --commit      # scrive, tutti
    venv/bin/python scripts/mark_placeholder_users.py --user-id 42  # prova su uno
    venv/bin/python scripts/mark_placeholder_users.py --user-id 42 57 --commit

Prima dell'ADR-085 chi giocava una serata senza account se lo vedeva creare dal
direttore, con email e password che nessuno ha mai usato. Questi utenti sono
non registrati a tutti gli effetti: segnarli ``is_placeholder`` li rende
riscattabili (ADR-086). I criteri stanno in ``models/user/placeholder_storici.py``.

**Solo le gare vive** (emendamento del 2026-10-25). «Ha giocato» vuol dire
almeno un'iscrizione a una gara non eliminata e non di prova, fuori da un
campionato o dentro uno non eliminato e non di prova (``gara_viva``). Chi è
iscritto solo a gare eliminate non si segna — con ``--user-id`` lo script lo
dice — e la prima gara da cui si ricostruisce il creatore è la prima gara
viva. Il 25/10/2026 la prova generale elencava otto account di prova iscritti
solo a gare eliminate, con «nessun creatore ricostruibile».

**Un utente alla volta.** ``--user-id`` (ripetibile, o con più id) limita lo
script agli utenti dati, per provare su uno prima di farlo su tutti. Si
combina con la prova generale e con ``--commit``. Un utente che non rispetta
i criteri non si segna, e lo script dice **quale** criterio manca.

**Chi l'ha creato** (emendamento del 2026-10-19 all'ADR-086). Insieme al segno
lo script ricostruisce il creatore dalla **prima gara** del giocatore: chi lo
ha iscritto, se è registrato ed è un direttore o l'admin; altrimenti l'unico
direttore della gara. Il creatore va in ``created_by_id`` e confermerà lui il
riscatto. Con più direttori non si scrive niente: il riscatto lo confermano
tutti, e lo calcola l'app. Senza nessuno dei due, conferma l'admin. La prova
generale stampa per ogni utente chi è stato ricostruito e come.

**Si rilancia.** Un utente segnato da una versione precedente dello script,
che il creatore non lo cercava, si completa rilanciandolo: lo script riprende
i non registrati senza creatore e non ancora riscattati, e aggiunge solo il
creatore. Chi il creatore ce l'ha già non si tocca.

⚠️  Segnato non registrato, un utente **non entra più**: il login lo rifiuta
finché qualcuno non lo riscatta. Per questo la prova generale stampa l'elenco
completo, da rivedere prima del ``--commit``. Il segno si toglie a mano
(``is_placeholder = 0``) se qualcuno in elenco l'account lo usa davvero.

⚠️  In produzione va eseguito con la web app su **Disabled** (storage NFS, lock
SQLite inaffidabili), riabilitandola subito dopo.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.prod_env import (  # noqa: E402
    PRODUCTION_REQUIRED,
    bootstrap_and_create_app,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class Esito:
    """Che cosa ha fatto (o farebbe) lo script."""

    #: Id degli utenti segnati non registrati.
    segnati: List[int] = field(default_factory=list)
    #: Id degli utenti a cui è stato scritto il creatore.
    con_creatore: List[int] = field(default_factory=list)
    #: Id degli utenti chiesti con ``--user-id`` e lasciati com'erano.
    scartati: List[int] = field(default_factory=list)


def _descrivi_ricostruzione(ricostruzione: Any) -> str:
    from models.user.placeholder_storici import ModoRicostruzione

    gara = ricostruzione.gara
    nome_gara = f"gara #{gara.id} «{gara.display_name}» del {gara.date}" if gara else ""
    modo = ricostruzione.modo
    if modo is ModoRicostruzione.ISCRIZIONE:
        return (
            f"creatore {ricostruzione.creatore.username} "
            f"(l'ha iscritto alla {nome_gara})"
        )
    if modo is ModoRicostruzione.DIRETTORE_UNICO:
        return (
            f"creatore {ricostruzione.creatore.username} "
            f"(unico direttore della {nome_gara})"
        )
    if modo is ModoRicostruzione.DIRETTORI:
        nomi = ", ".join(u.username for u in ricostruzione.confermatori)
        return (
            f"nessun creatore unico: confermano i direttori della {nome_gara} "
            f"({nomi})"
        )
    return "nessun creatore ricostruibile: conferma l'admin"


def _riga(utente: Any) -> str:
    from models.user.placeholder_storici import iscrizioni_vive

    vive = iscrizioni_vive(utente)
    tutte = len(utente.inscriptions)
    altre = f" (+{tutte - vive} a gare eliminate)" if tutte > vive else ""
    return "#%s %s — %s · creato %s · %s iscrizioni%s%s" % (
        utente.id,
        utente.username,
        utente.full_name or "senza nome e cognome",
        utente.created_at,
        vive,
        altre,
        " · email presente" if utente.email else "",
    )


def elabora(commit: bool = False, user_ids: Optional[Sequence[int]] = None) -> Esito:
    """Il lavoro dello script, dentro un contesto applicativo già aperto.

    Senza ``user_ids`` prende tutti i candidati e tutti i non registrati
    storici ancora senza creatore; con ``user_ids`` solo quelli. Scrive se
    ``commit``, altrimenti annulla tutto alla fine.
    """
    from models import db
    from models.user.claim_service import utente_anche_cancellato
    from models.user.placeholder_storici import (
        candidati_storici,
        completa_creatore,
        criteri_mancanti,
        da_completare,
        segna,
        storici_da_completare,
    )

    esito = Esito()
    if commit:
        logger.info("Le modifiche VERRANNO scritte sul database.")
    else:
        logger.info("PROVA GENERALE: non viene scritto niente.")

    da_segnare: List[Any] = []
    gia_segnati: List[Any] = []
    if user_ids:
        for user_id in dict.fromkeys(user_ids):
            utente = utente_anche_cancellato(user_id)
            if utente is None:
                logger.info("  #%s: non esiste, non si segna.", user_id)
                esito.scartati.append(user_id)
                continue
            if da_completare(utente):
                gia_segnati.append(utente)
                continue
            mancanti = criteri_mancanti(utente)
            if mancanti:
                logger.info(
                    "  #%s %s: non si segna — %s.",
                    utente.id,
                    utente.username,
                    "; ".join(mancanti),
                )
                esito.scartati.append(utente.id)
                continue
            da_segnare.append(utente)
    else:
        da_segnare = candidati_storici()
        gia_segnati = storici_da_completare()

    if not da_segnare and not gia_segnati:
        logger.info("Nessun utente storico da segnare o da completare.")
        db.session.rollback()
        return esito

    if da_segnare:
        logger.info("Utenti mai entrati che hanno giocato: %s", len(da_segnare))
        segna(da_segnare)
        for utente in da_segnare:
            esito.segnati.append(utente.id)
            ricostruzione = completa_creatore(utente)
            if ricostruzione.creatore is not None:
                esito.con_creatore.append(utente.id)
            logger.info("  %s", _riga(utente))
            logger.info("      → %s", _descrivi_ricostruzione(ricostruzione))

    if gia_segnati:
        logger.info(
            "Già segnati non registrati, ancora senza creatore: %s", len(gia_segnati)
        )
        for utente in gia_segnati:
            ricostruzione = completa_creatore(utente)
            if ricostruzione.creatore is not None:
                esito.con_creatore.append(utente.id)
            logger.info("  %s", _riga(utente))
            logger.info("      → %s", _descrivi_ricostruzione(ricostruzione))

    if commit:
        db.session.commit()
        logger.info(
            "Scritto. Segnati non registrati: %s · creatore scritto: %s",
            len(esito.segnati),
            len(esito.con_creatore),
        )
    else:
        db.session.rollback()
        logger.info(
            "Prova generale conclusa, niente scritto. Da segnare: %s · "
            "creatore da scrivere: %s",
            len(esito.segnati),
            len(esito.con_creatore),
        )
    return esito


def esegui(commit: bool = False, user_ids: Optional[Sequence[int]] = None) -> Esito:
    # Nome e cognome sono cifrati: senza la chiave vera l'elenco li
    # mostrerebbe vuoti, e l'admin rivedrebbe la scelta al buio.
    app = bootstrap_and_create_app(required=PRODUCTION_REQUIRED + ("ENCRYPTION_KEY",))
    with app.app_context():
        return elabora(commit=commit, user_ids=user_ids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Segna non registrati gli utenti storici mai entrati."
    )
    parser.add_argument(
        "--commit", action="store_true", help="Scrive le modifiche sul database"
    )
    parser.add_argument(
        "--user-id",
        dest="user_ids",
        type=int,
        nargs="+",
        action="extend",
        metavar="ID",
        help="Solo questi utenti (ripetibile, o più id dopo l'opzione)",
    )
    args = parser.parse_args()
    esegui(commit=args.commit, user_ids=args.user_ids)
