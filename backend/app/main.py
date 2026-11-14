import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.config import settings
from backend.app.api.endpoints import router as api_router
from backend.app.db.mongo import mongodb

app = FastAPI(
    title="TaxPilot AI - Memory You Can Govern",
    description="A personalized, memory-governed Canadian tax-planning companion backed by MongoDB Atlas.",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router)

# Mount static dashboard directory
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/health")
def health_check():
    """System health check & MongoDB Atlas connectivity verification."""
    try:
        db = mongodb.get_database()
        cols = db.list_collection_names()
        return {
            "status": "healthy",
            "database": settings.MONGODB_DATABASE,
            "connected": True,
            "collections_count": len(cols)
        }
    except Exception as e:
        return {
            "status": "degraded",
            "database": settings.MONGODB_DATABASE,
            "connected": False,
            "error": str(e)
        }

@app.get("/")
def serve_index():
    """Serve the hybrid conversational and governance dashboard."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "TaxPilot AI API is running. Open /docs for Swagger API documentation."}

@app.on_event("shutdown")
def on_shutdown():
    mongodb.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main.py:app", host="0.0.0.0", port=8000, reload=True)
