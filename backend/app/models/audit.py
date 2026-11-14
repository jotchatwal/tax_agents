from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId
from backend.app.models.common import PyObjectId

class AuditLogModel(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: PyObjectId
    session_id: Optional[str] = None
    event_type: str  # memory_created, memory_updated, memory_deleted, profile_versioned, recommendation_generated
    entity_type: str  # agent_memory, tax_profile, recommendation
    entity_id: Optional[PyObjectId] = None
    action: str  # create, supersede, correct, delete, compare
    actor: str = "user"  # user, agent, system
    reason: Optional[str] = None
    previous_version: Optional[int] = None
    new_version: Optional[int] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
