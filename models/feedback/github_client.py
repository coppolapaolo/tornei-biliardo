"""Il pezzo che parla con GitHub, e l'unico che sa che GitHub esiste.

Sta sulla stdlib (`urllib.request`) e non su `requests`: quella libreria non è
in `requirements.txt`, e `urllib3` ci arriva solo di rimbalzo da `sentry-sdk`
— usarla sarebbe appoggiarsi a una dipendenza che nessuno ha dichiarato. In
cambio ogni chiamata dichiara il suo **timeout**: senza, una richiesta appesa
tiene occupato un worker di PythonAnywhere finché non lo ricicla.

Nessun metodo qui solleva per un guasto di rete: restituiscono un esito che il
chiamante sa leggere. Una segnalazione già salvata non deve perdersi perché
GitHub è in 502, e un job che muore alla prima issue non aggiorna le altre.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: Oltre questo, la richiesta si considera persa. Il valore è alto per una
#: pagina web e basso per un job: qui siamo sempre nel secondo caso, perché
#: nella richiesta HTTP di un utente non si chiama GitHub (vedi il modello).
TIMEOUT_SECONDI = 15

API = "https://api.github.com"
#: La versione dell'API si dichiara: senza header, GitHub è libero di cambiare
#: la forma della risposta sotto i piedi.
VERSIONE_API = "2022-11-28"


class GitHubNonConfigurato(RuntimeError):
    """Il token non c'è. Non è un errore di rete: è una scelta di ambiente."""


@dataclass
class IssueRemota:
    """Ciò che ci serve sapere di una issue, e nulla di più."""

    numero: int
    stato: str
    """`open` o `closed`."""
    motivo_chiusura: Optional[str]
    """`completed`, `not_planned`, o `None` se ancora aperta."""
    etichette: List[str] = field(default_factory=list)
    ha_assegnatario: bool = False
    ha_milestone: bool = False

    @classmethod
    def da_json(cls, dato: Dict[str, Any]) -> "IssueRemota":
        return cls(
            numero=dato["number"],
            stato=dato.get("state", "open"),
            motivo_chiusura=dato.get("state_reason"),
            etichette=[e["name"] for e in dato.get("labels", []) if "name" in e],
            ha_assegnatario=bool(dato.get("assignees") or dato.get("assignee")),
            ha_milestone=dato.get("milestone") is not None,
        )


@dataclass
class Risposta:
    """Esito di una chiamata: o il corpo, o il motivo per cui non c'è."""

    ok: bool
    corpo: Any = None
    errore: Optional[str] = None
    etag: Optional[str] = None
    non_modificato: bool = False
    """304: nulla è cambiato dall'ETag passato. Non è un errore, è un
    risparmio — ed è il motivo per cui l'ETag si conserva fra un giro e
    l'altro."""


class GitHubClient:
    """Chiamate all'API delle issue, con token e repo dati alla costruzione."""

    def __init__(self, token: Optional[str], repo: str) -> None:
        self._token = token
        self._repo = repo

    @property
    def configurato(self) -> bool:
        return bool(self._token and self._repo)

    @classmethod
    def dalla_configurazione(cls) -> "GitHubClient":
        """Costruito dalla config dell'app corrente.

        Le due chiavi arrivano da `Config.environment_settings()`, non dal
        corpo della classe: gli scheduled task caricano le env **dopo**
        l'import, e un valore congelato all'import sarebbe vuoto per sempre.
        """
        from flask import current_app

        return cls(
            token=current_app.config.get("GITHUB_FEEDBACK_TOKEN"),
            repo=current_app.config.get("GITHUB_FEEDBACK_REPO", ""),
        )

    # ── Le due chiamate che servono ────────────────────────────────────────

    def crea_issue(self, titolo: str, corpo: str, etichette: List[str]) -> Risposta:
        """Apre una issue. L'esito porta il numero assegnato."""
        return self._chiama(
            "POST",
            f"/repos/{self._repo}/issues",
            dati={"title": titolo, "body": corpo, "labels": etichette},
        )

    def issue_toccate(
        self,
        etichetta: str,
        da_quando: Optional[str] = None,
        etag: Optional[str] = None,
    ) -> Risposta:
        """Le issue con quell'etichetta toccate dopo `da_quando` (ISO 8601).

        Una chiamata sola per tutta l'app, non una per utente: `since` più
        l'`ETag` del giro precedente rendono il caso normale — «non è
        cambiato niente» — un 304 da poche centinaia di byte.
        """
        parametri = {
            "labels": etichetta,
            "state": "all",
            "per_page": "100",
            # `since` filtra su `updated_at`, che è esattamente la domanda:
            # cosa è stato toccato da quando ho guardato l'ultima volta.
            **({"since": da_quando} if da_quando else {}),
        }
        percorso = f"/repos/{self._repo}/issues?" + urllib.parse.urlencode(parametri)
        return self._chiama("GET", percorso, etag=etag)

    def commenti(self, numero_issue: int) -> Risposta:
        """I commenti di una issue, dal più vecchio."""
        return self._chiama(
            "GET", f"/repos/{self._repo}/issues/{numero_issue}/comments?per_page=100"
        )

    # ── Il trasporto ───────────────────────────────────────────────────────

    def _chiama(
        self,
        metodo: str,
        percorso: str,
        dati: Optional[Dict[str, Any]] = None,
        etag: Optional[str] = None,
    ) -> Risposta:
        if not self.configurato:
            return Risposta(ok=False, errore="token GitHub non configurato")

        intestazioni = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": VERSIONE_API,
            "User-Agent": "tornei-biliardo-feedback",
        }
        if etag:
            intestazioni["If-None-Match"] = etag

        corpo = None
        if dati is not None:
            corpo = json.dumps(dati).encode("utf-8")
            intestazioni["Content-Type"] = "application/json"

        richiesta = urllib.request.Request(
            API + percorso, data=corpo, headers=intestazioni, method=metodo
        )

        try:
            with urllib.request.urlopen(richiesta, timeout=TIMEOUT_SECONDI) as risposta:
                testo = risposta.read().decode("utf-8")
                return Risposta(
                    ok=True,
                    corpo=json.loads(testo) if testo else None,
                    etag=risposta.headers.get("ETag"),
                )
        except urllib.error.HTTPError as errore:
            if errore.code == 304:
                # Non è un guasto: è la risposta giusta quando l'ETag combacia.
                return Risposta(ok=True, non_modificato=True, etag=etag)
            dettaglio = self._dettaglio(errore)
            logger.warning(
                "GitHub ha risposto %s a %s %s: %s",
                errore.code,
                metodo,
                percorso.split("?")[0],
                dettaglio,
            )
            return Risposta(ok=False, errore=f"HTTP {errore.code}: {dettaglio}")
        except Exception as errore:  # rete assente, DNS, timeout, TLS
            logger.warning(
                "Chiamata a GitHub fallita (%s %s): %s",
                metodo,
                percorso.split("?")[0],
                errore,
            )
            return Risposta(ok=False, errore=str(errore)[:400])

    @staticmethod
    def _dettaglio(errore: urllib.error.HTTPError) -> str:
        """Il messaggio di GitHub, quando c'è, invece del codice nudo."""
        try:
            payload = json.loads(errore.read().decode("utf-8"))
        except Exception:
            return errore.reason or "errore sconosciuto"
        messaggio = payload.get("message", "")
        errori = payload.get("errors") or []
        if errori:
            pezzi = [e.get("message") or e.get("code", "") for e in errori]
            messaggio = f"{messaggio} ({'; '.join(p for p in pezzi if p)})"
        return messaggio[:400] or (errore.reason or "errore sconosciuto")
