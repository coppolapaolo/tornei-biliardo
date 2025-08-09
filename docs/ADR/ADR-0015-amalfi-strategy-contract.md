# ADR-0015 — Contratto Strategy per Amalfi (Adapter al legacy engine)

Stato: ACCEPTED  
Data: 2025-08-09  
Autore: team tornei-biliardo

## Contesto
L’engine Amalfi esistente gestisce: anti-reincontro tramite PlayerEncounter, gestione "bye (X)" e "trii", salto dinamico dai round ≥2, funzioni di preview. C’è un mismatch storico nella firma di registrazione degli incontri (ordine argomenti).

## Decisione
- Introdurre `AmalfiStrategy` che **adatta** l’engine esistente dietro l’interfaccia `PairingStrategy`.
- Per evitare breaking change immediati, l’Adapter corregge l’ordine dei parametri quando registra gli incontri (`PlayerEncounter`). Il fix definitivo lato domain/engine sarà differito alla Sprint “UoW”.

## Contratti
- `validate(prova)` verifica prerequisiti (numero iscritti, vincoli con/without X, ecc.).
- `propose(prova, round_number)` produce la proposta di pairing **senza** cambiare stato (idealmente). Nella fase Adapter, se l’engine non espone una API “dry-run”, il metodo invocherà la routine legacy e riporterà i pairing effettivamente creati.

## Conseguenze
- **Pro**: Strategy Amalfi subito disponibile sotto il Registry; route più pulite.
- **Contro**: finché non introduciamo UoW, i side-effect restano nel legacy engine.

## Piano di test
- Contract test per Strategy (shape dei Pairing, no self-match, riproducibilità su seed quando applicabile).
- Test integrazione per Amalfi quando i binding all’engine sono disponibili nel repo.