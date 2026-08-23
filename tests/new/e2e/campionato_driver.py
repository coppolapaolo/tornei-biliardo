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
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
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

#: Tetto di sicurezza sul numero di gruppi di spareggio da sciogliere: con lo
#: spareggio fino al terzo posto i gruppi sono al più tre, e un ciclo che non
#: converge è un guasto da far emergere, non da assecondare.
SPAREGGI_AL_MASSIMO = 10


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

    # ── Configurazione per turno (ADR-027) ──────────────────────────

    def configura_turno(
        self, gara_id: int, numero: int, **override: Any
    ) -> dict[str, Any]:
        """Imposta l'override di un turno. Risponde JSON, come il pannello.

        Si può fare **solo in `setup`**: a gara avviata la route risponde 409.
        I campi omessi restano senza override, cioè seguono la gara.
        """
        risposta = self.client.post(
            f"/admin/gara/{gara_id}/round-config/{numero}", json=override
        )
        return {"status": risposta.status_code, **(risposta.get_json() or {})}

    def override_dei_turni(self, gara_id: int) -> dict[int, dict[str, Any]]:
        """Gli override per turno come li rilegge la pagina, per numero di turno."""
        risposta = self.client.get(f"/admin/gara/{gara_id}/round-config")
        assert risposta.status_code == 200, f"round-config: {risposta.status_code}"
        dati = risposta.get_json() or {}
        return {
            configurazione["round_number"]: configurazione
            for configurazione in dati.get("overrides", [])
        }

    # ── Iscrizioni: gli altri pulsanti ──────────────────────────────

    def chiudi_iscrizioni(self, gara_id: int) -> Any:
        return self.client.post(
            f"/admin/gara/{gara_id}/close_inscriptions", follow_redirects=True
        )

    def iscrivi_dal_direttore(self, gara_id: int, utente: Utente) -> str:
        """Il direttore iscrive qualcuno al posto suo (foglio cartaceo, telefonata)."""
        risposta = self.client.post(
            f"/admin/gara/{gara_id}/admin_inscribe",
            data={"user_id": str(utente.id)},
            follow_redirects=True,
        )
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    def cancella_iscrizione(self, gara_id: int, utente: Utente) -> str:
        risposta = self.client.post(
            f"/admin/gara/{gara_id}/admin_uninscribe/{utente.id}",
            follow_redirects=True,
        )
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    def disiscriviti(self, gara_id: int, utente: Utente) -> Any:
        """Il giocatore si toglie da solo, dal suo pulsante."""
        self.entra(utente)
        return self.client.post(
            f"/player/gara/{gara_id}/unsubscribe", follow_redirects=True
        )

    # ── Categorie dell'handicap (ADR-049) ───────────────────────────

    def iscrizione_di(self, gara_id: int, utente: Utente):
        """L'iscrizione di quel giocatore a quella gara."""
        from models.competition.models import Inscription

        iscrizione = Inscription.query.filter_by(
            gara_id=gara_id, user_id=utente.id
        ).first()
        assert iscrizione is not None, f"{utente.username} non è iscritto a {gara_id}"
        return iscrizione

    def assegna_categoria(
        self, gara_id: int, utente: Utente, nome: str
    ) -> dict[str, Any]:
        """Scrive la categoria di un iscritto dal combo accanto al suo nome.

        Il combo manda un **nome**, non un id: se la categoria non esiste
        ancora nasce lì. È ciò che rende «definire l'elenco» e «assegnare» un
        gesto solo. Nome vuoto = togli la categoria.
        """
        iscrizione = self.iscrizione_di(gara_id, utente)
        risposta = self.client.post(
            f"/admin/gara/{gara_id}/inscription/{iscrizione.id}/categoria",
            json={"name": nome},
        )
        return {"status": risposta.status_code, **(risposta.get_json() or {})}

    def categoria_di(self, gara_id: int, utente: Utente) -> str | None:
        """Il nome della categoria dell'iscritto, o `None` se non ne ha."""
        from models.categoria.models import Categoria

        iscrizione = self.iscrizione_di(gara_id, utente)
        if iscrizione.categoria_id is None:
            return None
        categoria = db.session.get(Categoria, iscrizione.categoria_id)
        return categoria.name if categoria else None

    def categorie_della_gara(self, gara_id: int) -> list[str]:
        """I nomi delle categorie disponibili in quella competizione."""
        from models.categoria.service import CategoriaService

        return [
            categoria.name
            for categoria in CategoriaService.list_for_gara(self.gara(gara_id))
        ]

    def elo(self, utente: Utente) -> int | None:
        """Il rating competitivo del giocatore, `None` se non ne ha ancora."""
        from models.user.models import User

        record = db.session.get(User, utente.id)
        assert record is not None
        db.session.refresh(record)
        return record.elo_rating

    # ── Tavoli ──────────────────────────────────────────────────────

    def configura_tavoli(self, gara_id: int, tavoli: str) -> str:
        """I tavoli della gara, in ordine di pregio. Solo fra apertura e avvio."""
        risposta = self.client.post(
            f"/admin/gara/{gara_id}/tables-config",
            data={"available_tables": tavoli},
            follow_redirects=True,
        )
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    def assegna_tavolo(self, match_id: int, tavolo: str | None) -> dict[str, Any]:
        """Assegna, sposta o libera il tavolo di una partita.

        Se il tavolo è già occupato da un'altra partita dello stesso turno il
        service **scambia** le due: è il gesto del direttore che sposta due
        partite, non un errore.
        """
        risposta = self.client.post(
            f"/admin/match/{match_id}/assign-table", json={"table_name": tavolo}
        )
        return {"status": risposta.status_code, **(risposta.get_json() or {})}

    # ── Correzioni ──────────────────────────────────────────────────

    def resetta_match(self, match_id: int) -> Any:
        """Il reset del direttore: la partita torna da giocare."""
        return self.client.post(f"/admin/match/{match_id}/reset", follow_redirects=True)

    def rifiuta_risultato(self, match_id: int, utente: Utente) -> Any:
        """Il «non è andata così» del giocatore: toglie l'ultimo rack."""
        self.entra(utente)
        return self.client.post(f"/player/match/{match_id}/reject")

    # ── Spareggio SSR ───────────────────────────────────────────────

    def avvia_spareggio(self, gara_id: int) -> dict[str, Any]:
        """Apre la fase di spareggio. Risponde JSON se chiamata come il JS."""
        risposta = self.client.post(
            f"/admin/gara/{gara_id}/start_ssr",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        return {"status": risposta.status_code, **(risposta.get_json() or {})}

    def salva_spareggio(
        self, gara_id: int, posizione: int, punteggi: dict[int, int]
    ) -> dict[str, Any]:
        """Salva i punteggi di spareggio di un gruppo di pari merito."""
        risposta = self.client.post(
            f"/admin/gara/{gara_id}/save_ssr_group",
            json={
                "group_position": posizione,
                "scores": {str(k): v for k, v in punteggi.items()},
            },
        )
        return {"status": risposta.status_code, **(risposta.get_json() or {})}

    def risolvi_spareggi(self, gara_id: int) -> int:
        """Apre lo spareggio e assegna a ciascun gruppo punteggi tutti diversi.

        Restituisce quanti gruppi ha risolto — zero se non c'erano pari merito
        da sciogliere. Chi vince lo spareggio non interessa al percorso: conta
        che dopo non restino pari merito e che la gara si possa chiudere.

        Ogni salvataggio rifinalizza la classifica, quindi i gruppi si
        rileggono dalla risposta invece di iterare sull'elenco iniziale, che
        dopo il primo salvataggio può descrivere posizioni diverse.
        """
        avvio = self.avvia_spareggio(gara_id)
        if not avvio.get("success"):
            return 0

        gruppi = avvio.get("ssr_groups") or []
        risolti = 0
        for _ in range(SPAREGGI_AL_MASSIMO):
            gruppo = self._gruppo_da_sciogliere(gruppi)
            if gruppo is None:
                break
            punteggi = {
                giocatore["user_id"]: 100 - indice * 10
                for indice, giocatore in enumerate(gruppo["players"])
            }
            esito = self.salva_spareggio(gara_id, gruppo["position"], punteggi)
            assert esito.get("success"), esito
            risolti += 1
            gruppi = esito.get("ssr_groups") or []
            if esito.get("all_resolved"):
                break
        return risolti

    @staticmethod
    def _gruppo_da_sciogliere(gruppi: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Il primo gruppo in cui manca un punteggio o due sono uguali."""
        for gruppo in gruppi:
            punteggi = [
                giocatore.get("current_ssr_score") for giocatore in gruppo["players"]
            ]
            if any(punteggio is None for punteggio in punteggi):
                return gruppo
            if len(set(punteggi)) < len(punteggi):
                return gruppo
        return None

    def pareggia_match(self, match_id: int) -> None:
        """Chiude una partita in parità, alternando i rack fra i due.

        Ha senso solo in «esattamente N» con N pari — l'unico formato in cui il
        pareggio esiste. Serve a rendere *certi* i pari merito in classifica,
        che altrimenti dipendono dal sorteggio e comparirebbero a giorni
        alterni.
        """
        partita = db.session.get(Match, match_id)
        assert partita is not None, f"partita {match_id} inesistente"
        distanza = partita.distance_config
        assert not distanza.is_race_to_racks, "il pareggio esiste solo a rack esatti"
        assert distanza.racks % 2 == 0, "con N dispari il pareggio è impossibile"

        for indice in range(distanza.racks):
            vincitore = partita.player1_id if indice % 2 == 0 else partita.player2_id
            risposta = self.aggiungi_rack(match_id, vincitore)
            assert risposta.status_code == 200, risposta.get_data(as_text=True)

    def pareggia_turno(self, gara_id: int, numero: int) -> None:
        """Tutte le partite giocabili del turno finiscono in parità."""
        for partita in self.partite(gara_id, turno=numero):
            if partita.is_bye or partita.is_trio:
                continue
            if MatchStatus.is_finished(partita.status):
                continue
            self.pareggia_match(partita.id)

    def chiudi_gara(self, gara_id: int) -> str:
        """Chiude la gara, sciogliendo prima i pari merito se ce ne sono.

        È la sequenza vera del direttore: preme «termina», e se la gara ha lo
        spareggio acceso e dei pari merito nelle posizioni che contano il
        pulsante lo rimanda al percorso SSR. Restituisce lo stato finale della
        gara, così il test può dire se si è chiusa e non solo se non ha dato
        errore.
        """
        self.termina(gara_id)
        if self.gara(gara_id).status != GaraStatus.COMPLETED.value:
            self.risolvi_spareggi(gara_id)
            self.termina(gara_id)
        return self.gara(gara_id).status

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

    def classifica_di_turno(self, gara_id: int, turno: int):
        """La classifica di gara dopo quel turno, in ordine di posizione.

        La scrive `gara_detail`: va letta **dopo** aver aperto la pagina.
        """
        from models.classification.models import RoundClassification

        return (
            RoundClassification.query.filter_by(gara_id=gara_id, round_number=turno)
            .order_by(
                RoundClassification.matches_won.desc(),
                RoundClassification.rack_difference.desc(),
            )
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
