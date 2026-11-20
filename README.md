# API Test Otomasyon Platformu

API servislerinin doğruluğunu, çalışırlığını ve performansını otomatik test eden,
kod yazmadan test senaryosu tanımlanabilen web uygulaması.

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| Kuyruk | Redis, Celery (worker + beat) |
| Veritabanı | PostgreSQL 16 |
| Frontend | Vue 3, Vite, Pinia, Vue Router |
| Çalıştırma | Docker Compose |

## Klasör yapısı

```
api-test-platform/
├── backend/            FastAPI uygulaması
│   ├── app/
│   │   ├── api/        HTTP endpoint'leri (router'lar)
│   │   ├── core/       ayarlar (config) ve logging
│   │   ├── db/         veritabanı bağlantısı ve Base model
│   │   ├── models/     SQLAlchemy modelleri
│   │   └── worker/     Celery uygulaması ve görevleri
│   ├── alembic/        veritabanı migration'ları
│   └── tests/          pytest testleri
├── frontend/           Vue 3 uygulaması
├── docker-compose.yml  tüm servisler
└── .github/workflows/  CI
```

## Hızlı başlangıç (Docker ile — önerilen)

Gerekenler: **Docker Desktop** ve **Git**.

```bash
cp .env.example .env          # Windows PowerShell: copy .env.example .env
docker compose up --build
```

| Adres | Ne var |
|---|---|
| http://localhost:5173 | Frontend |
| http://localhost:8000/docs | API dokümantasyonu (Swagger) |
| http://localhost:8000/api/health | Sağlık kontrolü (DB + Redis) |

Durdurmak için `Ctrl+C`, ardından `docker compose down`.
Veritabanını da silmek için: `docker compose down -v`.

## Docker'sız geliştirme (VS Code'da)

PostgreSQL ve Redis'i yine Docker'dan çalıştırmak en kolayı:

```bash
docker compose up db redis
```

**Backend** (ayrı terminal):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate         # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

**Celery worker** (ayrı terminal, venv aktifken):

```bash
cd backend
celery -A app.worker.celery_app worker --loglevel=info --pool=solo   # Windows'ta --pool=solo gerekli
```

**Frontend** (ayrı terminal):

```bash
cd frontend
npm install
npm run dev
```

VS Code'da **Run and Debug** panelinde hazır "Backend: FastAPI" hata ayıklama ayarı var.

## Testler

```bash
cd backend && pytest
cd frontend && npm run build
```

## Branch stratejisi

- `main` — her zaman çalışır durumda, sadece PR ile güncellenir.
- `develop` — günlük entegrasyon dalı.
- Özellik dalları `develop`'tan açılır ve Jira anahtarıyla adlandırılır:
  `feature/ATOP-12-fastapi-iskeleti`, `fix/ATOP-30-prod-koruma`.
- Commit mesajı Jira anahtarıyla başlar: `ATOP-12 health endpoint eklendi`
  (Jira, commit'i ilgili task'a bağlar).
- PR açılmadan önce CI (lint + test + build) yeşil olmalı.

Ayrıntılar: [CONTRIBUTING.md](CONTRIBUTING.md)
