"""Ortamlar (Dev, Stage, Prod...) ve ortam değişkenleri.

Aynı API tanımı farklı ortamlarda çalıştırılabilir: URL'de {{base_url}} yazılır,
hangi ortam seçilirse onun base_url değeri kullanılır.

Gizli (is_secret) değişkenlerin değeri şifreli saklanır. Şifrelemeyi domain yapmaz;
use case, Cipher portunun encrypt/decrypt fonksiyonlarını verir.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.errors import InvalidInput, SecretUnreadable
from app.domain.secrets import MASK


@dataclass(frozen=True)
class VariableInput:
    """Kullanıcının gönderdiği değişken (gizliyse düz metin ya da MASK)."""

    key: str
    value: str = ""
    is_secret: bool = False


@dataclass(eq=False, kw_only=True)
class EnvironmentVariable:
    key: str
    # is_secret ise şifreli metin, değilse düz değer
    value: str = ""
    is_secret: bool = False
    id: int | None = None
    environment_id: int | None = None

    @property
    def display_value(self) -> str:
        """Dışarıya gösterilecek değer: gizliyse MASK."""
        return MASK if self.is_secret and self.value else self.value


@dataclass(eq=False, kw_only=True)
class Environment:
    name: str
    description: str | None = None
    # Production ortamında veri değiştiren istekler açık onay olmadan çalışmaz
    is_production: bool = False
    variables: list[EnvironmentVariable] = field(default_factory=list)
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def replace_variables(
        self, incoming: list[VariableInput], encrypt: Callable[[str], str]
    ) -> None:
        """Değişken listesini gelenle değiştirir.

        Aynı adlı mevcut satırlar güncellenir (silip yeniden eklemek benzersizlik kuralına
        takılabilir). Gizli bir değişken için MASK gelirse kayıtlı değer korunur.
        Listede olmayan eski değişkenler silinir.
        """
        existing = {variable.key: variable for variable in self.variables}
        result: list[EnvironmentVariable] = []

        for item in incoming:
            previous = existing.pop(item.key, None)
            if item.is_secret and item.value == MASK:
                if previous is None or not previous.is_secret:
                    raise InvalidInput(
                        f"'{item.key}' için kayıtlı gizli değer yok, yeni değer girin"
                    )
                stored = previous.value
            elif item.is_secret and item.value:
                stored = encrypt(item.value)
            else:
                stored = item.value

            variable = previous or EnvironmentVariable(key=item.key)
            variable.value = stored
            variable.is_secret = item.is_secret
            result.append(variable)

        self.variables = result

    def resolve_variables(self, decrypt: Callable[[str], str]) -> tuple[dict[str, str], list[str]]:
        """Değişkenleri çözülmüş halde döndürür: (ad -> değer, gizli değerler).

        Gizli değerler listesi, sonuçlarda maskelenmeleri için ayrıca döner.
        """
        values: dict[str, str] = {}
        secrets: list[str] = []
        for variable in self.variables:
            if variable.is_secret and variable.value:
                try:
                    plain = decrypt(variable.value)
                except SecretUnreadable as exc:
                    raise SecretUnreadable(
                        f"'{variable.key}' çözülemedi; şifreleme anahtarı değişmiş olabilir"
                    ) from exc
                secrets.append(plain)
            else:
                plain = variable.value
            values[variable.key] = plain
        return values, secrets
