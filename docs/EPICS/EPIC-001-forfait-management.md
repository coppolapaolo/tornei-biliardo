# EPIC-001: Gestione Forfait nei Tornei

## 📋 Epic Overview

| Campo | Valore |
|-------|--------|
| **Epic ID** | EPIC-001 |
| **Epic Owner** | Tournament Director / Competition Manager |
| **Created** | 2025-08-08 |
| **Last Updated** | 2025-08-08 |
| **Status** | 📋 BACKLOG |
| **Priority** | HIGH |
| **Business Value** | HIGH |
| **Effort Estimate** | 13 Story Points (2 Sprint) |

## 🎯 Business Value Statement

**Per** i Tournament Directors e i Giocatori  
**Che** necessitano di gestire abbandoni durante tornei multi-turno  
**Il** sistema di gestione forfait  
**È una** funzionalità di gestione competizioni  
**Che** permette di mantenere l'equità competitiva quando un giocatore abbandona  
**A differenza di** cancellare manualmente i match o gestire caso per caso  
**Il nostro prodotto** automatizza la gestione secondo strategie configurabili  

## 📊 Success Metrics

- **Riduzione tempo gestione**: -80% tempo Director per gestire forfait
- **Equità percepita**: >90% giocatori ritengono giusta la gestione
- **Completamento tornei**: <5% tornei interrotti per forfait
- **Automation rate**: 95% forfait gestiti senza intervento manuale

## 👥 User Stories

### US-001.1: Dichiarazione Forfait Giocatore
**Priority**: MUST HAVE  
**Points**: 3

**Come** Giocatore  
**Voglio** dichiarare forfait da un match/torneo  
**Così che** non devo presentarmi fisicamente e libero il posto

**Acceptance Criteria:**
- [ ] Pulsante "Dichiara Forfait" visibile fino a X minuti prima del match
- [ ] Form con motivazione obbligatoria (menu + testo libero)
- [ ] Conferma con doppio check ("Sei sicuro?")
- [ ] Notifica immediata a Director e avversario
- [ ] Blocco modifiche dopo dichiarazione
- [ ] Storico forfait nel profilo giocatore

**Technical Notes:**
- Aggiungere `forfait_reason` enum: ['injury', 'personal', 'work', 'other']
- Timestamp `forfait_declared_at` per tracking
- Trigger notifiche via WebSocket per real-time update

---

### US-001.2: Configurazione Strategia Forfait per Torneo
**Priority**: MUST HAVE  
**Points**: 5

**Come** Director  
**Voglio** configurare come il sistema gestisce i forfait  
**Così che** posso adattare alle regole specifiche del torneo

**Acceptance Criteria:**
- [ ] Selezione strategia: "Ghost Player" vs "Dynamic BYE"
- [ ] Configurazione punti assegnati (0-0, N-0, custom)
- [ ] Penalità in classifica generale (punti sottratti)
- [ ] Blocco forfait dopo N turni
- [ ] Gestione differenziata per fase (gironi vs eliminazione)
- [ ] Template salvabili per riuso
- [ ] Preview impatto su classifiche

**Technical Notes:**
```python
class ForfaitStrategy(Enum):
    GHOST_PLAYER = "ghost"  # Rimane negli abbinamenti
    DYNAMIC_BYE = "bye"     # Sostituito con BYE
    ELIMINATION = "elim"    # Eliminato dal torneo

forfait_config = {
    "strategy": "ghost",
    "winner_points": 5,
    "loser_points": 0,
    "penalty_points": -10,
    "max_forfeits": 2,
    "block_after_round": 3
}
```

---

### US-001.3: Gestione Automatica Turni Post-Forfait
**Priority**: MUST HAVE  
**Points**: 5

**Come** Sistema  
**Voglio** gestire automaticamente i turni successivi al forfait  
**Così che** il torneo prosegue senza interruzioni

**Acceptance Criteria:**
- [ ] Ghost Player: genera match automatici con vittoria avversario
- [ ] Dynamic BYE: ricalcola abbinamenti escludendo il giocatore
- [ ] Amalfi: aggiorna salto e anti-reincontro
- [ ] Notifica tutti i giocatori impattati
- [ ] Aggiornamento classifiche immediate
- [ ] Log dettagliato per audit

**Technical Notes:**
- Transazione atomica per consistency
- Background job per ricalcolo se >50 giocatori
- Cache invalidation per classifiche

## 🏗️ Technical Architecture

### Database Schema Changes
```sql
ALTER TABLE match ADD COLUMN forfait_type VARCHAR(20);
ALTER TABLE match ADD COLUMN forfait_player_id INTEGER REFERENCES user(id);
ALTER TABLE match ADD COLUMN forfait_declared_at TIMESTAMP;
ALTER TABLE match ADD COLUMN forfait_reason VARCHAR(200);

ALTER TABLE tournament ADD COLUMN forfait_strategy VARCHAR(20) DEFAULT 'ghost';
ALTER TABLE tournament ADD COLUMN forfait_config JSON;

CREATE TABLE forfait_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES user(id),
    tournament_id INTEGER REFERENCES tournament(id),
    match_id INTEGER REFERENCES match(id),
    reason VARCHAR(200),
    declared_at TIMESTAMP,
    impact_description TEXT
);
```

### Service Layer
```python
class ForfaitService:
    def declare_forfait(self, match_id: int, player_id: int, reason: str)
    def apply_forfait_strategy(self, match: Match, strategy: ForfaitStrategy)
    def recalculate_future_rounds(self, prova_id: int, from_round: int)
    def get_forfait_impact_preview(self, match_id: int) -> Dict
    def can_declare_forfait(self, match_id: int, player_id: int) -> bool
```

### API Endpoints
```
POST /api/match/{match_id}/forfait
GET  /api/tournament/{tournament_id}/forfait-config
PUT  /api/tournament/{tournament_id}/forfait-config
GET  /api/user/{user_id}/forfait-history
GET  /api/match/{match_id}/forfait-impact
```

## 🔄 Dependencies

- **Depends On**: 
  - Match management system
  - Notification system
  - Classification system
  
- **Blocks**:
  - Advanced tournament reporting
  - Player reliability scoring

## ⚠️ Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Cascading forfeits | Medium | High | Limit forfait per player per tournament |
| Unfair advantage | Low | High | Penalty points system |
| System abuse | Low | Medium | Cooldown period between forfeits |
| Performance impact | Medium | Low | Async processing for large tournaments |

## 📝 Additional Notes

### Open Questions
1. Should forfeit affect player's global ranking?
2. How to handle forfeit in final matches?
3. Should there be a forfeit fee/penalty?

### Future Enhancements
- ML prediction of forfeit probability
- Automatic replacement from waiting list
- Forfeit insurance for entry fees
- Reputation system based on forfeit history

### Acceptance Testing Scenarios
1. Single forfeit in round-robin
2. Multiple forfeits same round
3. Forfeit in elimination bracket
4. Forfeit after partial match completion
5. Last-minute forfeit handling

## 📅 Implementation Plan

### Sprint 1 (Points: 8)
- [ ] Database schema updates
- [ ] Basic forfeit declaration UI
- [ ] Ghost Player strategy implementation
- [ ] Notification system integration

### Sprint 2 (Points: 5)  
- [ ] Dynamic BYE strategy
- [ ] Configuration UI for Directors
- [ ] Impact preview
- [ ] Comprehensive testing

## ✅ Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests >90% coverage
- [ ] Integration tests for all strategies
- [ ] Performance tests <2s for 100 players
- [ ] Documentation updated
- [ ] UI responsive on mobile
- [ ] Accessibility WCAG 2.1 AA compliant
- [ ] Security review passed
- [ ] Deployed to staging
- [ ] UAT sign-off from 3 Directors