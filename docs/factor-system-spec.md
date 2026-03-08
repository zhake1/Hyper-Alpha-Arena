# Factor System - Design Specification

> This document summarizes the discussion conclusions for the Factor System feature.
> It serves as the guiding reference for all subsequent development.

## 1. Goals & Positioning

### Core Problem

AI trading tools appear smart but perform unstably in live markets. When market
structure changes, models break down. Users need a "constraint layer" between AI
and execution — not replacing AI, but giving it better raw materials and guardrails.

### Product Positioning

**Make institutional-grade factor analysis accessible to ordinary users.**

- The word "Factor" MUST be visible to users — it serves as a trust anchor
  that signals professionalism, even if users don't fully understand the math.
- Behind the scenes, factors are an evolution of the existing signal system,
  not a replacement.
- AI is the bridge: users speak in natural language, AI translates to
  quantitative logic, the engine validates with math.

### Target User Experience

1. New users: see a "Factor Library" with effectiveness scores, feel professional
2. Intermediate users: chat with Hyper AI to discover and validate factor hypotheses
3. Advanced users: use validated factors in Signal Pools, AI Trader prompts,
   or Program Trader code

### Key Differentiator

No retail-facing product currently offers "AI-interactive factor mining" as a
usable feature. Academic research (Alpha-GPT, FactorMiner, LLM+MCTS) proves
the approach works, but none have been productized for ordinary users.

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│              Factor Computation Engine               │
│                                                      │
│  Data Source: CryptoKline (can backfill)              │
│  Library: pandas-ta (130+ technical indicators)       │
│  + Existing micro-structure factors (CVD, OI, etc.)  │
│                                                      │
│  Two computation cycles:                             │
│  1. Factor VALUES: follow K-line period              │
│     (4h K-line → update every 4h, cached in DB)     │
│  2. Factor EFFECTIVENESS: once per day               │
│     (IC, win rate, decay — batch job, off-peak)      │
│  3. On-demand: Hyper AI factor validation            │
│     (triggered by user chat, single computation)     │
│                                                      │
│  Output: factor_values table                         │
│          factor_effectiveness table                  │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌─────────┐  ┌───────────┐  ┌──────────┐
   │ Signal  │  │ AI Trader │  │ Program  │
   │  Pool   │  │ (Prompt)  │  │ Trader   │
   │Trigger  │  │ Context   │  │ Data API │
   └─────────┘  └───────────┘  └──────────┘
```

### Three Consumers

1. **Signal Pool**: Read latest factor value from `factor_values` table during
   15-second detection cycle. Uses generic `factor` metric type — no changes
   to existing CVD/OI/MACD logic needed.

2. **AI Trader**: Factor effectiveness data injected into prompt context.
   AI sees "BTC effective factors: OI Delta (IC=0.12, positive), RSI
   (IC=-0.08, inverse)" and incorporates into decisions.

3. **Program Trader**: Exposed via `data_provider` interface.
   `data.get_factor('rsi', '4h')` for value,
   `data.get_factor_effectiveness('rsi', '4h')` for effectiveness score.

## 3. Factor Effectiveness Evaluation

### Core Math (Industry Standard, Not Innovation)

- **IC (Information Coefficient)**: Spearman correlation between factor value
  and future N-period return. Measures predictive power.
- **Win Rate**: Percentage of times factor direction matches future price
  direction.
- **Factor Decay**: How IC changes over time — detects when a factor stops
  working.

### Key Insight: Factors Are Direction-Agnostic

A factor does NOT need to know "which direction the user wants." IC measures
correlation — positive IC means factor and price move together, negative IC
means they move inversely. Both are useful. IC near zero means the factor
has no predictive power. The system automatically determines directionality.

### Multi-Timeframe Evaluation

Different factors have different optimal prediction horizons:
- CVD 5min change → best for 1-4h prediction
- Funding rate change → best for 24-72h prediction
- RSI → best for 4-12h prediction

Each factor must be evaluated across multiple forward windows (1h, 4h, 12h,
24h) to find its "sweet spot." This information itself is valuable to users.

### Difference from Attribution Analysis

| Dimension        | Attribution Analysis    | Factor Effectiveness     |
|-----------------|------------------------|--------------------------|
| Data needed     | User's trade history   | Market data only (K-line)|
| Timing          | Post-trade (ex-post)   | Pre-trade (ex-ante)      |
| What it answers | "Did my strategy work?" | "Does this signal work?" |
| User dependency | Requires trading first | Works for new users too  |

They are complementary, not overlapping.

### Factor Effectiveness vs Signal Threshold (Critical Distinction)

These are two independent concepts solving different problems:

| Concept       | What it answers                | Update frequency     | Used by          |
|--------------|-------------------------------|---------------------|------------------|
| Effectiveness | "Is this factor predictive?"  | Once per day (batch) | Factor Library UI |
| Threshold     | "When should I trigger?"      | N/A (user-set)      | Signal Pool       |
| Factor Value  | "What's the current reading?" | Follows K-line period| Signal detection  |

**User flow**: See effectiveness dashboard → pick a factor with good IC →
configure it in Signal Pool with threshold + K-line period + operator →
signal detection reads cached factor value every 15s and compares to threshold.

Effectiveness does NOT need to be real-time. It guides factor SELECTION.
Threshold controls signal EXECUTION. They are decoupled.

### Factor-to-Strategy Decay (Industry-Known Problem)

A factor with IC=0.12 does not guarantee 12% better trading results.
Between factor predictive power and actual trading profit, every layer
introduces decay: threshold setting, entry timing, holding period,
fees, slippage, position sizing.

This is called "factor-to-strategy decay" — an acknowledged challenge
in quantitative finance with no perfect solution, but several mitigations:

**Mitigation 1: Backtest validation (already available)**
User configures factor + threshold in Signal Pool → runs backtest →
sees actual historical trigger win rate and P&L. Existing signal backtest
feature can be reused directly.

**Mitigation 2: Parameter sensitivity analysis (Phase 3+)**
Instead of testing one threshold, auto-test a range (e.g., RSI < 25/28/30/
32/35) and show which value produces the most stable results. Helps users
avoid overfitting to a single "lucky" parameter.

**Mitigation 3: Multi-factor combination (already supported)**
Signal Pool AND logic — combining 2-3 factors reduces noise significantly.
Single factor win rate 55% is normal; combined can reach 60-65%.

**Mitigation 4: Theory vs Reality dashboard (key UX feature)**
Display side by side in Factor Library:
- "Factor IC = 0.12 (theoretical predictive power)" — from factor engine
- "Your Signal Pool actual win rate = 52%" — from attribution analysis

This comparison educates users that decay is normal, and provides a
feedback loop to optimize threshold/timing. No new module needed —
attribution analysis already tracks PnL by trigger type, just reference
that data in the factor dashboard.

**Future research direction**: Factor-to-strategy decay optimization is
a valuable long-term research topic. Potential approaches include adaptive
thresholds (auto-adjust based on recent market volatility), regime-aware
parameter switching, and reinforcement learning for execution optimization.

## 4. AI's Role in the Factor System

### Three Layers of AI Involvement

**Layer 1: Factor Interpretation (Hyper AI existing capability)**
- Translate raw numbers (IC=0.12, win rate=58%) into plain language
- "BTC's OI indicator has strong predictive power this week, suitable for
  trend following, but note it fails in ranging markets"

**Layer 2: Factor Combination Recommendation**
- User says "I want to scalp BTC short-term"
- AI recommends: "Combine OI Delta + CVD + Volatility — best recent
  performance on 4h timeframe"
- Based on current effectiveness rankings from the engine

**Layer 3: Interactive Factor Mining (Core Competitive Advantage)**
- Inspired by Alpha-GPT (academic research, 2023-2025)
- Flow: User shares trading intuition → AI generates factor hypothesis
  (math expression) → Engine validates (IC, win rate) → AI interprets
  results → Suggests optimization → Loop
- Implementation: Add `evaluate_factor` tool to `hyper_ai_tools.py`
- AI has "experience memory" — remembers which factor directions have
  been explored, avoids dead ends (inspired by FactorMiner)

### AI Does NOT Compute

AI generates hypotheses and interprets results. All computation is done by
the backend factor engine. This separation is critical — LLMs cannot reliably
do statistical calculations.

## 5. Web Search Capability (AI Factor Research)

### Purpose

Hyper AI needs web access to search for latest quantitative research, new
factor ideas, and market analysis — expanding factor hypothesis sources
beyond user intuition and AI training knowledge.

### Three Sources of Factor Hypotheses

1. **User intuition**: "I think high funding rate means short opportunity"
2. **AI training knowledge**: AI proposes based on known quant research
3. **Web search (NEW)**: AI searches latest papers, community discussions,
   and market analysis for fresh factor ideas

Source 3 solves the "user has no intuition" problem — user just says
"find me new trading ideas for BTC" and AI does the research.

### Chosen Service: Tavily

- **Why Tavily**: Purpose-built for AI agents. Returns structured content
  (title + summary + extracted text + citations) in a single API call.
  No need to crawl/parse HTML ourselves. Highest adoption in AI dev
  community (LangChain, LlamaIndex official integrations).
- **Free tier**: 1,000 searches/month per API key (sufficient for
  individual users doing 1-2 searches/day)
- **Paid**: $0.008/request (negligible cost)
- **Website**: https://tavily.com

### User Configuration Flow (Important: Open Source Consideration)

Since the project is open source, we CANNOT embed a shared API key —
it would be exposed in the codebase and exhausted immediately.

**Flow**:
1. User asks Hyper AI to search for quant research
2. AI checks if user has configured a Tavily API key
3. If NO key configured → AI responds in chat:
   "I need web search access to look up latest research for you.
   Please configure your Tavily API key in the tools panel.
   Register at tavily.com — you get 1,000 free searches per month."
4. If key configured → AI performs search → extracts factor hypotheses
   → calls `evaluate_factor` to validate → presents results

### Configuration UI Location

**Place in Hyper AI's tool panel** (NOT in global Settings page).

Rationale:
- Web search is exclusively consumed by Hyper AI
- When AI prompts user to configure, user looks for the setting in the
  current interface, not in a separate Settings page
- Shorter user path: AI prompts → configure in sidebar → continue chat
- Natural mental model: "I'm giving AI a new tool"
- Extensible: future AI tools (other data source APIs) fit naturally here

### Implementation Notes

- Backend: `hyper_ai_tools.py` adds `web_search` tool
- Tool reads Tavily API key from user's configuration (stored in DB)
- Search results are processed by AI to extract factor hypotheses
- AI then calls `evaluate_factor` to validate hypotheses against
  real market data
- Frontend: Hyper AI sidebar gets a "Tools" tab with API key config

## 6. Implementation Plan

### Phase 1: Factor Computation Engine + Effectiveness Dashboard (Foundation)

**Goal**: Users see a "Factor Library" page with effectiveness scores.
No trading integration yet — pure display.

**Backend tasks**:
- New database tables: `factor_values`, `factor_effectiveness`
- Background service: `factor_computation_service.py`
  - Uses pandas-ta to compute 130+ technical factors from K-line data
  - Integrates existing micro-structure factors (CVD, OI, Funding, etc.)
  - Factor value update: follows K-line period (4h K-line → every 4h)
  - Values cached in `factor_values` table with computation timestamp
- Effectiveness calculator: `factor_effectiveness_service.py`
  - Computes IC, win rate, decay curve for each factor × symbol × timeframe
  - Multi-forward-window: 1h, 4h, 12h, 24h
  - Runs once per day (batch job, configurable schedule)
- API routes: `factor_routes.py`
  - GET /api/factors — list all factors with latest effectiveness
  - GET /api/factors/{name}/effectiveness — detailed stats for one factor

**Frontend tasks**:
- New page/tab: "Factor Library"
  - Factor list with green/yellow/red effectiveness indicator
  - Click to see: IC curve, win rate trend, best timeframe
  - Filter by category (momentum, volatility, micro-structure, etc.)

**Key decisions**:
- Factor categories: Momentum, Trend, Volatility, Volume, Micro-structure
- pandas-ta handles technical factors; existing collectors handle
  micro-structure factors
- Do NOT build alphalens dependency — implement IC/win-rate math directly
  (lightweight, ~200 lines of numpy/pandas code)

### Phase 2: Hyper AI Factor Mining Tool + Web Search

**Goal**: Users chat with AI to discover and validate factor hypotheses.
AI can also search the web for latest quant research as hypothesis source.

**Backend tasks**:
- New tool in `hyper_ai_tools.py`: `evaluate_factor`
  - Input: factor expression (e.g., "RSI(14) on 4h for BTC")
  - Output: IC, win rate, best forward window, decay info
- New tool: `recommend_factors`
  - Input: symbol, trading style (trend/mean-reversion/scalp)
  - Output: top-N effective factors for current market regime
- New tool: `web_search`
  - Uses Tavily API (key from user config)
  - Searches arxiv, quant forums, crypto research for factor ideas
  - Returns structured content for AI to extract hypotheses
  - Graceful fallback: if no key configured, prompt user to set up
- Factor mining memory: store explored hypotheses and results
  per user conversation

**AI prompt engineering**:
- System prompt addition: teach AI how to formulate factor hypotheses
- Include current market regime context
- Teach AI to interpret IC values and suggest next exploration direction
- Teach AI the web search → extract hypothesis → validate flow

**Frontend tasks**:
- Hyper AI chat can display factor evaluation results inline
- "Try this factor" button → adds to user's watchlist
- Hyper AI sidebar: "Tools" tab with Tavily API key configuration
  - Input field for API key
  - Link to tavily.com registration
  - Status indicator: configured / not configured

### Phase 3: Signal Pool Integration

**Goal**: Users can use any factor from the library as a signal trigger.

**Backend tasks**:
- Add `factor` metric type to `signal_detection_service.py`
  - Single new branch: read latest value from `factor_values` table
  - No changes to existing CVD/OI/MACD detection logic
- Signal creation UI supports selecting from factor library
- Factor effectiveness shown alongside signal configuration

**Frontend tasks**:
- Signal creation modal: "Choose from Factor Library" option
- Show factor effectiveness when user selects a factor
- Threshold suggestion based on factor distribution

**Caution**: This phase requires careful UX design — how to let users
choose from 150+ factors without overwhelming them. AI recommendation
should be the primary path, manual selection secondary.

### Phase 4: AI Trader & Program Trader Integration

**Goal**: Factors become first-class data in trading decisions.

**AI Trader**:
- Inject top effective factors into prompt context automatically
- AI can reference factor data when making trade decisions
- Factor effectiveness warnings when relied-upon factors decay

**Program Trader**:
- `data.get_factor(name, period)` → latest factor value
- `data.get_factor_effectiveness(name, period)` → effectiveness stats
- `data.list_effective_factors(symbol, min_ic=0.05)` → filtered list

## 7. Technical Dependencies

| Component          | Library/Approach              | Notes                    |
|-------------------|-------------------------------|--------------------------|
| Technical factors | pandas-ta                     | 130+ built-in indicators |
| Micro-structure   | Existing collectors           | CVD, OI, Funding, etc.  |
| IC calculation    | Custom (numpy/pandas)         | ~200 lines, no framework |
| Factor storage    | PostgreSQL (new tables)       | factor_values, factor_effectiveness |
| AI factor mining  | Hyper AI tool call            | evaluate_factor tool     |
| Signal integration| factor_values table read      | Generic metric type      |
| Web search        | Tavily API                    | User-provided key, 1000/mo free |

### What We Do NOT Use

- alphalens: designed for offline research, not online continuous computation
- qlib: too heavy, overkill for our use case
- gplearn: genetic programming, Phase 2+ consideration for auto-discovery
- FinRL: reinforcement learning, not relevant to factor system

## 8. Key Risks & Mitigations

**Risk 1: Overfitting**
Factors that look great on historical data may fail in live markets.
Mitigation: Always show "recent 7-day" vs "30-day" effectiveness comparison.
Highlight when recent performance diverges from historical average.

**Risk 2: Computation load**
150 factors × multiple symbols × multiple timeframes = heavy computation.
Mitigation: Only compute for symbols that users are actively trading.
Lazy computation — calculate on demand, cache aggressively.

**Risk 3: User overwhelm**
150 factors is too many to browse manually.
Mitigation: AI recommendation as primary path. Default view shows only
top-10 effective factors per symbol. Full library accessible but secondary.

**Risk 4: Factor decay not detected**
A factor stops working but users keep relying on it.
Mitigation: Automated decay detection — when 7-day IC drops below 50% of
30-day IC, flag as "weakening." Push notification via Hyper AI.

## 9. Academic References

- Alpha-GPT: Human-AI Interactive Alpha Mining (2023)
  https://www.researchgate.net/publication/372827826
- FactorMiner: Self-Evolving Agent for Alpha Discovery (2026)
  https://arxiv.org/html/2602.14670v1
- LLM-Powered MCTS for Formulaic Factor Mining (2025)
  https://arxiv.org/html/2505.11122v3
- LLM for Alpha Mining in Quantitative Trading (2025)
  https://arxiv.org/abs/2508.06312

## 10. Relationship to Existing Systems

### What Changes

- New: Factor computation engine (background service)
- New: Factor effectiveness calculation service
- New: Factor Library UI page
- New: Hyper AI factor mining tools
- Extended: Signal Pool supports `factor` metric type
- Extended: AI Trader prompt includes factor context
- Extended: Program Trader data_provider exposes factor API

### What Does NOT Change

- Existing signal detection logic (CVD, OI, MACD, etc.) — untouched
- Existing attribution analysis — complementary, not replaced
- Existing K-line collection — data source for factor computation
- Existing market flow collection — micro-structure factors reuse this data
- Signal Pool AND/OR logic, edge triggering — all preserved
