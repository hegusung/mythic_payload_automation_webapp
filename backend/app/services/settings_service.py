from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.settings import SettingsModel


SETTING_KEYS = ('mythic_url', 'mythic_username', 'mythic_password')


def get_all(db: Session) -> dict[str, str | None]:
    rows = db.query(SettingsModel).filter(SettingsModel.key.in_(SETTING_KEYS)).all()
    result: dict[str, str | None] = {k: None for k in SETTING_KEYS}
    for row in rows:
        result[row.key] = row.value
    return result


def set_all(db: Session, data: dict[str, str | None]) -> None:
    for key, value in data.items():
        if key not in SETTING_KEYS:
            continue
        row = db.get(SettingsModel, key)
        if row is None:
            row = SettingsModel(key=key, value=value)
            db.add(row)
        else:
            row.value = value
    db.commit()
