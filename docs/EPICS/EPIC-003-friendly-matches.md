# EPIC-003: Friendly Matches (Match Amichevoli)

## 📋 Epic Overview

| Campo | Valore |
|-------|--------|
| **Epic ID** | EPIC-003 |
| **Epic Owner** | Player Community Manager |
| **Created** | 2025-08-01 |
| **Last Updated** | 2025-08-08 |
| **Status** | 🚀 IN PROGRESS (Sprint 3) |
| **Priority** | MEDIUM |
| **Business Value** | MEDIUM |
| **Effort Estimate** | 8 Story Points (1 Sprint) |

## 🎯 Business Value Statement

**Per** i Giocatori   
**Che** vogliono giocare partite informali per pratica o divertimento  
**Il** sistema Friendly Matches  
**È una** funzionalità social di match-making  
**Che** permette di organizzare e tracciare partite amichevoli tra giocatori  
**A differenza di** organizzare informalmente via WhatsApp/telefono  
**Il nostro prodotto** fornisce scheduling, tracking risultati e statistiche dedicate  

## 📊 Success Metrics

- **Adoption Rate**: >60% giocatori attivi usano friendly matches entro 3 mesi
- **Match Frequency**: Almeno 20 friendly matches/settimana
- **User Satisfaction**: NPS >40 per la feature
- **Engagement**: Aumento 30% login giornalieri

## 👥 User Stories

### US-003.1: Creazione Match Amichevole 📋 TO DO
**Priority**: MUST HAVE  
**Points**: 3  
**Sprint**: 3  
**Status**: 📋 TO DO

**Come** Giocatore  
**Voglio** proporre un match amichevole a un altro giocatore  
**Così che** possiamo organizzare una partita informale

**Acceptance Criteria:**
- [ ] Lista giocatori disponibili per sfida
- [ ] Form proposta con data/ora/location
- [ ] Selezione formato partita (disciplina, distanza)
- [ ] Note opzionali per messaggio personale
- [ ] Invio notifica all'avversario
- [ ] Stato "pending" per match proposto

**Variante 1**
Il giocatore si rende disponibile. Definisce una o piu' sale biliardo e una data/ora inizio e data/ora fine. 
I suoi amici o tutti, a seconda della privacy impostata, vedono la sua disponibilità ed eventualmente rispondono

**Variante 2**
La giocatore inserisce disponibilità ricorrenti (es: ogni venerdì dalle 20 alle 23 alla sala biliardi Mario)

---

### US-003.2: Accettazione/Rifiuto Sfida 🚧 IN PROGRESS
**Priority**: MUST HAVE  
**Points**: 3  
**Sprint**: 3  
**Status**: 📋 TO DO

**Come** Giocatore sfidato  
**Voglio** rispondere a una proposta di match  
**Così che** posso confermare o proporre alternative

**Acceptance Criteria:**
- [ ] Notifica con badge su menù profilo con dettagli sfida
- [ ] Dashboard con sfide pendenti
- [ ] Pulsanti Accetta/Rifiuta
- [ ] Notifica al proponente della risposta
- [ ] Limite temporale risposta (6h default)
- [ ] Auto-decline dopo timeout

**Current Progress:**
- In app notification: 📋 To do
- Dashboard view: 📋 To do  
- Accept/Reject buttons: 📋 To do
- Counter-proposal: 📋 To do

---

### US-003.3: Inserimento Risultati Amichevoli 📋 TO DO
**Priority**: MUST HAVE  
**Points**: 2  
**Sprint**: 3  
**Status**: 📋 TO DO

**Come** Giocatore partecipante  
**Voglio** inserire il risultato del match amichevole  
**Così che** viene tracciato nelle statistiche

**Acceptance Criteria:**
- [ ] Form inserimento risultato post-match
- [ ] Conferma reciproca del risultato
- [ ] Aggiornamento statistiche "amichevoli"
- [ ] Badge/achievements per milestone amichevoli

---

### US-003.4: Statistiche Dedicate Amichevoli 📋 BACKLOG
**Priority**: SHOULD HAVE  
**Points**: 2  
**Sprint**: 4 (planned)  
**Status**: 📋 BACKLOG

**Come** Giocatore  
**Voglio** vedere le mie statistiche dei match amichevoli  
**Così che** posso tracciare i progressi informali

**Acceptance Criteria:**
- [ ] Sezione "Amichevoli" nel profilo
- [ ] Win rate amichevoli separato
- [ ] Head-to-head record con ogni avversario
- [ ] Trend performance nel tempo
- [ ] Confronto stats ufficiali vs amichevoli
- [ ] Export statistiche

## 🔄 Dependencies

- **Depends On**:
  - User authentication system ✅
  - Notification system (in app) 📋 TO DO
  - Basic match tracking ✅
  
- **Blocks**:
  - Social features (friends, following) 📋 TO DO
  - Tournament seeding based on friendly results
  - Ladder/ranking system

## ⚠️ Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Low adoption | Medium | High | Gamification, badges, incentives |
| Result disputes | High | Low | Require double confirmation |
| Scheduling conflicts | Medium | Low | Calendar integration |
| Spam challenges | Low | Medium | Rate limiting, block list |

## 📝 Additional Notes

### Design Decisions
1. **No referee/admin validation** - Trust system with double confirmation. admin/director può sempre intervenire
2. **Separate from official stats** - Friendly stats don't affect rankings
3. **No entry fees** - Purely recreational
4. **Time limits** - 6h to respond, auto-decline after

### Future Enhancements (Post-MVP)
- Recurring challenges (weekly games)
- Group challenges (mini-tournaments)
- Spectator mode
- Live scoring

## 📅 Sprint Progress

### Sprint 3 (Current)
- [ ] Database setup (Day 1)
- [ ] Models creation (Day 1)
- [ ] Challenge creation (Day 2)
- [ ] notifications (Day 3)
- [ ] Accept/Reject (Day 4) - IN PROGRESS
- [ ] Result submission (Day 5)
- [ ] Testing & fixes (Day 6)

### Sprint 4 (Planned)
- [ ] Statistics implementation
- [ ] UI polish
- [ ] Performance optimization
- [ ] Documentation

## ✅ Definition of Done

- [ ] Database schema implemented
- [ ] Models with relationships
- [ ] Service layer complete
- [ ] API endpoints tested
- [ ] UI responsive on mobile
- [ ] notifications working
- [ ] Unit tests >90% coverage
- [ ] Integration tests passing
- [ ] Documentation updated
- [ ] Code review completed
- [ ] Deployed to staging
- [ ] UAT with 5+ players
- [ ] Performance <1s response time