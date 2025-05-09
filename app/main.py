from fastapi import FastAPI
from app.api.SECAPI import app as secapi_app
from app.api.run_pipeline import router as pipeline_router

app = FastAPI(
    title="Your New Multi-Agent API",
    version="0.1.0"
)

# Mount existing SECAPI routes
app.mount("/secapi", secapi_app)

# Include new /run_pipeline route
app.include_router(pipeline_router)

