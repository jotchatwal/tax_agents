from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from backend.app.models.common import PyObjectId

class UserModel(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    email: str = Field(..., pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    display_name: str
    auth_provider: str = "demo"
    role: str = "taxpayer"  # taxpayer, admin
    status: str = "active"  # active, suspended, deleted
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

