from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.db.database import Base, engine
# Import models to ensure they're registered
import app.models.chain  # noqa: F401
import app.models.settings  # noqa: F401
import app.models.file_cache  # noqa: F401

Base.metadata.create_all(bind=engine)

# Runtime migrations — add columns that didn't exist in older DB versions
from sqlalchemy import text as _text
with engine.connect() as _conn:
    for _stmt in [
        'ALTER TABLE chains ADD COLUMN mythic_tag VARCHAR(255)',
        'ALTER TABLE file_cache ADD COLUMN sha256 VARCHAR(64)',
        'ALTER TABLE chains ADD COLUMN variables TEXT',
    ]:
        try:
            _conn.execute(_text(_stmt))
            _conn.commit()
        except Exception:
            pass  # Column already exists

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(router, prefix=settings.api_prefix)
