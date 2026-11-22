"""Koleksiyonlar: API'leri sıralı bir senaryoda birleştirir (ATOP-37..39).

Örnek senaryo:
    1. Giriş yap           -> cevaptaki $.access_token'ı {{token}} olarak al
    2. Kullanıcıları listele (Authorization: Bearer {{token}})
    3. Yeni kullanıcı ekle -> cevaptaki $.id'yi {{user_id}} olarak al
    4. Kullanıcıyı getir   ({{base_url}}/users/{{user_id}})

Her adım bir API tanımına işaret eder; aynı API birden fazla koleksiyonda kullanılabilir.
Cevaptan değişken çıkarma ayarları (extractions) adıma aittir, API tanımına değil.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.api_definition import ApiDefinition
from app.models.environment import Environment
from app.models.test_run import RunStatus


class Collection(TimestampMixin, Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Bir adım geçemezse kalan adımlar çalıştırılmasın mı? (ATOP-39)
    stop_on_failure: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    items: Mapped[list["CollectionItem"]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionItem.position",
        lazy="selectin",
    )


class CollectionItem(Base):
    __tablename__ = "collection_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    api_definition_id: Mapped[int] = mapped_column(
        ForeignKey("api_definitions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # [{"variable": "token", "source": "json_path", "path": "$.access_token", "secret": true}]
    extractions: Mapped[list] = mapped_column(JSON, default=list)

    collection: Mapped[Collection] = relationship(back_populates="items")
    api: Mapped[ApiDefinition | None] = relationship(lazy="selectin")


class RunState(StrEnum):
    """Çalıştırmanın yaşam döngüsü (ATOP-44). Sonuç (passed/failed/error) ayrı: status."""

    QUEUED = "queued"  # kuyruğa alındı, worker henüz başlamadı
    RUNNING = "running"  # adımlar çalışıyor
    COMPLETED = "completed"  # bitti; status alanında sonuç var


class RunTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"


class CollectionRun(Base):
    """Bir koleksiyonun bir kez çalıştırılması. Adımların detayı test_runs tablosunda."""

    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    collection_name: Mapped[str] = mapped_column(String(150))
    environment_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    triggered_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Sonuç; kuyrukta veya çalışırken henüz yok (None)
    status: Mapped[RunStatus | None] = mapped_column(
        Enum(RunStatus, name="run_status", values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        index=True,
    )
    state: Mapped[str] = mapped_column(String(20), default=RunState.COMPLETED.value)
    trigger: Mapped[str] = mapped_column(String(20), default=RunTrigger.MANUAL.value)
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Çalıştırma hiç başlayamadıysa nedeni (kuyruk erişilemedi, ortam silindi...)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    passed_steps: Mapped[int] = mapped_column(Integer, default=0)
    failed_steps: Mapped[int] = mapped_column(Integer, default=0)
    skipped_steps: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0)
    # Adım özetleri: [{"position", "api_name", "status", "test_run_id", "extracted": [...]}]
    steps: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


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
