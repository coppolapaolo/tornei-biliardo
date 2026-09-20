"""«I tuoi ruoli»: cosa sei, cosa puoi chiedere, cosa stai aspettando.

Una vista di sola lettura, come `models/exam/overview.py`: la route non fa
domande al dominio, riceve delle righe già pronte da stampare.

I ruoli sono di due specie e la pagina non lo nasconde. Il **primario**
(giocatore, direttore, amministratore) è uno solo e non si somma: lo si ha e
basta. I **concedibili** (ADR-041) si sommano, e ciascuno può essere in uno di
quattro momenti — attivo, richiesto, richiedibile, ancora chiuso.

Una regola sola, che vale la pena scrivere: un ruolo concedibile che non si
può chiedere — il beta tester, che lo assegna un amministratore — **compare
solo se lo si ha**. Elencarlo a tutti come «non lo puoi chiedere» significa
mostrare una porta per dire che è murata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set

from flask_babel import gettext as _

from .models import User
from .role_copy import RoleCopy, copy_for
from .role_enum import GrantableRole, UserRole
from .role_grant_service import GRANT_POLICY, RoleGrantService


@dataclass(frozen=True)
class RigaRuolo:
    """Un ruolo come si legge in pagina."""

    codice: str
    nome: str
    descrizione: str
    stato: str
    #: `ok` · `warn` · `muted`: il tono del segnalino, non un colore scritto.
    tono: str
    icona: str = "fa-user"
    dal: Optional[datetime] = None
    #: Valorizzato solo quando il ruolo si può chiedere adesso.
    ruolo_da_chiedere: Optional[GrantableRole] = None
    #: Chi ha concesso il ruolo, quando lo si ha. `None` per il ruolo primario
    #: e per un concedente anonimizzato.
    concesso_da: Optional[str] = None
    #: Valorizzato solo sui ruoli che l'utente **ha**: è la chiave con cui la
    #: pagina offre la catena delle nomine, che vedono i titolari.
    ruolo_posseduto: Optional[GrantableRole] = None
    #: True quando manca solo la progressione: la pagina lo dice invece di
    #: tacere, altrimenti la riga sembrerebbe un vicolo cieco.
    in_arrivo: bool = False


def _riga_primaria(user: User) -> RigaRuolo:
    if user.is_admin:
        nome, descrizione = _("Amministratore"), _("gestisce la piattaforma")
        icona = "fa-shield-halved"
    elif user.is_director:
        nome, descrizione = _("Direttore di gara"), _("organizza gare e campionati")
        icona = "fa-clipboard-list"
    else:
        nome, descrizione = _("Giocatore"), _("si iscrive, gioca e si allena")
        icona = "fa-user"
    return RigaRuolo(
        codice=user.role or UserRole.PLAYER.value,
        nome=nome,
        descrizione=descrizione,
        stato=_("attivo"),
        tono="ok",
        icona=icona,
        dal=user.created_at,
    )


_DESCRIZIONI = {
    GrantableRole.EXAMINER: lambda: _("compone gli esami e li certifica"),
    GrantableRole.INSTRUCTOR: lambda: _("legge le schede che gli allievi gli aprono"),
    GrantableRole.BETA_TESTER: lambda: _("prova le funzioni non ancora aperte"),
}

_ICONE = {
    GrantableRole.EXAMINER: "fa-certificate",
    GrantableRole.INSTRUCTOR: "fa-chalkboard-user",
    GrantableRole.BETA_TESTER: "fa-flask",
}


def _riga_concedibile(user: User, ruolo: GrantableRole) -> Optional[RigaRuolo]:
    grant = RoleGrantService.get_active_grant(user.id, ruolo)
    nome = RoleGrantService.role_label(ruolo)
    descrizione = _DESCRIZIONI.get(ruolo, lambda: "")()
    comune = {
        "codice": ruolo.value,
        "nome": str(nome),
        "descrizione": descrizione,
        "icona": _ICONE.get(ruolo, "fa-user"),
    }

    if grant is not None:
        # Chi ti ha nominato si dice, e si dice **a te**: un ruolo che si
        # propaga a catena senza che il titolare sappia da dove arriva il
        # proprio è una delega al buio (emendamento ADR-041 del 20/09).
        return RigaRuolo(
            **comune,
            stato=_("attivo"),
            tono="ok",
            dal=grant.granted_at,
            concesso_da=(
                grant.granted_by.username
                if grant.granted_by and not grant.granted_by.is_deleted
                else None
            ),
            ruolo_posseduto=ruolo,
        )

    richiesta = RoleGrantService.get_pending_request(user.id, ruolo)
    if richiesta is not None:
        return RigaRuolo(
            **comune,
            stato=_("richiesto"),
            tono="warn",
            dal=richiesta.requested_at,
        )

    codice = RoleGrantService.get_policy(ruolo).request_feature_code
    if codice is None:
        # Non si chiede e non ce l'hai: la riga non esiste.
        return None
    if user.can_access(codice):
        return RigaRuolo(
            **comune,
            stato=_("puoi chiederlo"),
            tono="muted",
            ruolo_da_chiedere=ruolo,
        )
    return RigaRuolo(**comune, stato=_("più avanti"), tono="muted", in_arrivo=True)


def build_roles_view(user: User) -> List[RigaRuolo]:
    """Le righe della pagina «Ruoli», il primario in cima."""
    righe = [_riga_primaria(user)]
    for ruolo in GRANT_POLICY:
        riga = _riga_concedibile(user, ruolo)
        if riga is not None:
            righe.append(riga)
    return righe


# ────────────────────────────────────────────────────────────────────────────
# Le azioni dell'amministrazione
# ────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AzioneRuolo:
    """Un ruolo concedibile come lo vede chi lo assegna."""

    valore: str
    nome: str
    copy: RoleCopy
    #: Se l'utente in questione il ruolo ce l'ha già: decide quale dei due
    #: comandi si mostra.
    posseduto: bool


def azioni_ruoli(
    user: User, titolari: Optional[Dict[str, Set[int]]] = None
) -> List[AzioneRuolo]:
    """I ruoli concedibili con lo stato di ``user``, uno per riga.

    Si ciclano da ``GRANT_POLICY`` e non si scrivono a mano: un ruolo nuovo
    compare dove lo si assegna il giorno stesso in cui entra nel meccanismo.
    Era questo a mancare, e senza il primo titolare la catena non parte.

    ``titolari`` è la mappa ruolo → id dei titolari, per gli elenchi: senza,
    ogni riga costerebbe una query per ruolo (`RoleGrantService.holder_ids`).
    """
    return [
        AzioneRuolo(
            valore=ruolo.value,
            nome=str(RoleGrantService.role_label(ruolo)),
            copy=copy_for(ruolo),
            posseduto=(
                user.id in titolari.get(ruolo.value, set())
                if titolari is not None
                else RoleGrantService.has_role(user.id, ruolo)
            ),
        )
        for ruolo in GRANT_POLICY
    ]


def titolari_per_ruolo() -> Dict[str, Set[int]]:
    """Gli id dei titolari, un ruolo per query. Per gli elenchi lunghi."""
    return {ruolo.value: RoleGrantService.holder_ids(ruolo) for ruolo in GRANT_POLICY}
