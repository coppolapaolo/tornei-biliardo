# 🧪 Testing Guide - Webapp Tornei Biliardo

> **Guida completa** per testare tutte le funzionalità implementate prima di continuare con nuovi sviluppi.

## 🎯 Overview Testing

Questa guida ti permette di verificare che tutte le funzionalità di **STEP 1, 2 e 2.5** funzionino correttamente prima di procedere con **STEP 3** (Sistema Amalfi).

### 🚀 Quick Start
1. **Avvia applicazione**: `python app.py`
2. **Vai a**: `http://localhost:5000`
3. **Segui i test** in ordine sequenziale
4. **Documenta problemi** riscontrati

---

## 🔄 Test 1: Reset Database e Setup Iniziale

### 🎯 Obiettivo
Verificare reset database e creazione dati di esempio

### 📋 Procedura
```bash
1. Vai a: http://localhost:5000/reset
2. Inserisci password: RESET_DB_CONFIRM
3. Clicca "RESET DATABASE"
4. Verifica messaggio di successo
5. Verifica creazione utenti: admin/admin123, mario/mario123, pino/pino123
```

### ✅ Risultati Attesi
- ✅ Database resettato senza errori
- ✅ Creati 2 tornei di esempio: "Torneo Primavera 2025", "Coppa Estate 2025"
- ✅ Ogni torneo ha almeno 1 prova configurata
- ✅ Logout automatico dopo reset
- ✅ Redirect a homepage con tornei visibili

### 🐛 Problemi Comuni
- ❌ **Errore 403**: DEBUG_MODE = False in config.py
- ❌ **Database locked**: Chiudi altre connessioni al DB
- ❌ **Errore permissions**: Verifica permessi cartella instance/

---

## 🏠 Test 2: Homepage Multi-Torneo

### 🎯 Obiettivo
Verificare visualizzazione simultanea di tutti i tornei attivi

### 📋 Procedura
```bash
1. Homepage: http://localhost:5000
2. Verifica presenza entrambi i tornei
3. Controlla informazioni per ogni torneo:
   - Nome e tipo torneo
   - Status badge corretto
   - Prove prossime con date
   - Classifiche (se disponibili)
4. Testa pulsanti "Iscriviti" (senza login)
5. Verifica sezione "Come Partecipare" per utenti non autenticati
```

### ✅ Risultati Attesi
- ✅ Entrambi i tornei visibili simultaneamente
- ✅ Ogni torneo mostra le sue prove specifiche
- ✅ Status badge corretto per ogni prova
- ✅ Date visualizzate nel timezone locale
- ✅ Pulsanti iscrizione funzionali
- ✅ UI responsive su mobile

### 🐛 Problemi Comuni
- ❌ **Solo 1 torneo**: Controlla create_sample_tournament() in utils.py
- ❌ **Date sbagliate**: Problema timezone JavaScript
- ❌ **Layout rotto**: Errori Bootstrap CSS

---

## 🔐 Test 3: Sistema Autenticazione e Quick Login

### 🎯 Obiettivo
Verificare login, registrazione e quick login debug

### 📋 Procedura

#### 3.1 Login Normale
```bash
1. Vai a: /auth/login
2. Login: admin / admin123
3. Verifica redirect a dashboard admin
4. Logout: Menu utente → Logout
5. Login: mario / mario123  
6. Verifica redirect a dashboard player
```

#### 3.2 Quick Login Debug (Footer)
```bash
1. Scroll in fondo alla pagina
2. Verifica presenza footer DEBUG (se DEBUG_MODE=True)
3. Clicca "Admin" nel footer → Verifica login automatico admin
4. Clicca "Mario" nel footer → Verifica switch a mario
5. Clicca "Pino" nel footer → Verifica switch a pino
```

#### 3.3 Registrazione
```bash
1. Vai a: /auth/register
2. Crea nuovo utente: test_user / test@email.com / password123
3. Verifica login automatico dopo registrazione
4. Verifica redirect a dashboard player
```

### ✅ Risultati Attesi
- ✅ Login funziona con credenziali corrette
- ✅ Error handling per credenziali sbagliate
- ✅ Quick login debug opera correttamente
- ✅ Registrazione crea utente e fa login automatico
- ✅ Redirect appropriati basati su ruolo utente
- ✅ Navbar mostra utente corrente e badge admin

### 🐛 Problemi Comuni
- ❌ **Quick login non visibile**: DEBUG_MODE = False
- ❌ **Errore login**: Password hash problema
- ❌ **Redirect loop**: Errore in login_manager configuration

---

## 👨‍💼 Test 4: Dashboard e Funzionalità Admin

### 🎯 Obiettivo
Verificare tutte le funzionalità amministrative

### 📋 Procedura

#### 4.1 Dashboard Admin
```bash
1. Login come admin
2. Vai a: /admin/
3. Verifica lista tornei con statistiche
4. Testa "Nuovo Torneo" → Crea "Torneo Test 2025"
5. Verifica opzioni: Senza X, Playoff, Challenge
```

#### 4.2 Gestione Tornei
```bash
1. Clicca "Dettagli" su un torneo
2. Verifica informazioni torneo complete
3. Testa "Nuova Prova" con tutti i campi:
   - Numero: 2
   - Nome: Seconda Prova
   - Data: prossima settimana
   - Luogo: Test Location  
   - Disciplina: palla 8
   - Distanza: 5 rack esatti (non "al meglio di")
   - Quota: €12.50
   - Min/Max partecipanti: 4/12
```

#### 4.3 Gestione Prove
```bash
1. Clicca su prova creata
2. Verifica tutte le informazioni
3. Testa "Apri Iscrizioni":
   - Inizio: ora corrente
   - Fine: tra 2 ore
4. Verifica status prova → "Iscrizioni Aperte"
```

#### 4.4 Gestione Utenti
```bash
1. Vai a: /admin/users
2. Verifica lista utenti con statistiche
3. Clicca "Dettagli" su mario
4. Verifica scheda completa:
   - Info personali
   - Statistiche partite
   - Iscrizioni per torneo
   - Classifiche (se disponibili)
```

### ✅ Risultati Attesi
- ✅ Dashboard mostra tutti i tornei
- ✅ Creazione torneo funziona con tutte le opzioni
- ✅ Creazione prova con configurazione completa
- ✅ Apertura iscrizioni con timezone corretto
- ✅ Lista utenti con statistiche accurate
- ✅ Schede dettagliate utenti complete

---

## 🎮 Test 5: Dashboard Giocatore Multi-Torneo

### 🎯 Obiettivo
Verificare dashboard giocatore con selezione torneo

### 📋 Procedura

#### 5.1 Dashboard Multi-Torneo
```bash
1. Login come mario
2. Vai a: /player/
3. Verifica dropdown selezione torneo (se >1 torneo)
4. Testa switch tra tornei:
   - Seleziona "Torneo Primavera 2025"
   - Verifica prove specifiche per quel torneo
   - Seleziona "Coppa Estate 2025"  
   - Verifica cambio prove
```

#### 5.2 Iscrizioni e Disiscrizioni
```bash
1. Iscriviti a una prova disponibile
2. Verifica comparsa in "Le Mie Iscrizioni"
3. Verifica pulsante "Disiscriviti" attivo
4. Testa disiscrizione → Conferma rimozione
5. Verifica ritorno in "Prove Disponibili"
```

#### 5.3 Profilo Personale
```bash
1. Menu utente → "Il mio Profilo"
2. Verifica tutte le sezioni:
   - Statistiche generali
   - Partite recenti (se disponibili)
   - Classifiche per torneo
   - Informazioni personali
   - Iscrizioni per torneo
```

### ✅ Risultati Attesi
- ✅ Dropdown torneo presente se >1 torneo attivo
- ✅ Switch torneo aggiorna contenuto appropriatamente
- ✅ Iscrizioni/disiscrizioni funzionano correttamente
- ✅ Profilo mostra statistiche accurate
- ✅ URL mantiene tournament_id selezionato

---

## ⚙️ Test 6: Sistema Partite e Risultati

### 🎯 Obiettivo
Verificare inserimento risultati e controlli admin

### 📋 Procedura

#### 6.1 Setup Partita
```bash
1. Admin: Iscrivere mario e pino a stessa prova
2. Admin: Avviare primo turno  
3. Verifica creazione match mario vs pino
4. Vai al dettaglio partita (admin o player)
```

#### 6.2 Inserimento Risultati Player
```bash
1. Login mario → Vai al match
2. Aggiungi rack vinto da mario
3. Verifica badge "In attesa conferma"
4. Login pino → Vai al match
5. Conferma rack di mario
6. Verifica badge "Confermato"
7. Mario: Aggiungi rack, poi rimuovilo
8. Verifica aggiornamento punteggio
```

#### 6.3 Controlli Admin  
```bash
1. Login admin → Vai al match
2. Verifica sezione "Controlli Amministratore"
3. Testa "Imposta Risultato Diretto":
   - Mario: 4, Pino: 2
   - Verifica creazione rack automatica
   - Verifica match completato
4. Testa "Reset Partita"
5. Verifica rimozione tutti i rack
```

### ✅ Risultati Attesi
- ✅ Abbinamenti primo turno casuali
- ✅ Sistema conferma punti funziona
- ✅ Rimozione rack per chi ha inserito
- ✅ Admin può impostare risultati diretti
- ✅ Validazione modalità "al meglio di" vs "esatto numero"
- ✅ Reset partita pulisce tutto

---

## 🔧 Test 7: Admin Tools Avanzati

### 🎯 Obiettivo
Verificare strumenti admin per gestione risultati

### 📋 Procedura

#### 7.1 Overview Risultati
```bash
1. Admin: Vai a prova con partite create
2. Clicca "Overview Risultati"
3. Verifica tabella partite per turno
4. Testa "Risultato Rapido":
   - Clicca icona tachimetro su una partita
   - Imposta risultato nel modal
   - Verifica aggiornamento immediato
```

#### 7.2 Gestione Rack Admin
```bash
1. Vai a partita con rack inseriti
2. Verifica pulsanti admin su ogni rack:
   - Rimuovi (cestino rosso)
   - Valida (check verde)
3. Testa validazione admin → Badge "Validato Admin"
4. Verifica che giocatori non possano più modificare
```

#### 7.3 Batch Operations
```bash
1. Crea multiple partite con risultati diversi
2. Usa Overview per gestire tutte rapidamente
3. Verifica statistiche aggiornate in tempo reale
4. Testa reset multipli partite
```

### ✅ Risultati Attesi
- ✅ Overview mostra tutte le partite organizzate
- ✅ Risultato rapido funziona correttamente
- ✅ Validazione admin override sistema conferma
- ✅ Batch operations migliorano efficienza
- ✅ Statistiche aggiornate in tempo reale

---

## 👤 Test 8: Gestione Account Avanzata

### 🎯 Obiettivo
Verificare funzionalità gestione account giocatori

### 📋 Procedura

#### 8.1 Cancellazione Account
```bash
1. Login test_user (creato nel test 3)
2. Menu utente → "Elimina Account"
3. Leggi warnings e procedure
4. SENZA completare, torna indietro
5. Verifica che account sia ancora attivo
```

#### 8.2 Statistiche Utente
```bash
1. Admin: Crea alcune partite completate
2. Player: Verifica aggiornamento statistiche in:
   - Dashboard sidebar
   - Profilo personale  
   - Admin scheda utente
3. Verifica calcoli corretti:
   - Partite giocate/vinte/perse
   - Percentuale vittorie
   - Differenza rack
```

#### 8.3 Gestione Iscrizioni Complessa
```bash
1. Iscriviti a multiple prove di tornei diversi
2. Verifica visualizzazione per torneo
3. Testa disiscrizione da prove diverse
4. Verifica mantenimento contesto torneo
```

### ✅ Risultati Attesi
- ✅ Cancellazione account sicura con warnings
- ✅ Statistiche calcolate correttamente
- ✅ Aggiornamenti real-time
- ✅ Gestione multi-torneo senza conflitti

---

## 🌐 Test 9: Responsive e UI/UX

### 🎯 Obiettivo
Verificare esperienza utente su diversi dispositivi

### 📋 Procedura

#### 9.1 Desktop Testing
```bash
1. Testa su Chrome, Firefox, Safari
2. Verifica tutte le funzionalità principali
3. Controlla console JavaScript per errori
4. Verifica performance (< 2 secondi caricamento)
```

#### 9.2 Mobile Testing  
```bash
1. Ridimensiona browser a 375px (iPhone)
2. Testa navigazione mobile:
   - Menu hamburger
   - Dropdown funzionanti
   - Form utilizzabili
   - Tabelle scrollabili
3. Verifica touch interactions
```

#### 9.3 Accessibility
```bash
1. Testa navigazione con Tab
2. Verifica contrast ratio
3. Controlla aria-labels
4. Testa screen reader compatibility
```

### ✅ Risultati Attesi
- ✅ Layout responsive su tutte le dimensioni
- ✅ Funzionalità accessibili da mobile
- ✅ Performance ottimale
- ✅ Nessun errore JavaScript console
- ✅ Accessibility standards rispettati

---

## 🔍 Test 10: Edge Cases e Error Handling

### 🎯 Obiettivo
Verificare gestione casi limite ed errori

### 📋 Procedura

#### 10.1 Validazioni Form
```bash
1. Prova creare torneo con nome vuoto
2. Prova creare prova con data passata
3. Prova iscriversi a prova scaduta
4. Prova inserire rack con vincitore sbagliato
5. Verifica messaggi errore appropriati
```

#### 10.2 Autorizzazioni
```bash
1. Logout → Prova accedere /admin/ 
2. Player → Prova accedere funzioni admin
3. Prova modificare partita di altri
4. Verifica redirect e messaggi errore
```

#### 10.3 Database Constraints
```bash
1. Prova duplicare username in registrazione
2. Prova email duplicata
3. Prova eliminare torneo con iscrizioni
4. Verifica error handling database
```

### ✅ Risultati Attesi
- ✅ Validazioni client e server-side
- ✅ Error messages informativi
- ✅ Autorizzazioni rispettate sempre
- ✅ Database integrity mantenuta
- ✅ Graceful error handling

---

## 📊 Checklist Completa

### ✅ STEP 1: Sistema Base
- [ ] Reset database funziona
- [ ] Creazione tornei e prove
- [ ] Sistema iscrizioni con timezone
- [ ] Abbinamenti primo turno
- [ ] Inserimento risultati rack-by-rack
- [ ] Modalità "al meglio di" vs "esatto numero"

### ✅ STEP 2: Gestione Utenti  
- [ ] Lista utenti admin con statistiche
- [ ] Schede dettagliate utenti
- [ ] Profilo personale giocatori
- [ ] Sistema cancellazione account
- [ ] Disiscrizione prove
- [ ] Sistema conferma/rimozione punti
- [ ] Ultime partite in dashboard
- [ ] Quick login debug

### ✅ STEP 2.5: Multi-Tournament
- [ ] Homepage multi-torneo
- [ ] Dashboard con selezione torneo
- [ ] Admin risultati diretti
- [ ] Overview risultati batch
- [ ] Controlli admin match
- [ ] Reset partite
- [ ] Validazione rack admin

### ✅ Qualità Generale
- [ ] UI responsive mobile/desktop
- [ ] Performance < 2 secondi
- [ ] Error handling robusto
- [ ] Autorizzazioni sicure
- [ ] Validazioni complete
- [ ] Nessun errore JavaScript

---

## 🚨 Troubleshooting

### Problemi Comuni e Soluzioni

#### Database Issues
```bash
# Database locked
pkill python
rm instance/billiard_tournament.db
python app.py

# Migration needed
flask db upgrade
# oppure reset completo
```

#### Debug Mode Issues
```python
# In config.py
DEBUG_MODE = True  # Per vedere quick login e debug footer
```

#### Timezone Problems
```javascript
// Browser console
console.log(Intl.DateTimeFormat().resolvedOptions().timeZone)
// Deve mostrare timezone corretto
```

#### Performance Issues
```bash
# Check query performance
export FLASK_ENV=development
export SQLALCHEMY_ECHO=True
python app.py
# Vedi query SQL nella console
```

---

## 🎯 Report Testing

### Template Report
```markdown
## Test Results - [Data]

### Funzionalità Testate:
- [ ] ✅ Reset Database
- [ ] ✅ Homepage Multi-Torneo  
- [ ] ✅ Sistema Autenticazione
- [ ] ✅ Dashboard Admin
- [ ] ✅ Dashboard Player
- [ ] ✅ Sistema Partite
- [ ] ✅ Admin Tools
- [ ] ✅ Gestione Account
- [ ] ✅ Responsive UI
- [ ] ✅ Edge Cases

### Problemi Riscontrati:
1. [Descrizione problema]
   - Priorità: Alta/Media/Bassa
   - Impatto: Critico/Moderato/Minore
   - Soluzione: [Se nota]

### Performance:
- Tempo caricamento homepage: X secondi
- Tempo reset database: X secondi  
- Errori JavaScript: X

### Raccomandazioni:
- [Azioni necessarie prima di STEP 3]
```

---

## ✅ Ready for STEP 3?

### Pre-requisiti STEP 3:
- [ ] **Tutti i test** completati con successo
- [ ] **Nessun errore critico** nel sistema attuale
- [ ] **Performance** accettabile (< 2 sec)
- [ ] **Database** in stato consistente
- [ ] **Documentazione** committed nel repository

### Se tutto OK:
🚀 **PROCEDI CON STEP 3: Sistema Abbinamenti Amalfi**

### Se problemi:
🔧 **RISOLVI ISSUES** prima di continuare sviluppo

---

*Testing Guide aggiornata: 27 luglio 2025*  
*Versione testata: v2.5.0*  
*Prossimo test: v3.0.0 (post-Amalfi)*