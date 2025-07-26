# 🎱 Webapp Torneo Biliardo

Applicazione web completa per la gestione professionale di tornei di biliardo con sistema modulare, abbinamenti automatici, classifiche e gestione match avanzata.

## ✨ Caratteristiche Principali

- 🏗️ **Architettura Modulare** con Blueprint Flask
- 🎮 **Modalità di Gioco Avanzate** ("Al meglio di" vs "Esatto numero")  
- 📍 **Gestione Completa Prove** (luogo, quota, min/max partecipanti)
- ⏰ **Timezone-Aware** per iscrizioni e orari
- 🔧 **Sistema Debug** integrato per sviluppatori
- 📱 **Responsive Design** per mobile e desktop

## 🚀 Funzionalità Attuali

### 👨‍💼 **Amministratori:**
- ✅ **Gestione Tornei**: Creazione, modifica, attivazione/disattivazione
- ✅ **Configurazione Prove Avanzata**:
  - 📍 Luogo dell'evento
  - 💰 Quota di partecipazione
  - 👥 Numero minimo/massimo partecipanti
  - 🎯 Modalità di gioco ("Al meglio di" o "Esatto numero")
  - 🔄 Numero di turni personalizzabile
  - 📝 Descrizioni opzionali
- ✅ **Auto-popolamento**: Copia automatica impostazioni da prove precedenti
- ✅ **Gestione Iscrizioni**: Apertura/chiusura con date timezone-aware
- ✅ **Sorteggi Automatici** per primo turno
- ✅ **Validazione Risultati** con sistema rack-by-rack

### 🎮 **Giocatori:**
- ✅ **Dashboard Personalizzata** con prove disponibili
- ✅ **Iscrizioni Intelligenti** con controllo date e limiti
- ✅ **Visualizzazione Deadline** per iscrizioni in scadenza
- ✅ **Inserimento Risultati** rack per rack
- ✅ **Abbinamenti Real-time** per ogni turno

### 🛠️ **Sistema:**
- ✅ **Debug Mode Avanzato** con statistiche database
- ✅ **Reset Database** con dati di test
- ✅ **Git Workflow** completo
- ✅ **Status Dinamici** per prove (considerando date reali)

## 📁 Struttura Progetto (Modulare)

```
tornei-biliardo/
├── app.py                 # 🔥 App principale (factory pattern)
├── config.py             # ⚙️ Configurazioni ambiente
├── models.py             # 🗄️ Modelli SQLAlchemy completi
├── utils.py              # 🛠️ Funzioni helper e decoratori
├── routes/               # 📦 Route organizzate per funzionalità
│   ├── __init__.py       # Blueprint registration
│   ├── auth.py           # 🔐 Autenticazione (login/register/logout)
│   ├── admin.py          # 👨‍💼 Gestione tornei e prove (admin)
│   ├── player.py         # 🎮 Dashboard e iscrizioni (giocatori)
│   └── main.py           # 🏠 Home, reset, redirects
├── templates/            # 📄 Template HTML organizzati
│   ├── base.html         # Template base con debug e timezone
│   ├── index.html        # Homepage con tornei attivi
│   ├── login.html        # Sistema login
│   ├── register.html     # Registrazione utenti
│   ├── match_detail.html # Dettaglio partite
│   ├── reset.html        # Reset database (debug)
│   ├── admin/           # 👨‍💼 Template amministratore
│   │   ├── dashboard.html      # Dashboard tornei
│   │   ├── tournament_detail.html  # Gestione torneo completa
│   │   ├── tournament_edit.html    # Modifica torneo
│   │   ├── prova_detail.html       # Gestione prova avanzata
│   │   └── prova_edit.html         # Modifica prova
│   └── player/          # 🎮 Template giocatore
│       └── dashboard.html      # Dashboard personalizzata
├── requirements.txt      # Dipendenze Python
├── README.md            # Questa documentazione
└── .gitignore           # File da ignorare
```

## 🎯 Modelli Database

### **Tournament** (Semplificato)
```python
- name: str              # Nome torneo (include anno se necessario)
- tournament_type: str   # Tipo (Amalfi, ecc.)
- without_x: bool        # Opzione "senza X"
- final_playoffs: bool   # Playoff finali
- challenge_mode: bool   # Modalità challenge
- is_active: bool        # Stato attivazione
```

### **Prova** (Molto Avanzato)
```python
- number: int            # Numero prova (1-20)
- name: str             # Nome opzionale
- date: date            # Data dell'evento
- location: str         # 📍 Luogo
- description: text     # 📝 Descrizione opzionale
- rounds_count: int     # 🔄 Numero turni (1-10)
- min_participants: int # 👥 Minimo iscritti
- max_participants: int # 👥 Massimo iscritti (opzionale)
- entry_fee: float      # 💰 Quota partecipazione
- discipline: str       # Disciplina (palla 8/9/10)
- distance: int         # Numero rack
- best_of: bool         # 🎯 True="Al meglio di", False="Esatto numero"
```

## 🔧 Setup e Installazione

### **Requisiti:**
- Python 3.8+
- Git
- Account GitHub (per deploy)

### **Setup Locale:**
```bash
# Clona repository
git clone https://github.com/coppolapaolo/tornei-biliardo.git
cd tornei-biliardo

# Virtual environment
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
# oppure: venv\Scripts\activate  # Windows

# Installa dipendenze
pip install -r requirements.txt

# Avvia applicazione
python app.py
```

**App disponibile su:** `http://localhost:5000`

### **Deploy PythonAnywhere:**
```bash
# Console PythonAnywhere
cd mysite
git pull origin main
# Se modifiche Python: Web → Reload webapp
```

**App produzione:** `https://coppolapaolo.pythonanywhere.com`

## 🚀 Quick Start

### **1. Reset Database (Prima volta):**
1. Vai su `http://localhost:5000/reset`
2. Password: `RESET_DB_CONFIRM`
3. ✅ Crea utenti: `admin/admin123`, `mario/mario123`, `pino/pino123`

### **2. Test Amministratore:**
1. **Login** → `admin/admin123`
2. **Nuovo Torneo** → "Torneo Test 2025"
3. **Nuova Prova** → Configura tutti i parametri
4. **Apri Iscrizioni** → Imposta date di inizio/fine

### **3. Test Giocatore:**
1. **Login** → `mario/mario123`
2. **Dashboard** → Vedi prove disponibili con scadenze
3. **Iscriviti** → Conferma iscrizione
4. **Admin** → Avvia primo turno → **Player** → Inserisci risultati

## 🎮 Modalità di Gioco

### **"Al Meglio Di" (Consigliato)**
- Esempio: "Al meglio di 7" → Vince chi arriva a **4 rack**
- La partita finisce appena qualcuno raggiunge la soglia
- ⚡ Partite più dinamiche e veloci

### **"Esatto Numero"** 
- Esempio: "5 rack esatti" → Si giocano esattamente **5 rack**
- Vince chi ne ha vinti di più alla fine
- 📊 Migliori statistiche, partite più lunghe
- 🔢 **Disponibile solo per numeri dispari > 1**

## 🐛 Debug Mode

**Attivazione:** `DEBUG_MODE = True` in `config.py`

**Funzionalità:**
- 🟡 Badge "DEBUG" nella navbar
- 📊 Footer con statistiche real-time
- 🔗 Quick actions per reset e navigazione
- 🕒 Info timezone e conversioni automatiche
- 🔍 Dettagli tecnici su utenti e database

## 📋 Utenti di Test

| Username | Password | Ruolo | Descrizione |
|----------|----------|--------|-------------|
| `admin` | `admin123` | 👨‍💼 Admin | Gestione completa tornei |
| `mario` | `mario123` | 🎮 Player | Giocatore test 1 |
| `pino` | `pino123` | 🎮 Player | Giocatore test 2 |

## 🔄 Prossimi Sviluppi

### **STEP 2 - Sistema Utenti Avanzato** 🚧
- [ ] 👥 Sezione admin per gestione utenti
- [ ] 📊 Schede dettagliate con statistiche
- [ ] 🗑️ Auto-cancellazione account giocatori

### **STEP 3 - Partite Avanzate** 🎯
- [ ] ✅ Sistema conferma/rimozione punti
- [ ] 🔄 Possibilità disiscrizione tornei
- [ ] 📈 Dashboard con ultime partite giocate

### **STEP 4 - Debug Potenziato** 🛠️
- [ ] 🔐 Quick login automatico per test
- [ ] 🎮 Switch rapido tra utenti
- [ ] 📊 Statistiche sviluppo avanzate

### **STEP 5 - Abbinamenti Intelligenti** 🧠
- [ ] 🔄 Turno 2: Skip logic (1°-3°, 2°-4°)
- [ ] 🎯 Turno 3: Direct logic (1°-2°, 3°-4°)
- [ ] 🚫 Controllo duplicati (evita reincontri)
- [ ] ❌ Gestione "senza X" avanzata

### **STEP 6 - Playoff e Classifiche** 🏆
- [ ] 🥇 Sistema playoff Elite/Academy
- [ ] 📊 Classifiche generali e per prova
- [ ] 🎖️ Statistiche giocatori avanzate

## 🤝 Workflow Git

```bash
# Sviluppo locale
git checkout -b feature/nuova-funzionalita
# ... modifiche ...
git add .
git commit -m "🚀 Aggiunge nuova funzionalità"
git push origin feature/nuova-funzionalita

# Merge su main
git checkout main
git merge feature/nuova-funzionalita
git push origin main

# Deploy PythonAnywhere
cd mysite && git pull origin main
```

## 📞 Supporto e Contributi

- 🐛 **Issues:** [GitHub Issues](https://github.com/coppolapaolo/tornei-biliardo/issues)
- 📧 **Email:** paolo.coppola@gmail.com
- 🔄 **Pull Requests:** Benvenute!

## 📊 Statistiche Progetto

- 🏗️ **Architettura:** Modulare con Blueprint
- 📱 **Responsive:** Bootstrap 5
- 🗄️ **Database:** SQLAlchemy + SQLite
- 🔐 **Auth:** Flask-Login
- ⏰ **Timezone:** JavaScript automatico
- 🎨 **UI/UX:** FontAwesome + Custom CSS

---

## 🏆 Status Attuale: **STEP 1 COMPLETATO** ✅

**Sistema base completo e funzionante con:**
- ✅ Gestione tornei e prove avanzata
- ✅ Sistema iscrizioni intelligente  
- ✅ Modalità di gioco multiple
- ✅ Architettura modulare scalabile
- ✅ Debug system completo

**Pronto per STEP 2: Gestione Utenti Avanzata** 🚀

---

*Webapp professionale per tornei di biliardo - Sviluppata con ❤️ e Python* 🎱