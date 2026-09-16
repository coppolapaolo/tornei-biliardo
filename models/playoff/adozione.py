"""Adotta come finale del campionato una gara di playoff giocata fuori dall'app.

**Il caso d'uso** (campionato 4, 15/09/2026). La scadenza degli inviti
coincideva con l'orario di gioco: all'apertura della pagina, dieci inviti su
quattordici sono scaduti, e la lista non offriva più nessuna azione al
direttore — un invito scaduto non si accetta e chi lo ha ricevuto «è già in
lista», quindi non si aggiunge nemmeno. Il direttore ha creato una gara
standalone e ci ha giocato la finale in otto. Restano un campionato «in attesa
dei playoff», una gara di playoff vuota e una gara standalone con tutti i
risultati.

**Perché si adotta la gara e non si spostano i risultati.** Le partite, i rack,
il referto, l'ELO e gli XP puntano tutti alla gara **giocata**: spostarli nella
gara vuota vorrebbe dire riscrivere una quindicina di tabelle e ricopiare a
mano turni, strategia, tavoli e configurazioni per turno. Cambiare invece a
chi appartiene la gara è **una riga**: la gara giocata entra nel campionato con
la chiave alla configurazione di playoff, il numero e il peso della finale; la
gara vuota, che non ha nessuna partita, si cancella. Ogni id resta quello che
era.

Cosa fa, in ordine:

1. **valida** — configurazione attiva di un campionato terminato; gara giocata
   standalone e conclusa; gara di playoff esistente senza partite; sistema di
   classifica compatibile con la modalità della finale (SPECIFICHE.md riga
   289); data non anteriore all'ultima gara del campionato (ADR-016); ogni
   iscritto alla gara giocata ha un invito che si può considerare accettato;
2. **accetta gli inviti** di chi ha giocato — quelli in attesa o scaduti
   diventano confermati, registrati da chi esegue (`responded_by_id`, come
   `respond_on_behalf`); chi aveva già accettato resta com'era; chi non ha
   giocato resta com'è;
3. **scarta la gara vuota** — sganciando prima la riga legacy
   `playoff_campionato`, come fa `GaraService.delete_gara`;
4. **adotta la gara giocata** — campionato, numero, configurazione, peso; e
   riporta i campi amministrativi (nome, direttore proprietario, finestra
   iscrizioni, minimo e massimo) a come `create_playoff_gara` li scrive, così
   la gara non si distingue da una finale nata dall'app. Ciò che dice *come si
   è giocato* resta vero;
5. **ricalcola la classifica generale**, che da quel momento somma la finale
   col suo peso. Il campionato risulta «completato» da solo: lo stato si deriva
   dalla gara della configurazione (`compute_campionato_status`).

Non manda notifiche: è una riparazione di dati, non un evento di gioco.

Il punto d'ingresso da console è `scripts/adotta_gara_come_playoff.py`, che è
un dry-run finché non gli si passa `--commit`.
"""

from __future__ import annotations

import logging
from datetime import datetime, time as time_type
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from models.base import db, utc_now
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.transaction.manager import transactional

from .models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffTournament,
    QualificationStatus,
)
from .services import PLAYOFF_MIN_PARTICIPANTS

logger = logging.getLogger(__name__)

#: Stati dell'invito che l'adozione può considerare «ha accettato».
_ACCETTABILI = (
    QualificationStatus.CONFIRMED,
    QualificationStatus.PENDING,
    QualificationStatus.EXPIRED,
)

#: Campi della gara che descrivono *come si gioca*: il confronto fra la gara
#: vuota (ciò che la configurazione avrebbe prodotto) e quella giocata dice al
#: lettore dove le due differiscono, prima che decida.
_CAMPI_CONFRONTO = (
    "name",
    "date",
    "time",
    "discipline",
    "distance",
    "is_race_to",
    "rounds_count",
    "matchmaking_strategy",
    "odd_number_policy",
    "classification_system",
    "has_handicap",
    "min_participants",
    "max_participants",
    "entry_fee",
    "location",
    "director_id",
)


def _ora(gara) -> datetime:
    return datetime.combine(gara.date, gara.time or time_type(20, 0))


class AdozioneGaraGiocata:
    """Fa della gara standalone giocata la finale di playoff del campionato."""

    # ------------------------------------------------------------ ingresso

    @staticmethod
    def plan(
        config_id: int,
        gara_id: int,
        *,
        performed_by_id: int,
        nome: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Inventario di **sola lettura**: cosa cambierebbe, e cosa lo impedisce.

        Esegue le stesse validazioni di `esegui` — quindi solleva sugli stessi
        conflitti — e non tocca nessuna riga.
        """
        return AdozioneGaraGiocata._prepara(
            config_id, gara_id, performed_by_id=performed_by_id, nome=nome
        )

    @staticmethod
    @transactional(domain="playoff")
    def esegui(
        config_id: int,
        gara_id: int,
        *,
        performed_by_id: int,
        nome: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adotta la gara e ricalcola la classifica. Restituisce il resoconto."""
        from ..classification.campionato_classification import ClassificationService
        from ..classification.models import Classification
        from ..competition.models import Gara
        from ..competition.services import GaraService

        report = AdozioneGaraGiocata._prepara(
            config_id, gara_id, performed_by_id=performed_by_id, nome=nome
        )
        config = db.session.get(PlayoffConfiguration, config_id)
        gara = db.session.get(Gara, gara_id)
        assert config is not None and gara is not None  # validati da _prepara
        adesso = utc_now()

        # 2. Gli inviti di chi ha giocato.
        for riga in report["inviti"]:
            if riga["azione"] != "confermato d'ufficio":
                continue
            qualification = db.session.get(PlayoffQualification, riga["invito_id"])
            assert qualification is not None
            # `confirm_participation` accetta solo un invito in attesa: uno
            # scaduto lo si riporta in attesa un istante prima, così a
            # registrare la risposta è lo stesso metodo del giocatore e del
            # direttore, con la stessa firma di chi l'ha data.
            qualification.status = QualificationStatus.PENDING
            qualification.confirm_participation(responded_by_id=performed_by_id)

        # 3. La gara vuota.
        scartata = config.gara
        if scartata is not None:
            GaraService._sgancia_dal_playoff(scartata)
            db.session.delete(scartata)
            db.session.flush()

        # 4. La gara giocata entra nel campionato.
        gara.campionato_id = config.campionato_id
        gara.number = report["numero_assegnato"]
        gara.playoff_config = config
        gara.weight = config.playoff_weight or 1
        for riga in report["allineamenti"]:
            setattr(gara, riga["campo"], riga["a"])

        confermati = PlayoffQualification.query.filter_by(
            configuration_id=config.id, status=QualificationStatus.CONFIRMED
        ).count()
        torneo = PlayoffTournament.query.filter_by(configuration_id=config.id).first()
        if torneo is None:
            torneo = PlayoffTournament(
                configuration_id=config.id,
                name=config.name,
                max_participants=config.max_participants,
            )
            db.session.add(torneo)
        # Come la scrive `create_playoff_gara`, e come sta su ogni altra finale:
        # la riga è legacy, nessuno la porta mai oltre «registration».
        torneo.gara_id = gara.id
        torneo.status = "registration"
        torneo.registration_start = adesso
        torneo.confirmed_participants = confermati
        db.session.flush()

        # 5. La classifica generale, con la finale dentro.
        ClassificationService.invalidate_campionato_cache(config.campionato_id)
        ClassificationService.update_campionato_classification(config.campionato_id)
        db.session.flush()

        report["eseguito"] = True
        report["campionato"]["stato_dopo"] = config.campionato.get_status()
        report["classifica_finale"] = [
            {
                "posizione": r.position,
                "user_id": r.user_id,
                "username": r.user.username if r.user else "?",
                "triangoli": r.total_racks_won,
                "vittorie": r.total_matches_won,
                "gare": r.gare_played,
            }
            for r in Classification.query.filter_by(campionato_id=config.campionato_id)
            .order_by(Classification.position)
            .all()
        ]
        logger.info(
            "Gara %d adottata come finale del campionato %d (config %d)",
            gara.id,
            config.campionato_id,
            config.id,
        )
        return report

    # ---------------------------------------------------------- validazione

    @staticmethod
    def _prepara(
        config_id: int,
        gara_id: int,
        *,
        performed_by_id: int,
        nome: Optional[str],
    ) -> Dict[str, Any]:
        from ..competition.models import Gara, Inscription
        from ..classification.models import Classification
        from ..match.models import Match
        from ..status_enum import GaraStatus, MatchStatus, TournamentStatus
        from ..tiebreaker.models import Tiebreaker
        from ..user.models import User
        from .services import PlayoffService

        if db.session.get(User, performed_by_id) is None:
            raise ConflictError(f"L'utente che esegue ({performed_by_id}) non esiste")

        config = db.session.get(PlayoffConfiguration, config_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")
        if not config.is_active:
            raise ValidationError("La configurazione playoff non è attiva")
        campionato = config.campionato
        if campionato.get_status() != TournamentStatus.AWAITING_PLAYOFF.value:
            raise ValidationError(
                "Il campionato non è in attesa dei playoff "
                f"(stato: {campionato.get_status()})"
            )

        gara = db.session.get(Gara, gara_id)
        if gara is None or gara.is_deleted:
            raise NotFoundError(f"Gara {gara_id} non trovata")
        if gara.campionato_id is not None or gara.playoff_config_id is not None:
            raise ValidationError(
                f"La gara {gara_id} non è standalone: appartiene già a un "
                "campionato o a un playoff"
            )
        if gara.status != GaraStatus.COMPLETED.value:
            raise ValidationError(
                f"La gara {gara_id} non è conclusa (stato: {gara.status})"
            )
        partite = [
            m
            for m in gara.matches
            if MatchStatus.is_finished(m.status) and not m.is_bye
        ]
        if not partite:
            raise ValidationError(f"La gara {gara_id} non ha partite giocate")

        # La finale sommata conta la stessa cosa del campionato (riga 289).
        PlayoffService._verifica_finale_sommabile(config, gara.classification_system)

        scartata = config.gara
        if scartata is not None:
            if scartata.id == gara.id:
                raise ValidationError("La gara è già la finale di questo playoff")
            n_partite = Match.query.filter_by(gara_id=scartata.id).count()
            n_spareggi = Tiebreaker.query.filter_by(gara_id=scartata.id).count()
            if n_partite or n_spareggi:
                raise ConflictError(
                    f"La gara di playoff {scartata.id} ha {n_partite} partite e "
                    f"{n_spareggi} spareggi: non si scarta una gara giocata"
                )

        # ADR-016: la finale è l'ultima gara del campionato, e il controllo di
        # sequenza vede anche le gare soft-eliminate.
        tutte = db.session.scalars(
            select(Gara)
            .where(Gara.campionato_id == campionato.id)
            .execution_options(include_deleted=True)
        ).all()
        altre = [g for g in tutte if scartata is None or g.id != scartata.id]
        ultima = max(altre, key=_ora) if altre else None
        if ultima is not None and _ora(gara) < _ora(ultima):
            raise ConflictError(
                f"La gara {gara.id} ha data {_ora(gara):%d/%m/%Y %H:%M}, anteriore "
                f"alla gara {ultima.number} del campionato "
                f"({_ora(ultima):%d/%m/%Y %H:%M}): la finale è l'ultima (ADR-016)"
            )
        numero = max((g.number for g in altre), default=0) + 1

        # Gli inviti di chi ha giocato.
        inviti = {
            q.user_id: q
            for q in PlayoffQualification.query.filter_by(configuration_id=config.id)
        }
        iscritti = (
            Inscription.query.filter_by(gara_id=gara.id, is_withdrawn=False)
            .order_by(Inscription.id)
            .all()
        )
        righe_inviti: List[Dict[str, Any]] = []
        problemi: List[str] = []
        for iscrizione in iscritti:
            utente = iscrizione.user
            nome_utente = utente.username if utente else f"#{iscrizione.user_id}"
            invito = inviti.get(iscrizione.user_id)
            if invito is None:
                problemi.append(f"{nome_utente}: iscritto senza invito al playoff")
                continue
            if invito.status not in _ACCETTABILI:
                problemi.append(
                    f"{nome_utente}: invito in stato «{invito.status.value}»"
                )
                continue
            if invito.status == QualificationStatus.CONFIRMED:
                azione = "già confermato"
            else:
                azione = "confermato d'ufficio"
            righe_inviti.append(
                {
                    "invito_id": invito.id,
                    "user_id": iscrizione.user_id,
                    "username": nome_utente,
                    "posizione": invito.qualifying_position,
                    "stato": invito.status.value,
                    "azione": azione,
                }
            )
        if problemi:
            raise ConflictError(
                "Non tutti gli iscritti alla gara giocata hanno un invito da "
                "accettare: " + "; ".join(problemi)
            )
        giocanti = {r["user_id"] for r in righe_inviti}
        non_giocanti = [
            {
                "invito_id": q.id,
                "user_id": q.user_id,
                "username": q.user.username if q.user else f"#{q.user_id}",
                "posizione": q.qualifying_position,
                "stato": q.status.value,
            }
            for q in sorted(inviti.values(), key=lambda q: q.qualifying_position)
            if q.user_id not in giocanti
        ]

        # La classifica attesa: triangoli e vittorie della stagione (righe
        # `Classification`, ferme all'ultimo ricalcolo) più la finale col suo
        # peso. Serve a confrontare col foglio del direttore prima di scrivere;
        # l'ordine vero lo dà il ricalcolo, che applica anche gli spareggi.
        peso = 0 if config.decides_final_ranking else (config.playoff_weight or 1)
        finale: Dict[int, Dict[str, int]] = {}
        for m in partite:
            for pid, propri, altrui in (
                (m.player1_id, m.player1_score or 0, m.player2_score or 0),
                (m.player2_id, m.player2_score or 0, m.player1_score or 0),
            ):
                if pid is None:
                    continue
                s = finale.setdefault(pid, {"triangoli": 0, "vittorie": 0})
                s["triangoli"] += propri
                s["vittorie"] += 1 if m.winner_id == pid else 0
        stagione = {
            r.user_id: r
            for r in Classification.query.filter_by(campionato_id=campionato.id)
        }
        sistema = campionato.classification_system.value
        classifica_attesa = []
        for pid in sorted(set(stagione) | set(finale)):
            riga = stagione.get(pid)
            fin = finale.get(pid, {"triangoli": 0, "vittorie": 0})
            tri_stagione = riga.total_racks_won if riga else 0
            vit_stagione = riga.total_matches_won if riga else 0
            utente = riga.user if riga else db.session.get(User, pid)
            classifica_attesa.append(
                {
                    "user_id": pid,
                    "username": utente.username if utente else f"#{pid}",
                    "triangoli_stagione": tri_stagione,
                    "vittorie_stagione": vit_stagione,
                    "triangoli_finale": fin["triangoli"],
                    "vittorie_finale": fin["vittorie"],
                    "atteso": (
                        tri_stagione + peso * fin["triangoli"]
                        if sistema == "RACK"
                        else vit_stagione + peso * fin["vittorie"]
                    ),
                }
            )
        classifica_attesa.sort(key=lambda r: -r["atteso"])

        confronto = []
        if scartata is not None:
            for campo in _CAMPI_CONFRONTO:
                prevista, giocata = getattr(scartata, campo), getattr(gara, campo)
                if prevista != giocata:
                    confronto.append(
                        {"campo": campo, "prevista": prevista, "giocata": giocata}
                    )

        # I campi amministrativi che una finale nativa non ha, o ha diversi,
        # si allineano a ciò che `create_playoff_gara` scrive: la gara adottata
        # non deve distinguersi da una nata dall'app. I campi che dicono *come
        # si è giocato* (distanza, turni, strategia, dispari, handicap, sistema)
        # restano quelli veri, e sede e quota sono fatti: non si toccano.
        valori_nativi = {
            "name": nome or config.name,
            "director_id": None,
            "inscription_start": None,
            "inscription_end": None,
            "min_participants": PLAYOFF_MIN_PARTICIPANTS,
            "max_participants": config.max_participants,
        }
        allineamenti = [
            {"campo": campo, "da": getattr(gara, campo), "a": valore}
            for campo, valore in valori_nativi.items()
            if getattr(gara, campo) != valore
        ]
        co_direttori = [u.username for u in gara.directors]

        return {
            "eseguito": False,
            "campionato": {
                "id": campionato.id,
                "nome": campionato.name,
                "sistema": sistema,
                "stato_prima": campionato.get_status(),
            },
            "config": {
                "id": config.id,
                "nome": config.name,
                "modalita": config.final_ranking_mode,
                "peso": config.playoff_weight,
                "posti": config.max_participants,
                "scadenza_inviti": config.response_deadline,
                "data_prevista": config.scheduled_date,
            },
            "gara_giocata": {
                "id": gara.id,
                "nome": gara.name,
                "nome_nuovo": valori_nativi["name"],
                "data": _ora(gara),
                "stato": gara.status,
                "sistema": gara.classification_system,
                "turni": gara.rounds_count,
                "strategia": gara.matchmaking_strategy,
                "iscritti": len(iscritti),
                "partite": len(partite),
            },
            "gara_scartata": (
                None
                if scartata is None
                else {
                    "id": scartata.id,
                    "nome": scartata.name,
                    "numero": scartata.number,
                    "stato": scartata.status,
                    "iscritti": Inscription.query.filter_by(
                        gara_id=scartata.id
                    ).count(),
                }
            ),
            "confronto": confronto,
            "allineamenti": allineamenti,
            "co_direttori_della_gara": co_direttori,
            "numero_assegnato": numero,
            "peso_applicato": config.playoff_weight or 1,
            "inviti": righe_inviti,
            "inviti_non_giocanti": non_giocanti,
            "classifica_attesa": classifica_attesa,
            "performed_by_id": performed_by_id,
        }
