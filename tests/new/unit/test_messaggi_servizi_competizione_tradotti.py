"""I messaggi composti dai servizi della gara passano da ``_()``.

Il presidio gemello, ``test_messaggi_competizione_tradotti.py``, guarda le
route e lascia passare il testo che arriva «già composto da un servizio»:
``flash(message)``, ``str(e)``. Ma fino al 2026-10-11 quei testi erano
f-string italiane scritte a mano nei servizi —
``AdvancedRoundManager.bulk_reset_round_matches`` rispondeva «Tutti i 4 match
sono stati resettati» — e in inglese il direttore leggeva l'italiano: una
f-string non si può nemmeno estrarre nel catalogo.

Qui si legge il sorgente dei servizi che le route di
``routes/admin/competition/`` chiamano e si rifiuta, se il testo è un
letterale con delle parole o una f-string:

* il primo argomento di un ``raise`` (le eccezioni di dominio finiscono nel
  flash o nella risposta JSON);
* un elemento di una tupla restituita (lo schema ``return False, "motivo"``);
* il valore di ``"message"``/``"error"`` in un dizionario.

Un'etichetta composta solo di segnaposto (``f"{disciplina} — {regola}"``) non
ha niente da tradurre e passa.
"""

import ast
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[3]

SERVIZI = sorted((RADICE / "models" / "competition").glob("*.py")) + [
    RADICE / "models" / "match" / "trio_scoring_service.py",
    RADICE / "models" / "categoria" / "service.py",
    RADICE / "models" / "squadra" / "service.py",
    RADICE / "models" / "prova" / "service.py",
    RADICE / "models" / "prova" / "simulation_service.py",
]


def _scritto_a_mano(nodo: ast.AST) -> bool:
    if isinstance(nodo, ast.JoinedStr):
        return any(
            isinstance(parte, ast.Constant)
            and isinstance(parte.value, str)
            and any(c.isalpha() for c in parte.value)
            for parte in nodo.values
        )
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        # Una frase, non un identificativo (``"excluded"``, ``"forfeit"``).
        return " " in nodo.value.strip() and any(c.isalpha() for c in nodo.value)
    if isinstance(nodo, ast.BinOp):
        return _scritto_a_mano(nodo.left) or _scritto_a_mano(nodo.right)
    return False


def _testi_non_tradotti(percorso: Path) -> list[str]:
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    trovati = []
    for nodo in ast.walk(albero):
        if (
            isinstance(nodo, ast.Raise)
            and isinstance(nodo.exc, ast.Call)
            and nodo.exc.args
            and _scritto_a_mano(nodo.exc.args[0])
        ):
            trovati.append(f"{percorso.name}:{nodo.lineno} raise")
        if isinstance(nodo, ast.Return) and isinstance(nodo.value, ast.Tuple):
            if any(_scritto_a_mano(e) for e in nodo.value.elts):
                trovati.append(f"{percorso.name}:{nodo.lineno} return")
        if isinstance(nodo, ast.Dict):
            for chiave, valore in zip(nodo.keys, nodo.values):
                if (
                    isinstance(chiave, ast.Constant)
                    and chiave.value in ("message", "error")
                    and _scritto_a_mano(valore)
                ):
                    trovati.append(f"{percorso.name}:{valore.lineno} {chiave.value}")
    return trovati


@pytest.mark.parametrize(
    "percorso", SERVIZI, ids=lambda p: str(p.relative_to(RADICE / "models"))
)
def test_nessun_messaggio_dei_servizi_senza_traduzione(percorso):
    assert _testi_non_tradotti(percorso) == []


def test_il_controllo_riconosce_le_frasi_e_lascia_gli_identificativi():
    """Il presidio non deve essere cieco né troppo zelante."""
    frase = ast.parse('f"Tutti i {n} match sono stati resettati"').body[0]
    assert _scritto_a_mano(frase.value)  # type: ignore[attr-defined]
    for codice in ('"excluded"', 'f"{a} — {b}"', '_("Gara non trovata")'):
        nodo = ast.parse(codice).body[0]
        assert not _scritto_a_mano(nodo.value)  # type: ignore[attr-defined]


def test_il_reset_in_blocco_non_ripete_il_conteggio():
    """Il messaggio del servizio porta già i numeri: la route non li riaggiunge.

    Prima il flash diceva «Tutti i 4 match sono stati resettati. 4 partite
    azzerate.»: lo stesso numero due volte, in due lingue di progetto.
    """
    sorgente = (RADICE / "routes" / "admin" / "competition" / "rounds.py").read_text(
        encoding="utf-8"
    )
    albero = ast.parse(sorgente)
    funzione = next(
        n
        for n in ast.walk(albero)
        if isinstance(n, ast.FunctionDef) and n.name == "bulk_reset_round_matches"
    )
    testo = ast.get_source_segment(sorgente, funzione) or ""
    assert "reset_count" not in testo
    assert "%(messaggio)s" not in testo
