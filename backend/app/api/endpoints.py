from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Depends, Query
from pydantic import BaseModel
from bson import ObjectId

from backend.app.db.repositories import (
    UserRepository,
    ProfileRepository,
    MemoryRepository,
    RecommendationRepository,
    AuditRepository,
    TaxRuleRepository
)
from backend.app.models.profile import TaxProfileModel
from backend.app.models.recommendation import RecommendationModel
from backend.app.models.common import serialize_mongo
from backend.app.services.tax_calc import calculate_rrsp_what_if, calculate_combined_tax
from backend.app.services.memory_service import MemoryGovernanceService
from backend.app.graph.orchestrator import run_taxpilot_workflow

router = APIRouter(prefix="/api")

user_repo = UserRepository()
profile_repo = ProfileRepository()
memory_repo = MemoryRepository()
rec_repo = RecommendationRepository()
audit_repo = AuditRepository()
tax_rule_repo = TaxRuleRepository()
memory_service = MemoryGovernanceService(memory_repo, audit_repo)

def get_current_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    """
    Server-side authentication principal resolver.
    Strict Invariant: All endpoints and queries derive user_id from the authenticated principal.
    Defaults to demo user Alex if header is not explicitly set.
    """
    if x_user_id and ObjectId.is_valid(x_user_id):
        user = user_repo.get_by_id(x_user_id)
        if user:
            return str(user["_id"])

    # Fallback to demo user Alex Mercer
    demo_alex = user_repo.get_by_email("alex@example.com")
    if demo_alex:
        return str(demo_alex["_id"])

    users = user_repo.list_demo_users()
    if users:
        return str(users[0]["_id"])

    raise HTTPException(status_code=401, detail="No active user found.")

# Request Schemas
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default_session"

class RRSPScenarioRequest(BaseModel):
    annual_income: float
    rrsp_contribution: float
    rrsp_limit: Optional[float] = None
    tax_year: int = 2025

class CorrectMemoryRequest(BaseModel):
    new_content: str
    new_structured_data: Optional[Dict[str, Any]] = None

# --- API Endpoints ---

@router.get("/users/demo")
def list_demo_users():
    """List available demo personas for testing."""
    users = user_repo.list_demo_users()
    return [
        {
            "id": str(u["_id"]),
            "email": u["email"],
            "display_name": u["display_name"],
            "role": u.get("role", "taxpayer")
        }
        for u in users
    ]

@router.get("/profile/current")
def get_current_profile(tax_year: int = 2025, user_id: str = Depends(get_current_user_id)):
    """Retrieve authenticated user's current tax profile."""
    profile = profile_repo.get_current_profile(user_id, tax_year)
    if not profile:
        raise HTTPException(status_code=404, detail="Tax profile not found for this tax year.")
    profile["id"] = str(profile["_id"])
    profile["user_id"] = str(profile["user_id"])
    del profile["_id"]
    return profile

@router.post("/profile")
def save_profile(profile_data: TaxProfileModel, user_id: str = Depends(get_current_user_id)):
    """Create or update a confirmed tax profile."""
    profile_id = profile_repo.create_profile(user_id, profile_data)
    return {"status": "success", "profile_id": profile_id}

@router.post("/chat")
def submit_chat(req: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """Conversational interaction with LangGraph multi-agent orchestrator."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    res = run_taxpilot_workflow(
        user_id=user_id,
        request=req.message,
        session_id=req.session_id
    )
    return serialize_mongo(res)

@router.get("/memories")
def list_memories(
    include_superseded: bool = False,
    include_deleted: bool = False,
    user_id: str = Depends(get_current_user_id)
):
    """Retrieve inspectable memories belonging to the authenticated user."""
    if include_superseded:
        mems = memory_repo.get_all_user_memories(user_id, include_deleted=include_deleted)
    else:
        mems = memory_repo.get_active_memories(user_id)

    formatted = []
    for m in mems:
        m_copy = dict(m)
        m_copy["id"] = str(m_copy["_id"])
        m_copy["user_id"] = str(m_copy["user_id"])
        del m_copy["_id"]
        # Do not expose raw vector embedding floats to API client
        if "embedding" in m_copy:
            m_copy["has_embedding"] = m_copy["embedding"] is not None
            del m_copy["embedding"]
        formatted.append(m_copy)
    return formatted

@router.patch("/memories/{memory_id}")
def correct_memory(
    memory_id: str,
    req: CorrectMemoryRequest,
    user_id: str = Depends(get_current_user_id)
):
    """User governance action: correct an active memory."""
    if not ObjectId.is_valid(memory_id):
        raise HTTPException(status_code=400, detail="Invalid memory ID")

    updated = memory_service.memory_repo.correct_memory(
        user_id=user_id,
        memory_id=memory_id,
        new_content=req.new_content,
        new_structured_data=req.new_structured_data
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found or not owned by user.")

    return {"status": "success", "message": "Memory corrected successfully."}

@router.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: str,
    reason: str = Query("User requested deletion", description="Audit reason for erasure"),
    user_id: str = Depends(get_current_user_id)
):
    """User governance action: erase memory and embeddings while retaining minimal audit trail."""
    if not ObjectId.is_valid(memory_id):
        raise HTTPException(status_code=400, detail="Invalid memory ID")

    success = memory_service.delete_memory(user_id=user_id, memory_id=memory_id, reason=reason)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or not owned by user.")

    return {"status": "success", "message": "Memory erased successfully."}

@router.get("/recommendations")
def list_recommendations(tax_year: int = 2025, user_id: str = Depends(get_current_user_id)):
    """Retrieve recommendation history with official evidence and status."""
    recs = rec_repo.get_latest_recommendations(user_id, tax_year)
    out = []
    for r in recs:
        r_copy = dict(r)
        r_copy["id"] = str(r_copy["_id"])
        r_copy["user_id"] = str(r_copy["user_id"])
        del r_copy["_id"]
        out.append(r_copy)
    return out

@router.post("/scenarios/rrsp")
def run_rrsp_scenario(req: RRSPScenarioRequest):
    """Run deterministic RRSP what-if scenario without LLM arithmetic."""
    result = calculate_rrsp_what_if(
        annual_income=req.annual_income,
        rrsp_contribution=req.rrsp_contribution,
        rrsp_limit=req.rrsp_limit,
        tax_year=req.tax_year
    )
    return result

@router.get("/audit")
def get_audit_trail(limit: int = 50, user_id: str = Depends(get_current_user_id)):
    """Retrieve transparent audit trail of memory and recommendation actions."""
    logs = audit_repo.get_user_audit_logs(user_id, limit=limit)
    out = []
    for l in logs:
        l_copy = dict(l)
        l_copy["id"] = str(l_copy["_id"])
        l_copy["user_id"] = str(l_copy["user_id"])
        if l_copy.get("entity_id"):
            l_copy["entity_id"] = str(l_copy["entity_id"])
        del l_copy["_id"]
        out.append(l_copy)
    return out

@router.get("/rules")
def get_tax_rules(tax_year: int = 2025):
    """List verified CRA & Ontario tax rules."""
    rules = tax_rule_repo.list_rules_for_calculation(tax_year=tax_year)
    out = []
    for r in rules:
        r_copy = dict(r)
        r_copy["id"] = str(r_copy["_id"])
        del r_copy["_id"]
        if "embedding" in r_copy:
            del r_copy["embedding"]
        out.append(r_copy)
    return out
