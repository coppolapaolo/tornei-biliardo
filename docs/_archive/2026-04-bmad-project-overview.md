# Panoramica Progetto — Tornei Biliardo

> Generato automaticamente il 2026-04-04 | Scansione esaustiva

## Descrizione

**Tornei Biliardo** è una piattaforma web community per appassionati di biliardo americano (pool), focalizzata sull'organizzazione di tornei e la gestione di partite. Produzione attiva su https://www.torneibiliardo.it.

## Funzionalità Principali

| Area | Funzionalità |
|------|-------------|
| **Tornei** | Campionati con gare multiple, wizard creazione, classifiche |
| **Gare** | 5 strategie matchmaking (Amalfi, Round Robin, Eliminazione, Random, Double KO) |
| **Match** | Singolo, multi-set, trio (3 giocatori), con scoring rack-by-rack |
| **Match Individuali** | Proposte casual tra giocatori, disponibilità, geolocalizzazione |
| **Sfide** | Prove di abilità con tentativi e favoriti |
| **Gamification** | XP, livelli, achievement, streak, quest, leaderboard, ABAC feature flags |
| **Rating** | Sistema ELO con handicap e categorie |
| **Notifiche** | Sistema notifiche event-driven con template e preferenze |
| **Utenti** | RBAC (Admin/Director/Player), soft delete, privacy GDPR |
| **Guest Access** | Visualizzazione pubblica tornei e classifiche |
| **i18n** | Supporto italiano e inglese |
| **KPI** | Metriche piattaforma, milestone, tracking |

## Tech Stack Riepilogo

| | Tecnologia |
|---|-----------|
| **Backend** | Python 3.11, Flask 2.3.3 |
| **Database** | SQLite + SQLAlchemy |
| **Frontend** | Jinja2 SSR + Bootstrap + JS vanilla |
| **Hosting** | PythonAnywhere |
| **CI/CD** | GitHub Actions |
| **Testing** | pytest + pyright |

## Numeri Chiave

| Metrica | Valore |
|---------|--------|
| Python LOC | 116.106 |
| HTML Template LOC | 29.419 |
| Domini (bounded context) | 27 |
| Classi modello | ~50 |
| Classi servizio | ~50 |
| Template Jinja2 | ~160 |
| ADR documentati | 18 |
| Test attivi (new/) | ~90 file |
| Migrazioni DB | 38 |
| Lingue | it, en |

## Architettura

- **Tipo**: Monolite con Domain-Driven Design
- **Pattern**: Service Layer + Strategy + Event-Driven
- **Entry Point**: `app.py` → `create_app()` (Flask factory)
- **Documentazione completa**: Vedi `CLAUDE.md` alla root

## Link Documentazione

- [Architettura](./architecture.md)
- [Source Tree](./source-tree-analysis.md)
- [Guida Sviluppo](./development-guide.md)
- [Schema Database](./DATABASE_SCHEMA.md)
- [Autenticazione](./AUTHENTICATION.md)
- [Gamification](./GAMIFICATION_V2.md)
- [Classifiche](./CLASSIFICATION_SYSTEM.md)
- [Specifiche](./SPECIFICHE.md)
- [UI Conventions](./UI_CONVENTIONS.md)
- [i18n](./INTERNATIONALIZATION.md)
- [ADR](./adr/)
- [Use Cases](./usecases/)
