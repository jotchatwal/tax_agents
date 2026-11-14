# 🍁 TaxPilot AI — A Governed, Memory-Driven Canadian Tax-Planning Companion

> **Hackathon Track:** Statement Two: Memory You Can Govern  
> **Jurisdiction:** Canada (Ontario MVP) • Tax Year 2025  
> **Core Architecture:** MongoDB Atlas + Atlas Vector Search + LangGraph + Google Gemini + FastAPI + Hybrid UI  
> **Technical Specifications:** See [ARCHITECTURE.md](file:///c:/Users/nimba/Desktop/Hackathon/tax_agents/ARCHITECTURE.md) • **1-Min Technical Demo:** See [DEMO.md](file:///c:/Users/nimba/Desktop/Hackathon/tax_agents/DEMO.md)

---

## 🏆 Problem Statement & Hackathon Thesis

Taxpayers and small business owners often miss legitimate tax planning opportunities because financial circumstances evolve over time, tax rules vary across years and jurisdictions, and conventional AI assistants lack a **reliable, user-governed memory** of the taxpayer across sessions.

### The Demo Thesis
Demonstrate the same taxpayer across multi-session life events:
1. **Session 1 (Baseline Profile):** Synthetic taxpayer (Alex Mercer, Ontario resident, full-time employee earning **$85,000 CAD**). The assistant evaluates 2025 Ontario & Federal tax brackets, models an initial $5,000 RRSP contribution saving **$1,482.50 CAD** (29.65% marginal rate), and persists the confirmed employment fact in MongoDB Atlas `agent_memories` with Vector Search embeddings.
2. **Session 2 (Circumstance Change):** Alex returns and states: *"I got promotion and I got salary increment of 20K now tell me what should i be looking for my upcoming year."* The assistant:
   - Recognizes the factual life event and computes the new baseline ($85k / $105k + $20k = **$105k / $125k CAD**).
   - Bumps the profile version with optimistic concurrency.
   - Archives the prior memory as `superseded` pointing directly to its replacement.
   - Deterministically re-evaluates tax impact: higher marginal rate (31.48% / 37.91%) increases RRSP tax savings.
   - Explains precisely **why** recommendations changed and **which** memory caused the change.
3. **Memory Governance & Lifecycle Controls:** The user inspects the memory timeline, corrects facts, or requests erasure (content and vectors are wiped from Atlas while minimal audit logs are preserved).
4. **Hypothetical What-If Protection:** When the user asks conditional questions (*"What if my salary changes to $95k?"*), the system simulates the scenario without corrupting or mutating the stored canonical memory.

---

## 🧱 Architectural Invariants & Rules

1. **Canonical State in MongoDB Atlas:** MongoDB Atlas (`taxpilot_db`) is the single source of truth for `users`, `tax_profiles`, `agent_memories`, `tax_rules`, `recommendations`, `agent_sessions`, and `audit_logs`.
2. **Strict Server-Side Tenant Isolation:** Every repository method and query strictly enforces `user_id` derived from the authenticated principal. Request body `user_id` values are never trusted.
3. **Atlas Vector Search Retrieval:** Vector queries on `agent_memories` enforce mandatory server-side prefilters: `user_id` and `governance.status == 'active'`.
4. **Deterministic Tax Calculations (Zero LLM Arithmetic):** LLMs **never** compute taxes, invent rates, or estimate savings with free-form arithmetic. All calculations are executed by deterministic Python functions backed by verified CRA and Ontario Ministry of Finance rules.
5. **Memory Governance & Provenance:** Every memory records provenance, verification status, and version. Superseded memories point to their replacement. Deletion wipes source text and vector embeddings while recording an audit event.
6. **Official Source Grounding:** Every recommendation cites official CRA / Ontario government URLs and explicit assumptions.
7. **Conversational Intent Routing:** LangGraph uses conditional branching to route greetings swiftly, simulate what-ifs safely, and only update persistent memory on confirmed factual life events.

---

## 📁 Repository Structure

```
tax_agents/
├── AGENTS.md                  # Workspace architectural rules and invariants
├── ARCHITECTURE.md            # Deep-dive system architecture and flow diagrams
├── README.md                  # Documentation, architecture, and demo guide
├── .env.example               # Environment variable templates
├── X509-cert-*.pem            # X.509 client certificate for MongoDB Atlas
├── backend/
│   └── app/
│       ├── main.py            # FastAPI entry point & health check
│       ├── config.py          # Pydantic Settings configuration
│       ├── api/
│       │   └── endpoints.py   # User, Profile, Chat, Memory, Scenario & Audit endpoints
│       ├── db/
│       │   ├── mongo.py       # MongoDB Atlas connection manager (X.509 / URI)
│       │   ├── init_db.py     # Schema validators, indexes, and vector search spec
│       │   └── repositories.py# Scoped repository layer enforcing tenant isolation
│       ├── models/            # Pydantic schemas for the 7 collection contracts
│       ├── services/
│       │   ├── tax_calc.py    # Deterministic tax engine (Federal/ON brackets & RRSP)
│       │   ├── llm_service.py # Google Gemini 3.5 Flash / Flash Lite integration
│       │   ├── memory_service.py # Vector embedding & memory lifecycle engine
│       │   └── audit_service.py  # Governance audit logging
│       ├── graph/
│       │   ├── state.py       # LangGraph state schema (AgentState)
│       │   ├── nodes.py       # Orchestrator & agent execution nodes
│       │   └── orchestrator.py# Compiled StateGraph workflow with conditional routing
│       └── static/
│           └── index.html     # Responsive hybrid conversational & governance dashboard
├── data/
│   └── seed/
│       ├── seed_data.py       # Verified CRA rules & synthetic persona seeder
│       └── vector_index_definition.json # Atlas Vector Search index definition
└── tests/
    ├── test_tenant_isolation.py   # Cross-user security & optimistic concurrency tests
    ├── test_tax_calculator.py     # Deterministic tax engine boundary & bracket tests
    ├── test_memory_governance.py  # Memory supersession, embedding & deletion tests
    ├── test_workflow.py           # Multi-session LangGraph end-to-end integration tests
    └── test_api_endpoints.py      # FastAPI HTTP endpoint tests (including /api/chat)
```

---

## 🚀 Quickstart & Setup Instructions

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.15)
- MongoDB Atlas Cluster with X.509 client certificate or URI
- Google Gemini API Key

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure your configuration in `.env` is set:
```ini
MONGODB_URI=mongodb+srv://cluster0.ofim2w.mongodb.net/taxpilot_db?authSource=%24external&authMechanism=MONGODB-X509
MONGODB_DATABASE=taxpilot_db
MONGODB_CERT_PATH=./X509-cert-3974345015379903984.pem

LLM_PROVIDER=gemini
LLM_API_KEY=<your-gemini-api-key>
LLM_MODEL=gemini-3.5-flash-lite

EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIMENSIONS=384

APP_SECRET_KEY=taxpilot-hackathon-2026-secret-governed-memory-key
FRONTEND_ORIGIN=http://localhost:8000
ENVIRONMENT=development
```

### 3. Initialize Database & Seed Verified Tax Rules
```bash
python -m backend.app.db.init_db
python -m data.seed.seed_data
```

### 4. Run the Automated Test Suite (23 Tests)
```bash
# Run security and tenant isolation tests
python -m tests.test_tenant_isolation

# Run deterministic tax calculations tests
python -m tests.test_tax_calculator

# Run memory governance and lifecycle tests
python -m tests.test_memory_governance

# Run multi-session LangGraph workflow integration tests
python -m tests.test_workflow

# Run FastAPI API endpoint tests
python -m tests.test_api_endpoints
```

### 5. Launch the Application
```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser to access the hybrid chat and governance dashboard.

---

## 🎬 Video Demo Walkthrough Script

| Time | Screen / Action | Narration |
| :--- | :--- | :--- |
| **00:00 - 00:10** | Overview & Track intro | *"Welcome to TaxPilot AI, built for the MongoDB Hackathon Track: Memory You Can Govern. Conventional assistants forget changing financial circumstances. TaxPilot maintains user-governed context in MongoDB Atlas."* |
| **00:10 - 00:20** | Profile & Initial Recommendation | *"We start with Alex Mercer, an Ontario employee earning $85,000 in Profile Version 1. Alex asks for opportunities. TaxPilot retrieves verified 2025 CRA rules and deterministically models a $5,000 RRSP deduction saving $1,482.50 at his 29.65% marginal rate."* |
| **00:20 - 00:30** | Memory Persistence in Atlas | *"Notice the Governed Memories tab: the $85,000 employment fact is stored in Atlas `agent_memories` with 384-dimensional vector embeddings, strictly scoped to Alex."* |
| **00:30 - 00:45** | Circumstance Change & Increment | *"Alex reports: 'I got a promotion and a salary increment of 20K, what should I look for?'. TaxPilot identifies the compound intent, computes the new $105,000 salary, increments to Version 2 using optimistic concurrency, supersedes the old memory, and shows increased RRSP savings of $1,574.00."* |
| **00:45 - 00:55** | Memory Governance (Erase & Audit) | *"Alex clicks 'Erase' on a memory. TaxPilot wipes the content and vector embeddings from Atlas while preserving an immutable governance audit trail in `audit_logs`."* |
| **00:55 - 01:00** | Conclusion | *"Zero LLM arithmetic, official CRA citations, and true memory you can govern with MongoDB Atlas."* |

---

## 🏛️ Verified Official Government References
- **Federal 2025 Tax Rates & Brackets:** [Canada Revenue Agency (CRA)](https://www.canada.ca/en/revenue-agency/services/tax/individuals/tax-rates-brackets/last-year.html)
- **Ontario 2025 Provincial Rates & Surtaxes:** [Ontario Ministry of Finance](https://www.ontario.ca/document/general-information-income-tax-and-benefit-return/tax-rates-and-brackets)
- **2025 RRSP Deduction Limits & Statutory Caps:** [CRA Registered Plans Directorate](https://www.canada.ca/en/revenue-agency/services/tax/registered-plans-administrators/pspa/mp-rrsp-dpsp-tfsa-limits-ympe.html)
- **Tuition Non-Refundable Tax Credit (Line 32300):** [CRA Tuition Guidance](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/deductions-credits-expenses/line-32300-your-tuition-education-textbook-amounts.html)
