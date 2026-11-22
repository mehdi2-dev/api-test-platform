# Uçtan Uca Kabul Testi (ATOP-58)

Proje tanımındaki her şartın nasıl karşılandığını ve nasıl doğrulanacağını listeler. Her satır
iki yoldan doğrulanır:

- **Otomatik:** `docker compose exec backend pytest -q` içindeki ilgili test dosyası
- **Elle:** arayüzde izlenecek adım

Hazırlık: `docker compose up -d --build` → admin ile giriş → **Koleksiyonlar → Örnekleri yükle**
→ sol menüden aktif ortam **Demo**.

## A. Fonksiyonel şartlar

| # | Şart | Otomatik test | Elle doğrulama | ✓ |
|---|---|---|---|---|
| A1 | API tanımı: URL, metod, header, body | `test_apis.py` | API'ler → + Yeni API; tüm alanları doldur, Kaydet | ☐ |
| A2 | Kimlik doğrulama: Bearer, Basic, API Key | `test_apis.py` (send_basic_auth, api_key_*) | Kimlik doğrulama sekmesinde üç tipi dene; "Gönderilen istek"te başlık maskeli | ☐ |
| A3 | Durum kodu kontrolü | `test_assertions.py` (status_code) | Testler → Durum kodu 200 → Kaydet ve Çalıştır | ☐ |
| A4 | Yanıt süresi kontrolü | `test_assertions.py` (response_time) | Testler → Süre < 1000 ms | ☐ |
| A5 | JSON alan ve değer kontrolü | `test_assertions.py` (json_path_rules) | Örnek 2 → Lead oluştur adımındaki kurallar ✓ | ☐ |
| A6 | Koleksiyonlar | `test_collections.py` | Örnek koleksiyonlar listede; adım ekle / sırala / kaldır | ☐ |
| A7 | Ortamlar (Dev / Stage / Prod) ve değişkenler | `test_environments.py` | Ortamlar sayfası; aynı API'yi iki ortamda çalıştır, URL değişir | ☐ |
| A8 | Manuel çalıştırma | `test_collections.py`, `test_schedules.py` (async) | Kaydet ve Çalıştır → Kuyrukta → Çalışıyor → Geçti | ☐ |
| A9 | Zamanlanmış çalıştırma | `test_schedules.py` (dispatch_due, cron) | Zamanlamalar → `*/2 * * * *` → 2 dk sonra "Son çalışma" dolar | ☐ |
| A10 | API'ler arası veri aktarımı | `test_collections.py`, `test_acceptance.py` | Örnek 1: Giriş adımında `token = ********`; 2. adım 200 | ☐ |
| A11 | Dashboard ve geçmiş | `test_reporting.py` | Genel Bakış grafikleri; Test Geçmişi filtreleri | ☐ |
| A12 | Hata durumunda bildirim | `test_reporting.py` (notifications) | Bildirimler → webhook.site kanalı → kalan bir koleksiyon → mesaj gelir | ☐ |
| A13 | Roller: Admin / Tester / Viewer | `test_security.py` (yetki matrisi, 45 endpoint × 3 rol) | Viewer ile gir: Yeni/Sil/Çalıştır düğmeleri yok; `/users` → 403 sayfası | ☐ |
| A14 | Kod yazmadan yeni test eklenebilmeli | `test_assertions.py` (kurallar API üzerinden kaydedilir) | Kılavuz bölüm 2-4: sadece arayüzle test oluştur ve çalıştır | ☐ |

## B. Güvenlik şartları

| # | Şart | Otomatik test | Elle doğrulama | ✓ |
|---|---|---|---|---|
| B1 | Token ve gizli bilgiler şifreli saklanır | `test_apis.py`, `test_environments.py`, `test_security.py` (key_rotation) | `docker compose exec db psql -U apitest -c "select auth_config_encrypted from api_definitions limit 1"` → okunamaz metin | ☐ |
| B2 | Hassas veriler maskelenir (UI, rapor, log) | `test_security.py` (stored_run_masks, log_masking) | Test Geçmişi → Giriş kaydı → cevapta `access_token: ********` | ☐ |
| B3 | Veri değiştiren testler varsayılan olarak test ortamında | `test_environments.py` (production), `test_schedules.py` | Prod ortamında POST → "Emin misiniz?" onayı | ☐ |
| B4 | Yetkisiz erişim engellenir | `test_security.py` (every_protected_route_requires_login, tampered_token) | Çıkış yap → `localhost:5173/apis` → giriş sayfasına yönlenir | ☐ |
| B5 | Kaba kuvvet koruması | `test_security.py` (login_is_locked) | 5 kez yanlış şifre → "Çok fazla hatalı deneme" | ☐ |

## C. Örnek senaryolar (proje tanımındaki)

| # | Senaryo | Koleksiyon | Otomatik test | ✓ |
|---|---|---|---|---|
| C1 | Login ve token kontrolü | Örnek 1 | `test_acceptance.py` | ☐ |
| C2 | Lead ve teklif oluşturma, şirket tekliflerinin doğrulanması | Örnek 2 | `test_acceptance.py` | ☐ |
| C3 | Yetkisiz erişim ve mükerrer istek | Örnek 3 | `test_acceptance.py` | ☐ |

Elle: her örnek koleksiyonu Demo ortamında **Kaydet ve Çalıştır** → hepsi **Geçti**.

## D. Teslim edilecekler

| # | Teslimat | Nerede | ✓ |
|---|---|---|---|
| D1 | Çalışan uygulama | `docker compose up -d --build` → http://localhost:5173 | ☐ |
| D2 | Kaynak kod | https://github.com/mehdi2-dev/api-test-platform (`main` dalı) | ☐ |
| D3 | Kurulum dokümanı | [docs/KURULUM.md](KURULUM.md) | ☐ |
| D4 | Kullanım kılavuzu | [docs/KULLANIM_KILAVUZU.md](KULLANIM_KILAVUZU.md) | ☐ |
| D5 | Örnek test koleksiyonu | [backend/examples/](../backend/examples/) (içe aktarılabilir JSON) | ☐ |
| D6 | Otomatik testler ve CI | `backend/tests/`, GitHub Actions yeşil | ☐ |

## Sonuç

| Tarih | Doğrulayan | Ortam | Sonuç | Not |
|---|---|---|---|---|
| | | | | |
