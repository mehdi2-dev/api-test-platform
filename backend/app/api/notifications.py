"""Bildirim kanalları yönetimi (ATOP-48).

Yetkiler: kanalları sadece Admin yönetir; Tester listeyi görebilir. Webhook adresleri
şifreli saklanır ve cevaplarda gizlenmiş hali (target_preview) döner.
"""

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.apis import HttpTransport
from app.api.deps import DbSession, require_roles
from app.core.crypto import decrypt_text, encrypt_text
from app.models.notification import NotificationChannel
from app.models.user import Role, User
from app.schemas.notification import (
    ChannelCreate,
    ChannelRead,
    ChannelTestResult,
    ChannelUpdate,
    check_target,
)
from app.services.notifications import sample_notification, send_to_channel

router = APIRouter(
    prefix="/notifications",
    tags=["Bildirimler"],
    responses={401: {"description": "Giriş yapılmamış"}},
)

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
Reader = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TESTER))]
NOT_FOUND = {404: {"description": "Kanal bulunamadı"}}
FORBIDDEN = {403: {"description": "Sadece Admin"}}


def _preview(channel_type: str, target: str) -> str:
    if channel_type == "email":
        return target
    parts = urlsplit(target)
    return f"{parts.scheme}://{parts.netloc}/****"


def _to_read(channel: NotificationChannel) -> ChannelRead:
    try:
        preview = _preview(channel.type, decrypt_text(channel.target_encrypted))
    except ValueError:
        preview = "(çözülemedi)"
    return ChannelRead(
        id=channel.id,
        name=channel.name,
        type=channel.type,
        target_preview=preview,
        enabled=channel.enabled,
        notify_on=channel.notify_on,
        last_sent_at=channel.last_sent_at,
        last_status=channel.last_status,
        last_error=channel.last_error,
        created_at=channel.created_at,
    )


def _get_or_404(db: DbSession, channel_id: int) -> NotificationChannel:
    channel = db.get(NotificationChannel, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kanal bulunamadı")
    return channel


@router.get("", response_model=list[ChannelRead], summary="Bildirim kanalları")
def list_channels(_: Reader, db: DbSession) -> list[ChannelRead]:
    query = select(NotificationChannel).order_by(NotificationChannel.name)
    return [_to_read(channel) for channel in db.scalars(query)]


@router.post(
    "",
    response_model=ChannelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni bildirim kanalı",
    responses=FORBIDDEN,
)
def create_channel(body: ChannelCreate, _: Admin, db: DbSession) -> ChannelRead:
    channel = NotificationChannel(
        name=body.name,
        type=body.type,
        target_encrypted=encrypt_text(body.target),
        enabled=body.enabled,
        notify_on=body.notify_on,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _to_read(channel)


@router.patch(
    "/{channel_id}",
    response_model=ChannelRead,
    summary="Kanalı güncelle",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def update_channel(channel_id: int, body: ChannelUpdate, _: Admin, db: DbSession) -> ChannelRead:
    channel = _get_or_404(db, channel_id)
    if body.name is not None:
        channel.name = body.name.strip()
    if body.target is not None:
        try:
            target = check_target(channel.type, body.target)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        channel.target_encrypted = encrypt_text(target)
    if body.enabled is not None:
        channel.enabled = body.enabled
    if body.notify_on is not None:
        channel.notify_on = body.notify_on
    db.commit()
    db.refresh(channel)
    return _to_read(channel)


@router.delete(
    "/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Kanalı sil",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_channel(channel_id: int, _: Admin, db: DbSession) -> None:
    db.delete(_get_or_404(db, channel_id))
    db.commit()


@router.post(
    "/{channel_id}/test",
    response_model=ChannelTestResult,
    summary="Deneme bildirimi gönder",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def send_test(
    channel_id: int, _: Admin, db: DbSession, transport: HttpTransport
) -> ChannelTestResult:
    channel = _get_or_404(db, channel_id)
    ok = send_to_channel(db, channel, sample_notification(), transport)
    return ChannelTestResult(ok=ok, error=None if ok else channel.last_error)
