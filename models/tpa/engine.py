"""Motore del referto TPA — regole Accu-Stats, senza database e senza Flask.

Questo modulo e' la traduzione fedele dell'app JS di riferimento
(`TPA-scorekeeper`, https://github.com/coppolapaolo/TPA-scorekeeper). E'
volutamente **puro**: nessun import da Flask o da SQLAlchemy, nessuna I/O. Le
regole di conteggio degli errori sono qui e solo qui; i modelli e i servizi si
limitano a persistere le annotazioni e a rigiocarle da capo.

## Il conto

    TPA = bilie imbucate / (bilie imbucate + errori)

Gli errori sono cinque, come da *Accu-Stats Scoresheet Instructions*:

- **miss** (M): il giocatore vede la bilia designata, prova a imbucare, sbaglia.
  Un errore se il tiro era piu' difficile di un tiro dal dischetto, **due** se
  era piu' facile (la piccola `n`, "no reason").
- **break** (spaccata): battente in buca o fuori dal tavolo sulla spaccata.
- **kick** (K): il giocatore non vede la bilia, e' costretto a un tiro di
  sponda / masse' / jump e non chiude bene.
- **safety** (S): si gioca una difesa e l'avversario, al turno dopo, imbuca
  oppure sbaglia un tiro facile. Se l'avversario entra di sponda alla prima
  bilia (kick-in) la difesa **non** e' un errore.
- **position** (posizione): battente in buca fuori da kick e spaccata, oppure
  almeno una bilia imbucata senza chiudere il rack — salvo le due eccezioni
  annotate, `n` (errore non forzato) e `x` (difesa premeditata).

## Divergenze note dall'esempio del PDF Accu-Stats

La sessione d'esempio del PDF (21 inning) e' riprodotta in
`tests/new/unit/test_tpa_engine.py`. Il punteggio finale combacia (7-2) e cosi'
quasi tutte le categorie, ma **tre voci no**. Sono ereditate dall'app JS e qui
conservate di proposito:

1. **Inning 10** (una bilia, poi kick riuscito ma battente in buca). Il PDF lo
   conta come solo errore di posizione; qui si addebita anche un errore di
   kick, perche' la regola implementata e' "kick che finisce in fallo = errore
   di kick", senza distinguere se la battuta fosse buona. Un errore in piu'.
2. **Inning 4 del giocatore 2** (due bilie imbucate, poi battente in buca
   imbucando la terza). Qui valgono due errori — posizione per le bilie
   imbucate senza chiudere, posizione per il battente in buca — come il PDF
   stesso fa all'inning 14, che e' la stessa situazione. All'inning 4 pero' il
   PDF ne conta uno solo: e' il PDF a contraddirsi, non il motore.
3. **Bilie accreditate al giocatore 1**: 40 qui, 38 nel PDF. Il PDF non dice
   **quali** due non accredita e il referto compilato non e' allegato, quindi
   non c'e' una regola da dedurre: si accredita tutto cio' che il compilatore
   annota.

Cambiare l'una o l'altra cosa significa cambiare i numeri prodotti dall'app JS
con cui i referti esistenti sono stati compilati. Se un giorno si decide di
allinearsi al PDF, va fatto con una migrazione dei referti, non in silenzio.

## Come si verifica

`tests/new/unit/test_tpa_engine_corpus.py` rigioca 600 partite generate a caso
(palla 8, 9 e 10) sull'app JS e pretende gli stessi identici totali, gli stessi
tastierini e gli stessi momenti in cui si puo' passare il tavolo. Se si tocca
una regola qui dentro, quel corpus e' il primo posto dove si vede.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

#: Le cinque famiglie di errore, nell'ordine in cui si mostrano all'utente.
ERROR_KINDS = ("miss", "break", "kick", "safety", "position")

#: Discipline per cui il referto TPA e' definito, mappate sul numero di bilie
#: del rack. E' l'unico posto che sa tradurre disciplina -> conteggio bilie.
GAME_TYPE_BY_DISCIPLINE = {
    "8_ball": 8,
    "9_ball": 9,
    "10_ball": 10,
}


class TpaButton:
    """Identificatori dei comandi del tastierino, come nell'app JS.

    I numeri sono ``"0"``..``"10"``; le lettere hanno il significato del
    referto cartaceo. Sono stringhe e non un enum perche' arrivano cosi' dal
    client e finiscono cosi' nel log delle annotazioni.
    """

    MISS = "M"
    KICK = "K"
    SAFETY = "S"
    POCKET_FOUL = "P"
    NO_HIT_FOUL = "N"
    GAME = "G"
    NO_REASON = "n"
    PLANNED_SAFETY = "x"
    PUSH_OUT = "p"
    KICK_IN = "K-in"
    RUNOUT = "runout"

    LETTERS = frozenset(
        {
            MISS,
            KICK,
            SAFETY,
            POCKET_FOUL,
            NO_HIT_FOUL,
            GAME,
            NO_REASON,
            PLANNED_SAFETY,
            PUSH_OUT,
            KICK_IN,
            RUNOUT,
        }
    )

    @staticmethod
    def is_valid(button: str) -> bool:
        if button in TpaButton.LETTERS:
            return True
        return button.isdigit() and 0 <= int(button) <= 10


@dataclass
class TpaAnnotation:
    """Cosa e' successo in una visita al tavolo.

    ``None`` non e' zero: significa "non ancora annotato". La distinzione
    guida il tastierino (quali pulsanti mostrare) e non solo il conteggio.
    """

    total_potted: Optional[int] = None
    break_potted: Optional[int] = None
    miss_errors: Optional[int] = None  # 0, 1 oppure 2 (la piccola `n`)
    kick: Optional[bool] = None
    pocketed: Optional[bool] = None  # fallo P: battente in buca / fuori
    safety: Optional[bool] = None
    push: Optional[bool] = None  # la piccola `p`: push out
    safe_x: Optional[bool] = None  # la piccola `x`: difesa premeditata
    no_hit: Optional[bool] = None  # fallo N: bilia designata non colpita
    run_out: Optional[bool] = None  # conferma manuale del run-out ambiguo
    #: Kick-in alla **prima** bilia del turno. L'app JS registra solo questo
    #: caso (gli altri kick-in non cambiano nessun conteggio), quindi qui e'
    #: un booleano e non la lista del referto cartaceo.
    first_shot_kick_in: bool = False

    def balls_annotated(self) -> bool:
        return self.total_potted is not None

    def main_note(self) -> str:
        """La lettera grande della casella bianca (M / K / S), con l'apice."""
        if self.kick:
            return "K"
        if self.safety:
            if self.safe_x:
                return "S^x"
            if self.push:
                return "S^p"
            return "S"
        if self.miss_errors == 2:
            return "M^n"
        if self.miss_errors == 1:
            return "M"
        return ""

    def secondary_note(self) -> str:
        """La lettera della casella ombreggiata: il fallo."""
        if self.no_hit:
            return "N"
        if self.pocketed:
            return "P"
        return ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TurnState:
    """Una visita al tavolo."""

    player: int  # 1 oppure 2
    break_turn: bool
    balls_remaining: int
    annotation: TpaAnnotation = field(default_factory=TpaAnnotation)
    pushed: bool = False
    winning_turn: bool = False
    previous_turn: Optional["TurnState"] = None
    consecutive_errors: int = 0
    #: Il punteggio corrente subito dopo questo turno, per la riga di riepilogo
    #: che il referto cartaceo scrive a fine rack.
    score_snapshot: Optional[Dict[int, Dict[str, Any]]] = None

    def is_break(self) -> bool:
        return self.break_turn

    def is_break_shot(self) -> bool:
        """Spaccata in cui non si e' imbucato nulla **oltre** la spaccata."""
        return (
            self.is_break()
            and self.annotation.total_potted == self.annotation.break_potted
        )

    def push(self) -> None:
        self.pushed = True

    def is_pushed(self) -> bool:
        return self.pushed

    def set_winning_turn(self) -> None:
        self.winning_turn = True

    def is_winning(self) -> bool:
        """Vero se il turno chiude il rack.

        Come nell'originale JS **memorizza**: una volta vero resta vero. Un
        turno che parte con zero bilie sul tavolo, o che le imbuca tutte, vince
        senza bisogno che il compilatore prema `G`.
        """
        if not self.winning_turn:
            if self.balls_remaining == 0 or (
                self.annotation.total_potted is not None
                and self.balls_remaining == self.annotation.total_potted
            ):
                self.winning_turn = True
        return self.winning_turn

    def has_been_played(self) -> bool:
        return self.annotation.balls_annotated()


@dataclass
class PlayerTally:
    """Il conto corrente di un giocatore dentro un referto."""

    racks_won: int = 0
    balls_potted: int = 0
    miss_errors: int = 0
    break_errors: int = 0
    kick_errors: int = 0
    safety_errors: int = 0
    position_errors: int = 0
    run_outs: int = 0
    break_and_runs: int = 0
    perfect_racks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["total_errors"] = total_errors(self)
        data["tpa"] = tpa_score(self)
        return data


def total_errors(tally: PlayerTally) -> int:
    return (
        tally.miss_errors
        + tally.break_errors
        + tally.kick_errors
        + tally.safety_errors
        + tally.position_errors
    )


def tpa_score(tally: PlayerTally) -> Optional[int]:
    """Il TPA in millesimi (``780`` = ``.780``), oppure ``None`` se non c'e'.

    Millesimi interi e **troncati**, non arrotondati: e' la convenzione
    Accu-Stats, la stessa di una media di battuta nel baseball.
    """
    denominator = tally.balls_potted + total_errors(tally)
    if denominator == 0:
        return None
    return int(tally.balls_potted / denominator * 1000)


class TpaState:
    """Lo stato di un referto: i rack, i turni e il conto dei due giocatori.

    E' la traduzione della classe ``Match`` dell'app JS, tolta la parte di
    interfaccia. Non sa nulla del database: chi persiste ricostruisce lo stato
    rigiocando le annotazioni dall'inizio (vedi ``TpaRefertoService``).
    """

    def __init__(self, game_type: int) -> None:
        if game_type not in (8, 9, 10):
            raise ValueError(f"Disciplina senza referto TPA: {game_type}")
        self.game_type = game_type
        self.score: Dict[int, PlayerTally] = {1: PlayerTally(), 2: PlayerTally()}
        # Indice 0 non usato: i rack e i turni si contano da 1, come sul
        # referto cartaceo. Costa un None e risparmia una vita di off-by-one.
        self.racks: List[Optional[List[Optional[TurnState]]]] = [None]
        self.current_rack = 1
        self.current_turn = 1
        self.current_player = 1
        self.rack_errors: Dict[int, int] = {1: 0, 2: 0}
        self.racks.append([None, TurnState(self.current_player, True, game_type)])

    # ------------------------------------------------------------------
    # Accesso ai turni
    # ------------------------------------------------------------------

    def turns(self, rack_number: Optional[int] = None) -> List[TurnState]:
        """I turni giocati di un rack, senza il segnaposto in testa."""
        rack = self.racks[rack_number if rack_number is not None else self.current_rack]
        assert rack is not None
        return [t for t in rack[1:] if t is not None]

    def get_turn(self, offset: int = 0) -> Optional[TurnState]:
        """Il turno corrente, o quello a ``offset`` turni indietro nel rack."""
        rack = self.racks[self.current_rack]
        assert rack is not None
        index = self.current_turn + offset
        if index < 1 or index >= len(rack):
            return None
        return rack[index]

    def turn(self) -> TurnState:
        """Il turno corrente. Esiste sempre: lo stato non e' mai senza turno."""
        current = self.get_turn()
        assert current is not None
        return current

    # ------------------------------------------------------------------
    # Annotazione
    # ------------------------------------------------------------------

    def annotate(self, button: str) -> None:
        """Applica un comando del tastierino al turno corrente."""
        turn = self.turn()
        note = turn.annotation

        if button.isdigit():
            value = int(button)
            if value == 0:
                note.total_potted = 0
                if turn.is_break() and note.break_potted is None:
                    note.break_potted = 0
            elif turn.is_break() and note.break_potted is None:
                note.break_potted = value
            else:
                note.total_potted = value
            return

        if button == TpaButton.MISS:
            note.miss_errors = 1
            note.safety = False
            note.kick = False
        elif button == TpaButton.KICK:
            note.kick = True
            note.miss_errors = 0
            note.safety = False
        elif button == TpaButton.SAFETY:
            note.safety = True
            note.kick = False
            note.miss_errors = 0
        elif button == TpaButton.GAME:
            turn.set_winning_turn()
        elif button == TpaButton.POCKET_FOUL:
            note.pocketed = True if note.pocketed is None else not note.pocketed
            note.no_hit = False
        elif button == TpaButton.NO_HIT_FOUL:
            note.no_hit = True if note.no_hit is None else not note.no_hit
            note.pocketed = False
        elif button == TpaButton.NO_REASON:
            # La piccola `n`: il tiro sbagliato era piu' facile di un tiro dal
            # dischetto. Vale doppio, e toglie l'errore di posizione.
            note.miss_errors = 1 if note.miss_errors == 2 else 2
        elif button == TpaButton.PLANNED_SAFETY:
            note.safe_x = True if note.safe_x is None else not note.safe_x
            note.push = False
        elif button == TpaButton.PUSH_OUT:
            note.push = True if note.push is None else not note.push
            turn.pushed = bool(note.push)
            note.safe_x = False
        elif button == TpaButton.KICK_IN:
            note.first_shot_kick_in = True
        elif button == TpaButton.RUNOUT:
            note.run_out = not (note.run_out is True)
        else:
            raise ValueError(f"Comando di referto sconosciuto: {button}")

    # ------------------------------------------------------------------
    # Fine turno
    # ------------------------------------------------------------------

    def can_switch_player(self) -> bool:
        """Se il tavolo puo' passare all'altro giocatore in questo momento.

        Un turno a meta' annotazione non si chiude: manca ancora il perche'
        il giocatore ha lasciato il tavolo.
        """
        turn = self.turn()
        note = turn.annotation
        if not turn.has_been_played():
            return turn.is_break() and note.break_potted is None
        if turn.is_winning():
            return True
        if turn.is_break() and note.break_potted == 0 and note.total_potted == 0:
            return True
        if (
            turn.is_break()
            and (note.break_potted or 0) > 0
            and note.total_potted == 0
            and (note.no_hit or note.pocketed)
        ):
            return True
        if not (
            note.kick or note.safety or note.miss_errors or note.pocketed or note.no_hit
        ):
            return False
        return True

    def can_choose_seat(self) -> bool:
        """Se ora il tocco sull'avversario sceglie **chi spacca**.

        Vale solo sul turno di spaccata e solo finche' non e' stato annotato
        niente — nemmeno le bilie della spaccata. Dopo, quel tocco chiude il
        turno, e chi spacca non si cambia piu': il rack e' cominciato.

        La condizione e' la stessa del primo ramo di `can_switch_player`, ed e'
        qui perche' la usano in due — il tastierino per sapere che comando
        mandare, il servizio per validare quello che riceve. Duplicarla
        vorrebbe dire lasciarle divergere.
        """
        turn = self.turn()
        return (
            turn.is_break()
            and not turn.has_been_played()
            and turn.annotation.break_potted is None
        )

    def toggle_player(self) -> None:
        """Passa il tavolo: chiude il turno corrente e ne apre uno nuovo.

        Sul primo turno di un rack, se nessuno ha ancora annotato nulla, non
        chiude niente: cambia solo chi spacca.
        """
        self.current_player = 2 if self.current_player == 1 else 1
        turn = self.turn()

        if not turn.has_been_played() and turn.is_break():
            turn.player = self.current_player
            return

        self.update_score(turn)
        # Tre falli di fila: in palla 9 e palla 10 il rack e' dell'avversario.
        # In palla 8 la regola non esiste.
        triple_foul = self.game_type != 8 and turn.consecutive_errors >= 3
        turn.score_snapshot = {
            player: tally.to_dict() for player, tally in self.score.items()
        }

        if turn.is_winning():
            self.detect_rack_achievements(turn)
            self.racks.append([None])
            self.current_rack += 1
            self.current_turn = 1
            self.rack_errors = {1: 0, 2: 0}
            rack = self.racks[self.current_rack]
            assert rack is not None
            rack.append(TurnState(self.current_player, True, self.game_type))
            return

        note = turn.annotation
        balls_remaining = turn.balls_remaining - max(
            note.total_potted or 0, note.break_potted or 0
        )
        # Caso di scuola: tutte le bilie sulla spaccata e battente in buca.
        if note.break_potted == self.game_type and note.total_potted == 0:
            balls_remaining = 1

        previous = turn.previous_turn
        pushed = turn.is_pushed() and (
            turn.is_break()
            or (
                previous is not None
                and previous.is_break()
                and previous.annotation.total_potted == 0
                and note.total_potted == 0
            )
        )

        self.current_turn += 1
        rack = self.racks[self.current_rack]
        assert rack is not None
        if self.game_type == 8:
            # Palla 8: ogni giocatore ha il **suo** gruppo, quindi le bilie che
            # gli restano dipendono dal proprio turno precedente, non da quello
            # dell'avversario.
            if self.current_turn < 3:
                next_remaining = 8
            else:
                own_previous = rack[self.current_turn - 2]
                assert own_previous is not None
                next_remaining = own_previous.balls_remaining - (
                    own_previous.annotation.total_potted or 0
                )
        else:
            next_remaining = balls_remaining
        rack.append(TurnState(self.current_player, False, next_remaining))

        new_turn = self.turn()
        new_turn.previous_turn = rack[self.current_turn - 1]
        if pushed:
            new_turn.push()
        if triple_foul:
            # Equivale a premere `0` e poi `G`: il rack va all'avversario
            # senza che tocchi il tavolo.
            new_turn.annotation.total_potted = 0
            new_turn.set_winning_turn()

    # ------------------------------------------------------------------
    # Il conto degli errori
    # ------------------------------------------------------------------

    def update_score(self, turn: TurnState) -> None:
        """Registra bilie ed errori del turno appena chiuso.

        L'errore di **safety** e' l'unico che non si addebita a chi ha appena
        giocato: si scopre solo al turno dopo, guardando come e' andata
        all'avversario, e va a carico di chi la difesa l'ha giocata.
        """
        note = turn.annotation
        tally = self.score[turn.player]

        if turn.is_winning():
            tally.racks_won += 1

        if note.miss_errors:
            tally.miss_errors += note.miss_errors

        # Fallo sulla spaccata. Se pero' il giocatore aveva gia' imbucato
        # altre bilie dopo la spaccata, l'errore e' di posizione: la spaccata
        # era riuscita, e' il resto del turno ad essere andato storto.
        if turn.is_break() and (note.pocketed or note.no_hit):
            no_extra_balls = (note.total_potted or 0) <= (note.break_potted or 0)
            if no_extra_balls:
                tally.break_errors += 1
            else:
                tally.position_errors += 1

        if note.kick and (note.no_hit or note.pocketed):
            tally.kick_errors += 1

        # Errore di difesa, a carico del turno precedente.
        if self.current_turn > 1:
            rack = self.racks[self.current_rack]
            assert rack is not None
            previous = rack[self.current_turn - 1]
            if previous is not None and previous.annotation.safety:
                if (note.total_potted or 0) > 0:
                    # Il kick-in alla prima bilia salva la difesa: la posizione
                    # lasciata era buona, l'avversario l'ha risolta di sponda.
                    if not note.first_shot_kick_in:
                        self.score[previous.player].safety_errors += 1
                elif note.miss_errors == 2:
                    self.score[previous.player].safety_errors += 1

        # Errore di posizione: bilie imbucate senza chiudere il rack.
        if (
            note.miss_errors != 2
            and not note.safe_x
            and not turn.is_winning()
            and (note.total_potted or 0) > 0
            and note.break_potted != note.total_potted
        ):
            tally.position_errors += 1
        # ...oppure battente in buca fuori da kick e spaccata.
        if note.pocketed and not note.kick and not turn.is_break():
            tally.position_errors += 1

        tally.balls_potted += note.total_potted or 0

        # Falli consecutivi, per la regola dei tre falli.
        if note.no_hit or note.pocketed:
            own_previous = (
                turn.previous_turn.previous_turn if turn.previous_turn else None
            )
            previous_errors = own_previous.consecutive_errors if own_previous else 0
            turn.consecutive_errors = (
                previous_errors + 1 if (note.total_potted or 0) == 0 else 1
            )
        else:
            turn.consecutive_errors = 0

        self.rack_errors[turn.player] += self._turn_error_count(turn)

        # Anche l'errore di difesa pesa sul rack "perfetto" di chi l'ha giocata.
        if self.current_turn > 1:
            rack = self.racks[self.current_rack]
            assert rack is not None
            previous = rack[self.current_turn - 1]
            if previous is not None and previous.annotation.safety:
                if ((note.total_potted or 0) > 0 and not note.first_shot_kick_in) or (
                    note.miss_errors == 2
                ):
                    self.rack_errors[previous.player] += 1

    def _turn_error_count(self, turn: TurnState) -> int:
        """Errori del turno a carico di chi lo ha giocato (difese escluse)."""
        note = turn.annotation
        errors = 0
        if note.miss_errors:
            errors += note.miss_errors
        if turn.is_break() and (note.pocketed or note.no_hit):
            errors += 1
        if note.kick and (note.no_hit or note.pocketed):
            errors += 1
        if (
            note.miss_errors != 2
            and not note.safe_x
            and not turn.is_winning()
            and (note.total_potted or 0) > 0
            and note.break_potted != note.total_potted
        ):
            errors += 1
        if note.pocketed and not note.kick and not turn.is_break():
            errors += 1
        return errors

    # ------------------------------------------------------------------
    # Riconoscimenti di rack
    # ------------------------------------------------------------------

    def detect_rack_achievements(self, winning_turn: TurnState) -> None:
        """Break & run, run-out e rack perfetto del rack appena chiuso."""
        if not winning_turn.is_winning():
            return
        player = winning_turn.player
        tally = self.score[player]
        turns = self.turns()

        is_break_and_run = self.check_break_and_run(turns, player)
        is_run_out = not is_break_and_run and self.check_run_out(
            turns, player, winning_turn
        )
        is_perfect_rack = self.rack_errors[player] == 0

        if is_break_and_run:
            tally.break_and_runs += 1
        if is_run_out:
            tally.run_outs += 1
        if is_perfect_rack:
            tally.perfect_racks += 1

    def check_break_and_run(self, turns: List[TurnState], player: int) -> bool:
        """Spacca e chiude senza mai cedere il tavolo."""
        if not turns:
            return False
        break_turn = turns[0]
        if break_turn.player != player or not break_turn.is_break():
            return False
        return all(t.player == player for t in turns)

    def run_out_conditions_met(
        self, turns: List[TurnState], winning_turn: TurnState
    ) -> bool:
        """Le due condizioni comuni al run-out: non e' la spaccata, e prima
        del turno vincente non era stata imbucata nessuna bilia — salvo quelle
        della spaccata stessa."""
        if not turns or winning_turn is None:
            return False
        break_turn = turns[0]
        if not break_turn.is_break():
            return False
        if winning_turn is break_turn or winning_turn.is_break():
            return False
        for t in turns:
            if t is winning_turn:
                continue
            if t.is_break():
                if (t.annotation.total_potted or 0) > (t.annotation.break_potted or 0):
                    return False
            elif (t.annotation.total_potted or 0) > 0:
                return False
        return True

    def run_out_category(
        self, turns: List[TurnState], player: int, winning_turn: TurnState
    ) -> str:
        """``"yes"`` / ``"no"`` / ``"maybe"``.

        ``"maybe"`` e' il caso onesto: il giocatore ha chiuso alla prima
        visita ma il conteggio delle bilie e' ambiguo (palla 8 col conteggio
        nominale, palla 9/10 con un battente in buca), e allora lo conferma
        lui con il pulsante "Run-out?".
        """
        if not turns or winning_turn is None:
            return "no"
        break_turn = turns[0]

        if winning_turn is break_turn or winning_turn.is_break():
            return "no"
        for t in turns:
            if t is winning_turn:
                break
            if t.player == player:
                return "no"

        note = winning_turn.annotation
        if (
            self.run_out_conditions_met(turns, winning_turn)
            and (note.total_potted or 0) > 0
            and note.total_potted == winning_turn.balls_remaining
        ):
            return "yes"
        return "maybe"

    def check_run_out(
        self, turns: List[TurnState], player: int, winning_turn: TurnState
    ) -> bool:
        category = self.run_out_category(turns, player, winning_turn)
        if category == "yes":
            return True
        if category == "maybe":
            return winning_turn.annotation.run_out is True
        return False

    def is_ambiguous_run_out(self, turn: TurnState) -> bool:
        if not turn.is_winning():
            return False
        return self.run_out_category(self.turns(), turn.player, turn) == "maybe"

    # ------------------------------------------------------------------
    # Tastierino
    # ------------------------------------------------------------------

    def available_buttons(self, turn: Optional[TurnState] = None) -> List[str]:
        """I comandi ammessi ora, nell'ordine del tastierino.

        L'annotazione procede a fasi — prima quante bilie, poi perche' il turno
        e' finito, poi l'eventuale fallo — e ogni fase mostra solo cio' che ha
        senso premere. E' quello che rende il referto compilabile con una mano
        sola mentre si gioca.
        """
        turn = turn or self.turn()
        note = turn.annotation
        buttons: List[str] = []

        def add(*items: str) -> None:
            for item in items:
                if item not in buttons:
                    buttons.append(item)

        previous = turn.previous_turn
        after_safety = previous is not None and bool(
            previous.annotation.safe_x
            or previous.annotation.push
            or previous.annotation.safety
        )

        if turn.is_winning() or note.push:
            if turn.is_winning() and after_safety and not note.first_shot_kick_in:
                add(TpaButton.KICK_IN)
            if turn is self.get_turn() and self.is_ambiguous_run_out(turn):
                add(TpaButton.RUNOUT)
            return buttons

        if not note.balls_annotated():
            if not turn.is_break() or note.break_potted is None:
                add(*[str(i) for i in range(0, turn.balls_remaining + 1)])
            else:
                # Seconda fase della spaccata: quante bilie in tutto, spaccata
                # inclusa. Non si puo' scendere sotto le bilie gia' fatte.
                add("0")
                start = 0 if self.game_type == 8 else note.break_potted
                add(*[str(i) for i in range(start, turn.balls_remaining + 1)])
            return buttons

        if note.no_hit or note.pocketed:
            return buttons

        if (
            turn.is_break()
            and note.total_potted == 0
            and (self.game_type != 8 or note.break_potted == 0)
        ):
            # Spaccata a vuoto: o e' fallo, o si passa il tavolo e basta.
            add(TpaButton.NO_HIT_FOUL, TpaButton.POCKET_FOUL)
            return buttons

        if not (note.safety or note.miss_errors or note.kick):
            # Palla 8: si vince anche senza imbucare nulla, se l'avversario
            # ha appena fatto fallo sulla nera.
            won_by_opponent_foul = (
                self.game_type == 8
                and note.total_potted == 0
                and previous is not None
                and bool(previous.annotation.no_hit or previous.annotation.pocketed)
            )
            if (
                (note.break_potted or 0) <= (note.total_potted or 0)
                and (note.total_potted or 0) > 0
            ) or won_by_opponent_foul:
                add(TpaButton.GAME)
                if after_safety and not note.first_shot_kick_in:
                    add(TpaButton.KICK_IN)
            add(
                TpaButton.MISS,
                TpaButton.KICK,
                TpaButton.SAFETY,
                TpaButton.POCKET_FOUL,
                TpaButton.NO_HIT_FOUL,
            )
            return buttons

        add(TpaButton.NO_HIT_FOUL, TpaButton.POCKET_FOUL)
        if note.safety:
            # Il push out e' legale solo al primo tiro dopo la spaccata.
            if (
                turn.is_break_shot()
                or (turn.is_pushed() and note.total_potted == 0)
                or (
                    previous is not None
                    and previous.is_break()
                    and previous.annotation.total_potted == 0
                    and note.total_potted == 0
                )
            ):
                add(TpaButton.PUSH_OUT)
            if (note.total_potted or 0) > 0:
                add(TpaButton.PLANNED_SAFETY)
        elif note.miss_errors == 1:
            add(TpaButton.NO_REASON)
        return buttons

    # ------------------------------------------------------------------
    # Lettura
    # ------------------------------------------------------------------

    def tally(self, player: int) -> PlayerTally:
        return self.score[player]

    def to_dict(self) -> Dict[str, Any]:
        """Lo stato in forma serializzabile, per la pagina del referto."""
        racks = []
        for number in range(1, len(self.racks)):
            turns = self.turns(number)
            if not turns:
                continue
            racks.append(
                {
                    "number": number,
                    "turns": [
                        {
                            "turn": index + 1,
                            "player": t.player,
                            "is_break": t.is_break(),
                            "balls_remaining": t.balls_remaining,
                            "winning": t.winning_turn,
                            "main_note": t.annotation.main_note(),
                            "secondary_note": t.annotation.secondary_note(),
                            "annotation": t.annotation.to_dict(),
                            "score_snapshot": t.score_snapshot,
                        }
                        for index, t in enumerate(turns)
                    ],
                }
            )
        current = self.turn()
        return {
            "game_type": self.game_type,
            "current_rack": self.current_rack,
            "current_turn": self.current_turn,
            "current_player": self.current_player,
            "score": {player: tally.to_dict() for player, tally in self.score.items()},
            "racks": racks,
            "current": {
                "player": current.player,
                "is_break": current.is_break(),
                # Toccare l'avversario vuol dire due cose diverse a seconda del
                # momento: sul primo turno di un rack, finche' nessuno ha
                # annotato, sceglie chi spacca; dopo, chiude il turno e passa il
                # tavolo. La distinzione la fa il motore, cosi' l'interfaccia
                # non deve reimparare la regola.
                "can_choose_seat": self.can_choose_seat(),
                "balls_remaining": current.balls_remaining,
                # `is_winning()`, non il memo `winning_turn`: chi svuota il
                # tavolo senza premere `G` ha vinto, ma il memo lo scopre solo
                # quando qualcuno lo chiede — e qui nessuno l'ha ancora fatto.
                "winning": current.is_winning(),
                "main_note": current.annotation.main_note(),
                "secondary_note": current.annotation.secondary_note(),
                "annotation": current.annotation.to_dict(),
            },
            "buttons": self.available_buttons(),
            "can_switch_player": self.can_switch_player(),
        }
