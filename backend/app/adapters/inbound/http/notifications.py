"""Giren adaptör: bildirim kanalları yönetimi.

Yetkiler: kanalları sadece Admin yönetir; Tester listeyi görebilir. Webhook adresleri
şifreli saklanır ve cevaplarda gizlenmiş hali (target_preview) döner.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.adapters.inbound.http.apis import HttpTransport
from app.adapters.inbound.http.dependencies import (
    Channels,
    CipherDep,
    ClockDep,
    require_roles,
)
from app.adapters.outbound.notifications.senders import ChannelSender
from app.application.ports.security import Cipher
from app.application.use_cases.notifications import (
    CreateChannel,
    DeleteChannel,
    ListChannels,
    SendTestNotification,
    UpdateChannel,
)
from app.domain.notifications import NotificationChannel
from app.domain.users import Role, User
from app.schemas.notification import ChannelCreate, ChannelRead, ChannelTestResult, ChannelUpdate

router = APIRouter(
    prefix="/notifications",
    tags=["Bildirimler"],
    responses={401: {"description": "Giriş yapılmamış"}},
)

Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
Reader = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TESTER))]
NOT_FOUND = {404: {"description": "Kanal bulunamadı"}}
FORBIDDEN = {403: {"description": "Sadece Admin"}}


def get_list(channels: Channels) -> ListChannels:
    return ListChannels(channels)


def get_create(channels: Channels, cipher: CipherDep) -> CreateChannel:
    return CreateChannel(channels, cipher)


def get_update(channels: Channels, cipher: CipherDep) -> UpdateChannel:
    return UpdateChannel(channels, cipher)


def get_delete(channels: Channels) -> DeleteChannel:
    return DeleteChannel(channels)


def get_send_test(
    channels: Channels, cipher: CipherDep, clock: ClockDep, transport: HttpTransport
) -> SendTestNotification:
    return SendTestNotification(channels, cipher, ChannelSender(transport), clock)


def _to_read(channel: NotificationChannel, cipher: Cipher) -> ChannelRead:
    return ChannelRead(
        id=channel.id,
        name=channel.name,
        type=channel.type,
        target_preview=channel.target_preview(cipher.decrypt),
        enabled=channel.enabled,
        notify_on=channel.notify_on,
        last_sent_at=channel.last_sent_at,
        last_status=channel.last_status,
        last_error=channel.last_error,
        created_at=channel.created_at,
    )


@router.get("", response_model=list[ChannelRead], summary="Bildirim kanalları")
def list_channels(
    _: Reader, cipher: CipherDep, use_case: Annotated[ListChannels, Depends(get_list)]
) -> list[ChannelRead]:
    return [_to_read(channel, cipher) for channel in use_case()]


@router.post(
    "",
    response_model=ChannelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni bildirim kanalı",
    responses=FORBIDDEN,
)
def create_channel(
    body: ChannelCreate,
    _: Admin,
    cipher: CipherDep,
    use_case: Annotated[CreateChannel, Depends(get_create)],
) -> ChannelRead:
    channel = use_case(
        name=body.name,
        channel_type=body.type,
        target=body.target,
        enabled=body.enabled,
        notify_on=body.notify_on,
    )
    return _to_read(channel, cipher)


@router.patch(
    "/{channel_id}",
    response_model=ChannelRead,
    summary="Kanalı güncelle",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def update_channel(
    channel_id: int,
    body: ChannelUpdate,
    _: Admin,
    cipher: CipherDep,
    use_case: Annotated[UpdateChannel, Depends(get_update)],
) -> ChannelRead:
    channel = use_case(
        channel_id,
        name=body.name,
        target=body.target,
        enabled=body.enabled,
        notify_on=body.notify_on,
    )
    return _to_read(channel, cipher)


@router.delete(
    "/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Kanalı sil",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_channel(
    channel_id: int, _: Admin, use_case: Annotated[DeleteChannel, Depends(get_delete)]
) -> None:
    use_case(channel_id)


@router.post(
    "/{channel_id}/test",
    response_model=ChannelTestResult,
    summary="Deneme bildirimi gönder",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def send_test(
    channel_id: int,
    _: Admin,
    use_case: Annotated[SendTestNotification, Depends(get_send_test)],
) -> ChannelTestResult:
    result = use_case(channel_id)
    return ChannelTestResult(ok=result.ok, error=result.error)
