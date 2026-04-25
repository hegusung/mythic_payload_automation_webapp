from datetime import datetime, UTC

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.database import Base


class ChainModel(Base):
    __tablename__ = 'chains'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    yaml_content = Column(Text, nullable=False)
    graph_json = Column(Text, nullable=False)
    mythic_tag = Column(String(255), nullable=True)
    variables = Column(Text, nullable=True)  # JSON dict of {name: value}
    created_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), onupdate=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False)
