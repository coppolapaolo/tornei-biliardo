# ADR-0001: Processo ADR e Convenzioni

Data: 2025-08-01

## Stato
Accettato

## Contesto
Il progetto era partito in modalità prototipo rapido, senza alcuna documentazione delle decisioni architetturali. Senza uno standard, la motivazione delle scelte si perde e la conoscenza resta solo informale.

## Decisione
* Adottare gli **Architecture Decision Records (ADR)** secondo il template di Michael Nygard.
* Salvare i file Markdown in `docs/ADR/`.
* Usare identificatori numerici progressivi (`ADR-0001`, `ADR-0002`, …) per mantenere ordine e immutabilità.
* Formato nome file: `ADR-<id>-<slug>.md`, dove `<slug>` è un breve riassunto in snake_case.
* Sezioni obbligatorie: **Contesto**, **Decisione**, **Conseguenze**, **Alternative**, più lo **Stato** (Proposto, Accettato, Deprecato, Superato) in cima.
* Mai modificare un ADR accettato: se la decisione cambia se ne crea uno nuovo.

## Conseguenze
+ Rintracciabilità delle scelte.
+ On‑boarding rapido dei nuovi contributori.
− Lieve overhead (2‑3 min) per ogni decisione.

## Alternative considerate
*Google Docs*, *Wiki* – poco integrato con Git, versionamento più complesso.
