from sqlalchemy import Column, String, Text

from app.db.database import Base


class SettingsModel(Base):
    __tablename__ = 'settings'

    key = Column(String(255), primary_key=True, nullable=False)
    value = Column(Text, nullable=True)
