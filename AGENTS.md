# TaxPilot AI - Architectural Rules & System Invariants

## 1. Hackathon Objective & Track
- **Track:** Statement Two: Memory You Can Govern.
- **Goal:** Personalized AI Canadian tax-planning companion maintaining user-governed financial context in MongoDB Atlas, with Vector Search retrieval, verified official tax references (Ontario/Federal), deterministic calculations, and explicit memory lifecycle controls (inspect, correct, supersede, delete, audit).

## 2. Architectural Invariants
1. **Canonical State in MongoDB Atlas:** MongoDB Atlas (`taxpilot_db`) is the single source of truth for profiles, memories, sessions, recommendations, rules, and audit events.
2. **Strict Server-Side Tenant Isolation:** Every repository method and query MUST enforce `user_id` derived from the authenticated principal. Never trust a `user_id` from client request bodies.
3. **Atlas Vector Search Retrieval:** Vector queries on `agent_memories` MUST always include server-side prefilters: `user_id` and `governance.status == 'active'` (unless inspecting history).
4. **Deterministic Tax Calculations (Zero LLM Arithmetic):** LLMs must NEVER calculate taxes, invent rates, or estimate tax savings with free-form arithmetic. All tax bracket and RRSP calculations must be computed by deterministic Python functions backed by verified CRA / Ontario rules.
5. **Memory Governance & Provenance:** Every memory must record its provenance, verification status, and version. Superseded memories are marked `superseded` and point to their replacement. Deletion must wipe source memory and vector embeddings while recording an audit event.
6. **Optimistic Concurrency & Profile Versioning:** Any material profile update (e.g., income change) must increment `profile_version` and preserve historical audit trail for before/after comparison.
7. **Official Source Grounding:** Every tax recommendation must cite the exact CRA / Ontario government source URL, tax year, assumptions, and eligibility status.

## 3. Directory Layout
- `backend/app/main.py`: FastAPI entry point
- `backend/app/api/`: API endpoints
- `backend/app/models/`: Pydantic schemas and database collection contracts
- `backend/app/db/`: MongoDB connection, repositories, indexes, and schema validators
- `backend/app/services/`: Memory governance, deterministic tax calculations, rule retrieval, and audit
- `backend/app/agents/`: LangGraph orchestrator and specialized agents
- `data/seed/`: Official 2024/2025 CRA/Ontario tax rules and synthetic taxpayer profiles
- `tests/`: Pytest suite (unit, integration, security/cross-user isolation)
- `frontend/`: Hybrid chat and governance dashboard
