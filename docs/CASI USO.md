# Casi d’uso principali — Webapp Tornei di Biliardo (Mermaid)

Documento in **Markdown** con diagrammi in **Mermaid** per la webapp di gestione tornei e prove di biliardo professionale.

> Nota: i nomi dei servizi (es. `ProvaService`, `StandingService`) rappresentano l’Application Layer in ottica Clean Architecture; gli accessi a DB sono incapsulati in repository.

---

## 1) Overview attori e macro‑casi d’uso

```mermaid
flowchart LR
classDef actor fill:#eef,stroke:#336,stroke-width:1px,rx:6,ry:6

subgraph Gestione_Tornei[Gestione Tornei]
  UC_AdminDashboard["UC: Visualizza dashboard admin"]
  UC_CreateTournament["UC: Crea/Modifica Torneo"]
  UC_AssignDirector["UC: Assegna Director"]
end

subgraph Gestione_Prove[Gestione Prove]
  UC_CreateProva["UC: Crea/Modifica Prova"]
  UC_OpenInscr["UC: Apre/Chiude Iscrizioni"]
  UC_PublishSeeds["UC: Genera/Conferma Tabellone"]
  UC_RecordResults["UC: Registra Risultati"]
  UC_PublishStandings["UC: Pubblica Classifiche"]
end

subgraph Iscrizioni
  UC_PlayerBrowse["UC: Consulta prove disponibili"]
  UC_PlayerEnroll["UC: Iscrizione a Prova"]
  UC_PlayerWithdraw["UC: Ritiro Iscrizione"]
  UC_PayEnroll["UC: Pagamento iscrizione (opz.)"]
end

subgraph Account_Sicurezza["Account e Sicurezza"]
  UC_RequestDirector["UC: Richiesta promozione a Director"]
  UC_SoftDelete["UC: Soft Delete Utente"]
end

Admin((Admin)):::actor
Director((Director)):::actor
Player((Player)):::actor
Spectator((Spettatore)):::actor
Scheduler((Scheduler di Sistema)):::actor
PSP((Payment Provider)):::actor

Admin --> UC_AdminDashboard
Admin --> UC_CreateTournament
Admin --> UC_AssignDirector
Admin --> UC_CreateProva

Director --> UC_CreateProva
Director --> UC_OpenInscr
Director --> UC_PublishSeeds
Director --> UC_RecordResults
Director --> UC_PublishStandings

Player --> UC_PlayerBrowse
Player --> UC_PlayerEnroll
Player --> UC_PlayerWithdraw
Player --> UC_RequestDirector

Spectator --> UC_PublishStandings

UC_PlayerEnroll --> UC_PayEnroll
UC_OpenInscr -. include .-> UC_PlayerEnroll
UC_RecordResults -. include .-> UC_PublishStandings

Scheduler --> UC_PublishStandings
UC_PayEnroll --> PSP

UC_AssignDirector -. approva .-> UC_SoftDelete
Player -. auto-eliminazione .-> UC_SoftDelete

class Admin,Director,Player,Spectator,Scheduler,PSP actor;
```

---

## 2) UC‑01 — Iscrizione del Player a una Prova

### Sequenza

```mermaid
sequenceDiagram
actor Player
participant UI as UI Flask/Jinja
participant Auth as AuthService
participant ProvaSvc as ProvaService
participant InscSvc as IscrizioneService
participant PSP as PaymentProvider

Player->>UI: Apri pagina prova
UI->>ProvaSvc: get_prova(prova_id)
ProvaSvc-->>UI: Prova + stato iscrizioni
Player->>UI: Clic "Iscriviti"
UI->>Auth: check_authenticated()
Auth-->>UI: OK
UI->>InscSvc: enroll(user_id, prova_id)
InscSvc->>ProvaSvc: validate_iscrizione_window()
ProvaSvc-->>InscSvc: OK
InscSvc->>InscSvc: calcola_handicap(user)
alt pagamento richiesto
  UI->>PSP: create_checkout_session(...)
  PSP-->>UI: esito OK
end
InscSvc-->>UI: conferma iscrizione
UI-->>Player: Messaggio successo + badge
```

**Pre‑condizioni**

* Prova in stato **Iscrizioni Aperte**.
* Utente autenticato e con requisiti (ranking/limiti di partecipazione) validi.

**Post‑condizioni**

* Record di iscrizione creato; eventuale transazione registrata.

---

## 3) UC‑02 — Gestione stato di una Prova (Director)

### Macchina a stati

```mermaid
stateDiagram-v2
[*] --> Draft
Draft --> Inscription: apri_iscrizioni()
Inscription --> Seeded: chiudi_iscrizioni() / genera_tabellone
Seeded --> InProgress: avvia_match()
InProgress --> Completed: chiudi_ultimo_match()
Completed --> Archived: archivia()
Inscription --> Draft: annulla_apertura()

state Inscription {
  [*] --> Aperte
  Aperte --> Chiuse: chiudi_iscrizioni()
  Chiuse --> Aperte: riapri_iscrizioni()
}
```

**Regole di transizione (estratto)**

* `apri_iscrizioni()` vietato se esistono match già sorteggiati.
* `riapri_iscrizioni()` consentito solo se non sono iniziati i match.

---

## 4) UC‑03 — Admin crea Torneo/Prova e assegna Director

### Sequenza (riassunta)

```mermaid
sequenceDiagram
actor Admin
participant UI
participant TournSvc as TournamentService
participant ProvaSvc as ProvaService
participant UserSvc as UserService

Admin->>UI: Nuovo Torneo
UI->>TournSvc: create_tournament(...)
TournSvc-->>UI: torneo_id
Admin->>UI: Aggiungi Prova
UI->>ProvaSvc: create_prova(torneo_id, ...)
ProvaSvc-->>UI: prova_id
Admin->>UI: Assegna Director
UI->>UserSvc: assign_director(torneo_id, user_id)
UserSvc-->>UI: conferma assegnazione
```

---

## 5) UC‑04 — Richiesta promozione a Director (Player → Admin)

### Attività

```mermaid
flowchart TD
A["Player compila richiesta"];
B["UserService crea DirectorRequest (pending)"];
C["Admin riceve notifica"];
D{"Admin approva?"};
E["Promuovi a Director e aggiorna ruoli"];
F["Rifiuta e notifica motivo"];


A --> B;
B --> C;
C --> D;
D -- "sì" --> E;
D -- "no" --> F;
```

---

## 6) UC‑05 — Soft Delete Utente con riassegnazione

### Attività

```mermaid
flowchart TD
A["Utente richiede cancellazione account"];
B{"Utente è Director attivo?"};
C["Riassegna tornei all'Admin di sistema"];
D["Continua"];
E["Marca user.status = deleted<br/>Anonimizza PII (opzionale)"];
F["Revoca sessione corrente (logout)"];


A --> B;
B -- "sì" --> C;
B -- "no" --> D;
C --> E;
D --> E;
E --> F;
```

---

## 7) UC‑06 — Inserimento risultati e pubblicazione classifiche (live)

### Sequenza

```mermaid
sequenceDiagram
actor Director
participant UI
participant ProvaSvc as ProvaService
participant ResultSvc as ResultService
participant StandingSvc as StandingService

Director->>UI: Inserisci risultato match
UI->>ResultSvc: save_result(match_id, score)
ResultSvc->>ProvaSvc: update_match_state()
ResultSvc-->>UI: OK
UI->>StandingSvc: recompute_standings(prova_id)
StandingSvc-->>UI: nuove classifiche
UI-->>Director: Conferma + preview
```

---

## Glossario minimo

* **Torneo**: contenitore di più *Prove*.
* **Prova**: singolo evento/competizione; ha stati (draft, iscrizioni, in corso, completata...).
* **Iscrizione**: relazione Player–Prova con eventuale pagamento.
* **Director**: responsabile operativo di Tornei/Prove.
* **Admin**: superutente con poteri su tutto il dominio.

> Questi diagrammi sono base per ADR e test di integrazione; vanno sincronizzati con i Blueprint Flask (`admin`, `director`, `player`) e con i servizi applicativi.
