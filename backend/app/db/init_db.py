import logging
import json
from pathlib import Path
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.database import Database
from backend.app.db.mongo import get_db
from backend.app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# JSON Schema Validators for Critical Collections
SCHEMA_VALIDATORS = {
    "users": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["email", "role", "status", "created_at", "updated_at"],
            "properties": {
                "email": {"bsonType": "string", "pattern": "^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$"},
                "role": {"enum": ["taxpayer", "admin"]},
                "status": {"enum": ["active", "suspended", "deleted"]},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            }
        }
    },
    "tax_profiles": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "jurisdiction", "tax_year", "profile_version", "created_at", "updated_at"],
            "properties": {
                "user_id": {"bsonType": "objectId"},
                "tax_year": {"bsonType": "int", "minimum": 2020, "maximum": 2030},
                "profile_version": {"bsonType": "int", "minimum": 1},
                "jurisdiction": {
                    "bsonType": "object",
                    "required": ["country", "province"],
                    "properties": {
                        "country": {"bsonType": "string"},
                        "province": {"bsonType": "string"}
                    }
                },
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            }
        }
    },
    "agent_memories": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "memory_type", "content", "source", "governance", "created_at", "updated_at"],
            "properties": {
                "user_id": {"bsonType": "objectId"},
                "memory_type": {"bsonType": "string"},
                "content": {"bsonType": "string"},
                "embedding": {"bsonType": ["array", "null"]},
                "source": {
                    "bsonType": "object",
                    "required": ["type", "profile_version"],
                    "properties": {
                        "type": {"bsonType": "string"},
                        "profile_version": {"bsonType": "int"}
                    }
                },
                "governance": {
                    "bsonType": "object",
                    "required": ["status", "confidence", "verification_status"],
                    "properties": {
                        "status": {"enum": ["active", "superseded", "expired", "pending_confirmation", "deleted"]},
                        "confidence": {"bsonType": "double"},
                        "verification_status": {"enum": ["user_confirmed", "unconfirmed", "disputed", "inferred"]}
                    }
                },
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            }
        }
    },
    "tax_rules": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["rule_id", "jurisdiction", "tax_year", "category", "rule_name", "source_url", "source_authority", "verified_at", "status"],
            "properties": {
                "rule_id": {"bsonType": "string"},
                "tax_year": {"bsonType": "int"},
                "category": {"bsonType": "string"},
                "rule_name": {"bsonType": "string"},
                "source_url": {"bsonType": "string"},
                "source_authority": {"bsonType": "string"},
                "status": {"enum": ["active", "outdated", "superseded"]},
                "verified_at": {"bsonType": "date"},
            }
        }
    },
    "audit_logs": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "event_type", "entity_type", "action", "actor", "created_at"],
            "properties": {
                "user_id": {"bsonType": "objectId"},
                "event_type": {"bsonType": "string"},
                "entity_type": {"bsonType": "string"},
                "action": {"bsonType": "string"},
                "actor": {"bsonType": "string"},
                "created_at": {"bsonType": "date"},
            }
        }
    }
}

def init_collections_and_validators(db: Database):
    """Ensure collections exist and apply JSON Schema validators."""
    existing_collections = db.list_collection_names()
    for col_name, validator in SCHEMA_VALIDATORS.items():
        if col_name not in existing_collections:
            logger.info(f"Creating collection '{col_name}' with validator...")
            try:
                db.create_collection(col_name, validator=validator)
            except Exception as e:
                logger.warning(f"Could not create collection with validator: {e}. Creating plain collection.")
                db.create_collection(col_name)
        else:
            logger.info(f"Updating validator on existing collection '{col_name}'...")
            try:
                db.command({
                    "collMod": col_name,
                    "validator": validator,
                    "validationLevel": "moderate"
                })
            except Exception as e:
                logger.warning(f"Could not apply validator on '{col_name}': {e}")

    # Ensure other collections exist
    for other_col in ["recommendations", "agent_sessions"]:
        if other_col not in existing_collections:
            db.create_collection(other_col)

def create_indexes(db: Database):
    """Create all required compound and unique indexes."""
    logger.info("Creating indexes across collections...")

    # users indexes
    db["users"].create_indexes([
        IndexModel([("email", ASCENDING)], unique=True, name="idx_users_email_unique"),
        IndexModel([("status", ASCENDING)], name="idx_users_status")
    ])

    # tax_profiles indexes
    db["tax_profiles"].create_indexes([
        IndexModel([("user_id", ASCENDING), ("tax_year", ASCENDING)], unique=True, name="idx_profiles_user_tax_year_unique"),
        IndexModel([("jurisdiction.country", ASCENDING), ("jurisdiction.province", ASCENDING), ("tax_year", ASCENDING)], name="idx_profiles_jurisdiction_year")
    ])

    # agent_memories indexes
    db["agent_memories"].create_indexes([
        IndexModel([("user_id", ASCENDING), ("governance.status", ASCENDING), ("memory_type", ASCENDING)], name="idx_memories_user_status_type"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_memories_user_created_at")
    ])

    # tax_rules indexes
    db["tax_rules"].create_indexes([
        IndexModel([("rule_id", ASCENDING), ("tax_year", ASCENDING)], unique=True, name="idx_rules_rule_year_unique"),
        IndexModel([("jurisdiction.country", ASCENDING), ("jurisdiction.province", ASCENDING), ("tax_year", ASCENDING), ("category", ASCENDING), ("status", ASCENDING)], name="idx_rules_lookup")
    ])

    # recommendations indexes
    db["recommendations"].create_indexes([
        IndexModel([("user_id", ASCENDING), ("tax_year", ASCENDING), ("created_at", DESCENDING)], name="idx_recommendations_user_year_created"),
        IndexModel([("user_id", ASCENDING), ("status", ASCENDING)], name="idx_recommendations_user_status")
    ])

    # agent_sessions indexes
    db["agent_sessions"].create_indexes([
        IndexModel([("thread_id", ASCENDING)], unique=True, name="idx_sessions_thread_unique"),
        IndexModel([("user_id", ASCENDING), ("updated_at", DESCENDING)], name="idx_sessions_user_updated"),
        IndexModel([("idempotency_key", ASCENDING)], unique=True, sparse=True, name="idx_sessions_idempotency_unique")
    ])

    # audit_logs indexes
    db["audit_logs"].create_indexes([
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_audit_user_created"),
        IndexModel([("entity_type", ASCENDING), ("entity_id", ASCENDING), ("created_at", DESCENDING)], name="idx_audit_entity_created")
    ])
    logger.info("All indexes created successfully.")

def save_vector_search_index_spec():
    """Output the Atlas Vector Search index definition for `agent_memories`."""
    vector_spec = {
        "name": "memory_vector_index",
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": settings.EMBEDDING_DIMENSIONS,
                    "similarity": "cosine"
                },
                {
                    "type": "filter",
                    "path": "user_id"
                },
                {
                    "type": "filter",
                    "path": "memory_type"
                },
                {
                    "type": "filter",
                    "path": "governance.status"
                }
            ]
        }
    }
    out_dir = Path(settings.MONGODB_CERT_PATH).parent / "data" / "seed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "vector_index_definition.json"
    with open(out_file, "w") as f:
        json.dump(vector_spec, f, indent=2)
    logger.info(f"Vector search index definition written to: {out_file}")
    return vector_spec

def initialize_database():
    db = get_db()
    init_collections_and_validators(db)
    create_indexes(db)
    save_vector_search_index_spec()
    print("Database initialization complete.")

if __name__ == "__main__":
    initialize_database()
