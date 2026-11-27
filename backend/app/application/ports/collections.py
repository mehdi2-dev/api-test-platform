"""Koleksiyonlar ve koleksiyon çalıştırmalarıyla ilgili portlar."""

from typing import Protocol

from app.domain.collections import Collection, CollectionRun


class CollectionRepository(Protocol):
    def get(self, collection_id: int) -> Collection | None: ...


class CollectionRunRepository(Protocol):
    def get(self, run_id: int) -> CollectionRun | None: ...

    def save(self, run: CollectionRun) -> None:
        """Ekler veya değişiklikleri kalıcı yapar. Arayüz ilerlemeyi canlı görsün diye
        çalıştırma sırasında her adımdan sonra çağrılır."""
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
