from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from bson import ObjectId
from backend.app.models.common import PyObjectId

class Jurisdiction(BaseModel):
    country: str = "CA"
    province: str = "ON"

class EmploymentPeriod(BaseModel):
    employer_label: str = "Primary Employer"
    employment_type: str = "full_time"  # full_time, part_time, self_employed, contract
    annualized_income: Optional[float] = None
    actual_income_earned: Optional[float] = None
    income_currency: str = "CAD"
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    source_status: str = "user_confirmed"  # user_confirmed, user_reported, estimated

class FinancialContext(BaseModel):
    rrsp_contribution: Optional[float] = None
    rrsp_deduction_limit: Optional[float] = None  # CRA Notice of Assessment limit
    tfsa_contribution: Optional[float] = None
    tfsa_status: str = "unknown"  # active, none, unknown
    tuition_eligible: Optional[bool] = None
    eligible_tuition_amount: Optional[float] = None
    has_dependants: Optional[bool] = None
    num_dependants: Optional[int] = 0
    first_time_homebuyer: Optional[bool] = None

class ConsentSettings(BaseModel):
    memory_enabled: bool = True
    personalization_enabled: bool = True

class TaxProfileModel(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: PyObjectId
    jurisdiction: Jurisdiction = Field(default_factory=Jurisdiction)
    tax_year: int = 2025
    taxpayer_type: List[str] = Field(default_factory=lambda: ["employee"])
    employment_periods: List[EmploymentPeriod] = Field(default_factory=list)
    financial_context: FinancialContext = Field(default_factory=FinancialContext)
    consent: ConsentSettings = Field(default_factory=ConsentSettings)
    profile_version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
