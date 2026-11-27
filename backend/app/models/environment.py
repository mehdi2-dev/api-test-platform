"""Geçiş dönemi (ATOP-62): Environment artık domain'de, tablo eşlemesi persistence adaptöründe.

Eski import'lar bozulmasın diye buradan yeniden dışa aktarılır; ATOP-65'te kaldırılacak.
"""

from app.adapters.outbound.persistence.environments import (  # noqa: F401  (eşlemeyi yükler)
    environments_table,
)
from app.domain.environments import Environment, EnvironmentVariable  # noqa: F401
