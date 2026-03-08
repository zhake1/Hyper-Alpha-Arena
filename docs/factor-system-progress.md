# Factor System - Development Progress

> Track file for factor system development.
> Read `docs/factor-system-spec.md` for full design specification.

## Current Phase: Phase 1 — Factor Computation Engine + Effectiveness Dashboard

## Development Rules

- Factor system is an independent module — do NOT modify existing signal
  detection, attribution analysis, or any core trading logic (Phase 1-2)
- Each Phase must be confirmed with user before moving to next Phase
- New background services must have an on/off switch via env variable
  (`FACTOR_ENGINE_ENABLED=true/false`)
- Database changes follow existing ORM + migration conventions
  (models.py first, migration script if needed, register in migration_manager)
- All code and comments in English, UI text uses i18n (en.json + zh.json)
- No temporary test scripts committed to git

## Completed

(none yet)

## In Progress

(not started)

## Pending

### Phase 1
- [ ] Database models: `FactorValue`, `FactorEffectiveness` in models.py
- [ ] factor_computation_service.py (pandas-ta, K-line period update cycle)
- [ ] factor_effectiveness_service.py (daily batch: IC, win rate, decay)
- [ ] factor_routes.py (API endpoints)
- [ ] Frontend: Factor Library page/tab
- [ ] Env switch: FACTOR_ENGINE_ENABLED

### Phase 2
- [ ] Hyper AI tools: evaluate_factor, recommend_factors, web_search
- [ ] Tavily integration (user-provided API key)
- [ ] Hyper AI sidebar: Tools config panel
- [ ] Factor mining memory per conversation

### Phase 3
- [ ] Signal Pool: `factor` metric type in signal_detection_service.py
- [ ] Signal creation UI: factor selection from library
- [ ] Threshold suggestion based on factor distribution

### Phase 4
- [ ] AI Trader: factor context injection into prompts
- [ ] Program Trader: data_provider factor API
- [ ] Theory vs Reality dashboard (factor IC vs actual signal win rate)

## Decisions Log

- 2026-03-07: Factor values update follows K-line period, not fixed interval
- 2026-03-07: Factor effectiveness computed once per day (batch)
- 2026-03-07: Hyper AI on-demand validation is separate from scheduled tasks
- 2026-03-07: Web search uses Tavily, user-provided key, config in AI panel
- 2026-03-07: Factor effectiveness and signal threshold are decoupled concepts
