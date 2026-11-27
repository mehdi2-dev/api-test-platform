"""Geçiş dönemi (ATOP-62): ApiDefinition artık domain'de, eşlemesi persistence adaptöründe.

Eski import'lar bozulmasın diye buradan yeniden dışa aktarılır; ATOP-65'te kaldırılacak.
"""

from app.adapters.outbound.persistence.api_definitions import (  # noqa: F401  (eşlemeyi yükler)
    api_definitions_table,
)
from app.domain.api_definitions import (  # noqa: F401
    ApiDefinition,
    AuthType,
    BodyType,
    HttpMethod,
)
