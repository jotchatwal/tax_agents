import logging
from datetime import datetime
from backend.app.db.mongo import get_db
from backend.app.db.repositories import (
    UserRepository,
    ProfileRepository,
    MemoryRepository,
    TaxRuleRepository,
    AuditRepository
)
from backend.app.models.user import UserModel
from backend.app.models.profile import TaxProfileModel, EmploymentPeriod, FinancialContext, Jurisdiction
from backend.app.models.memory import AgentMemoryModel, MemorySource, MemoryGovernance
from backend.app.models.tax_rule import TaxRuleModel
from backend.app.models.audit import AuditLogModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verified Official CRA and Ontario Tax Rules (Tax Year 2025)
SEED_RULES = [
    {
        "rule_id": "CA_FED_TAX_BRACKETS_2025",
        "jurisdiction": {"country": "CA", "province": "ON"},
        "tax_year": 2025,
        "category": "income_tax",
        "rule_name": "Federal Income Tax Brackets and Rates 2025",
        "rule_data": {
            "authority": "Canada Revenue Agency",
            "brackets": [
                {"threshold": 0.0, "rate": 0.1500},
                {"threshold": 57375.0, "rate": 0.2050},
                {"threshold": 114750.0, "rate": 0.2600},
                {"threshold": 177882.0, "rate": 0.2900},
                {"threshold": 253414.0, "rate": 0.3300}
            ],
            "basic_personal_amount": 16129.0
        },
        "source_url": "https://www.canada.ca/en/revenue-agency/services/tax/individuals/tax-rates-brackets/last-year.html",
        "source_authority": "Canada Revenue Agency",
        "status": "active",
        "content": "2025 Canadian Federal income tax brackets: 15% on first $57,375; 20.5% on portion over $57,375 up to $114,750; 26% up to $177,882; 29% up to $253,414; 33% over $253,414."
    },
    {
        "rule_id": "ON_PROV_TAX_BRACKETS_2025",
        "jurisdiction": {"country": "CA", "province": "ON"},
        "tax_year": 2025,
        "category": "income_tax",
        "rule_name": "Ontario Provincial Income Tax Brackets and Rates 2025",
        "rule_data": {
            "authority": "Ontario Ministry of Finance",
            "brackets": [
                {"threshold": 0.0, "rate": 0.0505},
                {"threshold": 52875.0, "rate": 0.0915},
                {"threshold": 105754.0, "rate": 0.1116},
                {"threshold": 150000.0, "rate": 0.1216},
                {"threshold": 220000.0, "rate": 0.1316}
            ],
            "basic_personal_amount": 12692.0,
            "surtax_tier_1_threshold": 5554.0,
            "surtax_tier_1_rate": 0.20,
            "surtax_tier_2_threshold": 7108.0,
            "surtax_tier_2_rate": 0.36
        },
        "source_url": "https://www.ontario.ca/document/general-information-income-tax-and-benefit-return/tax-rates-and-brackets",
        "source_authority": "Government of Ontario",
        "status": "active",
        "content": "2025 Ontario provincial tax rates: 5.05% up to $52,875; 9.15% between $52,875 and $105,754; 11.16% up to $150,000; 12.16% up to $220,000; 13.16% over $220,000."
    },
    {
        "rule_id": "CA_RRSP_DEDUCTION_LIMIT_2025",
        "jurisdiction": {"country": "CA", "province": "ON"},
        "tax_year": 2025,
        "category": "rrsp",
        "rule_name": "Registered Retirement Savings Plan (RRSP) Annual Limit 2025",
        "rule_data": {
            "statutory_maximum": 32490.0,
            "earned_income_percentage": 0.18,
            "notice_of_assessment_required": True,
            "penalty_overcontribution_threshold": 2000.0,
            "penalty_overcontribution_monthly_rate": 0.01
        },
        "source_url": "https://www.canada.ca/en/revenue-agency/services/tax/registered-plans-administrators/pspa/mp-rrsp-dpsp-tfsa-limits-ympe.html",
        "source_authority": "Canada Revenue Agency",
        "status": "active",
        "content": "2025 RRSP deduction limit is 18% of previous year earned income up to statutory maximum of $32,490, plus unused carried-forward room from prior Notice of Assessment."
    },
    {
        "rule_id": "CA_TUITION_TAX_CREDIT_2025",
        "jurisdiction": {"country": "CA", "province": "ON"},
        "tax_year": 2025,
        "category": "tuition",
        "rule_name": "Federal Tuition Tax Credit (Form T2202)",
        "rule_data": {
            "federal_credit_rate": 0.15,
            "carry_forward_allowed": True,
            "max_transferable_to_supporter": 5000.0,
            "requires_form": "T2202 Tuition and Enrolment Certificate"
        },
        "source_url": "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/deductions-credits-expenses/line-32300-your-tuition-education-textbook-amounts.html",
        "source_authority": "Canada Revenue Agency",
        "status": "active",
        "content": "Federal non-refundable tuition tax credit calculated at 15% of eligible tuition and fees. Requires official T2202 from designated educational institution."
    }
]

def seed_database():
    db = get_db()
    user_repo = UserRepository(db)
    profile_repo = ProfileRepository(db)
    memory_repo = MemoryRepository(db)
    tax_rule_repo = TaxRuleRepository(db)
    audit_repo = AuditRepository(db)

    logger.info("1. Seeding verified CRA and Ontario tax rules...")
    for rule_data in SEED_RULES:
        rule_model = TaxRuleModel(**rule_data)
        tax_rule_repo.upsert_rule(rule_model)
        logger.info(f"Upserted tax rule: {rule_model.rule_id}")

    logger.info("2. Seeding synthetic demo users and profiles...")

    # Persona 1: Alex (Employee) - Ontario full-time employee
    alex_user = user_repo.get_by_email("alex@example.com")
    if not alex_user:
        alex_id = user_repo.create_user(UserModel(
            email="alex@example.com",
            display_name="Alex Mercer",
            role="taxpayer",
            status="active"
        ))
        alex_user = user_repo.get_by_id(alex_id)
        logger.info(f"Created demo user: Alex Mercer ({alex_user['_id']})")
    else:
        logger.info(f"Demo user Alex already exists: {alex_user['_id']}")

    alex_user_id = alex_user["_id"]

    # Initial Profile for Alex (Version 1: $85,000 CAD)
    existing_alex_profile = profile_repo.get_current_profile(alex_user_id, 2025)
    if not existing_alex_profile:
        profile_repo.create_profile(alex_user_id, TaxProfileModel(
            user_id=alex_user_id,
            jurisdiction=Jurisdiction(country="CA", province="ON"),
            tax_year=2025,
            taxpayer_type=["employee"],
            employment_periods=[
                EmploymentPeriod(
                    employer_label="TechCorp Canada Ltd",
                    employment_type="full_time",
                    annualized_income=85000.0,
                    actual_income_earned=85000.0,
                    income_currency="CAD",
                    effective_from=datetime(2025, 1, 1),
                    effective_to=None,
                    source_status="user_confirmed"
                )
            ],
            financial_context=FinancialContext(
                rrsp_contribution=5000.0,
                rrsp_deduction_limit=18000.0,
                tfsa_status="active",
                tuition_eligible=False,
                has_dependants=False
            ),
            profile_version=1
        ))
        logger.info(f"Created initial profile v1 for Alex ($85k salary).")

    # Persona 2: Priya (Student)
    priya_user = user_repo.get_by_email("priya@example.com")
    if not priya_user:
        priya_id = user_repo.create_user(UserModel(
            email="priya@example.com",
            display_name="Priya Patel",
            role="taxpayer",
            status="active"
        ))
        priya_user = user_repo.get_by_id(priya_id)
        profile_repo.create_profile(priya_user["_id"], TaxProfileModel(
            user_id=priya_user["_id"],
            jurisdiction=Jurisdiction(country="CA", province="ON"),
            tax_year=2025,
            taxpayer_type=["student", "employee"],
            employment_periods=[
                EmploymentPeriod(
                    employer_label="Campus Bookstore",
                    employment_type="part_time",
                    annualized_income=18000.0,
                    actual_income_earned=18000.0,
                    income_currency="CAD",
                    effective_from=datetime(2025, 1, 1),
                    source_status="user_confirmed"
                )
            ],
            financial_context=FinancialContext(
                tuition_eligible=True,
                eligible_tuition_amount=6500.0,
                rrsp_contribution=0.0,
                rrsp_deduction_limit=2500.0,
                tfsa_status="unknown"
            ),
            profile_version=1
        ))
        logger.info("Created demo user and profile for Priya (Student).")

    # Initial Memory for Alex: Employment Income fact
    active_memories = memory_repo.get_active_memories(alex_user_id, "employment_income")
    if not active_memories:
        mem_id = memory_repo.create_memory(alex_user_id, AgentMemoryModel(
            user_id=alex_user_id,
            memory_type="employment_income",
            content="Alex confirmed annual employment income of $85,000 CAD at TechCorp Canada Ltd for tax year 2025.",
            structured_data={
                "annualized_income": 85000.0,
                "employer": "TechCorp Canada Ltd",
                "tax_year": 2025,
                "currency": "CAD"
            },
            source=MemorySource(
                type="onboarding",
                profile_version=1,
                raw_statement="My salary is $85,000 at TechCorp Canada."
            ),
            governance=MemoryGovernance(
                status="active",
                confidence=1.0,
                verification_status="user_confirmed"
            )
        ))
        audit_repo.log_event(AuditLogModel(
            user_id=alex_user_id,
            event_type="memory_created",
            entity_type="agent_memory",
            entity_id=mem_id,
            action="create",
            actor="system",
            reason="Initial onboarding profile confirmation",
            new_version=1
        ))
        logger.info("Created initial governed memory record for Alex ($85k salary).")

    print("\nDatabase seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
