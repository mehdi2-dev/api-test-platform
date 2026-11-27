"""Koleksiyonlar ve koleksiyon çalıştırmalarıyla ilgili portlar."""

from typing import Protocol

from app.domain.collections import Collection, CollectionRun


class CollectionRepository(Protocol):
    def get(self, collection_id: int) -> Collection | None: ...

    def get_by_name(self, name: str) -> Collection | None: ...

    def list_all(self) -> list[Collection]:
        """Ada göre sıralı."""
        ...

    def save(self, collection: Collection) -> None:
        """Ekler veya değişiklikleri (adımlar dahil) kalıcı yapar."""
        ...

    def delete(self, collection: Collection) -> None: ...


class CollectionRunRepository(Protocol):
    def get(self, run_id: int) -> CollectionRun | None: ...

    def save(self, run: CollectionRun) -> None:
        """Ekler veya değişiklikleri kalıcı yapar. Arayüz ilerlemeyi canlı görsün diye
        çalıştırma sırasında her adımdan sonra çağrılır."""
        ...

    def latest_for(self, collection_id: int) -> CollectionRun | None:
        """Koleksiyonun en son çalıştırması."""
        ...

    def recent_for(self, collection_id: int, limit: int) -> list[CollectionRun]:
        """Koleksiyonun son çalıştırmaları, en yeni önce."""
        ...

    def discard_changes(self) -> None:
        """Beklenmeyen bir hatadan sonra yarım kalan, kaydedilmemiş değişiklikleri atar."""
        ...


class RunNotifier(Protocol):
    def notify(self, run: CollectionRun) -> None:
        """Biten çalıştırma için bildirim gönderir (Slack, Teams, e-posta...).

        Bildirimdeki bir sorun çalıştırmanın sonucunu bozmamalı: hata fırlatmaz.
        """
        ...


class RunQueue(Protocol):
    def enqueue(self, run_id: int, environment_id: int | None, confirm_production: bool) -> None:
        """Çalıştırmayı arka planda yürütülmek üzere kuyruğa atar; olmazsa hata fırlatır."""
        ...
