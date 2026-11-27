"""Geçiş dönemi (ATOP-64): NotificationChannel artık domain'de, eşlemesi persistence
adaptöründe. Eski import'lar bozulmasın diye buradan yeniden dışa aktarılır.
"""

from app.adapters.outbound.persistence.notifications import (  # noqa: F401  (eşlemeyi yükler)
    notification_channels_table,
)
from app.domain.notifications import NotificationChannel  # noqa: F401
