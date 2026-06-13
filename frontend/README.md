# Breakpoint V2 — AI-Powered Adversarial Product Testing Platform

An evolutionary simulation engine that deploys diverse AI agent populations to discover vulnerabilities in your product before real users do.

## 🏗️ Architecture

```
User → Intake (Conv/Doc/Code) → Blueprint → Agent Generation → Simulation → Report
                                     ↑                              ↓
                                  Refinement          Evolutionary Generations (1-5)
                                     ↑                              ↓
                                  Verification     Dedup → Fitness → Selection → Next Gen
```

## 📁 Project Structure

```
breakpoint/
├── src/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth/          # Registration, Login, Session
│   │   │   ├── projects/      # CRUD + settings
│   │   │   ├── intake/
│   │   │   │   ├── conversation/  # Mode 1: Multi-turn product interrogation
│   │   │   │   ├── document/      # Mode 2: PDF/DOCX/YAML upload & parse
│   │   │   │   └── codebase/      # Mode 3: GitHub repo analysis
│   │   │   ├── blueprint/     # Generation, verification, refinement, lock
│   │   │   ├── agents/        # Population generation, custom agents
│   │   │   ├── simulation/    # Configure, start, stop, stream (SSE)
│   │   │   └── report/        # Generate + 9 individual section endpoints
│   │   └── page.js
│   └── lib/
│       ├── config/
│       │   ├── constants.js    # All enums, thresholds, presets
│       │   ├── defaults.js     # Default configs for simulation, LLM, BSS
│       │   └── archetypes.js   # 12 agent archetype definitions
│       ├── db/
│       │   ├── connect.js      # MongoDB singleton connection
│       │   └── models/         # User, Project, Conversation, Blueprint,
│       │                       # Agent, Simulation, Generation, Vulnerability, Report
│       ├── llm/
│       │   ├── base.js         # Abstract LLM interface
│       │   ├── openai.js       # OpenAI adapter
│       │   ├── gemini.js       # Gemini adapter
│       │   └── factory.js      # Provider factory with caching
│       ├── middleware/
│       │   ├── auth.js         # JWT auth middleware
│       │   ├── errorHandler.js # Global error handler
│       │   └── rateLimit.js    # Rate limiting
│       ├── prompts/
│       │   ├── intake/         # Opening, decomposition, follow-up, doc extraction
│       │   ├── blueprint/      # Generation, verification, risk preview
│       │   ├── simulation/     # 5 generation-specific prompts
│       │   ├── agents/         # Persona, knowledge, product-specific generation
│       │   └── report/         # All 9 report section prompts
│       ├── services/
│       │   ├── auth.js         # User registration, login, JWT
│       │   ├── conversation.js # Multi-turn intake engine
│       │   ├── documentParser.js # Upload + text extraction + LLM parsing
│       │   ├── codebaseAnalyzer.js # GitHub + live URL analysis
│       │   ├── blueprint.js    # Blueprint CRUD + refinement loop
│       │   ├── agentGenerator.js # Population generation with LHS
│       │   ├── avatarGenerator.js # AI avatar generation
│       │   ├── lhsSampler.js   # Latin Hypercube Sampling
│       │   ├── simulationEngine.js # Main orchestrator
│       │   ├── generationRunner.js # Per-generation execution
│       │   ├── deduplication.js # Semantic dedup with embeddings
│       │   ├── fitnessScorer.js # Novelty + severity fitness scoring
│       │   ├── bssCalculator.js # BSS scoring formula
│       │   └── reportGenerator.js # 9-section report generation
│       └── validators/         # Zod schemas for all inputs
├── .env.example
├── vercel.json
└── package.json
```

## 🚀 Quick Start

### 1. Prerequisites
- Node.js 18+
- MongoDB Atlas (free tier works)
- API key for Gemini (default) or OpenAI

### 2. Install Dependencies
```bash
cd breakpoint
npm install
```

### 3. Configure Environment
```bash
cp .env.example .env.local
```

Edit `.env.local` with your credentials:
```env
# Required
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/breakpoint
JWT_SECRET=your-super-secret-key-minimum-32-chars

# LLM (at least one required)
GEMINI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key

# Optional (for document mode)
BLOB_READ_WRITE_TOKEN=your-vercel-blob-token
```

### 4. Get Your API Keys

**Gemini (Free - Recommended for testing):**
1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a new API key
3. Add to `.env.local` as `GEMINI_API_KEY`

**MongoDB Atlas (Free):**
1. Go to [MongoDB Atlas](https://cloud.mongodb.com)
2. Create a free M0 cluster
3. Create a database user and get the connection string
4. Add to `.env.local` as `MONGODB_URI`

### 5. Run Development Server
```bash
npm run dev
```

Server starts at `http://localhost:3000`

### 6. Test the API
```bash
# Health check
curl http://localhost:3000/api

# Register
curl -X POST http://localhost:3000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test123!","name":"Test User"}'
```

## 📜 API Flow

### Complete Workflow

```
1. Register/Login → Get JWT token
2. Create Project → Project ID
3. Start Intake (pick one):
   a. Conversation → Multi-turn product Q&A
   b. Document → Upload PRDs, API specs
   c. Codebase → Connect GitHub repo
4. Generate Blueprint → Structured product understanding
5. Verify Blueprint → Review for accuracy
6. Refine Blueprint → Correct any mistakes (max 3 cycles)
7. Lock Blueprint → Ready for simulation
8. Configure Simulation → Set intensity, agent composition
9. Start Simulation → Evolutionary agent testing begins
10. Stream Results → SSE live updates
11. Generate Report → 9-section vulnerability report
```

## 🤖 Agent Archetypes (12 Built-in)

| Archetype | Goal | Risk Level |
|-----------|------|------------|
| 🆓 Freeloader | Never pay, get max value for ₹0 | High |
| 🛡️ Guardian | Protect privacy, minimize data exposure | Medium |
| 💻 Hacker | Break things, find technical vulnerabilities | Critical |
| 📋 Organizer | Coordinate groups, exploit social dynamics | High |
| ⚡ Power User | Push every feature to its limit | Medium |
| 📝 Critic | Find UX failures, point out friction | Low |
| 🏢 Competitor | Extract intelligence, replicate features | High |
| 💀 Griefer | Ruin others' experience, cause chaos | High |
| 😊 Naive User | Just use it normally | Low |
| ⚖️ Regulator | Find compliance issues, flag legal risks | Medium |
| 💰 Scalper | Exploit for profit, monetize the platform | Critical |
| 📢 Advocate | Warn others, protect the community | Low |

## 🧬 Evolutionary Generations

| Generation | Focus | What It Finds |
|------------|-------|---------------|
| Gen 1 | Individual Probing | Single-feature vulnerabilities |
| Gen 2 | Combinatorial | Cross-feature exploits |
| Gen 3 | Systemic/Organized | Coordinated group attacks |
| Gen 4 | Business Impact | Revenue/reputation consequences |
| Gen 5 | Novel/Emergent | Hidden multi-system interactions |

## 📊 Report Sections (9 Total)

1. **Executive Summary** — Overall risk level + key stats
2. **Attack Surface Heatmap** — Which features are most targeted
3. **Threat Clusters** — Grouped vulnerability narratives
4. **Vulnerability Cards** — Top 20 detailed findings
5. **Evolution Tree** — How vulnerabilities evolved across generations
6. **Agent Behavior Cohorts** — User population behavior analysis
7. **Simulated Impact Timeline** — 90-day projection
8. **Remediation Roadmap** — Prioritized fix plan
9. **Full Agent Logs** — Every agent's reasoning chain

## 🚢 Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Set environment variables
vercel env add MONGODB_URI
vercel env add JWT_SECRET
vercel env add GEMINI_API_KEY
```

## 📄 License

MIT
