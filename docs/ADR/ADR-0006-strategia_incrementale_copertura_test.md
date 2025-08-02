# ADR-0006: Strategia Incrementale di Copertura Test

Data: 2025-08-01

## Stato
Accettato

## Contesto
Codebase legacy a copertura 0 %. Imporre subito ≥ 90 % bloccherebbe ogni commit.

## Decisione
* Gate differenziale: **≥ 90 %** sui file modificati da ciascuna PR.
* Configurare `pyproject.toml` (sezione `omit`) per escludere moduli legacy non ancora rifattorizzati.
* Road‑map: aumentare la copertura globale di 10‑15 punti percentuali a fase, fino a ≥ 90 %.
* Strumenti: `pytest`, `pytest-cov` con `--cov-branch`.

## Conseguenze
+ Incentiva i test dove si lavora.
+ Debito tecnico rimosso gradualmente.
− Parti legacy restano scoperte finché non si interviene.

## Alternative
*Abbassare temporaneamente la soglia globale* – maschera il problema.
*Nessun gate* – rischio di regressione test.
