"""Geçiş dönemi (ATOP-63): ApiTestRun artık domain'de, eşlemesi persistence adaptöründe.

Eski import'lar bozulmasın diye buradan yeniden dışa aktarılır; ATOP-65'te kaldırılacak.
"""

from app.adapters.outbound.persistence.test_runs import test_runs_table  # noqa: F401
from app.domain.testing.runs import ApiTestRun, RunStatus  # noqa: F401
