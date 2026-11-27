"""Geçiş dönemi (ATOP-61): User artık domain'de, tablo eşlemesi persistence adaptöründe.

Eski import'lar bozulmasın diye buradan yeniden dışa aktarılır; ATOP-65'te kaldırılacak.
"""

from app.adapters.outbound.persistence.users import users_table  # noqa: F401  (eşlemeyi yükler)
from app.domain.users import Role, User  # noqa: F401
