from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import setup_logging

settings = get_settings()
setup_logging()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(_, exc: AppException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


app.include_router(api_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.APP_NAME}
