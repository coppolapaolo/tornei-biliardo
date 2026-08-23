"""La stagione da mettere alla prova, scritta una volta sola.

Questo modulo **non** contiene test: contiene la *specifica* del campionato che
il direttore ha in programma, nella forma in cui i test la useranno. Sta a
parte per una ragione precisa: se la configurazione reale cambia — una
disciplina, una distanza, il numero di qualificati — si cambia qui, e tutti i
test seguono. Ripeterla in ogni file significherebbe che una modifica ne
aggiorna alcuni e ne lascia indietro altri, e i test rimasti indietro
continuerebbero a passare descrivendo un campionato che non esiste.

Il campionato:

* quattro gare **Amalfi**, tre turni ciascuna;
* numero **esatto** di rack, non «al N»: la partita finisce quando i rack
  giocati sono N e vince chi ne ha di più (`exact_number` nel form,
  `is_race_to=False` sul modello);
* dispari gestito **con la X**: chi resta spaiato vince a tavolino
  (`odd_number_policy="bye"`, che nella schermata si chiama «X (vinto a
  tavolino)»);
* minimo 6 iscritti, massimo 15;
* classifica a **vittorie**, spareggio SSR fino al **terzo** posto;
* playoff finale per i **primi 8**.

Le prime tre gare hanno una configurazione uniforme per tutti i turni. La
quarta cambia disciplina e distanza **turno per turno**, e per farlo usa gli
override di ADR-027 (`RoundConfiguration`), che si impostano dopo la creazione
e solo finché la gara è in `setup`. Il playoff ripete la stessa struttura della
quarta.

Le date sono relative a oggi e non alla data vera del campionato: una data
fissa renderebbe i test verdi finché non arriva quel giorno, e poi rossi per
sempre. L'ordine cronologico fra le gare (ADR-016) è quello che conta, ed è
quello che questo modulo garantisce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from models.matchmaking.configuration import MatchmakingStrategy, OddNumberPolicy
from models.status_enum import Discipline

#: Iscritti al completo. Quindici è il massimo consentito, ed è dispari: ogni
#: turno qualcuno prende la X. È il caso che il direttore avrà davvero.
ISCRITTI_AL_COMPLETO = 15

MINIMO_ISCRITTI = 6
MASSIMO_ISCRITTI = 15
TURNI = 3
CLASSIFICA = "WINS"
DISPARI_CON_X = OddNumberPolicy.BYE.value
SPAREGGIO_FINO_A = 3
QUALIFICATI_AL_PLAYOFF = 8

#: Giorni fra una gara e la successiva. Serve solo a tenere l'ordine
#: cronologico che ADR-016 pretende fra gare numerate.
GIORNI_FRA_LE_GARE = 7


@dataclass(frozen=True)
class Turno:
    """La configurazione di un singolo turno, quando diverge da quella di gara."""

    numero: int
    disciplina: str
    distanza: int


@dataclass(frozen=True)
class GaraProgrammata:
    """Una gara del calendario, come il direttore la creerà."""

    numero: int
    nome: str
    disciplina: str
    distanza: int
    #: Override per turno (ADR-027). Vuoto = tutti i turni come la gara.
    turni: tuple[Turno, ...] = field(default_factory=tuple)

    @property
    def data(self) -> str:
        """Una data che rispetta l'ordine cronologico fra le gare numerate."""
        return (
            date.today() + timedelta(days=GIORNI_FRA_LE_GARE * self.numero)
        ).isoformat()

    def disciplina_del_turno(self, numero: int) -> str:
        for turno in self.turni:
            if turno.numero == numero:
                return turno.disciplina
        return self.disciplina

    def distanza_del_turno(self, numero: int) -> int:
        for turno in self.turni:
            if turno.numero == numero:
                return turno.distanza
        return self.distanza


#: I tre turni della quarta gara — e, identici, quelli del playoff.
TURNI_MISTI: tuple[Turno, ...] = (
    Turno(1, Discipline.EIGHT_BALL.value, 5),
    Turno(2, Discipline.NINE_BALL.value, 6),
    Turno(3, Discipline.TEN_BALL.value, 5),
)

CALENDARIO: tuple[GaraProgrammata, ...] = (
    GaraProgrammata(1, "Prima gara", Discipline.EIGHT_BALL.value, 5),
    GaraProgrammata(2, "Seconda gara", Discipline.NINE_BALL.value, 6),
    GaraProgrammata(3, "Terza gara", Discipline.TEN_BALL.value, 5),
    GaraProgrammata(
        4,
        "Quarta gara",
        # La disciplina e la distanza «di gara» restano quelle del primo turno:
        # sono il valore che vale dove non c'è override, e la gara di playoff le
        # eredita da qui (`PlayoffConfiguration.get_gara_params` guarda i campi
        # della gara, non le RoundConfiguration).
        Discipline.EIGHT_BALL.value,
        5,
        turni=TURNI_MISTI,
    ),
)

#: Il form della gara, nella forma in cui la schermata lo manda. Vale per tutte
#: e quattro: quello che cambia da gara a gara è solo disciplina e distanza.
FORM_GARA_STAGIONE: dict[str, str] = {
    "time": "20:00",
    # «esattamente N rack»: la casella c'è, e il suo *esserci* è il segnale
    # (`is_race_to = "exact_number" not in request.form`).
    "exact_number": "1",
    "odd_number_policy": DISPARI_CON_X,
    "first_round_policy": "random",
    "anti_rematch_enabled": "on",
    "rounds_count": str(TURNI),
    "min_participants": str(MINIMO_ISCRITTI),
    "max_participants": str(MASSIMO_ISCRITTI),
    "tiebreaker_enabled": "on",
    "tiebreaker_until_position": str(SPAREGGIO_FINO_A),
    "entry_fee": "0",
    "location": "Sala di prova",
    # Un intero significa «quanti tavoli», non «quale tavolo». Otto tavoli
    # bastano per i sette match di un turno da quindici giocatori.
    "available_tables": "8",
    "withdraw_policy": "forfeit",
}

#: Il passo 1 del wizard del campionato.
FORM_CAMPIONATO_STAGIONE: dict[str, str] = {
    "planned_gare_count": str(len(CALENDARIO)),
    "campionato_type": MatchmakingStrategy.AMALFI.value,
    "default_classification_system": CLASSIFICA,
    "default_rounds_count": str(TURNI),
    "default_odd_policy": DISPARI_CON_X,
    "default_anti_rematch": "on",
    "default_entry_fee": "0",
    "playoff_elite_enabled": "on",
    "playoff_elite_participants": str(QUALIFICATI_AL_PLAYOFF),
}


def crea_stagione(driver: Any, direttore: Any) -> tuple[int, dict[int, int]]:
    """Crea il campionato e le quattro gare come da specifica, senza iscritti.

    Restituisce l'id del campionato e la mappa numero-di-gara → id.

    Gli override per turno della quarta gara si impostano **subito dopo** la
    creazione: la route li accetta solo finché la gara è in `setup`, quindi non
    c'è un momento più tardi in cui farlo.
    """
    driver.entra(direttore)
    campionato_id = driver.crea_campionato(**FORM_CAMPIONATO_STAGIONE)

    gare: dict[int, int] = {}
    for programmata in CALENDARIO:
        opzioni = dict(FORM_GARA_STAGIONE)
        opzioni.update(
            name=programmata.nome,
            date=programmata.data,
            discipline=programmata.disciplina,
            distance=programmata.distanza,
        )
        gara_id = driver.crea_gara_di_campionato(
            campionato_id, programmata.numero, **opzioni
        )
        for turno in programmata.turni:
            esito = driver.configura_turno(
                gara_id,
                turno.numero,
                discipline=turno.disciplina,
                distance=turno.distanza,
                is_race_to=False,
            )
            assert esito.get("success"), esito
        gare[programmata.numero] = gara_id

    return campionato_id, gare
