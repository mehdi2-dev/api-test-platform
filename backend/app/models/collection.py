"""Geçiş dönemi (ATOP-63): koleksiyonlar ve çalıştırmaları domain'de, eşlemeleri persistence
adaptöründe. Eski import'lar bozulmasın diye buradan yeniden dışa aktarılır.

Zamanlama planı (Schedule) henüz burada; ATOP-63'ün zamanlama adımında taşınacak.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.outbound.persistence.collections import (  # noqa: F401  (eşlemeyi yükler)
    collections_table,
)
from app.db.base import Base, TimestampMixin
from app.domain.collections import (  # noqa: F401
    Collection,
    CollectionItem,
    CollectionRun,
    RunState,
    RunTrigger,
)
from app.models.environment import Environment


class Schedule(TimestampMixin, Base):
    """Bir koleksiyonun cron ifadesiyle düzenli çalıştırılması (ATOP-42, ATOP-43).

    Celery Beat her dakika next_run_at'i gelmiş etkin planları bulur, bir CollectionRun
    oluşturup kuyruğa atar ve next_run_at'i bir sonraki zamana ilerletir.
    """

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    cron: Mapped[str] = mapped_column(String(100))
    environment_id: Mapped[int | None] = mapped_column(
        ForeignKey("environments.id", ondelete="SET NULL"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Production ortamında veri değiştiren adımları çalıştırmaya önceden verilmiş onay
    confirm_production: Mapped[bool] = mapped_column(Boolean, default=False)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    collection: Mapped[Collection] = relationship(lazy="selectin")
    environment: Mapped[Environment | None] = relationship(lazy="selectin")
