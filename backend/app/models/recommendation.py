from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from bson import ObjectId
from backend.app.models.common import PyObjectId

EligibilityStatus = Literal[
    "eligible_based_on_provided_facts",
    "potentially_eligible",
    "not_eligible",
    "needs_verification",
    "insufficient_information"
]

class TaxSavingEstimate(BaseModel):
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    currency: str = "CAD"
    calculation_status: str = "not_calculated"  # calculated, not_calculated, needs_more_info
    marginal_tax_rate: Optional[float] = None
    calculation_breakdown: Dict[str, Any] = Field(default_factory=dict)

class EligibilityAssessment(BaseModel):
    status: EligibilityStatus = "needs_verification"
    required_facts: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)

class EvidenceReference(BaseModel):
    rule_id: str
    source_url: str
    authority: str = "Canada Revenue Agency"
    description: Optional[str] = None

class RecommendationModel(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: PyObjectId
    tax_year: int
    recommendation_type: str  # rrsp_planning, tuition_credit, bracket_optimization, tfsa_guidance
    title: str
    description: str
    explanation: Optional[str] = None
    estimated_tax_saving: TaxSavingEstimate = Field(default_factory=TaxSavingEstimate)
    eligibility: EligibilityAssessment = Field(default_factory=EligibilityAssessment)
    evidence: List[EvidenceReference] = Field(default_factory=list)
    memory_ids: List[PyObjectId] = Field(default_factory=list)
    profile_version: int = 1
    calculation_assumptions: List[str] = Field(default_factory=list)
    confidence_label: str = "High"  # High, Medium, Low
    next_step: Optional[str] = None
    status: str = "proposed"  # proposed, accepted, dismissed, superseded
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
