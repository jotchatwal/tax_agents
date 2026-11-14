from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from pymongo.database import Database
from pymongo.collection import Collection
from backend.app.db.mongo import get_db
from backend.app.models.user import UserModel
from backend.app.models.profile import TaxProfileModel
from backend.app.models.memory import AgentMemoryModel, GovernanceState
from backend.app.models.tax_rule import TaxRuleModel
from backend.app.models.recommendation import RecommendationModel
from backend.app.models.audit import AuditLogModel
from backend.app.models.session import AgentSessionModel

class BaseRepository:
    collection_name: str = ""

    def __init__(self, db: Optional[Database] = None):
        self._db = db

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = get_db()
        return self._db

    @property
    def col(self) -> Collection:
        return self.db[self.collection_name]

    @staticmethod
    def to_object_id(val: Any) -> ObjectId:
        if isinstance(val, ObjectId):
            return val
        return ObjectId(str(val))


class UserRepository(BaseRepository):
    collection_name = "users"

    def get_by_id(self, user_id: Any) -> Optional[Dict[str, Any]]:
        return self.col.find_one({"_id": self.to_object_id(user_id)})

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return self.col.find_one({"email": email.strip().lower()})

    def create_user(self, user: UserModel) -> str:
        doc = user.model_dump(by_alias=True, exclude_none=True)
        doc["created_at"] = doc.get("created_at") or datetime.utcnow()
        doc["updated_at"] = doc.get("updated_at") or datetime.utcnow()
        if "_id" in doc and doc["_id"] is None:
            del doc["_id"]
        res = self.col.insert_one(doc)
        return str(res.inserted_id)

    def list_demo_users(self) -> List[Dict[str, Any]]:
        cursor = self.col.find({"status": "active"}).sort("created_at", 1)
        return list(cursor)


class ProfileRepository(BaseRepository):
    collection_name = "tax_profiles"

    def get_current_profile(self, user_id: Any, tax_year: int = 2025) -> Optional[Dict[str, Any]]:
        """Strict server-side tenant isolation: only retrieve profile for user_id."""
        return self.col.find_one({
            "user_id": self.to_object_id(user_id),
            "tax_year": int(tax_year)
        })

    def create_profile(self, user_id: Any, profile: TaxProfileModel) -> str:
        """Strict server-side tenant isolation: enforce authenticated user_id."""
        doc = profile.model_dump(by_alias=True, exclude_none=True)
        doc["user_id"] = self.to_object_id(user_id)
        doc["created_at"] = doc.get("created_at") or datetime.utcnow()
        doc["updated_at"] = doc.get("updated_at") or datetime.utcnow()
        if "_id" in doc and doc["_id"] is None:
            del doc["_id"]
        res = self.col.insert_one(doc)
        return str(res.inserted_id)

    def update_profile_version(
        self,
        user_id: Any,
        tax_year: int,
        updates: Dict[str, Any],
        expected_version: int
    ) -> Optional[Dict[str, Any]]:
        """Optimistic concurrency: only updates if profile_version matches expected_version."""
        new_version = expected_version + 1
        updates["profile_version"] = new_version
        updates["updated_at"] = datetime.utcnow()

        result = self.col.find_one_and_update(
            {
                "user_id": self.to_object_id(user_id),
                "tax_year": int(tax_year),
                "profile_version": expected_version
            },
            {"$set": updates},
            return_document=True
        )
        return result


class MemoryRepository(BaseRepository):
    collection_name = "agent_memories"

    def create_memory(self, user_id: Any, memory: AgentMemoryModel) -> str:
        doc = memory.model_dump(by_alias=True, exclude_none=True)
        doc["user_id"] = self.to_object_id(user_id)
        doc["created_at"] = doc.get("created_at") or datetime.utcnow()
        doc["updated_at"] = doc.get("updated_at") or datetime.utcnow()
        if "_id" in doc and doc["_id"] is None:
            del doc["_id"]
        res = self.col.insert_one(doc)
        return str(res.inserted_id)

    def get_memory_by_id(self, user_id: Any, memory_id: Any) -> Optional[Dict[str, Any]]:
        """Strict tenant isolation: cannot retrieve memory by ID unless owned by user_id."""
        return self.col.find_one({
            "_id": self.to_object_id(memory_id),
            "user_id": self.to_object_id(user_id)
        })

    def get_active_memories(
        self,
        user_id: Any,
        memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve only active memories belonging to the authenticated user."""
        query = {
            "user_id": self.to_object_id(user_id),
            "governance.status": "active"
        }
        if memory_type:
            query["memory_type"] = memory_type
        return list(self.col.find(query).sort("created_at", -1))

    def get_all_user_memories(
        self,
        user_id: Any,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Retrieve memory history for user governance timeline."""
        query: Dict[str, Any] = {"user_id": self.to_object_id(user_id)}
        if not include_deleted:
            query["governance.status"] = {"$ne": "deleted"}
        return list(self.col.find(query).sort("created_at", -1))

    def supersede_memory(
        self,
        user_id: Any,
        old_memory_id: Any,
        new_memory_id: Any
    ) -> bool:
        """Mark old memory as superseded and point to replacement."""
        res = self.col.update_one(
            {
                "_id": self.to_object_id(old_memory_id),
                "user_id": self.to_object_id(user_id)
            },
            {
                "$set": {
                    "governance.status": "superseded",
                    "governance.superseded_by_memory_id": self.to_object_id(new_memory_id),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return res.modified_count > 0

    def correct_memory(
        self,
        user_id: Any,
        memory_id: Any,
        new_content: str,
        new_structured_data: Optional[Dict[str, Any]] = None,
        new_embedding: Optional[List[float]] = None
    ) -> Optional[Dict[str, Any]]:
        """Direct correction of an active memory."""
        update_doc: Dict[str, Any] = {
            "content": new_content,
            "governance.verification_status": "user_confirmed",
            "updated_at": datetime.utcnow()
        }
        if new_structured_data is not None:
            update_doc["structured_data"] = new_structured_data
        if new_embedding is not None:
            update_doc["embedding"] = new_embedding

        return self.col.find_one_and_update(
            {
                "_id": self.to_object_id(memory_id),
                "user_id": self.to_object_id(user_id)
            },
            {"$set": update_doc},
            return_document=True
        )

    def delete_memory(
        self,
        user_id: Any,
        memory_id: Any,
        deletion_reason: str = "User requested erasure"
    ) -> bool:
        """
        Governance memory deletion:
        Wipes source memory content, structured data, and embeddings,
        marking record as 'deleted' to preserve auditability without storing private data.
        """
        res = self.col.update_one(
            {
                "_id": self.to_object_id(memory_id),
                "user_id": self.to_object_id(user_id)
            },
            {
                "$set": {
                    "content": "[DELETED BY USER]",
                    "structured_data": {},
                    "embedding": None,
                    "governance.status": "deleted",
                    "governance.deletion_reason": deletion_reason,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return res.modified_count > 0

    def vector_search(
        self,
        user_id: Any,
        query_vector: List[float],
        limit: int = 5,
        memory_type: Optional[str] = None,
        status: str = "active"
    ) -> List[Dict[str, Any]]:
        """
        Atlas Vector Search with mandatory server-side user_id & governance prefilters.
        Falls back to structured retrieval if Vector Search index is pending or in local fallback.
        """
        filter_doc: Dict[str, Any] = {
            "user_id": self.to_object_id(user_id),
            "governance.status": status
        }
        if memory_type:
            filter_doc["memory_type"] = memory_type

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "memory_vector_index",
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": limit * 10,
                    "limit": limit,
                    "filter": filter_doc
                }
            }
        ]
        try:
            results = list(self.col.aggregate(pipeline))
            return results
        except Exception:
            cursor = self.col.find(filter_doc).sort("created_at", -1).limit(limit)
            return list(cursor)


class TaxRuleRepository(BaseRepository):
    collection_name = "tax_rules"

    def upsert_rule(self, rule: TaxRuleModel) -> str:
        doc = rule.model_dump(by_alias=True, exclude_none=True)
        doc["verified_at"] = doc.get("verified_at") or datetime.utcnow()
        if "_id" in doc and doc["_id"] is None:
            del doc["_id"]
        res = self.col.update_one(
            {"rule_id": rule.rule_id, "tax_year": rule.tax_year},
            {"$set": doc},
            upsert=True
        )
        return rule.rule_id

    def get_rule(self, rule_id: str, tax_year: int) -> Optional[Dict[str, Any]]:
        return self.col.find_one({"rule_id": rule_id, "tax_year": int(tax_year), "status": "active"})

    def list_rules_for_calculation(
        self,
        tax_year: int,
        country: str = "CA",
        province: str = "ON",
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {
            "jurisdiction.country": country,
            "jurisdiction.province": province,
            "tax_year": int(tax_year),
            "status": "active"
        }
        if category:
            query["category"] = category
        return list(self.col.find(query))


class RecommendationRepository(BaseRepository):
    collection_name = "recommendations"

    def save_recommendation(self, user_id: Any, recommendation: RecommendationModel) -> str:
        doc = recommendation.model_dump(by_alias=True, exclude_none=True)
        doc["user_id"] = self.to_object_id(user_id)
        doc["created_at"] = doc.get("created_at") or datetime.utcnow()
        doc["updated_at"] = doc.get("updated_at") or datetime.utcnow()
        if "_id" in doc and doc["_id"] is None:
            del doc["_id"]
        res = self.col.insert_one(doc)
        return str(res.inserted_id)

    def get_latest_recommendations(self, user_id: Any, tax_year: int) -> List[Dict[str, Any]]:
        """Strict server-side tenant isolation: only retrieve user's recommendations."""
        cursor = self.col.find({
            "user_id": self.to_object_id(user_id),
            "tax_year": int(tax_year),
            "status": {"$in": ["proposed", "accepted"]}
        }).sort("created_at", -1)
        return list(cursor)

    def supersede_older_recommendations(self, user_id: Any, tax_year: int, recommendation_type: str):
        self.col.update_many(
            {
                "user_id": self.to_object_id(user_id),
                "tax_year": int(tax_year),
                "recommendation_type": recommendation_type,
                "status": "proposed"
            },
            {
                "$set": {
                    "status": "superseded",
                    "updated_at": datetime.utcnow()
                }
            }
        )


class AuditRepository(BaseRepository):
    collection_name = "audit_logs"

    def log_event(self, audit_log: AuditLogModel) -> str:
        doc = audit_log.model_dump(by_alias=True, exclude_none=True)
        doc["user_id"] = self.to_object_id(doc["user_id"])
        if doc.get("entity_id"):
            doc["entity_id"] = self.to_object_id(doc["entity_id"])
        doc["created_at"] = doc.get("created_at") or datetime.utcnow()
        if "_id" in doc and doc["_id"] is None:
            del doc["_id"]
        res = self.col.insert_one(doc)
        return str(res.inserted_id)

    def get_user_audit_logs(self, user_id: Any, limit: int = 50) -> List[Dict[str, Any]]:
        """Strict tenant isolation: only return audit entries for authenticated user."""
        cursor = self.col.find({
            "user_id": self.to_object_id(user_id)
        }).sort("created_at", -1).limit(limit)
        return list(cursor)


class SessionRepository(BaseRepository):
    collection_name = "agent_sessions"

    def get_session(self, user_id: Any, thread_id: str) -> Optional[Dict[str, Any]]:
        return self.col.find_one({
            "user_id": self.to_object_id(user_id),
            "thread_id": thread_id
        })

    def save_checkpoint(
        self,
        user_id: Any,
        thread_id: str,
        current_node: str,
        checkpoint: Dict[str, Any],
        workflow_status: str = "active",
        idempotency_key: Optional[str] = None
    ) -> str:
        doc = {
            "user_id": self.to_object_id(user_id),
            "thread_id": thread_id,
            "current_node": current_node,
            "checkpoint": checkpoint,
            "workflow_status": workflow_status,
            "updated_at": datetime.utcnow()
        }
        if idempotency_key:
            doc["idempotency_key"] = idempotency_key

        res = self.col.update_one(
            {"user_id": self.to_object_id(user_id), "thread_id": thread_id},
            {
                "$set": doc,
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
        return thread_id
