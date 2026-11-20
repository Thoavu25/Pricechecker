from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.errors import register_error_handlers
from app.api.routers import admin, auth, prices, stores
from app.infrastructure.database import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Simplified Price Checker Backend Service API",
    version="1.0.0",
    lifespan=lifespan,
)
register_error_handlers(app)
logger = logging.getLogger("price_checker")


@app.middleware("http")
async def log_api_errors(request, call_next):
    response = await call_next(request)
    if response.status_code >= 400:
        logger.warning(
            "API response error user_id=%s time=%s method=%s path=%s status=%s",
            getattr(request.state, "user_id", "anonymous"),
            datetime.now(timezone.utc).isoformat(),
            request.method,
            request.url.path,
            response.status_code,
        )
    return response


app.include_router(auth.router, prefix="/api/v1")
app.include_router(prices.router, prefix="/api/v1")
app.include_router(stores.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).parent / "frontend" / "index.html")
