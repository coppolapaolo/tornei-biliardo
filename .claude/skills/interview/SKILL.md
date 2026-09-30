---
name: interview
description: Intervista strutturata per elicitare e validare specifiche. Pone domande, identifica lacune, simula user journey e verifica edge cases. Attiva proattivamente quando si discute di nuove feature o modifiche significative.
allowed-tools: Read, Glob, Grep, AskUserQuestion
---

# Requirements Interview

Questa skill conduce un'intervista strutturata per elicitare, chiarire e validare le specifiche di una nuova feature o modifica.

## Trigger di Attivazione Proattiva

Suggerisci questa skill quando nella conversazione:
- Si propone una **nuova feature** senza specifiche dettagliate
- Si descrive un requisito in modo **vago o incompleto**
- Si usano termini come "dovrebbe", "potrebbe", "forse"
- Si discute di **modifiche a workflow esistenti**
- C'è **ambiguità** su comportamenti attesi
- Mancano informazioni su **casi limite** o errori

**Frase suggerita**: "Prima di implementare, vuoi che faccia un'intervista per chiarire tutti i dettagli? Usa `/interview`"

## Metodo

Obiettivo: arrivare alle specifiche del modello di output qui sotto senza
domande aperte bloccanti. Copri il problema e il suo perché, attori e permessi,
il percorso utente, casi limite ed errori, l'impatto su dati, notifiche,
gamification e traduzioni — nell'ordine che la conversazione suggerisce, poche
domande per volta, riformulando per conferma. Le domande tipo più sotto dicono
dove questo progetto nasconde i casi limite.

## Output dell'Intervista

Al termine, produci un documento strutturato:

```markdown
# Specifiche: [Nome Feature]

## Problema
[Descrizione del problema che risolve]

## User Story
Come [tipo utente], voglio [azione], in modo da [beneficio].

## Criteri di Accettazione
- [ ] AC1: ...
- [ ] AC2: ...
- [ ] AC3: ...

## User Journey
1. Utente è su [pagina]
2. Clicca [elemento]
3. Vede [risultato]
...

## Edge Cases Gestiti
| Scenario | Comportamento Atteso |
|----------|---------------------|
| Input invalido | Mostra errore X |
| Permessi mancanti | Redirect a Y |
| ... | ... |

## Impatto Tecnico
- Nuove entità: [elenco]
- Modifiche a: [elenco file/moduli]
- Migrazioni: [sì/no, dettagli]

## Domande Aperte
- [ ] Domanda 1 (da chiarire con stakeholder)
- [ ] Domanda 2
```

## Regole dell'Intervista

1. **Una domanda alla volta** - Non sovraccaricare l'utente
2. **Conferma comprensione** - Riformula e chiedi "Ho capito bene?"
3. **Non assumere** - Se non è esplicito, chiedi
4. **Esempi concreti** - Usa scenari reali del progetto
5. **Documenta dubbi** - Meglio una domanda aperta che un'assunzione sbagliata
6. **Usa il contesto** - Fai riferimento a feature esistenti simili

## Domande Tipo per Questo Progetto

### Per Feature relative a Gare/Tornei:
- Funziona per tutte le strategie di `MatchmakingStrategy` (Amalfi, girone all'italiana, casuale, eliminazione diretta, doppia eliminazione)?
- Funziona sia per gare standalone che dentro campionati?
- Chi può farlo? Admin, Director, entrambi?
- Funziona in tutti gli stati della gara (`GaraStatus`: setup, iscrizioni, in corso, attesa spareggi, conclusa, annullata)?

### Per Feature relative a Match:
- Funziona per match singoli E multi-set?
- Funziona per match di gara E individuali?
- Impatta il calcolo delle statistiche?

### Per Feature relative a Utenti:
- Come si comporta con utenti eliminati (soft delete)?
- Servono notifiche? A chi?
- Ci sono implicazioni sulla privacy/GDPR?

## Esempio di Intervista

**Utente**: "Vorrei aggiungere la possibilità di mettere in pausa una gara"

**Intervista**:

> **Q1**: Cosa significa "in pausa"? La gara rimane visibile ma non si possono giocare match, o diventa completamente nascosta?

*Risposta: Rimane visibile ma i match sono bloccati*

> **Q2**: Chi può mettere in pausa? Solo chi ha creato la gara o anche altri admin/director?

*Risposta: Chi l'ha creata + admin*

> **Q3**: Simuliamo: un director clicca "Pausa" durante una gara con 3 match in corso. Cosa succede a quei match? Si completano o vengono interrotti?

*Risposta: I match in corso possono essere completati, ma non se ne possono iniziare di nuovi*

> **Q4**: Come si toglie la pausa? C'è un limite di tempo massimo di pausa?

*Risposta: Stesso bottone diventa "Riprendi", nessun limite*

> **Q5**: I giocatori vengono notificati della pausa?

*Risposta: Sì, notifica a tutti gli iscritti*

[...continua fino a coprire tutti gli aspetti...]

## Checklist Pre-Implementazione

Prima di dichiarare le specifiche complete, verifica:

- [ ] User story chiara con attore, azione, beneficio
- [ ] Almeno 3 criteri di accettazione testabili
- [ ] User journey completo passo-passo
- [ ] Permessi/ruoli definiti
- [ ] Comportamento errori specificato
- [ ] Edge cases principali coperti
- [ ] Impatto su notifiche valutato
- [ ] Impatto su gamification valutato
- [ ] Necessità di i18n valutata
- [ ] Nessuna domanda aperta bloccante
