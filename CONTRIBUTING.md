# Katkı kuralları

## Dallar

| Dal | Amaç | Kimden açılır | Nereye birleşir |
|---|---|---|---|
| `main` | Teslim edilebilir sürüm | – | – |
| `develop` | Entegrasyon | `main` | `main` |
| `feature/ATOP-<no>-<kısa-ad>` | Yeni özellik | `develop` | `develop` |
| `fix/ATOP-<no>-<kısa-ad>` | Hata düzeltme | `develop` | `develop` |

İlk kurulum:

```bash
git init
git add .
git commit -m "ATOP-11 proje iskeleti"
git branch -M main
git checkout -b develop
```

## Commit mesajı

```
ATOP-<no> kısa açıklama (emir kipinde değil, ne yapıldığını söyle)
```

Örnek: `ATOP-14 Alembic migration altyapısı eklendi`

## Pull Request kontrol listesi

- [ ] Başlık Jira anahtarıyla başlıyor
- [ ] `ruff check` ve `pytest` yerelde geçiyor
- [ ] Yeni endpoint'ler Swagger'da açıklamalı
- [ ] Veritabanı değişikliği varsa Alembic migration eklendi
- [ ] Gizli bilgi (.env, token) commit edilmedi

## Kod stili

- Python: `ruff` (lint + format), satır uzunluğu 100.
- Vue/JS: 2 boşluk girinti, `<script setup>` kullanımı.
