"""Geçiş dönemi (ATOP-63): koleksiyon router'ı app.adapters.inbound.http.collections içindedir.

Henüz taşınmamış kod (zamanlamalar, dashboard, demo verileri) ve testler buradaki adları
kullandığı için yeniden dışa aktarılır; ATOP-65'te kaldırılacak.
"""

from sqlalchemy.orm import Session

from app.adapters.inbound.http.collections import (  # noqa: F401
    Enqueuer,
    get_enqueuer,
    import_from_export,
    run_summary_fields,
)
from app.adapters.outbound.persistence.api_definitions import SqlAlchemyApiDefinitionRepository
from app.adapters.outbound.persistence.collections import SqlAlchemyCollectionRepository
from app.adapters.outbound.security.cipher import FernetCipher
from app.application.use_cases.collections import ImportCollection
from app.domain.collections import Collection
from app.schemas.collection import CollectionExport


def create_from_export(
    db: Session, body: CollectionExport, user_id: int | None
) -> tuple[Collection, int]:
    """Dışa aktarılmış JSON'dan API tanımlarını ve koleksiyonu oluşturur (demo verileri için)."""
    use_case = ImportCollection(
        SqlAlchemyCollectionRepository(db), SqlAlchemyApiDefinitionRepository(db), FernetCipher()
    )
    return import_from_export(use_case, body, user_id)
