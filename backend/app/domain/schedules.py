"""Zamanlama planı: bir koleksiyonun cron ifadesiyle düzenli çalıştırılması.

Zamanlayıcı her dakika next_run_at'i gelmiş etkin planları bulur, bir koleksiyon
çalıştırması oluşturup kuyruğa atar ve next_run_at'i bir sonraki zamana ilerletir.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain import cron
from app.domain.collections import Collection
from app.domain.environments import Environment
from app.domain.errors import InvalidInput


def next_run(cron_text: str, after: datetime, timezone: str) -> datetime:
    """Cron ifadesine göre 'after'dan sonraki ilk çalışma zamanı (UTC)."""
    return cron.next_after(cron.parse(cron_text), after, timezone)


@dataclass(eq=False, kw_only=True)
class Schedule:
    """`collection` ve `environment` ilişkileri tablo eşlemesinde tanımlanır; burada alan
    olarak yazılmaz, çünkü yeni planda None atanırsa foreign key'leri boşaltırlar."""

    collection_id: int
    cron: str
    environment_id: int | None = None
    enabled: bool = True
    # Production ortamında veri değiştiren adımları çalıştırmaya önceden verilmiş onay
    confirm_production: bool = False
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_id: int | None = None
    created_by_id: int | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def schedule_next(self, now: datetime, timezone: str) -> None:
        """Pasif planın sonraki çalışma zamanı yoktur."""
        self.next_run_at = next_run(self.cron, now, timezone) if self.enabled else None

    @staticmethod
    def ensure_production_confirmed(
        collection: Collection, environment: Environment | None, confirmed: bool
    ) -> None:
        """Production'da veri değiştiren adımları içeren plan açık onay ister.

        Plan sonradan, kimse başındayken çalışmayacağı için onay plan kurulurken alınır.
        """
        if environment is None or not environment.is_production or confirmed:
            return
        risky = collection.risky_steps()
        if risky:
            raise InvalidInput(
                f"'{environment.name}' Production ortamı ve koleksiyonda veri değiştiren "
                f"adımlar var ({', '.join(risky)}). Planlamak için Production onayını işaretleyin."
            )
