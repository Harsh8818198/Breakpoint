# Breakpoint

> **Evolutionary Adversarial Product Simulation & Mechanical Code Vulnerability Verification**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Breakpoint is an adversarial evaluation platform designed to discover systemic vulnerabilities and logic flaws in software products and codebases before real attackers do.

Rather than relying on single-shot LLM prompts (which hallucinate security claims) or classical static analysis alone (which misses complex business logic and systemic multi-step attacks), Breakpoint deploys **populations of diverse adversarial agents** that evolve across multiple generations, paired with a **ground-truth mechanical code verifier**.

---

## 🏛️ System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                              INTAKE MODES                              │
│   Mode 1: Product Spec / Text  │  Mode 2: Docs  │  Mode 3: Git Repo    │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │       PRODUCT BLUEPRINT         │
                    │ State Machine & Component Model │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
               ┌───────────────────────────────────────────┐
               │    EVOLUTIONARY AGENT POPULATION (1-5)    │
               │   12 Threat Archetypes + Custom Vectors   │
               │                                           │
               │  • Gen 1: Single-Feature Surface Attacks  │
               │  • Gen 2: Combinatorial & Multi-Route     │
               │  • Gen 3: Systemic & Privilege Escalation │
               │  • Gen 4: Business Logic & Economic Abuses│
               │  • Gen 5: Novel & Emergent Edge Cases     │
               └─────────────────────┬─────────────────────┘
                                     │
                                     ▼
               ┌───────────────────────────────────────────┐
               │         MECHANICAL CLAIM VERIFIER         │
               │                                           │
               │  1. Extract Symbols, Files & Line Targets │
               │  2. Judge must cite VERBATIM source lines │
               │  3. Hard string match against real code   │
               │  4. Reject unverified / hallucinated CVEs │
               └─────────────────────┬─────────────────────┘
                                     │
                                     ▼
               ┌───────────────────────────────────────────┐
               │      CAUSAL VULNERABILITY GRAPH (CVG)     │
               │                                           │
               │  • Maps findings to shared Root Causes    │
               │  • Greedy Set-Cover -> Minimal Fix Set    │
               │  • Generates actionable remediation graph │
               └───────────────────────────────────────────┘
```

---

## ⚡ Key Innovations

1. **Evolutionary Multi-Agent Search**: Agents are parameterized by distinct behavioral vectors (adversarial archetypes: data exfiltration, race conditions, auth bypass, economic abuse). Each generation explores structurally different threat spaces with genetic crossover of successful attack vectors.
2. **Context-Steered Code Retrieval**: A lightweight keyword and security-control retrieval index scans the target codebase to isolate active attack surfaces (e.g. dangerous sinks, session flags, CSRF tokens, cryptographic routines), steering agents directly to relevant implementation slices.
3. **Mechanical Quote Verification**: AI vulnerability claims are notoriously prone to false positives. Breakpoint runs every generated claim through a strict mechanical verification judge: every cited line must exist verbatim in the source tree with exact line numbers. Claims that cannot produce real, verbatim code quotes are automatically rejected.
4. **Causal Vulnerability Graph (CVG) & Minimal Fix Set**: Instead of overwhelming developers with an unranked list of 50 disconnected warnings, Breakpoint maps findings into a causal dependency graph and solves a greedy set-cover problem to compute the **Minimal Fix Set**—the smallest set of architectural patches that remediates 100% of critical paths.

---

## 📁 Repository Structure

```
Breakpoint/
├── breakpoint/             # Core Python Engine & CLI
│   ├── breakpoint/         # Engine modules
│   │   ├── models.py       # Data models (Blueprint, Agent, Finding, CVG)
│   │   ├── llm.py          # Unified LLM provider client (OpenAI, Anthropic, Gemini)
│   │   ├── blueprint.py    # Multi-mode product and codebase intake
│   │   ├── agents.py       # Archetype population and persona vector sampling
│   │   ├── evolution.py    # Evolutionary loop, selection, crossover, and dedup
│   │   ├── codeindex.py    # Keyword and security cue indexing
│   │   ├── coderetrieval.py# Context-steered source region retrieval
│   │   ├── codeverify.py   # Mechanical quote and verbatim verification
│   │   ├── cvg.py          # Causal Vulnerability Graph & Minimal Fix Set
│   │   └── run.py          # CLI runner (`breakpoint-scan`)
│   ├── tests/              # Benchmark test suites (e.g., OWASP NodeGoat ground truth)
│   └── requirements.txt    # Python dependencies
│
└── frontend/               # Full-Stack Web Interface
    ├── src/app/            # Next.js 14 App Router (Intake, Simulation, Interactive Report)
    ├── src/components/     # UI components (DAG Visualizer, SSE Simulation Stream)
    └── src/lib/            # Database models (MongoDB), services, and API handlers
```

---

## 🚀 Quick Start

### 1. Python Core Engine (CLI)

The core engine requires Python 3.10+.

```bash
# Clone the repository
git clone https://github.com/Harsh8818198/breakpoint.git
cd breakpoint/breakpoint

# Install in editable mode
pip install -e .

# Configure LLM provider
export BREAKPOINT_PROVIDER=anthropic   # or: openai | gemini
export ANTHROPIC_API_KEY="sk-ant-..."

# Verify API connection
breakpoint-scan --check
```

#### Run a Scan

**A. Scan a Git Repository or Local Codebase (Verified Mode):**
```bash
breakpoint-scan --codebase https://github.com/OWASP/NodeGoat --gens 3 --output nodegoat_report.json
```

**B. Scan from a Product Description / Spec:**
```bash
breakpoint-scan --desc "A multi-tenant SaaS workspace for collaborative document editing and live code execution" --gens 3
```

**C. Benchmark vs. Plain Prompt Baseline:**
```bash
# Generate baseline (single-shot prompt on the same codebase)
python -m breakpoint.run --baseline baseline.json --codebase path/to/repo

# Verify claims and score against ground-truth benchmarks
python -m breakpoint.run --verify-report baseline.json --codebase path/to/repo --output verified_baseline.json
python -m tests.score_report nodegoat_report.json
```

---

### 2. Full-Stack Web Application

The interactive web UI provides real-time SSE simulation streaming and visual Causal Vulnerability Graphs.

```bash
cd frontend

# Install Node dependencies
npm install

# Setup environment variables
cp .env.example .env.local

# Run Next.js development server
npm run dev
```

Visit `http://localhost:3000` to access the interactive dashboard.

---

## 🔬 Benchmark Methodology

Breakpoint is evaluated against verified real-world vulnerability benchmarks (such as OWASP NodeGoat, commit `c5cb68a`), comparing single-shot LLM reasoning against generational agent populations with and without mechanical verification.

Results demonstrate that while unconstrained models produce high false-positive rates on complex web apps, Breakpoint's mechanical code verification filter eliminates 100% of hallucinated findings while preserving true architectural vulnerabilities.

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
