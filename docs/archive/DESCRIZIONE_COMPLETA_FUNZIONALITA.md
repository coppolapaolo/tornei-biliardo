# 📖 Descrizione Completa delle Funzionalità - Sistema Tornei Biliardo

> **Documento delle Specifiche Funzionali** - Descrizione in estremo dettaglio di tutte le funzionalità del sistema refactorato

---

## 🎯 **Sistema Tournament Management Completo**

Il sistema refactorato dovrà supportare la **gestione completa e professionale di tornei di biliardo multi-formato** con architettura modulare e strategie configurabili per ogni aspetto della competizione.

---

## 🏆 **Gestione Tornei Multi-Strategia**

### **Concetto di Torneo**
Un **Torneo** rappresenta l'entità principale che raggruppa più **Prove** (competizioni individuali) sotto un'unica organizzazione. Ogni torneo definisce un set di strategie predefinite che servono come template per tutte le sue prove, ma ogni prova può sovrascrivere queste impostazioni per comportamenti specifici.

### **Competition Strategy - Come si Svolge la Competizione**

#### **1. Sistema Amalfi (Esistente Enhanced)**
- **Descrizione**: Sistema attuale potenziato con abbinamenti basati su classifica e formula del salto dinamico
- **Funzionamento**: 
  - Primo turno: Sorteggio casuale
  - Turni successivi: Abbinamenti basati su classifica corrente
  - Formula salto: `Turni_Totali - Turno_Attuale` 
  - Anti-reincontro: Tracking completo per evitare che due giocatori si incontrino più volte
- **Configurazioni**:
  - Numero turni configurabile
  - Gestione numeri dispari (X o Trii)
  - Preview abbinamenti prima dell'avvio
- **Algoritmi Avanzati**:
  - Bilanciamento automatico delle forze
  - Minimizzazione reincontri
  - Gestione bye intelligente

#### **2. Girone All'Italiana (Round Robin)**
- **Descrizione**: Tutti giocano contro tutti una volta
- **Funzionamento**:
  - Calcolo automatico numero turni: `(n-1)` per n giocatori
  - Algoritmo per abbinamenti che garantisce ogni giocatore contro ogni altro
  - Gestione numeri dispari con bye rotazionale
- **Configurazioni**:
  - Round Robin completo o parziale
  - Possibilità di doppio round robin (andata e ritorno)
  - Criteri di ordinamento configurabili
- **Ottimizzazioni**:
  - Minimizzazione consecutivi bye per stesso giocatore
  - Bilanciamento temporale dei match

#### **3. Eliminazione Diretta**
- **Descrizione**: Torneo ad eliminazione con diverse varianti
- **Varianti**:
  - **Single Elimination**: Chi perde è eliminato
  - **Double Elimination**: Doppia possibilità (winners bracket + losers bracket)
  - **Swiss System**: Nessuna eliminazione, abbinamenti basati su punteggio
- **Funzionamento**:
  - Bracket automatico con calcolo potenze di 2
  - Gestione bye nei primi turni per numeri non potenza di 2
  - Seeding basato su ranking o sorteggio
- **Configurazioni**:
  - Tipo di eliminazione (single/double/swiss)
  - Criteri di seeding
  - Gestione finali consolazione

#### **4. Sistema Svizzero**
- **Descrizione**: Per grandi numeri di partecipanti, abbinamenti basati su performance
- **Funzionamento**:
  - Numero fisso di turni (tipicamente log₂(partecipanti))
  - Abbinamenti fra giocatori con punteggio simile
  - Nessuna eliminazione, tutti giocano tutti i turni
- **Algoritmi**:
  - Pairing algoritms per abbinamenti ottimali
  - Color allocation (bianco/nero nel biliardo)
  - Anti-pairing per evitare reincontri

### **Classification Strategy - Sistemi di Classifica**

#### **1. Standard Amalfi (Esistente Enhanced)**
- **Criteri in Ordine**:
  1. **Vittorie** (discendente): Numero match vinti
  2. **Differenza Punti** (discendente): Differenza rack vinti - rack persi
  3. **Ordine Precedente** (ascendente): Posizione classifica turno precedente
- **Calcolo Real-Time**: Aggiornamento istantaneo dopo ogni match
- **Tracking Storico**: Mantiene cronologia classifiche per ogni turno

#### **2. Sistema Pesato per Turno**
- **Descrizione**: Diversi pesi per turni diversi
- **Configurazioni**:
  - Pesi crescenti: ultimi turni valgono di più
  - Pesi decrescenti: primi turni più importanti  
  - Pesi custom: configurazione manuale per ogni turno
- **Calcolo**: `Punteggio = Σ(Risultato_Turno_i × Peso_i)`
- **Use Cases**: Tornei dove la consistenza finale è più importante dell'inizio

#### **3. Solo Vittorie**
- **Descrizione**: Ignora completamente la differenza punti
- **Criteri**:
  1. Numero vittorie
  2. Scontri diretti tra pari vittorie
  3. Sorteggio per pari merito irrisolvibile
- **Vantaggi**: Semplice, premia solo il vincere match

#### **4. Sistema a Punti Fissi**
- **Descrizione**: Punteggi fissi per vittoria/pareggio/sconfitta
- **Configurazioni**:
  - Vittoria: 3 punti, Pareggio: 1 punto, Sconfitta: 0 punti
  - Vittoria: 2 punti, Sconfitta: 0 punti
  - Sistema custom con punti configurabili
- **Calcolo**: Somma punti ottenuti in tutti i match

### **Bye Handling Strategy - Gestione Numeri Dispari**

#### **1. Con X (Bye Automatico)**
- **Funzionamento**: Giocatore "fortunato" riceve bye = vittoria automatica
- **Punteggio Bye**: 
  - Se "al meglio di N": ottiene punteggio necessario per vittoria
  - Se "esatto numero": ottiene punteggio massimo possibile
- **Rotazione**: Sistema per evitare che stesso giocatore abbia sempre bye
- **Criteri Assegnazione**: 
  - Ultimo in classifica (aiuto)
  - Primo in classifica (premio)
  - Rotazionale
  - Casuale

#### **2. Senza X (Trii Automatici)**
- **Funzionamento**: Ultimo giocatore viene aggiunto all'ultima partita creando un trio
- **Gestione Trii**:
  - 3 giocatori, tutti contro tutti in un'unica sessione
  - Ogni giocatore accumula punti contro gli altri due
  - Classifica interna al trio per determinare posizioni
- **Punteggio**: Somma rack vinti contro entrambi gli avversari

#### **3. Rotazione Avanzata**
- **Funzionamento**: Alternanza intelligente tra bye e trii
- **Algoritmo**: 
  - Turni pari: bye al giocatore X
  - Turni dispari: trio con giocatore Y
- **Tracking**: Cronologia per garantire equità nella distribuzione

---

## 🎮 **Sistema Prove Flessibile**

### **Concetto di Prova**
Una **Prova** rappresenta una competizione specifica all'interno di un torneo. È l'unità base dove avvengono le iscrizioni, i match e le classifiche. Ogni prova può avere configurazioni completamente autonome.

### **Configurazione Autonoma**

#### **Informazioni Base**
- **Identificazione**: Numero prova, nome, descrizione
- **Temporale**: Data, ora inizio, ora fine, scadenza iscrizioni
- **Logistica**: Location precisa, campo/tavolo assegnato
- **Economica**: Quota iscrizione, premi configurabili
- **Partecipazione**: Min/max partecipanti, liste d'attesa

#### **Configurazioni Avanzate**
- **Modalità Iscrizione**: 
  - Aperta: chiunque può iscriversi
  - Invitati: solo giocatori selezionati
  - Qualificati: basata su classifica tornei precedenti
- **Discipline Supportate**: 8-Ball, 9-Ball, 10-Ball, Snooker, etc.
- **Formato Match**: Distanza, "al meglio di" vs "esatto numero"

### **Strategy Override System**

#### **Ereditarietà dal Torneo**
```
Torneo: Competition=Amalfi, Classification=Standard, Bye=WithX
├── Prova 1: [eredita tutto dal torneo]
├── Prova 2: Competition=RoundRobin [sovrascrivi solo competition]
└── Prova 3: Classification=WinsOnly, Bye=WithoutX [sovrascrivi classification e bye]
```

#### **UI di Configurazione**
- **Dropdown con Default**: Mostra strategia ereditata dal torneo
- **Override Selettivo**: Possibilità di sovrascrivere solo alcune strategie
- **Preview Risultato**: Anteprima comportamento con nuove impostazioni
- **Reset a Default**: Ritorno rapido alle impostazioni del torneo

### **Gestione Iscrizioni Avanzata**

#### **Timeline Iscrizioni**
1. **Apertura**: Data/ora configurable per apertura iscrizioni
2. **Periodo Attivo**: Finestra temporale per iscrizioni
3. **Scadenza**: Deadline automatica per chiusura iscrizioni
4. **Grace Period**: Eventuali iscrizioni tardive con penale

#### **Controlli Automatici**
- **Numero Minimo**: Prova non parte se non raggiunge minimo
- **Numero Massimo**: Iscrizioni successive vanno in lista d'attesa
- **Conflitti**: Controllo sovrapposizioni con altre prove
- **Requisiti**: Verifica criteri di accesso automatici

#### **Sistema Notifiche**
- **Apertura Iscrizioni**: Email/notifica a giocatori interessati
- **Promemoria Scadenza**: Notifica X giorni prima della chiusura
- **Conferma Iscrizione**: Ricezione automatica con dettagli
- **Lista d'Attesa**: Notifica posizione e promozioni

### **Fasi Multiple in una Prova**

#### **Struttura Fase**
Una prova può essere composta da più fasi sequenziali:
```
Prova Complessa:
├── Fase 1: Gironi (Round Robin)
├── Fase 2: Quarti (Eliminazione)
├── Fase 3: Semifinali (Eliminazione)
└── Fase 4: Finale (Eliminazione)
```

#### **Passaggio tra Fasi**
- **Criteri Automatici**: Top N di ogni girone, migliori secondi, etc.
- **Configurazione**: Numero qualificati configurabile per fase
- **Ripescaggi**: Possibilità di "wild card" per bilanciare bracket

#### **Classifiche Multiple**
- **Classifica di Fase**: Posizione all'interno della singola fase
- **Classifica Generale**: Posizione finale considerando tutte le fasi
- **Punti Fase**: Diversi punteggi per diverse fasi (es. girone = 1x, finale = 3x)

---

## 🏅 **Sistema Playoff Configurabile**

### **Concetto di Playoff**
I **Playoff** sono prove speciali che rappresentano la fase finale/conclusiva di un torneo. Ereditano tutte le funzionalità di una Prova normale ma aggiungono logica specifica per:
- Criteri di accesso automatici
- Gestione qualificati e riserve
- Sostituzione automatica in caso di rinunce

### **Criteri di Accesso Multipli**

#### **1. Top N - Primi Classificati**
- **Configurazione**: `{type: "top_n", n: 8}`
- **Funzionamento**: Prende i primi N dalla classifica generale del torneo
- **Esempio**: Playoff per i primi 8 classificati
- **Gestione Pari Merito**: Criteri di spareggio automatici o manuali

#### **2. Range - Fascia Posizioni**
- **Configurazione**: `{type: "range", start: 5, end: 12}`
- **Funzionamento**: Playoff per giocatori dalla posizione X alla Y
- **Esempio**: Playoff "di consolazione" dal 5° al 12°
- **Use Case**: Playoff multipli (A per primi 8, B per successivi 8)

#### **3. Min Provas - Partecipazione Minima**
- **Configurazione**: `{type: "min_provas", start: 3, end: 10, min_provas: 5}`
- **Funzionamento**: Dal 3° al 10° che hanno partecipato ad almeno 5 prove
- **Scopo**: Premiare la costanza di partecipazione
- **Algoritmo**: Filtro partecipazione + range posizioni

#### **4. Custom Formula - Criteri Personalizzati**
- **Configurazione**: Formula configurabile con parametri
- **Esempi**:
  - Migliore media degli ultimi 3 tornei
  - Massimo punteggio singola prova
  - Combinazione ranking + partecipazione
- **Implementazione**: Sistema di espressioni valutabili

### **Gestione Rinunce e Sostituzioni**

#### **Processo Automatico**
```
1. Playoff con 8 qualificati: [A, B, C, D, E, F, G, H]
2. Giocatore C rinuncia
3. Sistema automaticamente:
   - Rimuove C dai qualificati
   - Trova il primo escluso (I) che soddisfa i criteri
   - Promuove I ai qualificati
   - Invia notifica a I
   - Aggiorna bracket/abbinamenti
```

#### **Window Temporale**
- **Deadline Rinunce**: Data limite per comunicare rinuncia
- **Replacement Window**: Tempo per sostituto di accettare
- **Auto-Accept**: Se sostituto non risponde entro X ore, accettazione automatica
- **Cascading**: Se primo sostituto rinuncia, passa al secondo, etc.

#### **Tracking Rinunce**
- **Storico**: Mantiene cronologia per penalizzazioni future
- **Reputation**: Sistema di "affidabilità" per qualificazioni future
- **Blacklist Temporanea**: Esclusione da playoff futuri per rinunce eccessive

### **Playoff Multipli per Torneo**

#### **Configurazione Multipla**
```yaml
Tournament:
  Playoff_A:
    name: "Playoff Principale"
    access: {type: "top_n", n: 8}
    format: "single_elimination"
  Playoff_B:
    name: "Playoff Consolazione"  
    access: {type: "range", start: 9, end: 16}
    format: "round_robin"
  Playoff_C:
    name: "Playoff Fedeltà"
    access: {type: "min_provas", start: 1, end: 20, min_provas: 8}
    format: "swiss"
```

#### **Gestione Sovrapposizioni**
- **Mutual Exclusion**: Un giocatore può qualificarsi solo per un playoff
- **Priority Order**: Ordine di priorità per playoff sovrapposti
- **Choice System**: Giocatore sceglie a quale playoff partecipare

#### **Scheduling Intelligente**
- **Timeline Optimization**: Pianificazione automatica per evitare conflitti
- **Resource Allocation**: Assegnazione tavoli/campi ottimale
- **Participant Availability**: Considerazione disponibilità giocatori

### **Accesso Combinato Multi-Torneo**

#### **Cross-Tournament Qualification**
- **Configurazione**: Playoff che considera classifiche di più tornei
- **Algoritmi**: Somma pesata, migliore risultato, media, etc.
- **Esempio**: "Masters Cup" per migliori giocatori di Torneo A + Torneo B

#### **Season Playoffs**
- **Accumulo Stagionale**: Punteggi accumulati in tutta la stagione
- **Weighted Average**: Media pesata con più peso ai tornei recenti
- **Participation Bonus**: Punti extra per partecipazione costante

---

## 📊 **Sistema Classifiche Multi-Dimensionale**

### **Tre Livelli di Classifiche**

#### **1. Classifica di Turno**
- **Definizione**: Posizione dopo ogni turno specifico di una prova
- **Utilità**: 
  - Tracking progressione durante la prova
  - Base per abbinamenti turno successivo (sistema Amalfi)
  - Analisi performance in tempo reale
- **Calcolo**: Basato su strategia di classificazione configurata
- **Storage**: Tabella `TurnClassification` con snapshot per ogni turno

#### **2. Classifica di Prova**
- **Definizione**: Posizione finale al termine di una singola prova
- **Utilità**:
  - Determinare vincitore della prova
  - Assegnazione premi prova-specifici  
  - Contributo alla classifica generale del torneo
- **Calcolo**: Classifica finale dell'ultimo turno della prova
- **Features**: Handling pari merito, spareggi, premiazioni

#### **3. Classifica di Torneo**
- **Definizione**: Posizione generale aggregando tutte le prove del torneo
- **Algoritmo**: Somma punti ottenuti in ogni prova del torneo
- **Configurazione**: Pesi diversi per prove diverse se necessario
- **Utilizzo**: Base per qualificazioni playoff, premiazioni finali

### **Algoritmi di Aggregazione Torneo**

#### **Somma Semplice (Default)**
```
Punteggio_Torneo = Σ(Punti_Prova_i)
dove Punti_Prova_i = f(Posizione_Prova_i)
```

#### **Sistema a Punti Posizionali**
```
Posizione 1°: 100 punti
Posizione 2°: 90 punti  
Posizione 3°: 85 punti
...
Ultima posizione: 10 punti
```

#### **Media Pesata**
- Prove più recenti pesano di più
- Prove "importanti" (finali stagione) pesano di più
- Configurazione pesi per prova

#### **Best-Of System**
- Conta solo le migliori N prove del giocatore
- Esempio: "Migliori 8 prove su 12 totali"
- Premia costanza eliminando peggiori performance

### **Gestione Partecipazione Parziale**

#### **Penalizzazioni Assenza**
- **Zero Points**: Assenza = 0 punti per quella prova
- **Minimum Points**: Assenza = punteggio minimo comunque
- **Participation Bonus**: Bonus per chi partecipa a tutte le prove

#### **Normalizzazione**
- **Per Numero Prove**: Punteggio medio per prova partecipata
- **Projected Score**: Proiezione basata su performance precedenti
- **Minimum Participation**: Minimo numero prove per classifica valida

---

## ⚖️ **Gestione Pari Merito Avanzata**

### **Livelli di Risoluzione Pari Merito**

#### **1. Automatic Resolution - Criteri Automatici**
**Ordine Standard (configurabile):**
1. **Vittorie**: Numero match vinti
2. **Differenza Punti**: Rack vinti - rack persi  
3. **Scontri Diretti**: Risultato negli incontri diretti tra i pari merito
4. **Ordine Precedente**: Posizione classifica turno precedente
5. **Performance Trend**: Media ultimi N turni
6. **Random**: Sorteggio finale se tutto uguale

**Configurazioni Alternative:**
- Solo vittorie (ignora differenza punti)
- Peso maggiore a scontri diretti
- Criterio temporale (chi ha finito prima)

#### **2. Playoff Match - Spareggio Diretto**
- **Trigger**: Quando criteri automatici non risolvono
- **Formato**: Match singolo con regole standard della prova
- **Scheduling**: Automatico nel primo slot disponibile
- **Gestione Multi-Player**: Torneino tra tutti i pari merito

#### **3. Spot Shot Rally - Sfida Tecnica**
- **Descrizione**: Sfida di abilità tecnica specifica
- **Formati**:
  - Imbucate consecutive da posizione fissa
  - Precisione su target specifici
  - Tempo limite per completare schema
- **Configurazione**: Tipo sfida configurabile per torneo/prova
- **Arbitraggio**: Supervisione ufficiale richiesta

#### **4. Maintain Tie - Posizione Condivisa**
- **Quando Usare**: Pari merito accettabile (es. 3° posto ex-aequo)
- **Implementazione**: Due giocatori con stessa posizione
- **Gestione Successive**: Posizione successiva salta (3°,3°,5°)
- **Premi**: Distribuzione equa dei premi per posizioni condivise

### **Configurazione UI Pari Merito**

#### **Tournament Level**
- **Default Strategy**: Strategia predefinita per tutto il torneo
- **Criteria Order**: Ordine dei criteri automatici
- **Playoff Threshold**: A che livello attivare spareggi (es. solo primi 3 posti)

#### **Prova Level Override**
- **Override Tournament**: Sovrascrivere per prova specifica
- **Special Rules**: Regole speciali per prove importanti
- **Time Constraints**: Gestione tempo per spareggi

#### **Real-Time Decision**
- **Admin Interface**: Decisione manuale durante pari merito
- **Player Choice**: I giocatori scelgono tipo spareggio
- **Automatic Fallback**: Criterio automatico se spareggio non possibile

---

## 👥 **Sistema Utenti e Permessi Gerarchico**

### **Ruoli e Responsabilità Dettagliate**

#### **Admin - Controllo Totale Sistema**

**Accessi Completi:**
- **Gestione Tornei**: Crea, modifica, elimina qualsiasi torneo
- **Gestione Prove**: Controllo completo su tutte le prove di tutti i tornei
- **Gestione Utenti**: 
  - Visualizza tutti gli utenti con statistiche complete
  - Promuove/retrocede ruoli (Player ↔ Director)
  - Gestisce richieste di promozione a Director
  - Può bannare/sbannare utenti
- **Strumenti Sistema**:
  - Reset database con dati di esempio
  - Configurazioni globali sistema
  - Backup/restore dati
  - Monitoraggio performance e log
- **Override Capabilities**:
  - Può sovrascrivere qualsiasi risultato match
  - Può modificare classifiche manualmente
  - Può forzare qualificazioni playoff

**Restrizioni Specifiche:**
- **NON può iscriversi** a nessuna prova (ruolo puramente amministrativo)
- Non appare in classifiche di gioco
- Non può partecipare a match o playoff

**Interfaccia Admin:**
- Dashboard con overview sistema completo
- Tools di gestione batch (es. iscrizioni multiple)
- Pannelli di monitoraggio e analytics
- Strumenti di debug e troubleshooting

#### **Director - Gestione Tornei Assegnati**

**Accessi sui Propri Tornei:**
- **Creazione Tornei**: Può creare nuovi tornei (diventa automaticamente director)
- **Gestione Prove**: Controllo completo su prove dei suoi tornei
  - Crea/modifica/elimina prove
  - Gestisce iscrizioni e liste d'attesa
  - Inserisce risultati match
  - Gestisce playoff e qualificazioni
- **Gestione Partecipanti**: 
  - Vede statistiche giocatori nei suoi tornei
  - Può rimuovere giocatori per violazioni regolamento
  - Gestisce comunicazioni ai partecipanti

**Accessi Limitati:**
- **Visualizzazione Read-Only**: Può vedere tutti gli altri tornei ma senza modificare
- **Partecipazione**: **Può iscriversi** a prove di tornei NON suoi
- **Auto-Assignment**: Tornei creati da Director vengono auto-assegnati a lui

**Sistema Assignment:**
- **Admin Assignment**: Admin può assegnare Director a tornei esistenti
- **Multiple Directors**: Un torneo può avere più Director
- **Granular Permissions**: Possibili permessi specifici per Director (solo risultati, solo iscrizioni, etc.)

**Interfaccia Director:**
- Dashboard filtrata sui propri tornei
- Tools di gestione prove e match
- Comunicazione con partecipanti
- Reports e statistiche dei propri tornei

#### **Player - Partecipazione Competizioni**

**Accessi Personali:**
- **Dashboard Personale**: 
  - Statistiche complete personali
  - Cronologia partecipazioni
  - Classifiche storiche e attuali
- **Gestione Iscrizioni**:
  - Iscrizione/disiscrizione prove aperte
  - Visualizzazione lista d'attesa e posizione
  - Notifiche promozioni da lista d'attesa
- **Inserimento Risultati**:
  - Può inserire risultati dei propri match
  - Sistema conferma con avversario
  - Storico inserimenti per trasparenza

**Accessi di Visualizzazione:**
- **Read-Only Completo**: Può vedere tutti tornei, prove, match, classifiche
- **Statistiche Globali**: Accesso a statistiche generali sistema
- **Performance Tracking**: Analisi delle proprie performance

**Gestione Account:**
- **Profilo**: Modifica informazioni personali
- **Privacy**: Controllo visibilità statistiche
- **Cancellazione Account**: Self-service con conferme multiple

**Interfaccia Player:**
- Dashboard ottimizzata per proprie attività
- Calendario prove disponibili
- Notifiche personalizzate
- Tools di analisi performance personale

### **Sistema Permessi Granulari**

#### **Permission Checking System**
```python
def can_user_perform_action(user, action, resource_id, context=None):
    """
    Esempi:
    - can_user_perform_action(user, 'manage_tournament', tournament_id)
    - can_user_perform_action(user, 'inscribe_to_prova', prova_id)
    - can_user_perform_action(user, 'insert_result', match_id)
    """
```

#### **Permission Matrix**
| Azione | Admin | Director (Own) | Director (Other) | Player |
|--------|-------|----------------|------------------|--------|
| View Tournament | ✅ | ✅ | ✅ | ✅ |
| Create Tournament | ✅ | ✅ | ❌ | ❌ |
| Modify Tournament | ✅ | ✅ | ❌ | ❌ |
| Delete Tournament | ✅ | ❌ | ❌ | ❌ |
| Inscribe to Prova | ❌ | ✅* | ✅ | ✅ |
| Manage Inscriptions | ✅ | ✅ | ❌ | ❌ |
| Insert Match Results | ✅ | ✅ | ❌ | ✅** |
| Override Results | ✅ | ✅ | ❌ | ❌ |
| Manage Users | ✅ | ❌ | ❌ | ❌ |

*Director può iscriversi solo a tornei NON suoi
**Player può inserire solo risultati dei propri match

#### **Context-Aware Permissions**
- **Time-Based**: Alcune azioni possibili solo in certi periodi
- **Status-Based**: Permessi cambiano in base a stato prova/torneo
- **Relationship-Based**: Permessi basati su relazioni specifiche (es. Director assegnato)

---

## 📱 **Sistema Liste d'Attesa Intelligente**

### **Meccanismo Base Liste d'Attesa**

#### **Trigger Attivazione**
- **Limite Raggiunto**: Prove con max_participants configurato
- **Iscrizione Oltre Limite**: Nuove iscrizioni vanno automaticamente in lista d'attesa
- **Posizione Tracking**: Sistema numerico progressivo (1°, 2°, 3°...)

#### **Auto-Enrollment Process**
```
1. Giocatore si disiscrive da prova piena
2. Sistema automaticamente:
   - Trova primo in lista d'attesa
   - Lo promuove a "iscritto"
   - Invia notifica immediata
   - Aggiorna posizioni restanti
   - Log dell'operazione
```

### **Sistema Notifiche Avanzate**

#### **Tipi di Notifiche**
- **Aggiunta Lista**: Conferma inserimento con posizione
- **Cambio Posizione**: Update quando posizione migliora
- **Promozione**: Notifica immediata quando promosso
- **Deadline Alert**: Promemoria accettazione entro X tempo
- **Cancellazione**: Notifica se rimosso da lista

#### **Canali Comunicazione**
- **Email**: Notifiche email immediate e riassuntive
- **Sistema Interno**: Notifiche in-app
- **SMS/WhatsApp**: Per notifiche critiche (da configurare)

### **Position Tracking e Analytics**

#### **Metriche per Utente**
- **Posizione Attuale**: In tutte le liste d'attesa attive
- **Storico Posizioni**: Tracking movimento nelle liste
- **Success Rate**: % di volte promosso da lista d'attesa
- **Average Wait Time**: Tempo medio di attesa prima promozione

#### **Metriche per Prova**
- **Lista Lunghezza**: Numero persone in attesa
- **Turnover Rate**: Frequenza cambi iscritti/lista
- **Demand Forecast**: Previsione richiesta basata su storico

### **Expiration Management**

#### **Window Accettazione**
- **Deadline**: Tempo limite per accettare promozione (es. 24h)
- **Auto-Accept**: Se non risposta entro deadline = accettazione automatica
- **Manual Decline**: Possibilità di rifiutare esplicitamente
- **Snooze Option**: Rimandare decisione per X ore

#### **Gestione Scadenze**
```
1. Player promosso da lista d'attesa
2. Riceve notifica con deadline 24h
3. Opzioni:
   - Accetta → diventa iscritto
   - Rifiuta → passa al successivo in lista
   - Non risponde → auto-accettazione dopo 24h
   - Snooze → rimanda di 12h (una volta sola)
```

### **Priority System Avanzato**

#### **Criteri di Priorità Configurabili**
- **FIFO (First In, First Out)**: Default - ordine di arrivo
- **Ranking-Based**: Priorità basata su classifica torneo
- **Loyalty-Based**: Priorità a chi partecipa spesso
- **Payment-Based**: Priorità a chi ha pagato quota in anticipo
- **Mixed Formula**: Combinazione pesata di più criteri

#### **Configurazione per Torneo/Prova**
```yaml
WaitingListConfig:
  primary_criterion: "fifo"  # fifo, ranking, loyalty, payment
  secondary_criterion: "ranking"
  weights:
    fifo: 0.6
    ranking: 0.3  
    loyalty: 0.1
```

#### **Dynamic Re-ordering**
- **Ranking Changes**: Riordino automatico se classifica cambia
- **Payment Updates**: Promozione immediata al pagamento
- **Manual Override**: Admin/Director può riordinare manualmente

### **Integration con Sistema Pagamenti**

#### **Payment States**
- **Unpaid**: In lista d'attesa senza pagamento
- **Paid**: Pagamento effettuato, priorità maggiore
- **Refund Pending**: Rimborso in corso per mancata promozione

#### **Automatic Refunds**
- **Timeout**: Rimborso automatico se non promosso entro X giorni
- **Event Cancelled**: Rimborso completo se prova annullata
- **Partial Refund**: Rimborso parziale se prova ridimensionata

---

## 📈 **Sistema Match e Risultati Professionale**

### **Tipologie Match Supportate**

#### **Match Normale (1 vs 1)**
- **Setup Standard**: Due giocatori, punteggio individuale
- **Tracking**: Player1, Player2, punteggi, vincitore
- **Stato**: pending → playing → completed → validated

#### **Match Trio (1 vs 1 vs 1)**
- **Setup Speciale**: Tre giocatori simultanei
- **Punteggio**: Ogni giocatore accumula punti contro gli altri due
- **Calcolo Finale**: Somma rack vinti contro tutti gli avversari
- **Classifica Trio**: 1°, 2°, 3° interno al trio

#### **Bye Match (1 vs X)**
- **Giocatore Fortunato**: Riceve vittoria automatica
- **Punteggio**: Automatico basato su regole prova
- **Zero Effort**: Nessun gioco richiesto, solo assegnazione punti

### **Sistema Inserimento Risultati**

#### **Multi-Source Input**
- **Player Self-Report**: Giocatori inseriscono propri risultati
- **Director Input**: Director inserisce per le sue prove
- **Admin Override**: Admin può inserire/modificare qualsiasi risultato

#### **Workflow Validazione**
```
1. Player A inserisce risultato match A vs B
2. Sistema notifica Player B per conferma
3. Opzioni Player B:
   - Conferma → risultato validato
   - Contesta → escalation a Director/Admin
   - Ignora → auto-conferma dopo 24h
4. Risultato validato → aggiornamento classifiche
```

#### **Conflict Resolution**
- **Contestazione**: Player può contestare risultato inserito
- **Escalation**: Director/Admin interviene per risoluzione
- **Evidence System**: Possibilità allegare foto/video risultato
- **Manual Override**: Admin può forzare risultato definitivo

### **Result Validation System**

#### **Automatic Checks**
- **Score Validity**: Punteggi coerenti con regole prova
- **Player Eligibility**: Verifica giocatori possano giocare match
- **Timeline Coherence**: Match giocato in finestra temporale valida
- **Duplicate Prevention**: Previene inserimento multiplo stesso match

#### **Business Rules Validation**
- **Match Format**: Rispetto formato "al meglio di" vs "esatto numero"
- **Tournament Rules**: Conformità a regole specifiche torneo
- **Fair Play**: Detection pattern sospetti (es. troppi forfeit)

### **Historical Tracking Completo**

#### **Match History**
- **Chi Ha Inserito**: Tracking completo di chi ha inserito ogni risultato
- **Timestamp**: Quando è stato inserito ogni risultato
- **Modifiche**: Cronologia di tutte le modifiche con motivi
- **Validation**: Chi ha validato e quando

#### **Audit Trail**
```
Match #123 History:
1. 2025-01-15 10:30 - Player A inserted result: 7-3
2. 2025-01-15 11:15 - Player B confirmed result
3. 2025-01-15 11:16 - System auto-validated result
4. 2025-01-16 09:00 - Director modified to 6-4 (correction)
5. 2025-01-16 09:01 - Admin approved modification
```

#### **Integrity Checks**
- **Tampering Detection**: Identificazione modifiche sospette
- **Performance Analytics**: Pattern analysis per detect anomalie
- **Consistency Verification**: Cross-check con altri match

### **Real-time Updates System**

#### **Live Classification Updates**
- **Immediate Calculation**: Classifiche aggiornate immediatamente dopo validazione
- **Cascade Updates**: Aggiornamento classifica torneo dopo classifica prova
- **Notification System**: Notifica cambio posizioni a giocatori interessati

#### **Dashboard Integration**
- **Live Scores**: Punteggi in tempo reale su dashboard
- **Progress Tracking**: Avanzamento turni e completamento prove
- **Performance Metrics**: Statistiche aggiornate in tempo reale

### **Match Scheduling e Logistics**

#### **Auto-Scheduling**
- **Time Slot Assignment**: Assegnazione automatica orari match
- **Table/Court Allocation**: Distribuzione ottimale risorse
- **Player Availability**: Considerazione disponibilità giocatori
- **Conflict Avoidance**: Prevenzione sovrapposizioni

#### **Resource Management**
- **Equipment Tracking**: Assegnazione tavoli/campi specifici
- **Official Assignment**: Assegnazione arbitri/giudici se necessario
- **Facility Integration**: Integrazione con sistemi prenotazione strutture

---

## 🎪 **Sistema Multi-Tournament**

### **Tournament Isolation - Isolamento Completo**

#### **Data Separation**
- **Separate Configurations**: Ogni torneo mantiene proprie strategie
- **Independent Classifications**: Classifiche separate per torneo
- **Isolated Match Pools**: Match non cross-contaminano tra tornei
- **Resource Independence**: Liste d'attesa, playoff, settings indipendenti

#### **Permission Isolation**
- **Director Assignments**: Director assegnati a tornei specifici
- **Scope Limitations**: Permessi limitati ai propri tornei
- **Cross-Tournament View**: Visualizzazione read-only altri tornei

### **Shared Resources Management**

#### **Player Sharing**
- **Single User Account**: Un account per tutti i tornei
- **Multiple Participations**: Stesso giocatore può partecipare a più tornei
- **Cross-Tournament Statistics**: Statistiche aggregate tra tornei
- **Conflict Detection**: Identificazione sovrapposizioni orarie

#### **Director Multi-Assignment**
- **Multiple Tournaments**: Director può gestire più tornei
- **Role Separation**: Ruoli diversi per tornei diversi
- **Workload Balance**: Distribution carico lavoro tra Director

### **Cross-Tournament Views e Analytics**

#### **Aggregate Dashboards**
- **System Overview**: Dashboard admin con tutti i tornei
- **Performance Comparison**: Confronto performance tra tornei
- **Resource Utilization**: Utilizzo risorse across tornei
- **Player Movement**: Tracking movimento giocatori tra tornei

#### **Global Statistics**

**Player Level:**
- **Overall Win Rate**: Win rate globale su tutti i tornei
- **Tournament Diversity**: Varietà tornei partecipati  
- **Cross-Tournament Ranking**: Ranking globale del giocatore
- **Activity Level**: Frequenza partecipazione generale

**System Level:**
- **Tournament Health**: Metriche salute per ogni torneo
- **Participation Trends**: Trend partecipazione nel tempo
- **Popular Formats**: Formati di torneo più popolari
- **Seasonal Patterns**: Pattern stagionali di attività

### **Season e League Management**

#### **Multi-Tournament Seasons**
- **Season Definition**: Gruppi di tornei che formano una stagione
- **Season Championship**: Playoff finale basato su performance stagionale
- **Points Allocation**: Sistema punti across multiple tornei
- **Season Statistics**: Statistiche e classifiche stagionali

#### **League Structure**
```
League: "Serie A Biliardo 2025"
├── Tournament 1: "Autumn Classic"
├── Tournament 2: "Winter Championship"  
├── Tournament 3: "Spring Open"
└── Season Playoff: "Grand Finale"
```

#### **Cross-Tournament Qualification**
- **Aggregate Scoring**: Punteggi combinati per qualificazioni
- **Best-Of Selection**: Migliori N risultati per qualificarsi
- **Participation Requirements**: Minimo tornei per qualificarsi
- **Weighted Scoring**: Pesi diversi per tornei diversi

### **Resource Optimization**

#### **Facility Management**
- **Shared Venues**: Gestione sedi condivise tra tornei
- **Scheduling Optimization**: Ottimizzazione calendario per evitare conflitti
- **Equipment Sharing**: Condivisione attrezzature tra eventi

#### **Staff Coordination**
- **Director Workload**: Bilanciamento carico lavoro Director
- **Official Scheduling**: Coordinamento arbitri/giudici
- **Volunteer Management**: Gestione volontari per eventi multipli

### **Communication e Notification System**

#### **Multi-Tournament Notifications**
- **Consolidated Alerts**: Notifiche aggregate per più tornei
- **Tournament-Specific**: Notifiche filtrate per torneo
- **Cross-Tournament**: Comunicazioni che riguardano più tornei
- **Preference Management**: Controllo preferenze notifiche per torneo

#### **Centralized Communication**
- **Announcement System**: Comunicazioni generali sistema
- **Tournament Updates**: Update specifici per torneo
- **Emergency Communications**: Comunicazioni urgenti cross-torneo
- **Newsletter Integration**: Newsletter aggregate sistema

---

## 🔧 **Configurazioni e Customizations**

### **System-Level Configuration**

#### **Global Settings**
- **Default Behaviors**: Comportamenti di default per nuovi tornei
- **UI Themes**: Temi personalizzabili per organizzazioni
- **Language Support**: Multi-language support
- **Timezone Management**: Gestione fusi orari per eventi internazionali

#### **Business Rules Configuration**
- **Point Systems**: Sistemi punti configurabili
- **Penalty Systems**: Sistema penalità per comportamenti scorretti
- **Reward Systems**: Sistema premi e riconoscimenti
- **Integration APIs**: API per sistemi esterni

### **Organization Customization**

#### **Branding**
- **Logo Upload**: Logo personalizzato per tornei
- **Color Schemes**: Schemi colori personalizzati
- **Custom Fields**: Campi aggiuntivi per giocatori/tornei
- **Document Templates**: Template personalizzati per certificati/reports

#### **Rule Variations**
- **Discipline Variants**: Supporto varianti discipline (8-ball, 9-ball, etc.)
- **Scoring Variations**: Variazioni sistemi punteggio
- **Format Modifications**: Modifiche formati standard
- **Custom Strategies**: Possibilità sviluppare strategie custom

---

## 📊 **Reporting e Analytics**

### **Standard Reports**

#### **Tournament Reports**
- **Participation Summary**: Riassunto partecipazioni
- **Performance Analysis**: Analisi performance giocatori
- **Revenue Reports**: Report economici tornei
- **Attendance Trends**: Trend presenza nel tempo

#### **Player Reports**
- **Individual Performance**: Report prestazioni individuali
- **Progress Tracking**: Tracking progressi nel tempo
- **Comparative Analysis**: Confronto con altri giocatori
- **Achievement Summary**: Riassunto traguardi raggiunti

### **Advanced Analytics**

#### **Predictive Analytics**
- **Performance Prediction**: Previsione prestazioni future
- **Participation Forecasting**: Previsione partecipazioni
- **Tournament Success Factors**: Fattori successo tornei
- **Player Retention Analysis**: Analisi retention giocatori

#### **Machine Learning Integration**
- **Matchmaking Optimization**: ML per abbinamenti ottimali
- **Churn Prediction**: Previsione abbandono giocatori
- **Performance Pattern Recognition**: Riconoscimento pattern performance
- **Fraud Detection**: Detection comportamenti anomali

---

Questo documento rappresenta la **visione completa** del sistema refactorato, con ogni funzionalità descritta in estremo dettaglio per guidare l'implementazione nelle prossime fasi del progetto.