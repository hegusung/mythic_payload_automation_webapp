from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, LargeBinary, String
from app.db.database import Base


class FileCache(Base):
    __tablename__ = "file_cache"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    mythic_file_uuid = Column(String, index=True, nullable=True)  # NULL until deployed to Mythic
    sha256 = Column(String, index=True, nullable=True)  # SHA-256 hex digest for deduplication
    content = Column(LargeBinary, nullable=False)
    size = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
