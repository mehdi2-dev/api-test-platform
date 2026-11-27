"""Geçiş dönemi (ATOP-61): henüz taşınmamış router'lar için yeni HTTP bağımlılıkları.

Asıl kod app.adapters.inbound.http.dependencies içindedir; ATOP-65'te bu dosya kaldırılacak.
"""

from app.adapters.inbound.http.dependencies import (  # noqa: F401
    CurrentUser,
    DbSession,
    bearer_scheme,
    get_current_user,
    require_roles,
)
