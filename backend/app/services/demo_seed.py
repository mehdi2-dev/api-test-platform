"""Demo verilerini yükleme (ATOP-52..55).

- "Demo" ortamı: base_url (demo servisinin adresi), demo_user, demo_password (gizli)
- backend/examples/*.json içindeki örnek koleksiyonlar

İki kez çalıştırılırsa var olanlara dokunmaz.

    Arayüz:  Koleksiyonlar > "Örnekleri yükle" (Admin)
    Komut:   docker compose exec backend python -m app.cli seed-demo
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import encrypt_text
from app.models.collection import Collection
from app.models.environment import Environment, EnvironmentVariable
from app.schemas.collection import CollectionExport, DemoSeedResult, SeededCollection

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
DEMO_ENVIRONMENT = "Demo"


def _ensure_environment(db: Session) -> tuple[Environment, bool]:
    environment = db.scalar(select(Environment).where(Environment.name == DEMO_ENVIRONMENT))
    if environment is not None:
        return environment, False
    environment = Environment(
        name=DEMO_ENVIRONMENT,
        description="Demo CRM servisi (örnek senaryolar için)",
        is_production=False,
        variables=[
            EnvironmentVariable(key="base_url", value=settings.demo_base_url, is_secret=False),
            EnvironmentVariable(key="demo_user", value="demo", is_secret=False),
            EnvironmentVariable(key="demo_password", value=encrypt_text("demo123"), is_secret=True),
        ],
    )
    db.add(environment)
    db.commit()
    db.refresh(environment)
    return environment, True


def example_files() -> list[Path]:
    return sorted(EXAMPLES_DIR.glob("*.json"))


def seed_demo(db: Session, user_id: int | None) -> DemoSeedResult:
    from app.api.collections import create_from_export

    environment, environment_created = _ensure_environment(db)
    collections: list[SeededCollection] = []
    for path in example_files():
        data = CollectionExport.model_validate_json(path.read_text(encoding="utf-8"))
        existing = db.scalar(select(Collection).where(Collection.name == data.name))
        if existing is not None:
            collections.append(SeededCollection(id=existing.id, name=existing.name, created=False))
            continue
        collection, _ = create_from_export(db, data, user_id)
        collections.append(SeededCollection(id=collection.id, name=collection.name, created=True))
    return DemoSeedResult(
        environment_id=environment.id,
        environment_created=environment_created,
        collections=collections,
    )
