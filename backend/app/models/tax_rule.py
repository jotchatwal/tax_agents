from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId
from backend.app.models.common import PyObjectId
from backend.app.models.profile import Jurisdiction

class TaxRuleModel(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    rule_id: str  # e.g. "CA_FED_BRACKETS_2025", "ON_PROV_BRACKETS_2025", "CA_RRSP_LIMIT_2025"
    jurisdiction: Jurisdiction = Field(default_factory=Jurisdiction)
    tax_year: int
    category: str  # income_tax, rrsp, tfsa, tuition, credits
    rule_name: str
    rule_data: Dict[str, Any] = Field(default_factory=dict)
    source_url: str  # verified official CRA or Ontario URL
    source_authority: str = "Canada Revenue Agency / Government of Ontario"
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    verified_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"  # active, outdated, superseded
    content: str  # normalized text summary
    embedding: Optional[List[float]] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
