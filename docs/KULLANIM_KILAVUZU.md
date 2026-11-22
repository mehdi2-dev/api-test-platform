# Kullanım Kılavuzu: Kod Yazmadan API Testi

Bu kılavuz, platformda bir API testini sıfırdan oluşturup çalıştırmayı, sonucunu okumayı ve
otomatik hale getirmeyi adım adım anlatır. Örnekler demo CRM servisini kullanır
(önce **Koleksiyonlar → Örnekleri yükle**).

## Roller

| Rol | Yapabildikleri |
|---|---|
| **Admin** | Her şey + kullanıcı yönetimi, bildirim kanalları, örnek veri yükleme |
| **Tester** | API, ortam, koleksiyon, zamanlama oluşturma ve çalıştırma |
| **Viewer** | Her şeyi görüntüleme (test çalıştıramaz, değiştiremez) |

Kullanıcılar **Kullanıcılar** sayfasından (Admin) eklenir.

---

## 1. Ortamı hazırla

Aynı testi farklı sunucularda (Dev, Stage, Prod) çalıştırmak için adresler ve gizli bilgiler
**ortam değişkeni** olarak tutulur.

1. **Ortamlar → + Yeni ortam** → Ad: `Dev`
2. Değişken ekle: `base_url` = `http://demo:8001`
3. Gizli bilgiler (şifre, API anahtarı) için **Gizli** kutusunu işaretleyin: şifreli saklanır,
   ekranda `********` görünür.
4. **Kaydet → Aktif ortam yap.** Seçili ortam sol menünün altında görünür.

> Gerçek bir canlı ortamı **Production** işaretleyin. O ortamda POST / PUT / PATCH / DELETE
> istekleri "Emin misiniz?" onayı olmadan gönderilmez.

> Docker içinde `localhost` konteynerin kendisidir. Platformun kendi API'si için
> `http://backend:8000`, demo için `http://demo:8001` yazın.

## 2. API tanımla

**API'ler → + Yeni API**

| Alan | Örnek |
|---|---|
| Ad | `Şirketleri listele` |
| Metod + URL | `GET` · `{{base_url}}/companies` |
| Params | `?page=1` gibi parametreler, satır satır |
| Headers | `Accept: application/json` (varsayılan gelir) |
| Body | JSON / Metin. JSON yazarken anında doğrulanır; **Biçimlendir** düzenler |
| Kimlik doğrulama | Yok · Bearer Token · Basic Auth · API Key (header veya query) |

URL'nin altındaki etiketler, kullanılan `{{değişken}}`'lerin aktif ortamda tanımlı olup
olmadığını gösterir: **yeşil** tanımlı, **kırmızı** eksik.

> Token'ı header'a elle yazmak yerine **Kimlik doğrulama** sekmesini kullanın; orada şifreli
> saklanır ve sonuçlarda maskelenir.

## 3. Test kuralları ekle

**Testler** sekmesi: "bu cevap ne zaman doğru sayılır?" sorusunun cevabı. Hızlı düğmeler:
**+ Durum kodu 200**, **+ Süre < 1000 ms**, **+ JSON alanı**, **+ Header**.

| Tip | Hedef | Operatörler | Örnek |
|---|---|---|---|
| Durum kodu | – | eşittir, eşit değildir, aralıkta, listede | `200` · `2xx` · `200-299` · `200,201` |
| Yanıt süresi | – | şundan kısa (ms) | `500` |
| JSON alanı | JSONPath | var, yok, eşittir, eşit değildir, içerir, regex, tipi, büyüktür, küçüktür | `$.status` eşittir `ok` |
| Header | Header adı | var, yok, eşittir, içerir | `Content-Type` içerir `json` |

**JSONPath yazımı**

| Yol | Anlamı |
|---|---|
| `$` | Cevabın tamamı |
| `$.status` | Üst düzeydeki `status` alanı |
| `$.data.user.id` | İç içe alan |
| `$[0].name` | Dizinin ilk elemanının `name` alanı |
| `$.items[-1]` | Dizinin son elemanı |
| `$['alan adı']` | Boşluk içeren alan adı |

**Eşittir** karşılaştırması tip duyarlıdır: `3` sayı, `"3"` metin, `true` mantıksal değerdir.
Beklenen değerde `{{değişken}}` kullanılabilir (ör. `$.id` eşittir `{{lead_id}}`).

## 4. Çalıştır ve sonucu oku

**Kaydet ve Çalıştır**:

- Rozet: **Geçti** (tüm kurallar geçti) · **Kaldı** (en az bir kural kaldı) · **Hata** (cevap
  hiç alınamadı: bağlantı, zaman aşımı, eksik değişken)
- **Testler** sekmesi: her kural ✓ / ✗ ve **gelen** değer
- **Cevap**, **Cevap header'ları**, **Gönderilen istek** (gizli değerler maskeli)
- **Hata raporu →** bağlantısı ayrıntılı rapora gider (bkz. 7)

## 5. Senaryo kur: Koleksiyon

Birden fazla API'yi sırayla çalıştırmak ve aralarında veri taşımak için.

1. **Koleksiyonlar → + Yeni koleksiyon** → Ad
2. Alttaki menüden API seçip **+ Adım ekle** (sırayla)
3. Değer taşımak için ilgili adımda **+ Cevaptan değişken al**:
   kaynak **JSON alanı**, yol `$.access_token`, değişken adı `token`, **gizli** ✓
4. Sonraki adımın API'sinde bu değeri `{{token}}` olarak kullanın (ör. Bearer Token alanında)
5. Sıralama: satırı **⋮⋮** tutamacından sürükleyin ya da ↑ ↓
6. **Bir adım geçemezse dur**: işaretliyse ilk hatada kalan adımlar "Atlandı" olur
7. **Kaydet ve Çalıştır**: arka planda çalışır, durum canlı görünür
   (Kuyrukta → Çalışıyor → Geçti/Kaldı, ilerleme çubuğu)

> Değişken adını yazarken süslü parantez kullanmayın (`token`); kullanırken kullanın (`{{token}}`).

**Hazır değişkenler**: her kullanımda yeni değer üretir, ortamda tanımlamaya gerek yoktur.

| Değişken | Örnek değer | Kullanım |
|---|---|---|
| `{{$uuid}}` | `3f2b9c…` | Benzersiz e-posta: `ayse-{{$uuid}}@firma.com` |
| `{{$timestamp}}` | `1763830000` | Unix zamanı |
| `{{$isoTimestamp}}` | `2026-11-22T19:30:00+00:00` | Tarih alanları |
| `{{$randomInt}}` | `48213` | Rastgele sayı |

### Örnek koleksiyonlar

| Koleksiyon | Ne gösterir |
|---|---|
| **Örnek 1 · Giriş ve token kontrolü** | Giriş → token'ı al → token'la korumalı listeyi çek |
| **Örnek 2 · Lead ve teklif oluşturma** | Lead oluştur → `lead_id`'yi al → teklif ver → lead durumu ve şirket tekliflerini doğrula |
| **Örnek 3 · Negatif senaryolar** | Yanlış şifre (401), token'sız / geçersiz token (401), mükerrer kayıt (409), geçersiz tutar (422), olmayan kayıt (404) |

Negatif senaryolarda kurallar **hatayı bekler**; koleksiyonun "Geçti" olması sistemin hatalı
isteklere doğru cevap verdiği anlamına gelir.

## 6. Otomatikleştir: Zamanlama

**Zamanlamalar → Yeni plan**: koleksiyon, ortam ve cron ifadesi (hazır düğmeler var). Altta
sonraki çalışma saatleri önizlenir.

| İfade | Anlamı |
|---|---|
| `*/5 * * * *` | 5 dakikada bir |
| `0 * * * *` | Saat başı |
| `0 9 * * 1-5` | Hafta içi 09:00 |
| `0 3 * * 1` | Pazartesi 03:00 |

Alanlar: `dakika saat ayın-günü ay haftanın-günü` (0 = Pazar). Saatler Europe/Istanbul.
**Şimdi çalıştır** beklemeden tetikler; **Durdur** planı pasif yapar.

## 7. Sonuçları izle

- **Genel Bakış:** başarı oranı, ortalama süre, günlük grafik, en çok kalan ve en yavaş API'ler
- **Test Geçmişi:** API adı, sonuç, ortam, kaynak ve tarihe göre filtre; bağlantı paylaşılabilir
- **Hata raporu** (geçmişte bir kayda tıklayınca):
  - Kalan kurallar en üstte
  - **Önceki başarılıyla karşılaştır:** aynı API'nin son başarılı çalıştırmasıyla durum kodu,
    süre, URL ve cevap gövdesi (değişen satırlar renkli)
  - **Hata raporunu kopyala:** Jira'ya yapıştırmaya hazır metin

Raporlarda `token`, `password`, `api_key` gibi alanlar ve `Authorization` / `Cookie`
başlıkları `********` olarak saklanır; kurallar ise gerçek değerle çalışır.

## 8. Haberdar ol: Bildirimler (Admin)

**Bildirimler → Yeni kanal**: Slack, Microsoft Teams, Webhook (JSON) veya E-posta.
"Sadece başarısız olunca" ya da "Her çalıştırmada". **Deneme gönder** ile kontrol edin.
Mesajda koleksiyon, ortam, kalan adımlar, kalan kural ve sonucun bağlantısı bulunur.

> Denemek için https://webhook.site size geçici bir adres verir.

## 9. Paylaş: İçe / dışa aktarma

- **Dışa aktar (JSON):** koleksiyon sayfasında. API tanımları, kurallar, adımlar ve değişken
  çıkarma ayarları dosyaya yazılır; **token ve şifreler yazılmaz** (yerine `{{token}}`).
  `required_variables` listesi ortamda tanımlanması gereken değişkenleri söyler.
- **İçe aktar:** Koleksiyonlar sayfasında; dosyadaki API'ler ve koleksiyon yeniden oluşturulur.
