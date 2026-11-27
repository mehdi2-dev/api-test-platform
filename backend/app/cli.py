"""Yönetim komutları.

docker compose exec backend python -m app.cli generate-key     yeni şifreleme anahtarı üret
docker compose exec backend python -m app.cli rotate-keys      gizli verileri yeni anahtarla şifrele
docker compose exec backend python -m app.cli check            güvenlik ayarlarını kontrol et
docker compose exec backend python -m app.cli seed-demo        demo ortamı + örnek koleksiyonlar
"""

import argparse
import sys

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.outbound.security.crypto import rotate_text
from app.core.config import settings


def rotate_all(db: Session) -> dict[str, int]:
    """Şifreli tüm alanları güncel ENCRYPTION_KEY ile yeniden şifreler (ATOP-49)."""
    from app.domain.api_definitions import ApiDefinition
    from app.domain.environments import EnvironmentVariable
    from app.domain.notifications import NotificationChannel

    counts = {"api_auth": 0, "environment_secrets": 0, "notification_targets": 0}
    for api in db.scalars(
        select(ApiDefinition).where(ApiDefinition.auth_config_encrypted.is_not(None))
    ):
        api.auth_config_encrypted = rotate_text(api.auth_config_encrypted)
        counts["api_auth"] += 1
    for variable in db.scalars(
        select(EnvironmentVariable).where(EnvironmentVariable.is_secret.is_(True))
    ):
        if variable.value:
            variable.value = rotate_text(variable.value)
            counts["environment_secrets"] += 1
    for channel in db.scalars(select(NotificationChannel)):
        channel.target_encrypted = rotate_text(channel.target_encrypted)
        counts["notification_targets"] += 1
    db.commit()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("generate-key", help="Yeni ENCRYPTION_KEY üret")
    command.add_parser("rotate-keys", help="Gizli verileri güncel anahtarla yeniden şifrele")
    command.add_parser("check", help="Güvenlik ayarlarını kontrol et")
    command.add_parser("seed-demo", help="Demo ortamını ve örnek koleksiyonları yükle")
    args = parser.parse_args(argv)

    if args.command == "generate-key":
        print(Fernet.generate_key().decode())
        return 0

    if args.command == "check":
        warnings = settings.security_warnings()
        for warning in warnings:
            print(f"UYARI: {warning}")
        print("Güvenlik ayarları tamam." if not warnings else f"{len(warnings)} uyarı var.")
        return 1 if warnings and settings.environment == "production" else 0

    from app.adapters.outbound.persistence.session import SessionLocal

    if args.command == "seed-demo":
        from app.adapters.inbound.demo_seed import seed_demo

        with SessionLocal() as db:
            result = seed_demo(db, None)
        state = "oluşturuldu" if result.environment_created else "zaten vardı"
        print(f"Demo ortamı {state}.")
        for item in result.collections:
            print(f"  - {item.name}: {'yüklendi' if item.created else 'zaten vardı'}")
        return 0

    with SessionLocal() as db:
        counts = rotate_all(db)
    print(
        "Yeniden şifrelendi: "
        f"{counts['api_auth']} API kimlik bilgisi, "
        f"{counts['environment_secrets']} gizli ortam değişkeni, "
        f"{counts['notification_targets']} bildirim adresi. "
        "Artık ENCRYPTION_KEY_PREVIOUS'ı boşaltabilirsiniz."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
