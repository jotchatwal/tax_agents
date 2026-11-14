from typing import Any
from datetime import date, datetime
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema
from bson import ObjectId

class PyObjectId(str):
    """Custom type for MongoDB ObjectId handling with Pydantic v2."""
    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls.validate),
                ]),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x)
            ),
        )

    @classmethod
    def validate(cls, v: Any) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str) and ObjectId.is_valid(v):
            return ObjectId(v)
        raise ValueError(f"Invalid ObjectId: {v}")

def serialize_mongo(obj: Any) -> Any:
    """Recursively convert ObjectIds and datetimes to JSON-safe primitives."""
    if isinstance(obj, dict):
        return {k: serialize_mongo(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [serialize_mongo(item) for item in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj

