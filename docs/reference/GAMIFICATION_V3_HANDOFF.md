# Gamification V3 — Handoff per l'implementazione

**Data**: 2026-06-05 · **Branch**: `claude/gamification-system-review-beIB0`
**Stato**: design **completo**, codice **non ancora toccato**.

## Cos'è questo
Punto di ingresso per la fase di **implementazione** della revisione gamification.
Il design è interamente deciso e documentato — leggere come fonte di verità:
- **`docs/reference/GAMIFICATION_V3.md`** (design completo; §13 rollout a fasi, §14 tarature)
- **`docs/adr/ADR-031-gamification-gating-model.md`** (decisione + dettagli risolti)

## Decisioni chiave (riassunto, dettaglio nei doc)
- 3 layer di gating ortogonali; **un solo motore ABAC** (via legacy `LEVEL_UNLOCKS`).
- Livelli = **feedback**, non barriera. Loop base aperto dal day-1.
- **Onboarding** brevissimo/obbligatorio + backfill esistenti al primo login (`User.onboarding_completed`).
- Drill: creazione a **slot di engagement** (cap = 3 + drill ingaggiati).
- **Modello geografico per prossimità** (coordinate + raggio), GeoNames `cities500` offline, identico per utenti e sale → merita **ADR dedicato** prima di implementare.
- **Segnale-domanda → director** (richieste geolocalizzate, soglia ≥6 nel raggio).
- **Leaderboard** riformulato locale/contributo; loop quotidiano auto-referenziale.
- **Quest**: status calcolato dalle date + seed minimo, dietro maturity-gate.
- **Achievement**: agganciare `seed_achievements` in prod; nascondere i non-ottenibili.
- **Badge navbar** vivo (anello progresso + scala di intensità toast-vs-badge).

## Prossimo passo: Fase 1 — pulizia a basso rischio (non visibile agli utenti)
Da pianificare nel dettaglio (file, ordine, verifica):
1. Agganciare `seed_achievements` a migrazione/startup; nascondere stub
   `win_streak`/`category_reached` + progress-based non cablati.
2. Quest: status **lazy** (derivato da `start_date`/`end_date`) — rimuove la
   dipendenza dal cron; seed minimo quest personali.
3. Dedup proposte match: ritirare `routes/player/proposals.py` (vecchia),
   redirigere ai link, allineare il service `models/individual_match/`.
4. Fix micro-bug `STREAK_LONGEST` senza `calculated_at` (leaderboard).
5. Cablare `ConfigService.get_xp_rate()` nell'editor tassi XP **oppure** rimuovere
   l'editor `/admin/config/xp` (oggi no-op, usa `XP_RATES` hardcoded).
6. Rimuovere legacy `LEVEL_UNLOCKS` + consolidare console unlock su `/admin/features`.

Tutto resta **director-only** (maturity-gate ADR-028) finché non validato.

## Convenzioni
Vedi `CLAUDE.md` (transactional, utc_now, Distance VO/ADR-027, ADR-028 endpoint
allowlist, naming italiano, EventBus isolation nei test). Verifica con `pyright`
+ `pytest tests/new/`.

## Tarature (NON bloccanti — affinare sui dati reali)
Soglie progressione/drill, raggio default (~30 km), finestre scadenza (~60 gg),
set quest seed, grafica onboarding, classifiche locali (leghe vs raggio).
