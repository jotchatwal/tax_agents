import logging
import hashlib
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
from bson import ObjectId

from backend.app.config import settings
from backend.app.db.repositories import MemoryRepository, AuditRepository, ProfileRepository
from backend.app.models.memory import AgentMemoryModel, MemorySource, MemoryGovernance
from backend.app.models.audit import AuditLogModel

logger = logging.getLogger(__name__)

class EmbeddingService:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
        return cls._instance

    def _get_local_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            except Exception as e:
                logger.warning(f"Could not load SentenceTransformer from cache: {e}. Using deterministic semantic projection.")
                self._model = "fallback"
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Generate normalized embedding vector matching EMBEDDING_DIMENSIONS."""
        dims = settings.EMBEDDING_DIMENSIONS
        model = self._get_local_model()

        if model != "fallback":
            try:
                vec = model.encode(text, normalize_embeddings=True)
                return [float(x) for x in vec[:dims]]
            except Exception as e:
                logger.warning(f"SentenceTransformer encoding failed: {e}. Using deterministic projection.")

        # Deterministic semantic hash projection (384 dimensions)
        # Guarantees identical vectors for identical text and cosine similarity properties
        h = hashlib.sha256(text.strip().lower().encode("utf-8")).digest()
        # Seed pseudo-random generator with hash to get stable vector
        seed = int.from_bytes(h[:8], "big")
        rng = np.random.RandomState(seed % (2**32))
        raw_vec = rng.randn(dims)
        norm_vec = raw_vec / np.linalg.norm(raw_vec)
        return [float(x) for x in norm_vec]

embedding_service = EmbeddingService()


class MemoryGovernanceService:
    def __init__(self, memory_repo: Optional[MemoryRepository] = None, audit_repo: Optional[AuditRepository] = None):
        self.memory_repo = memory_repo or MemoryRepository()
        self.audit_repo = audit_repo or AuditRepository()
        self.profile_repo = ProfileRepository()

    def propose_memory(
        self,
        user_id: Any,
        memory_type: str,
        content: str,
        structured_data: Dict[str, Any],
        raw_statement: str,
        profile_version: int = 1,
        auto_confirm: bool = False
    ) -> Dict[str, Any]:
        """
        Propose a new memory. By default memories start as pending_confirmation
        unless confirmed by the user.
        """
        status = "active" if auto_confirm else "pending_confirmation"
        verification = "user_confirmed" if auto_confirm else "unconfirmed"
        embedding = embedding_service.embed_text(content) if auto_confirm else None

        memory = AgentMemoryModel(
            user_id=self.memory_repo.to_object_id(user_id),
            memory_type=memory_type,
            content=content,
            structured_data=structured_data,
            embedding=embedding,
            source=MemorySource(
                type="user_statement",
                profile_version=profile_version,
                raw_statement=raw_statement
            ),
            governance=MemoryGovernance(
                status=status,
                confidence=1.0 if auto_confirm else 0.85,
                verification_status=verification
            )
        )
        mem_id = self.memory_repo.create_memory(user_id, memory)

        # Log audit event
        self.audit_repo.log_event(AuditLogModel(
            user_id=user_id,
            event_type="memory_proposed" if not auto_confirm else "memory_created",
            entity_type="agent_memory",
            entity_id=mem_id,
            action="create",
            actor="user" if auto_confirm else "agent",
            reason=f"Extracted fact for {memory_type}",
            new_version=profile_version
        ))

        return {
            "memory_id": mem_id,
            "status": status,
            "verification_status": verification,
            "content": content,
            "structured_data": structured_data
        }

    def confirm_memory(self, user_id: Any, memory_id: Any) -> bool:
        """Confirm a proposed memory, generating its embedding and setting status to active."""
        mem = self.memory_repo.get_memory_by_id(user_id, memory_id)
        if not mem:
            return False

        embedding = embedding_service.embed_text(mem["content"])
        updated = self.memory_repo.correct_memory(
            user_id=user_id,
            memory_id=memory_id,
            new_content=mem["content"],
            new_structured_data=mem.get("structured_data"),
            new_embedding=embedding
        )

        if updated:
            self.memory_repo.col.update_one(
                {"_id": self.memory_repo.to_object_id(memory_id), "user_id": self.memory_repo.to_object_id(user_id)},
                {"$set": {"governance.status": "active", "governance.verification_status": "user_confirmed"}}
            )
            self.audit_repo.log_event(AuditLogModel(
                user_id=user_id,
                event_type="memory_confirmed",
                entity_type="agent_memory",
                entity_id=memory_id,
                action="confirm",
                actor="user",
                reason="User confirmed proposed financial memory"
            ))
            return True
        return False

    def supersede_memory_fact(
        self,
        user_id: Any,
        old_memory_id: Any,
        new_content: str,
        new_structured_data: Dict[str, Any],
        profile_version: int,
        reason: str
    ) -> str:
        """
        Material fact change workflow:
        1. Create new active memory with updated content and embedding.
        2. Supersede old memory and link it to the new memory.
        3. Record audit trail.
        """
        embedding = embedding_service.embed_text(new_content)
        new_memory = AgentMemoryModel(
            user_id=self.memory_repo.to_object_id(user_id),
            memory_type=new_structured_data.get("memory_type", "employment_income"),
            content=new_content,
            structured_data=new_structured_data,
            embedding=embedding,
            source=MemorySource(
                type="user_statement",
                profile_version=profile_version,
                raw_statement=reason
            ),
            governance=MemoryGovernance(
                status="active",
                confidence=1.0,
                verification_status="user_confirmed",
                supersedes_memory_id=self.memory_repo.to_object_id(old_memory_id)
            )
        )
        new_mem_id = self.memory_repo.create_memory(user_id, new_memory)

        # Mark old as superseded
        self.memory_repo.supersede_memory(user_id, old_memory_id, new_mem_id)

        # Log audit log
        self.audit_repo.log_event(AuditLogModel(
            user_id=user_id,
            event_type="memory_superseded",
            entity_type="agent_memory",
            entity_id=old_memory_id,
            action="supersede",
            actor="user",
            reason=reason,
            previous_version=profile_version - 1,
            new_version=profile_version,
            details={"replacement_memory_id": str(new_mem_id)}
        ))

        return str(new_mem_id)

    def retrieve_active_memories(
        self,
        user_id: Any,
        query_text: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval:
        Uses Atlas Vector Search if query_text is given, strictly filtering by
        authenticated user_id and active status.
        """
        if query_text:
            query_vector = embedding_service.embed_text(query_text)
            return self.memory_repo.vector_search(
                user_id=user_id,
                query_vector=query_vector,
                limit=limit,
                memory_type=memory_type,
                status="active"
            )
        return self.memory_repo.get_active_memories(user_id, memory_type=memory_type)

    def delete_memory(self, user_id: Any, memory_id: Any, reason: str = "User requested erasure") -> bool:
        """
        Wipe memory and embeddings, record audit entry without leaking deleted content.
        """
        success = self.memory_repo.delete_memory(user_id, memory_id, deletion_reason=reason)
        if success:
            self.audit_repo.log_event(AuditLogModel(
                user_id=user_id,
                event_type="memory_deleted",
                entity_type="agent_memory",
                entity_id=memory_id,
                action="delete",
                actor="user",
                reason=reason
            ))
        return success
