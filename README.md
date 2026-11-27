# API Test Otomasyon Platformu

API servislerinin doğruluğunu, çalışırlığını ve performansını otomatik test eden,
**kod yazmadan** test senaryosu tanımlanabilen web uygulaması.

[![CI](https://github.com/mehdi2-dev/api-test-platform/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/mehdi2-dev/api-test-platform/actions/workflows/ci.yml)

| Doküman | İçerik |
|---|---|
| [docs/KURULUM.md](docs/KURULUM.md) | Kurulum, ortam değişkenleri, sorun giderme, prod kontrol listesi |
| [docs/KULLANIM_KILAVUZU.md](docs/KULLANIM_KILAVUZU.md) | Kod yazmadan test ekleme, adım adım |
| [docs/KABUL_TESTI.md](docs/KABUL_TESTI.md) | Teslim kriterleri kontrol listesi |
| [backend/examples/](backend/examples/) | Örnek koleksiyonlar (içe aktarılabilir JSON) |

## Neler yapabilir?

- **API yönetimi:** URL, metod, header, query, body (JSON doğrulamalı) ve kimlik doğrulama
  (Bearer, Basic, API Key). Token ve şifreler veritabanında **şifreli**, ekranda **maskeli**.
- **Test motoru:** durum kodu, yanıt süresi, JSON alanı (JSONPath) ve header kuralları;
  sonuç **Geçti / Kaldı / Hata** olarak kaydedilir.
- **Ortamlar:** Dev / Stage / Prod ve `{{değişken}}` desteği. Production'da veri değiştiren
  istekler açık onay ister.
- **Koleksiyonlar:** API'leri sıralı senaryoda birleştirme, cevaptan değişken alıp sonraki
  adıma aktarma (ör. giriş token'ı), sürükle-bırak sıralama, JSON içe/dışa aktarma.
- **Çalıştırma:** elle veya **cron** ile zamanlanmış; Celery üzerinde arka planda, canlı izleme.
- **Raporlama:** dashboard, filtrelenebilir test geçmişi, hata raporu ve önceki başarılı
  çalıştırmayla karşılaştırma.
- **Bildirimler:** başarısız testte Slack, Teams, webhook veya e-posta.
- **Roller:** Admin, Tester, Viewer.

| Katman | Teknoloji |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, httpx |
| Kuyruk | Redis, Celery (worker + beat) |
| Veritabanı | PostgreSQL 16 |
| Frontend | Vue 3, Vite, Pinia, Vue Router |
| Çalıştırma | Docker Compose, GitHub Actions (CI) |

## Hızlı başlangıç

Gerekenler: **Docker Desktop** ve **Git**. Ayrıntılar: [docs/KURULUM.md](docs/KURULUM.md)

```bash
git clone https://github.com/mehdi2-dev/api-test-platform.git
cd api-test-platform
cp .env.example .env          # Windows PowerShell: copy .env.example .env
docker compose up -d --build
```

| Adres | Ne var |
|---|---|
| http://localhost:5173 | Uygulama |
| http://localhost:8000/docs | Platform API dokümantasyonu (Swagger) |
| http://localhost:8001/docs | Demo CRM servisi (örnek senaryoların hedefi) |

İlk giriş: **admin@apitest.com / Admin12345** (`.env` içinden değiştirilebilir).

**Örnek senaryoları denemek için:** Koleksiyonlar → **Örnekleri yükle** → sol menüden aktif
ortamı **Demo** yap → bir örnek koleksiyonu açıp **Kaydet ve Çalıştır**.

## Klasör yapısı

```
api-test-platform/
├── backend/
│   ├── app/
│   │   ├── domain/         iş kuralları (saf Python: test motoru, cron, koleksiyon, bildirim...)
│   │   ├── application/
│   │   │   ├── ports/      dış dünyaya açılan arayüzler (Protocol)
│   │   │   └── use_cases/  uygulama senaryoları (giriş, API testi, koleksiyon koşturma...)
│   │   ├── adapters/
│   │   │   ├── inbound/    giren adaptörler: FastAPI router'ları, HTTP şemaları, demo verisi
│   │   │   └── outbound/   çıkan adaptörler: veritabanı, şifreleme, HTTP istemcisi, e-posta/webhook, kuyruk
│   │   ├── core/           ayarlar ve logging
│   │   ├── demo/           demo CRM servisi (örnek senaryolar için)
│   │   ├── worker/         Celery görevleri
│   │   ├── composition.py  use case'leri gerçek adaptörlerle kuran kompozisyon kökü
│   │   ├── bootstrap.py    ilk admin kullanıcısını oluşturma
│   │   ├── main.py         FastAPI uygulaması
│   │   └── cli.py          yönetim komutları
│   ├── alembic/        veritabanı migration'ları
│   ├── examples/       örnek koleksiyonlar (JSON)
│   └── tests/          pytest testleri (unit/: sahte adaptörlerle use case testleri)
├── frontend/src/       Vue 3 uygulaması (views, components, stores)
├── docs/               kurulum, kullanım kılavuzu, kabul testi
├── docker-compose.yml  tüm servisler
└── .github/workflows/  CI (lint, test, build, import kuralları)
```

## Mimari: Hexagonal (Ports & Adapters)

Backend hexagonal mimariyle yazılmıştır. İş kuralları tek yerde (`domain`) durur ve
hiçbir framework bilmez. Dış dünyayla (veritabanı, HTTP, e-posta, kuyruk) sadece
**portlar** üzerinden konuşur; teknolojiyi **adaptörler** sağlar. Örneğin veritabanını
değiştirmek istediğimizde sadece `adapters/outbound/persistence` değişir.

```mermaid
flowchart LR
    HTTP[FastAPI router'ları] --> UC
    CEL[Celery görevleri] --> UC
    subgraph Çekirdek
        UC[Use case'ler] --> D[Domain: iş kuralları]
        UC --> P[Portlar]
    end
    P -.uygular.- DB[(PostgreSQL<br/>SQLAlchemy)]
    P -.uygular.- SND[httpx ile istek]
    P -.uygular.- NTF[E-posta / Webhook]
    P -.uygular.- Q[Celery kuyruğu]
```

Bağımlılık hep içe doğrudur: `adapters → application → domain`. Bu kural
[import-linter](https://import-linter.readthedocs.io/) ile denetlenir ve CI'da çalışır:

```bash
docker compose run --rm --no-deps backend lint-imports
```

## Testler

```bash
docker compose exec backend pytest -q     # backend (uçtan uca kabul testi dahil)
cd frontend && npm run build              # frontend derleme kontrolü
```

GitHub Actions her push'ta lint, testler, frontend derlemesi ve Docker imajlarını kontrol eder.

## Branch stratejisi

- `main`: teslim edilebilir sürüm, sadece `develop`'tan birleştirme ile güncellenir.
- `develop`: günlük entegrasyon dalı.
- Commit mesajı Jira anahtarıyla başlar: `ATOP-12 health endpoint eklendi`.

Ayrıntılar: [CONTRIBUTING.md](CONTRIBUTING.md)
