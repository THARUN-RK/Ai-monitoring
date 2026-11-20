import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from .config import settings
from .database import Base, engine, SessionLocal
from .routes import router

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("secure_aiops")

app = FastAPI(title=settings.app_name, version="0.2.0",
              description="Privacy-conscious, tenant-scoped infrastructure telemetry API")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_credentials=True, allow_methods=["GET","POST"], allow_headers=["Authorization","Content-Type"])
app.include_router(router)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    logger.info("database_initialized")

@app.get("/")
def root():
    return {"service": settings.app_name, "docs": "/docs"}

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
