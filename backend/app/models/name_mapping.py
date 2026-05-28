from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NameMapping(Base):
    """研发叫法与系统物料命名对照。"""

    __tablename__ = "name_mapping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    system_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    system_name: Mapped[str] = mapped_column(String(255), nullable=False)
    spec: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
