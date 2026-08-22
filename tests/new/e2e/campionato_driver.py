"""Driver HTTP per i test end-to-end di un campionato intero.

Estende `GaraDriver` con i gesti che stanno **sopra** la singola gara: il
wizard di creazione, le gare numerate dentro il campionato, la terminazione, e
tutto il percorso dei playoff (avvio, inviti, conferme, lista composta a mano
dal direttore, gara finale).

Vale la stessa divisione di `gara_driver.py` — azioni solo via HTTP,
osservazioni prima dall'HTML e poi dal DB — con un'aggiunta che riguarda solo
questo livello: **le giunzioni**. Un campionato è una catena di stati in cui
ogni anello è già coperto dai suoi test, ciascuno però partendo da uno stato
costruito a mano. `test_avvio_playoff_route.py` scrive `terminated_at` e le
righe di classifica direttamente sul DB; i test dei casi d'uso giocano le gare
ma si fermano prima dei playoff. Fra i due c'è un giunto che nessuno percorre,
ed è esattamente dove è nato il guasto documentato in
`docs/debug20260528.md` (bug 8): `start_playoff` non trovava qualificati
perché la classifica non era mai stata materializzata da nessuno.

Questo driver esiste per percorrere quel giunto.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Any, Sequence

from gara_driver import FORM_GARA_DEFAULT, GaraDriver, Utente

from models import db
from models.campionato.models import Campionato
from models.classification.models import Classification
from models.competition.models import Gara
from models.matchmaking.configuration import MatchmakingStrategy, OddNumberPolicy
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    QualificationStatus,
)

#: Il passo 1 del wizard, come lo manderebbe la schermata. `default_anti_rematch`
#: è una casella di spunta e Amalfi la pretende accesa: il campionato la eredita
#: alle sue gare, quindi spegnerla qui renderebbe increabile ogni gara.
FORM_WIZARD_DEFAULT: dict[str, str] = {
    "planned_gare_count": "4",
    "campionato_type": MatchmakingStrategy.AMALFI.value,
    "default_classification_system": "WINS",
    "default_rounds_count": "3",
    "default_odd_policy": OddNumberPolicy.BYE.value,
    "default_anti_rematch": "on",
    "default_entry_fee": "0",
}

#: I campi che la creazione di una gara *dentro un campionato* manda in più (il
#: numero progressivo) e quelli che invece non manda affatto: la strategia la
#: impone il campionato (`GaraFormParser` legge `camp.campionato_type`), quindi
#: mandarla dal form darebbe l'idea di poterla scegliere per gara.
_CAMPI_SOLO_STANDALONE = ("matchmaking_strategy", "classification_system")


class CampionatoDriver(GaraDriver):
    """Guida un campionato intero attraverso le route, dal wizard ai playoff."""

    # ── Campionato ──────────────────────────────────────────────────

    def crea_campionato(self, **opzioni: Any) -> int:
        """Percorre i due passi del wizard e restituisce l'id del campionato.

        Il wizard tiene il passo 1 **in sessione** e lo rilegge al passo 2: due
        POST separati, come li farebbe il browser. Chiamare solo il secondo
        darebbe «Sessione wizard scaduta», ed è un pezzo di comportamento che
        solo questo percorso mette alla prova.
        """
        dati = dict(FORM_WIZARD_DEFAULT)
        dati.setdefault("name", f"Campionato e2e {uuid.uuid4().hex[:6]}")
        dati.update({chiave: str(valore) for chiave, valore in opzioni.items()})

        passo2 = self.client.post("/admin/campionato/wizard/step2", data=dati)
        assert passo2.status_code == 200, (
            "il passo 1 del wizard è stato rifiutato "
            f"({passo2.status_code}: {passo2.headers.get('Location')})"
        )

        creazione = self.client.post("/admin/campionato/wizard/create", data=dati)
        assert creazione.status_code == 302, "creazione campionato: atteso un redirect"

        trovato = re.search(r"/admin/campionato/(\d+)$", creazione.headers["Location"])
        assert trovato, (
            "la creazione è stata rifiutata: la route rimanda al wizard invece "
            f"che al campionato ({creazione.headers['Location']})"
        )
        return int(trovato.group(1))

    def crea_gara_di_campionato(
        self, campionato_id: int, numero: int, **opzioni: Any
    ) -> int:
        """Crea la gara numero `numero` del campionato. Restituisce il suo id.

        È una route diversa da quella delle gare singole
        (`/admin/gara/create` invece di `/create_standalone`) e legge campi
        diversi: la strategia e il sistema di classifica li prende dal
        campionato, non dal form.
        """
        dati = {
            chiave: valore
            for chiave, valore in FORM_GARA_DEFAULT.items()
            if chiave not in _CAMPI_SOLO_STANDALONE
        }
        dati["campionato_id"] = str(campionato_id)
        dati["number"] = str(numero)
        dati.setdefault("name", f"Gara {numero}")
        dati.setdefault("date", (date.today() + timedelta(days=7)).isoformat())
        dati.update({chiave: str(valore) for chiave, valore in opzioni.items()})

        risposta = self.client.post("/admin/gara/create", data=dati)
        assert risposta.status_code == 302, "creazione gara: atteso un redirect"

        trovato = re.search(r"/admin/gara/(\d+)$", risposta.headers["Location"])
        assert trovato, (
            "la creazione è stata rifiutata: la route rimanda al campionato "
            f"invece che alla gara ({risposta.headers['Location']})"
        )
        return int(trovato.group(1))

    def termina_campionato(self, campionato_id: int) -> Any:
        return self.client.post(
            f"/admin/campionato/{campionato_id}/terminate", follow_redirects=True
        )

    def pagina_campionato(self, campionato_id: int) -> str:
        risposta = self.client.get(f"/admin/campionato/{campionato_id}")
        assert risposta.status_code == 200, f"pagina campionato: {risposta.status_code}"
        return risposta.get_data(as_text=True)

    # ── Il ciclo completo di una gara ───────────────────────────────

    def gioca_gara_intera(
        self,
        gara_id: int,
        direttore: Utente,
        giocatori: Sequence[Utente],
        turni: int,
    ) -> None:
        """Dall'apertura delle iscrizioni alla chiusura, tutti i turni.

        Il `pagina_gara` dopo ogni turno **non è cosmetico**: la classifica di
        turno di Amalfi la scrive `gara_detail`, e senza quella GET il turno
        successivo si rifiuta di partire (vedi
        `test_il_turno_successivo_pretende_che_la_pagina_sia_stata_aperta`).
        """
        self.entra(direttore)
        self.apri_iscrizioni(gara_id)
        self.iscrivi_tutti(gara_id, giocatori)

        self.entra(direttore)
        self.avvia_primo_turno(gara_id)

        for turno in range(1, turni + 1):
            if turno > 1:
                esito = self.avvia_turno(gara_id, turno)
                assert esito["success"] is True, esito.get("error")
            self.gioca_turno(gara_id, turno)
            self.pagina_gara(gara_id)

        self.termina(gara_id)

    def gioca_gara_gia_iscritta(
        self, gara_id: int, direttore: Utente, turni: int
    ) -> None:
        """Come sopra, ma per una gara che ha già i suoi iscritti, e **senza
        chiuderla**.

        È il caso della gara di playoff: nasce in `setup` con dentro i
        qualificati, quindi l'unico passo che resta prima del sorteggio è
        aprire la finestra di iscrizione — che il dominio pretende comunque,
        perché `start_playing` ammette solo `inscription → playing`.

        La chiusura la chiede il test, perché su una finale non è affatto
        scontata: `terminate_gara` la rifiuta se ci sono pari merito da
        spareggiare, e la gara di playoff nasce con lo spareggio acceso.
        """
        self.entra(direttore)
        self.apri_iscrizioni(gara_id)
        self.avvia_primo_turno(gara_id)

        for turno in range(1, turni + 1):
            if turno > 1:
                esito = self.avvia_turno(gara_id, turno)
                assert esito["success"] is True, esito.get("error")
            self.gioca_turno(gara_id, turno)
            self.pagina_gara(gara_id)

    # ── Playoff: il percorso del direttore ──────────────────────────

    def avvia_playoff(self, campionato_id: int) -> str:
        """Il pulsante «avvia playoff»: genera le qualificazioni e invita."""
        risposta = self.client.post(
            f"/admin/campionato/{campionato_id}/start-playoff", follow_redirects=True
        )
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    def aggiungi_al_playoff(
        self, campionato_id: int, config_id: int, utente: Utente
    ) -> str:
        """Il direttore mette un giocatore in lista di sua iniziativa."""
        risposta = self.client.post(
            f"/admin/campionato/{campionato_id}/playoff/{config_id}/add-player",
            data={"user_id": str(utente.id)},
            follow_redirects=True,
        )
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    def rimuovi_dal_playoff(
        self, campionato_id: int, config_id: int, qualificazione_id: int
    ) -> str:
        risposta = self.client.post(
            f"/admin/campionato/{campionato_id}/playoff/{config_id}/remove-player",
            data={"qualification_id": str(qualificazione_id)},
            follow_redirects=True,
        )
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    def crea_gara_playoff(self, campionato_id: int, config_id: int) -> int:
        """Crea la gara di playoff. Restituisce il suo id.

        La route redirige alla gara appena creata; se invece rimanda alla
        pagina del campionato la creazione è stata rifiutata, e il messaggio
        sta nel flash — che qui verrebbe perso, quindi si fallisce subito.
        """
        risposta = self.client.post(
            f"/admin/campionato/{campionato_id}/create-playoff-gara/{config_id}"
        )
        assert risposta.status_code == 302, "gara playoff: atteso un redirect"

        trovato = re.search(r"/admin/gara/(\d+)$", risposta.headers["Location"])
        assert trovato, (
            "la gara di playoff non è stata creata: la route rimanda al "
            f"campionato ({risposta.headers['Location']})"
        )
        return int(trovato.group(1))

    # ── Playoff: il percorso del giocatore ──────────────────────────

    def invito_playoff(self, qualificazione_id: int, utente: Utente) -> Any:
        """La pagina dell'invito, quella che il giocatore apre dalla notifica."""
        self.entra(utente)
        return self.client.get(f"/player/playoff/invitation/{qualificazione_id}")

    def conferma_playoff(self, qualificazione_id: int, utente: Utente) -> Any:
        self.entra(utente)
        return self.client.post(
            f"/player/playoff/confirm/{qualificazione_id}", follow_redirects=True
        )

    def rifiuta_playoff(self, qualificazione_id: int, utente: Utente) -> Any:
        self.entra(utente)
        return self.client.post(
            f"/player/playoff/decline/{qualificazione_id}", follow_redirects=True
        )

    # ── Osservazioni ────────────────────────────────────────────────

    def campionato(self, campionato_id: int) -> Campionato:
        campionato = db.session.get(Campionato, campionato_id)
        assert campionato is not None, f"campionato {campionato_id} inesistente"
        db.session.refresh(campionato)
        return campionato

    def gare_del_campionato(self, campionato_id: int) -> list[Gara]:
        """Le gare vive del campionato, in ordine di numero.

        Le soft-eliminate restano fuori: la terminazione ne cancella alcune
        (quelle mai giocate) e continuare a contarle darebbe un campionato più
        lungo di quello che si è disputato.
        """
        return (
            Gara.query.filter_by(campionato_id=campionato_id)
            .filter(Gara.deleted_at.is_(None))
            .order_by(Gara.number)
            .all()
        )

    def classifica_generale(self, campionato_id: int) -> list[Classification]:
        return (
            Classification.query.filter_by(campionato_id=campionato_id)
            .order_by(Classification.position)
            .all()
        )

    def configurazioni_playoff(self, campionato_id: int) -> list[PlayoffConfiguration]:
        return (
            PlayoffConfiguration.query.filter_by(campionato_id=campionato_id)
            .order_by(PlayoffConfiguration.id)
            .all()
        )

    def qualificazioni(self, config_id: int) -> list[PlayoffQualification]:
        return (
            PlayoffQualification.query.filter_by(configuration_id=config_id)
            .order_by(PlayoffQualification.qualifying_position)
            .all()
        )

    def qualificati_confermati(self, config_id: int) -> list[PlayoffQualification]:
        return [
            qualificazione
            for qualificazione in self.qualificazioni(config_id)
            if qualificazione.status == QualificationStatus.CONFIRMED
        ]

    def iscritti(self, gara_id: int) -> set[int]:
        """Gli id di chi risulta iscritto alla gara (esclusa la lista d'attesa)."""
        from models.competition.models import Inscription

        return {
            inscription.user_id
            for inscription in Inscription.query.filter_by(
                gara_id=gara_id, is_waitlist=False
            ).all()
        }
