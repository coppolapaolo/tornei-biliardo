# 🎱 Webapp Torneo Biliardo - v2.5.0

> **Applicazione web completa** per la gestione professionale di tornei di biliardo con sistema modulare, abbinamenti automatici, classifiche e gestione match avanzata secondo il protocollo **Sistema Amalfi**.

## 🎯 Stato Attuale - v2.5.0 ✅

### ✨ **COMPLETATO - Funzionalità Principali**

- ✅ **Sistema Base Tornei** completo con configurazione avanzata
- ✅ **Multi-Tournament Support** nativo con navigazione fluida
- ✅ **Gestione Utenti Avanzata** con statistiche e profili completi
- ✅ **Admin Tools Professionali** per gestione risultati e overview
- ✅ **Sistema Conferma Punti** robusto tra giocatori
- ✅ **Mobile Responsive** con Bootstrap 5

### 🚀 **IN SVILUPPO - Prossimo Obiettivo**

- 🔄 **STEP 3: Sistema Abbinamenti Amalfi** (abbinamenti automatici professionali)

---

## 📚 Documentazione Completa

> **📖 Leggi la documentazione dettagliata** per comprendere completamente il sistema prima di continuare lo sviluppo.

### 📋 **File Documentazione** *(nel repository)*

| File | Descrizione | Quando Usarlo |
|------|-------------|---------------|
| **[SISTEMA_AMALFI.md](docs/SISTEMA_AMALFI.md)** | 🎯 Logica completa abbinamenti automatici | Prima di implementare STEP 3 |
| **[PIANO_SVILUPPO.md](docs/PIANO_SVILUPPO.md)** | 🗺️ Roadmap e stato implementazione | Per pianificare sviluppi futuri |
| **[ARCHITETTURA.md](docs/ARCHITETTURA.md)** | 🏗️ Architettura tecnica e database | Per comprendere il codice esistente |
| **[TESTING_GUIDE.md](docs/TESTING_GUIDE.md)** | 🧪 Guida testing completa | Prima di ogni sviluppo/deploy |

### 🎯 **Quick Links**
- **Sistema Amalfi**: Algoritmi abbinamenti professionali → [SISTEMA_AMALFI.md](docs/SISTEMA_AMALFI.md)
- **Prossimi Steps**: Roadmap dettagliata → [PIANO_SVILUPPO.md](docs/PIANO_SVILUPPO.md)  
- **Database Schema**: Modelli e relazioni → [ARCHITETTURA.md](docs/ARCHITETTURA.md)
- **Come Testare**: Verifica funzionalità → [TESTING_GUIDE.md](docs/TESTING_GUIDE.md)

---

## 🚀 Quick Start

### 🔧 **Setup Locale**
```bash
# Clone repository
git clone https://github.com/coppolapaolo/tornei-biliardo.git
cd tornei-biliardo

# Virtual environment
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Launch application
python app.py
```

**🌐 App disponibile su**: `http://localhost:5000`

### 🎮 **Test Rapido**
```bash
1. Vai a http://localhost:5000/reset
2. Password: RESET_DB_CONFIRM  
3. Login: admin/admin123 (Admin) o mario/mario123 (Player)
4. Esplora multi-tournament dashboard!
```

### 🔧 **Deploy Produzione** *(PythonAnywhere)*
```bash
cd /home/username/mysite
git pull origin main
# Web tab → Reload webapp
```

**🌐 App produzione**: `https://username.pythonanywhere.com`

---

## ✨ Caratteristiche Principali

### 🏗️ **Architettura Modulare**
- **Blueprint Flask** per organizzazione scalabile
- **SQLAlchemy ORM** con relazioni complete
- **Responsive Design** Bootstrap 5
- **Timezone-Aware** gestione automatica

### 🎮 **Sistema Tornei Avanzato** 
- **Multi-Tournament** simultanei con navigazione fluida
- **Modalità di Gioco**: "Al meglio di" vs "Esatto numero"
- **Gestione Prove** completa (luogo, quota, min/max partecipanti)
- **Iscrizioni Intelligenti** con controllo date e limiti

### 👨‍💼 **Strumenti Admin Professionali**
- **Gestione Tornei**: Creazione, modifica, attivazione/disattivazione
- **Configurazione Prove** avanzata con auto-popolamento
- **Inserimento Risultati Diretto** con validazione automatica
- **Overview Risultati** per batch operations
- **Gestione Utenti** con statistiche dettagliate

### 🎯 **Dashboard Giocatori**
- **Multi-Tournament** con selezione dropdown
- **Iscrizioni/Disiscrizioni** intelligenti  
- **Profilo Personale** con statistiche complete
- **Sistema Conferma Punti** rack-by-rack
- **Ultime Partite** e storico completo

### 🔧 **Sistema Debug Avanzato**
- **Debug Mode** con statistiche real-time
- **Quick Login** per test rapidi
- **Reset Database** con dati di esempio
- **Error Handling** robusto

---

## 🎯 Funzionalità Dettagliate

### 📋 **Per Amministratori**
```
✅ Dashboard tornei con overview completo
✅ Creazione/modifica tornei multi-configurazione  
✅ Gestione prove con settings avanzati
✅ Apertura/chiusura iscrizioni timezone-aware
✅ Sorteggi automatici primo turno
✅ Inserimento risultati diretto con validazione
✅ Overview risultati per gestione batch
✅ Reset partite e correzione errori
✅ Gestione utenti con schede dettagliate
✅ Statistiche complete e tracking
```

### 🎮 **Per Giocatori**  
```
✅ Dashboard multi-torneo con selezione
✅ Iscrizioni intelligenti con deadline visibili
✅ Disiscrizione prove (se permesso)
✅ Inserimento risultati rack-by-rack
✅ Sistema conferma/rimozione punti
✅ Profilo personale con statistiche
✅ Storico partite e classifiche
✅ Visualizzazione ultime partite giocate
✅ Cancellazione account sicura
```

### 🔧 **Sistema e Debug**
```
✅ Multi-tournament support nativo
✅ Timezone handling automatico
✅ Modalità debug con quick login
✅ Reset database con dati esempio
✅ Validazione dati robusta
✅ Error handling completo
✅ Mobile responsive design
✅ Performance ottimizzate
```

---

## 🗄️ Database Models

### **Core Models**
- **Tournament**: Configurazione tornei multi-tipo
- **Prova**: Gestione prove con settings avanzati  
- **User**: Utenti con ruoli e statistiche
- **Inscription**: Iscrizioni con tracking temporale
- **Match**: Partite con stati avanzati
- **Rack**: Risultati rack-by-rack con conferme

### **Advanced Models** 
- **Classification**: Classifiche per torneo
- **MatchResult**: Tracking risultati inviati
- **Playoff**: Sistema playoff futuro

**📖 Schema Completo**: [ARCHITETTURA.md - Database Schema](docs/ARCHITETTURA.md#-database-schema)

---

## 🎯 Prossimi Sviluppi

### 🚀 **STEP 3: Sistema Abbinamenti Amalfi** *(In Corso)*
**Implementazione abbinamenti automatici professionali**
- Algoritmo salto dinamico per turni successivi
- Anti-reincontro intelligente
- Gestione X vs Trii automatica
- Classifiche tra turni
- Logica sostituzione complessa

**📖 Dettagli Completi**: [SISTEMA_AMALFI.md](docs/SISTEMA_AMALFI.md)

### 📊 **STEP 4: Classifiche Avanzate** *(Pianificato)*
- Classifiche real-time sempre aggiornate
- Statistiche giocatori avanzate
- Head-to-head tra giocatori
- Grafici performance e export dati

### 🏆 **STEP 5: Sistema Playoff** *(Pianificato)*
- Elite playoff (primi 6) e Academy playoff (secondi 6)
- Qualificazione automatica con conferma
- Tabelloni eliminatori completi

**📖 Roadmap Completa**: [PIANO_SVILUPPO.md - Roadmap Futura](docs/PIANO_SVILUPPO.md#-roadmap-futura)

---

## 🧪 Testing

### 🎯 **Come Testare**
La webapp include una guida testing completa per verificare tutte le funzionalità:

**📖 Guida Completa**: [TESTING_GUIDE.md](docs/TESTING_GUIDE.md)

### ⚡ **Quick Test**
```bash
1. Reset DB: /reset → RESET_DB_CONFIRM
2. Homepage: Verifica 2 tornei visibili
3. Admin: Login admin/admin123 → Dashboard tornei
4. Player: Login mario/mario123 → Dashboard multi-torneo  
5. Quick Login: Footer debug → Switch rapido utenti
```

### 📊 **Metriche Qualità**
- ✅ **Performance**: < 2 secondi tutte le pagine
- ✅ **Responsive**: Mobile + Desktop ottimizzato
- ✅ **Error Handling**: Robusto per tutti i casi
- ✅ **Security**: Autorizzazioni e validazioni complete

---

## 📞 Supporto e Contributi

### 🐛 **Issues e Bug Reports**
- **GitHub Issues**: [Crea Issue](https://github.com/coppolapaolo/tornei-biliardo/issues)
- **Email Support**: paolo.coppola@gmail.com

### 🤝 **Contributi**
- **Pull Requests**: Benvenute! Segui il workflow Git
- **Feature Requests**: Apri issue con label "enhancement"
- **Documentation**: Migliora docs esistente

### 🔄 **Workflow Git**
```bash
# Feature development
git checkout -b feature/nome-funzionalita
git commit -m "✨ feat: descrizione funzionalità"
git push origin feature/nome-funzionalita

# Release
git checkout main  
git merge feature/nome-funzionalita
git tag vX.Y.Z
git push origin main --tags
```

---

## 🛠️ Stack Tecnologico

### **Backend**
- **Python 3.8+** con Flask framework
- **SQLAlchemy ORM** per database management  
- **Flask-Login** per autenticazione
- **SQLite** (dev) / **PostgreSQL** (prod)

### **Frontend**
- **HTML5 + CSS3** responsive design
- **Bootstrap 5** per UI components
- **JavaScript vanilla** per interattività
- **FontAwesome** per iconografia

### **Infrastructure**
- **Git** version control con GitHub
- **PythonAnywhere** hosting produzione
- **Local development** environment

**📖 Dettagli Tecnici**: [ARCHITETTURA.md - Stack Tecnologico](docs/ARCHITETTURA.md#-tools--development)

---

## 📊 Statistiche Progetto

### 📈 **Metrics v2.5.0**
- **📝 Linee Codice**: 3000+ Python/HTML/CSS
- **🎯 Features**: 25+ funzionalità principali implementate
- **📱 Templates**: 15+ pagine responsive complete  
- **🗄️ Database**: 8+ tabelle con relazioni complete
- **🔗 Routes**: 30+ endpoint REST funzionanti
- **🧪 Test Coverage**: Manuale completo, automatico in sviluppo

### 🏆 **Milestone Raggiunti**
- ✅ **v1.0.0**: Sistema base tornei (STEP 1)
- ✅ **v2.0.0**: Gestione utenti avanzata (STEP 2)  
- ✅ **v2.5.0**: Multi-tournament + Admin tools (STEP 2.5)
- 🔄 **v3.0.0**: Sistema Amalfi (STEP 3) - *In corso*

---

## 🎯 Status Attuale

### ✅ **PRONTO PER PRODUZIONE**
- Sistema base completo e testato
- Multi-tournament support funzionante
- Admin tools professionali
- Mobile responsive design

### 🔄 **IN SVILUPPO ATTIVO**
- Sistema abbinamenti Amalfi
- Algoritmi classifiche avanzate
- Performance optimizations

### 📈 **ROADMAP FUTURA**
- Sistema playoff completo
- Notifiche real-time
- PWA mobile app
- Analytics avanzati

---

## 🏷️ Versioni

### **v2.5.0** *(Current - Luglio 2025)*
- ✨ Multi-tournament homepage e dashboard
- ✨ Admin direct result input con validazione
- ✨ Results overview per batch operations  
- ✨ Enhanced match detail con admin controls
- 🔧 Improved user management e statistics
- 📱 Mobile UX optimizations

### **v2.0.0** *(Luglio 2025)*
- ✨ Advanced user management system
- ✨ Player profiles e personal statistics
- ✨ Account deletion con data cleanup
- ✨ Tournament unsubscription system
- ✨ Rack confirmation/removal system
- ✨ Debug quick login tools

### **v1.0.0** *(Luglio 2025)*
- ✨ Core tournament management system
- ✨ Advanced prova configuration
- ✨ Timezone-aware inscriptions
- ✨ Multi-game modes support
- ✨ First round automatic matching
- ✨ Rack-by-rack result input

**📖 Changelog Completo**: [GitHub Releases](https://github.com/coppolapaolo/tornei-biliardo/releases)

---

## 🎱 **Ready for Professional Tournaments!**

La webapp è **production-ready** per gestire tornei reali di biliardo con:
- 🎯 **Gestione Multi-Torneo** simultanea
- 👨‍💼 **Admin Tools** professionali per organizzatori  
- 🎮 **Player Experience** ottimizzata e intuitiva
- 📱 **Mobile Support** completo
- 🔒 **Security & Data Protection** robusti

### 🚀 **Prossimo Traguardo: Sistema Amalfi**
L'implementazione del **Sistema Amalfi** renderà gli abbinamenti completamente automatici e professionali secondo gli standard dei circoli italiani.

---

*🎱 Webapp professionale per tornei di biliardo - Sviluppata con ❤️ e Python*

**📧 Contatti**: paolo.coppola@gmail.com  
**🌐 Repository**: https://github.com/coppolapaolo/tornei-biliardo  
**📅 Ultimo aggiornamento**: 27 luglio 2025