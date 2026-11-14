from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId
from backend.app.models.common import PyObjectId

class AgentSessionModel(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: PyObjectId
    thread_id: str
    workflow_status: str = "active"  # active, completed, failed, awaiting_confirmation
    current_node: str = "init"
    context_summary: Optional[str] = None
    checkpoint: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
