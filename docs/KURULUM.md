# Kurulum Dokümanı

Bu doküman platformu sıfırdan bir bilgisayarda çalıştırmayı, ayarları ve sık karşılaşılan
sorunları anlatır.

## 1. Gereksinimler

| Araç | Neden | İndirme |
|---|---|---|
| Docker Desktop | Tüm servisler konteynerde çalışır | https://www.docker.com/products/docker-desktop |
| Git | Kodu indirmek için | https://git-scm.com |
| (İsteğe bağlı) VS Code | Kodu incelemek / düzenlemek için | https://code.visualstudio.com |

Python, Node.js veya PostgreSQL kurmanıza **gerek yoktur**; hepsi Docker içinde gelir.

### Windows'a özel

1. Docker Desktop WSL 2 kullanır. Yönetici olarak açılan PowerShell'de: `wsl --install`,
   sonra bilgisayarı yeniden başlatın.
2. Docker "Virtualization is disabled in firmware" derse BIOS'ta sanallaştırmayı
   (Intel VT-x / AMD SVM) açın.
3. Komutlar PowerShell'de çalışır; tek fark dosya kopyalama: `cp` yerine `copy`.

### macOS (Apple Silicon dahil)

Docker Desktop for Mac'i kurun. Kullanılan tüm imajların ARM sürümü var; ek ayar gerekmez.

## 2. İlk kurulum

```bash
git clone https://github.com/mehdi2-dev/api-test-platform.git
cd api-test-platform
git checkout develop                 # en güncel geliştirme dalı
cp .env.example .env                 # Windows: copy .env.example .env
docker compose up -d --build
```

İlk derleme internet hızına göre birkaç dakika sürer. Durumu kontrol edin:

```bash
docker compose ps
```

Yedi servisin hepsi **Up / running** olmalı:

| Servis | Görevi | Port |
|---|---|---|
| `db` | PostgreSQL veritabanı | 5432 |
| `redis` | Celery kuyruğu | 6379 |
| `backend` | Platform API'si (FastAPI); açılışta migration'ları uygular | 8000 |
| `worker` | Koleksiyonları arka planda çalıştırır (Celery) | – |
| `beat` | Her dakika zamanı gelen planları kuyruğa atar (Celery Beat) | – |
| `demo` | Örnek senaryoların test ettiği demo CRM servisi | 8001 |
| `frontend` | Web arayüzü (Vue + Vite) | 5173 |

Uygulama: **http://localhost:5173** · İlk giriş: `admin@apitest.com` / `Admin12345`

## 3. Örnek verileri yükleme

Arayüzden: **Koleksiyonlar → Örnekleri yükle** (Admin). Ya da komutla:

```bash
docker compose exec backend python -m app.cli seed-demo
```

Bu işlem "Demo" ortamını (`base_url`, `demo_user`, gizli `demo_password`) ve
`backend/examples/` içindeki üç örnek koleksiyonu oluşturur. İki kez çalıştırılırsa var
olanlara dokunmaz.

## 4. Ortam değişkenleri (`.env`)

`.env` git'e eklenmez; her bilgisayarda `.env.example`'dan kopyalanır.

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` yapılırsa güvensiz ayarlarla açılış engellenir |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`... |
| `CORS_ORIGINS` | `http://localhost:5173` | Arayüzün adresi (virgülle birden fazla) |
| `DATABASE_URL` | `postgresql+psycopg://apitest:apitest@db:5432/apitest` | Veritabanı bağlantısı |
| `REDIS_URL` | `redis://redis:6379/0` | Celery kuyruğu |
| `SECRET_KEY` | (değiştirin) | JWT imzalama anahtarı; en az 32 rastgele karakter |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Giriş token'ının ömrü |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Yenileme token'ının ömrü |
| `ENCRYPTION_KEY` | boş | Gizli verileri şifreleyen anahtar; boşsa `SECRET_KEY`'den türetilir |
| `ENCRYPTION_KEY_PREVIOUS` | boş | Anahtar değiştirirken eski anahtar(lar) |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCK_SECONDS` | `5` / `900` | Hatalı giriş sınırı ve kilit süresi |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Test edilen API'lere giden isteklerin zaman aşımı |
| `TIMEZONE` | `Europe/Istanbul` | Cron ifadelerinin saat dilimi |
| `DEMO_BASE_URL` | `http://demo:8001` | Örnek verilerdeki "Demo" ortamının adresi |
| `FRONTEND_URL` | `http://localhost:5173` | Bildirim mesajlarındaki bağlantılar |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` | boş / 587 | E-posta bildirimi |
| `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` | `admin@apitest.com` / `Admin12345` | Veritabanı boşken oluşturulan ilk admin |

`.env` değiştirdikten sonra: `docker compose up -d` (değişen servisler yeniden başlar).

## 5. Günlük kullanım komutları

| Ne | Komut |
|---|---|
| Başlat (arka planda) | `docker compose up -d` |
| Kod/paket değişti, yeniden derle | `docker compose up -d --build` |
| Durdur | `docker compose down` |
| Durdur ve **veritabanını sil** | `docker compose down -v` |
| Servis durumları | `docker compose ps` |
| Loglar | `docker compose logs -f backend` · `docker compose logs -f worker beat` |
| Testler | `docker compose exec backend pytest -q` |
| Güvenlik ayarı kontrolü | `docker compose exec backend python -m app.cli check` |

Backend, demo ve frontend kod değişikliklerini kendiliğinden algılar. **Worker ve beat**
algılamaz: `docker compose restart worker beat`. Yeni migration eklendiyse:
`docker compose restart backend`.

## 6. Sorun giderme

| Belirti | Neden / Çözüm |
|---|---|
| `docker: command not found` / Docker açılmıyor | Docker Desktop çalışmıyor; açın ve balina simgesinin yeşil olmasını bekleyin |
| `port is already allocated` | Port başka bir programda (ör. başka bir proje 8000'de). O programı kapatın ya da `docker-compose.yml`'da sol taraftaki portu değiştirin (`"8010:8000"`) |
| Sayfa boş / giriş ekranı gelmiyor | `docker compose logs frontend --tail 30`; tarayıcıda F12 → Console'daki kırmızı hata |
| `GET /api/health` 503 | Veritabanı veya Redis ayakta değil: `docker compose ps` |
| Testi çalıştırınca "Sunucuya bağlanılamadı", URL `localhost` | Konteyner içinde `localhost` konteynerin kendisidir. Platformun kendi API'si için `http://backend:8000`, demo için `http://demo:8001` kullanın |
| "Tanımsız değişken: …" | Sol menüde doğru ortam seçili mi? Değişken o ortamda tanımlı mı? |
| Zamanlanmış plan çalışmıyor | `docker compose logs -f beat worker`; plan **etkin** mi, cron saati doğru mu (önizlemeye bakın)? |
| Girişte "Çok fazla hatalı deneme" | 5 hatalı denemeden sonra 15 dk kilit. Beklemeden açmak için: `docker compose restart backend` |
| Kod değişikliği worker'a yansımadı | `docker compose restart worker beat` |
| "Şifreli veri çözülemedi" | `ENCRYPTION_KEY` / `SECRET_KEY` değişmiş. Eski anahtarı `ENCRYPTION_KEY_PREVIOUS`'a yazın (bkz. 7) |

## 7. Prod'a çıkmadan önce (güvenlik kontrol listesi)

1. `ENVIRONMENT=production`
2. `SECRET_KEY`: en az 32 karakter, rastgele:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`
3. `ENCRYPTION_KEY`: `docker compose exec backend python -m app.cli generate-key`
4. `FIRST_ADMIN_PASSWORD` değiştirildi; ilk girişten sonra admin şifresi değiştirildi
5. `CORS_ORIGINS` sadece gerçek arayüz adresi
6. Kontrol: `docker compose exec backend python -m app.cli check`, "Güvenlik ayarları tamam."
7. Gerçek prod ortamı platformda **Production** işaretli (veri değiştiren istekler onay ister)

Bu ayarlar eksikse `ENVIRONMENT=production` iken backend açılmaz ve nedenini loglara yazar.

### Şifreleme anahtarını değiştirme (rotasyon)

1. Yeni anahtar üretin: `docker compose exec backend python -m app.cli generate-key`
2. `.env`: `ENCRYPTION_KEY=<yeni>`, `ENCRYPTION_KEY_PREVIOUS=<eski>` → `docker compose up -d`
3. Kayıtları yeni anahtarla yeniden şifreleyin:
   `docker compose exec backend python -m app.cli rotate-keys`
4. `ENCRYPTION_KEY_PREVIOUS`'ı boşaltın → `docker compose up -d`

## 8. Docker'sız geliştirme (isteğe bağlı)

Veritabanı ve Redis'i yine Docker'dan çalıştırmak en kolayı: `docker compose up -d db redis`

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate                  # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
celery -A app.worker.celery_app worker --loglevel=info --pool=solo   # ayrı terminal
celery -A app.worker.celery_app beat --loglevel=info                 # ayrı terminal
uvicorn app.demo.main:app --port 8001                                # ayrı terminal
```

```bash
cd frontend
npm install
npm run dev
```

Bu durumda `.env` içindeki adresler `localhost` olmalı (`DATABASE_URL=...@localhost:5432/...`,
`REDIS_URL=redis://localhost:6379/0`, `DEMO_BASE_URL=http://localhost:8001`).
