from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from bson import ObjectId
from backend.app.models.common import PyObjectId

GovernanceState = Literal["active", "superseded", "expired", "pending_confirmation", "deleted"]
VerificationStatus = Literal["user_confirmed", "unconfirmed", "disputed", "inferred"]

class MemorySource(BaseModel):
    type: str = "user_statement"  # user_statement, onboarding, document_upload, agent_inference
    session_id: Optional[str] = None
    profile_version: int = 1
    raw_statement: Optional[str] = None

class MemoryGovernance(BaseModel):
    status: GovernanceState = "active"
    confidence: float = 1.0
    verification_status: VerificationStatus = "user_confirmed"
    expires_at: Optional[datetime] = None
    supersedes_memory_id: Optional[PyObjectId] = None
    superseded_by_memory_id: Optional[PyObjectId] = None
    deletion_reason: Optional[str] = None

class AgentMemoryModel(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: PyObjectId
    memory_type: str  # employment_change, rrsp_intent, residency_fact, tuition_status, etc.
    content: str
    structured_data: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
    source: MemorySource = Field(default_factory=MemorySource)
    governance: MemoryGovernance = Field(default_factory=MemoryGovernance)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
