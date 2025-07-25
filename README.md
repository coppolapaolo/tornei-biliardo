# README.md

# 🎱 Webapp Torneo Biliardo

Applicazione web completa per la gestione di tornei di biliardo con sistema di abbinamenti automatici, classifiche e gestione match in tempo reale.

## 🚀 Funzionalità

### 👨‍💼 Per gli Amministratori:
- ✅ Creazione e gestione tornei
- ✅ Configurazione prove (data, disciplina, distanza)
- ✅ Apertura/chiusura iscrizioni
- ✅ Generazione sorteggi automatici
- ✅ Validazione risultati partite
- 🔄 Gestione playoff (Elite/Academy) - *in sviluppo*

### 🎮 Per i Giocatori:
- ✅ Registrazione e iscrizione alle prove
- ✅ Visualizzazione abbinamenti in tempo reale
- ✅ Inserimento risultati rack per rack
- 🔄 Consultazione classifiche - *in sviluppo*
- ✅ Dashboard personalizzata

### 🛠️ Funzionalità di Sviluppo:
- ✅ **Debug Mode**: Informazioni dettagliate nel footer
- ✅ **Reset Database**: Pagina per resettare tutto ai dati di test
- ✅ **Git Integration**: Workflow completo con GitHub

## 🔧 Setup Locale (Mac/Windows)

### Requisiti:
- Python 3.8+
- Git
- Account GitHub

### Installazione:
```bash
# Clona il repository
git clone https://github.com/TUO_USERNAME/tornei-biliardo.git
cd tornei-biliardo

# Crea virtual environment
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
# oppure
venv\Scripts\activate  # Windows

# Installa dipendenze
pip install -r requirements.txt

# Avvia l'app
python app.py
```

L'app sarà disponibile su `http://localhost:5000`

## ☁️ Deploy su PythonAnywhere

### Setup iniziale:
```bash
# Console PythonAnywhere
cd ~
git clone https://github.com/TUO_USERNAME/tornei-biliardo.git mysite
cd mysite
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Workflow di sviluppo:
1. **Sul Mac**: Modifica codice con VSCode
2. **Commit e push**:
   ```bash
   git add .
   git commit -m "Descrizione modifiche"
   git push origin main
   ```
3. **Su PythonAnywhere**:
   ```bash
   cd mysite
   git pull origin main
   # Se hai modificato Python files:
   # Vai su Web → Reload
   ```

## 🎯 Quick Start

### Primo utilizzo:
1. **Vai su `/reset`** (solo in debug mode)
2. **Reset database** con password `RESET_DB_CONFIRM`
3. **Login**: `admin` / `admin123` (amministratore) o `mario` / `mario123` (giocatore)

### Creazione primo torneo:
1. **Admin** → Nuovo Torneo → `Torneo Test 2025`
2. **Nuova Prova** → Prova 1, disciplina, data, distanza
3. **Dettaglio Prova** → Apri Iscrizioni (imposta date)
4. **Testa come giocatore** → Iscriviti alla prova

## 🐛 Debug Mode

Imposta `DEBUG_MODE = True` in `app.py` per attivare:
- 🟡 Badge "DEBUG" nella navbar
- 📊 Footer con statistiche sistema
- 🔗 Link rapidi per reset e admin
- 🔍 Informazioni dettagliate utente/database

## 📁 Struttura Progetto

```
tornei-biliardo/
├── app.py                 # App principale Flask
├── requirements.txt       # Dipendenze Python
├── README.md             # Documentazione
├── .gitignore           # File da ignorare in Git
└── templates/           # Template HTML
    ├── base.html        # Template base con debug
    ├── index.html       # Homepage
    ├── login.html       # Login
    ├── register.html    # Registrazione
    ├── reset.html       # Reset database
    ├── admin/          # Template amministratore
    │   ├── dashboard.html
    │   └── prova_detail.html
    └── player/         # Template giocatore
        └── dashboard.html
```

## 🔄 Prossimi Sviluppi

- [ ] **Abbinamenti turno 2 e 3** con logica skip
- [ ] **Sistema playoff** Elite/Academy completo
- [ ] **Classifiche** generali e per prova
- [ ] **Aggiornamenti real-time** con WebSocket
- [ ] **API REST** per app mobile
- [ ] **Notifiche** email/SMS

## 🤝 Contribuire

1. Fork del repository
2. Crea branch feature: `git checkout -b feature/nuova-funzionalita`
3. Commit: `git commit -m 'Aggiunge nuova funzionalità'`
4. Push: `git push origin feature/nuova-funzionalita`
5. Crea Pull Request

## 📞 Supporto

Per problemi o domande:
- 📧 Email: paolo.coppola@gmail.com
- 🐛 Issues: [GitHub Issues](https://github.com/TUO_USERNAME/tornei-biliardo/issues)

---

*Webapp sviluppata per la gestione professionale di tornei di biliardo* 🎱

---

# requirements.txt - AGGIORNATO
Flask==2.3.3
Flask-SQLAlchemy==3.0.5
Flask-Login==0.6.3
Werkzeug==2.3.7

---

# deploy.sh - Script per deploy rapido
#!/bin/bash

echo "🚀 Deploy Tornei Biliardo"
echo "========================"

# Controlla se siamo in un repo git
if [ ! -d ".git" ]; then
    echo "❌ Non sei in un repository Git!"
    exit 1
fi

# Status git
echo "📊 Status Git:"
git status --short

# Chiede conferma
read -p "🤔 Vuoi fare commit e push? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    # Chiede messaggio commit
    read -p "📝 Messaggio commit: " commit_message

    # Git operations
    echo "📦 Adding files..."
    git add .

    echo "💾 Committing..."
    git commit -m "$commit_message"

    echo "🌐 Pushing to GitHub..."
    git push origin main

    echo "✅ Deploy completato!"
    echo ""
    echo "🔗 Ora vai su PythonAnywhere e fai:"
    echo "   cd mysite"
    echo "   git pull origin main"
    echo "   # Se hai modificato app.py, fai reload della webapp"

else
    echo "❌ Deploy annullato"
fi

---

# local_run.sh - Script per test locale
#!/bin/bash

echo "🎱 Avvio Webapp Torneo Biliardo"
echo "==============================="

# Controlla se virtual environment esiste
if [ ! -d "venv" ]; then
    echo "📦 Creando virtual environment..."
    python3 -m venv venv
fi

# Attiva virtual environment
echo "🔄 Attivando virtual environment..."
source venv/bin/activate

# Installa/aggiorna dipendenze
echo "📥 Installando dipendenze..."
pip install -r requirements.txt

# Avvia app
echo "🚀 Avviando applicazione..."
echo "🌐 App disponibile su: http://localhost:5000"
echo "🛑 Premi Ctrl+C per fermare"
echo ""

python app.py