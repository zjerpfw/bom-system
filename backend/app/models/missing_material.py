from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MissingMaterial(Base):
    """AI匹配失败后的缺失物料队列。"""

    __tablename__ = "missing_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    ai_suggested_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_suggested_spec: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_suggested_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_suggested_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
