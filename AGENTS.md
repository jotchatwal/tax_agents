# TaxPilot AI — Architectural Rules & Agent Guidelines

## 1. Hackathon Objective & Track
* **Track:** Statement Two: Memory You Can Govern.
* **Jurisdiction:** Canada (Ontario MVP) • Tax Year 2025.
* **Mission:** A personalized AI Canadian tax-planning companion maintaining user-governed financial context in MongoDB Atlas, with Vector Search retrieval, verified official CRA/Ontario tax rules, zero LLM arithmetic, and explicit memory lifecycle controls (inspect, correct, supersede, erase, audit).

---

## 2. Architectural Invariants & Rules

1. **Canonical State in MongoDB Atlas:** MongoDB Atlas (`taxpilot_db`) is the sole system of record for profiles, memories, sessions, recommendations, rules, and audit events.
2. **Strict Server-Side Tenant Isolation:** Every repository method and query MUST enforce `user_id` derived from the authenticated principal. Never trust a `user_id` from client request bodies.
3. **Atlas Vector Search Retrieval:** Vector queries on `agent_memories` MUST always include server-side prefilters: `user_id` and `governance.status == 'active'` (unless explicitly inspecting history).
4. **Deterministic Tax Calculations (Zero LLM Arithmetic):** LLMs must NEVER calculate taxes, invent rates, or estimate tax savings with free-form arithmetic. All tax bracket and RRSP calculations must be computed by deterministic Python functions in `backend/app/services/tax_calc.py` backed by verified CRA / Ontario rules.
5. **Memory Governance & Provenance:** Every memory must record its provenance, verification status, and version. Superseded memories are marked `superseded` and store pointers to their replacement. Deletion must wipe source memory and vector embeddings while recording an audit event.
6. **Optimistic Concurrency & Profile Versioning:** Any material profile update (e.g., income change) must increment `profile_version` and preserve historical audit trail for before/after comparison.
7. **Fact vs. Hypothesis Separation:** Factual life events (promotions, job changes, raises) update the profile and supersede memories. Hypothetical "what-if" queries are simulated in memory without mutating stored Atlas state.
8. **Official Source Grounding:** Every tax recommendation must cite the exact CRA / Ontario government source URL, tax year, assumptions, and eligibility status.

---

## 3. Repository Layout

* `backend/app/main.py`: FastAPI entry point, CORS middleware, and `/health` verification.
* `backend/app/config.py`: Pydantic Settings configuration reading `.env` (MongoDB Atlas URI, X.509 cert, Gemini LLM settings).
* `backend/app/api/endpoints.py`: REST API endpoints with recursive BSON `ObjectId` sanitization (`/api/chat`, `/api/memories`, `/api/profile`, `/api/scenarios/rrsp`, `/api/audit`, `/api/rules`).
* `backend/app/db/`:
  * `mongo.py`: MongoDB Atlas connection manager with X.509 client certificate and SRV URI support.
  * `repositories.py`: Scoped repository layer enforcing server-side tenant isolation.
  * `init_db.py`: MongoDB collection validators, indexes, and vector search specification.
* `backend/app/services/`:
  * `tax_calc.py`: Pure Python deterministic CRA 2025 Federal & Ontario progressive tax engine.
  * `llm_service.py`: Google Gemini integration (`gemini-3.5-flash-lite`) for dynamic NLP intent/entity extraction and grounded response synthesis.
  * `memory_service.py`: Vector embeddings (384-dim semantic hash / SentenceTransformer) and memory lifecycle engine.
  * `audit_service.py`: Immutable governance audit logging.
* `backend/app/graph/`:
  * `state.py`: LangGraph typed state schema (`AgentState`).
  * `nodes.py`: 12 execution nodes (intent classification, greeting handler, memory retrieval, conflict detection, deterministic calculations, recommendation generator, memory persistence, grounded response synthesis).
  * `orchestrator.py`: Compiled LangGraph StateGraph with conditional routing.
* `backend/app/static/`:
  * `index.html`: Responsive single-page dashboard with real-time hybrid chat, profile inspector, governed memory timeline, and immutable audit log.
* `data/seed/`: Verified CRA/Ontario tax rules and synthetic demo personas.
* `tests/`: Automated unit, integration, and security test suites (23 test cases).

---

## 4. Code Change Conventions

* When updating API responses, ensure all nested BSON `ObjectId` objects are sanitized using `sanitize_doc` to prevent JSON serialization errors.
* Never introduce LLM-generated numbers into tax calculations; always pass values through `backend/app/services/tax_calc.py`.
* Ensure automated test suites pass:
  ```bash
  python -m tests.test_tenant_isolation
  python -m tests.test_tax_calculator
  python -m tests.test_memory_governance
  python -m tests.test_workflow
  python -m tests.test_api_endpoints
  ```
