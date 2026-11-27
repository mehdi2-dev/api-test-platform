"""Geçiş dönemi (ATOP-62): API tanımı router'ı app.adapters.inbound.http.apis içindedir.

Henüz taşınmamış router'lar ve testler buradaki adları kullandığı için yeniden dışa
aktarılır; ATOP-65'te kaldırılacak.
"""

from app.adapters.inbound.http.apis import (  # noqa: F401
    PRODUCTION_CONFIRMATION,
    HttpTransport,
    get_http_transport,
)
