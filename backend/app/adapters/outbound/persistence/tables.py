"""Tüm tablo eşlemelerini yükler; Alembic autogenerate ve uygulama bu modülü içe aktarır.

Domain sınıfları ORM bilmez: hangi sınıfın hangi tabloya yazıldığı aşağıdaki modüllerde
(imperative mapping) tanımlıdır. Yeni bir tablo eklediğinizde buraya da ekleyin.
"""

from app.adapters.outbound.persistence import (  # noqa: F401
    api_definitions,
    app_info,
    collections,
    environments,
    notifications,
    schedules,
    test_runs,
    users,
)
from app.adapters.outbound.persistence.base import Base  # noqa: F401
