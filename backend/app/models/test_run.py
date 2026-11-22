"""Bir API testinin çalıştırılma kaydı (ATOP-35).

Her "Çalıştır" bir satır üretir: hangi API, hangi ortam, kim çalıştırdı, gönderilen istek
(gizli değerler maskeli), gelen cevap, süre ve her kuralın sonucu. Test geçmişi ve
dashboard (Epic 7) bu tablodan beslenecek.

API tanımı silinse bile geçmiş kaybolmasın diye adı ve metodu ayrıca saklanır.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RunStatus(StrEnum):
    PASSED = "passed"  # cevap geldi ve tüm kurallar geçti
    FAILED = "failed"  # cevap geldi ama en az bir kural kaldı
    ERROR = "error"  # cevap hiç alınamadı (bağlantı, zaman aşımı, eksik değişken...)


class ApiTestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    api_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("api_definitions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    api_name: Mapped[str] = mapped_column(String(150))
    method: Mapped[str] = mapped_column(String(10))
    environment_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    triggered_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status", values_callable=lambda e: [i.value for i in e]),
        index=True,
    )
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Gönderilen istek (maskeli), cevap (kısaltılmış) ve kural sonuçları
    request: Mapped[dict] = mapped_column(JSON, default=dict)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assertion_results: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
