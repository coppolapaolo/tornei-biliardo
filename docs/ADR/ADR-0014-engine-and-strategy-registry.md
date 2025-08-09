# ADR-0014 — Engine & Strategy Registry per il pairing

Stato: ACCEPTED  
Data: 2025-08-09  
Autore: team tornei-biliardo

## Contesto
Il progetto supporta (e supporterà) più metodi di abbinamento: Amalfi, girone all’italiana, eliminazione diretta, doppio KO, ecc. Al momento la logica è dispersa tra un engine “Amalfi” e alcune utilità duplicate. L’aggiunta di varianti tende a richiedere modifiche trasversali (route, template, model).

## Decisione
Introdurre un **Registry** di strategie di pairing e un **Service** che le orchestri. Ogni metodo di abbinamento è una **Strategy** con interfaccia comune:
- `validate(prova) -> ValidationResult`
- `propose(prova, round_number) -> list[Pairing]`

Nel breve (Sprint 1) l’implementazione Amalfi sarà un **Adapter** che delega all’engine esistente, mantenendo i side-effect attuali (persistence dentro l’engine). In Sprint successivi inseriremo Unit of Work e Repository per riportare i side-effect nel Service.

## Alternative considerate
1. Continuare con funzioni libere/utility: bassa coesione, alta duplicazione → scartata.
2. Un’unica classe Engine con `if/elif` per tipo: viola OCP, rischio di God Object → scartata.
3. Strategy + Policy separabili + Registry (scelta): estendibile, testabile, chiari confini.

## Conseguenze
- **Pro**: Estendibilità per nuove strategie; test di contratto condivisi; UI/route più pulite.
- **Contro**: Passaggio intermedio con Adapter (side-effect nel legacy engine) fino a Sprint UoW.

## Migrazione
- Aggiunta package `models/matchmaking/` con base Strategy/Registry/Service.
- Route migrano gradualmente: chiamano il `MatchmakingService` per generare i pairing.
- Successivi Sprint sposteranno i side-effect (creazione Match, PlayerEncounter) nel Service.