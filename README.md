# Air Quality Platform

Bir hava kalitesi platformu. Gerçek zamanlı hava kalitesi verilerini toplamak, işlemek, depolamak ve görselleştirmek için tasarlanmış tam yığın (full-stack) bir uygulamadır.

## Projenin Amacı ve Kapsamı

Bu projenin temel amacı, çeşitli sensörlerden veya kaynaklardan gelen hava kalitesi verilerini (PM2.5, PM10, NO2, SO2, O3 gibi) merkezi bir sistemde toplamaktır. Toplanan veriler işlenir, zaman serisi veritabanında saklanır ve kullanıcıların bu verileri coğrafi bir harita üzerinde görselleştirmesine, analiz etmesine ve potansiyel anomalileri tespit etmesine olanak tanıyan bir web arayüzü aracılığıyla sunulur.

**Kapsam:**

*   API aracılığıyla hava kalitesi verilerinin alınması.
*   Verilerin asenkron olarak işlenmesi ve veritabanına kaydedilmesi.
*   Verilerin harita üzerinde nokta ve ısı haritası olarak gösterilmesi.
*   Belirli bir alan için ortalama kirlilik yoğunluğunun hesaplanması.
*   Anormal veri noktalarının tespit edilmesi ve haritada işaretlenmesi.
*   Gerçek zamanlı güncellemeler için WebSocket kullanımı.
*   Kolay kurulum ve dağıtım için Docker konteynerleştirmesi.

## Sistem Mimarisi ve Komponentler

Platform, aşağıdaki ana bileşenlerden oluşan bir mikroservis mimarisine sahiptir:

1.  **Frontend (React/Vite):** Kullanıcı arayüzünü sağlar. Harita etkileşimleri, veri görselleştirme (noktalar, ısı haritası, grafikler) ve API ile iletişimden sorumludur.
2.  **Backend (Python/FastAPI):** API uç noktalarını sunar, gelen verileri alır, RabbitMQ'ya iletir, veritabanından veri sorgular ve WebSocket bağlantılarını yönetir.
3.  **Worker (Python):** RabbitMQ kuyruğundan mesajları alır, verileri işler (örn. anomali tespiti), ve InfluxDB'ye yazar.
4.  **InfluxDB:** Zaman serisi veritabanıdır. Hava kalitesi okumalarını ve anomalileri zaman damgalarıyla birlikte depolar. Coğrafi ve zaman bazlı sorgulamalar için optimize edilmiştir.
5.  **RabbitMQ:** Mesaj kuyruğu sistemidir. Backend ve Worker arasındaki asenkron iletişimi sağlar, böylece API istekleri hızlı yanıt verirken veri işleme arka planda devam edebilir.
6.  **Nginx (Implicit via Docker):** Genellikle frontend dosyalarını sunmak ve API isteklerini backend'e yönlendirmek için bir ters proxy olarak kullanılır (docker-compose içinde yapılandırılabilir).

**Veri Akışı:**

*   Sensör/Kaynak -> Backend API (`/ingest`) -> RabbitMQ -> Worker -> InfluxDB
*   Kullanıcı (Tarayıcı) <-> Frontend <-> Backend API (veri sorguları) <-> InfluxDB
*   Kullanıcı (Tarayıcı) <-> Frontend <-> Backend API (WebSocket) <- Worker (anomali bildirimleri)

## Teknoloji Seçimleri ve Gerekçeleri

*   **Backend (Python/FastAPI):**
    *   *Neden:* Yüksek performanslı API'ler oluşturmak için modern, hızlı bir framework. Asenkron yetenekleri G/Ç ağırlıklı işlemler (veritabanı, mesaj kuyruğu) için uygundur. Pydantic ile veri doğrulama kolaylığı sağlar.
*   **Frontend (React/Vite):**
    *   *Neden:* Popüler, bileşen tabanlı bir UI kütüphanesi. Geniş ekosistemi ve topluluk desteği. Vite, hızlı geliştirme ve derleme süreçleri sunar.
*   **Database (InfluxDB):**
    *   *Neden:* Zaman serisi verileri için özel olarak tasarlanmıştır. Yüksek yazma/okuma performansı, veri sıkıştırma ve zaman bazlı sorgulama yetenekleri hava kalitesi gibi metrikler için idealdir. Geohash gibi coğrafi sorguları destekler.
*   **Message Queue (RabbitMQ):**
    *   *Neden:* Olgun, güvenilir ve esnek bir mesaj kuyruğu sistemidir. Backend'in anlık yükünü azaltır ve veri işleme sürecini API yanıt süresinden ayırarak sistemin daha dayanıklı olmasını sağlar.
*   **Containerization (Docker/Docker Compose):**
    *   *Neden:* Uygulamanın ve bağımlılıklarının farklı ortamlarda (geliştirme, test, üretim) tutarlı bir şekilde çalışmasını sağlar. Kurulumu ve dağıtımı basitleştirir. Servislerin kolayca yönetilmesini sağlar.
*   **Harita (Leaflet):**
    *   *Neden:* Açık kaynaklı, esnek ve popüler bir interaktif harita kütüphanesi. Eklentilerle genişletilebilir (örn. ısı haritası).

## Kurulum Adımları (Detaylı)

1.  **Depoyu Klonlama:**
    ```bash
    git clone https://github.com/abozten/air-quality-platform-kartaca/ # Depo URL'sini güncelleyin
    cd air-quality-platform
    ```

2.  **Gerekli Araçların Kurulumu:**
    *   **Docker:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) veya Linux için Docker Engine'in kurulu olduğundan emin olun.
    *   **Docker Compose:** Genellikle Docker Desktop ile birlikte gelir. Değilse, [Docker Compose kurulum talimatlarını](https://docs.docker.com/compose/install/) izleyin.
    *   **Git:** Versiyon kontrol sistemi.

3.  **Ortam Değişkenleri Dosyasını Oluşturma:**
    *   Örnek dosyayı kopyalayın:
        ```bash
        cp .env.example .env
        ```
    *   **`.env` Dosyasını Düzenleme:** Bu dosya, servislerin (InfluxDB, RabbitMQ, Backend, Frontend) yapılandırmasını ve kimlik bilgilerini içerir. **Mutlaka kendi değerlerinizle doldurun.** Özellikle dikkat edilmesi gerekenler:
        *   `INFLUXDB_USERNAME`, `INFLUXDB_PASSWORD`: InfluxDB için oluşturulacak ilk kullanıcı adı ve şifre.
        *   `INFLUXDB_ORG`: InfluxDB organizasyon adı.
        *   `INFLUXDB_BUCKET`: Verilerin saklanacağı InfluxDB bucket adı.
        *   `INFLUXDB_TOKEN`: Backend'in InfluxDB'ye bağlanmak için kullanacağı API token'ı. **Güçlü bir token oluşturun.**
        *   `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`: RabbitMQ kullanıcı adı ve şifresi.
        *   `BACKEND_API_PORT`: Backend API'sinin çalışacağı port (varsayılan: 8000).
        *   `FRONTEND_DEV_PORT`: Frontend geliştirme sunucusunun çalışacağı port (varsayılan: 5173).
        *   `VITE_API_BASE_URL`: Frontend'in backend API'sine istek yaparken kullanacağı URL. Docker Compose ortamında genellikle `http://backend:8000/api/v1` gibi bir değer alır (servis adını kullanır). Tarayıcıdan erişim için `http://localhost:8000/api/v1` (veya `BACKEND_API_PORT` ne ise) olmalıdır. **Bu değeri dikkatlice ayarlayın.**
        *   `GEOHASH_PRECISION_STORAGE`: Veritabanına yazarken kullanılacak geohash hassasiyeti.
        *   `GEOHASH_PRECISION_QUERY`: Harita sorgularında kullanılacak geohash hassasiyeti.

4.  **Docker Compose ile Uygulamayı Başlatma:**
    *   Proje kök dizinindeyken aşağıdaki komutu çalıştırın:
        ```bash
        docker-compose up --build -d
        ```
    *   `--build`: Eğer Dockerfile veya bağımlılıklarda değişiklik yapıldıysa imajları yeniden oluşturur. İlk çalıştırmada gereklidir.
    *   `-d`: Konteynerleri arka planda (detached modda) çalıştırır.
    *   İlk çalıştırma biraz zaman alabilir, çünkü imajların indirilmesi ve oluşturulması gerekir.

5.  **Uygulamaya Erişim:**
    *   **Frontend:** Tarayıcınızı açın ve `http://localhost:5173` (veya `.env` dosyasında belirlediğiniz `FRONTEND_DEV_PORT`) adresine gidin.
    *   **Backend API Dokümantasyonu (Swagger UI):** `http://localhost:8000/docs` (veya `.env` dosyasında belirlediğiniz `BACKEND_API_PORT`) adresine gidin. Buradan API endpoint'lerini test edebilirsiniz.
    *   **RabbitMQ Yönetim Arayüzü:** `http://localhost:15672` (veya `.env` dosyasında belirlediğiniz `RABBITMQ_MANAGEMENT_PORT`) adresine gidin. `.env` dosyasındaki `RABBITMQ_DEFAULT_USER` ve `RABBITMQ_DEFAULT_PASS` ile giriş yapın. Kuyrukları ve mesajları buradan izleyebilirsiniz.
    *   **InfluxDB UI (Opsiyonel):** InfluxDB genellikle `8086` portunda çalışır. Eğer dışarıya açtıysanız (`docker-compose.yaml` içinde port mapping varsa) `http://localhost:8086` adresinden erişebilir ve `.env` dosyasındaki bilgilerle giriş yapabilirsiniz.

## Kullanım Rehberi

1.  **Harita Arayüzü:**
    *   Uygulamayı açtığınızda, mevcut hava kalitesi verilerini gösteren bir harita göreceksiniz.
    *   Noktalar, belirli konumlardaki son okumaları temsil eder. Üzerlerine tıklayarak detayları (ölçüm değerleri, zaman damgası) görebilirsiniz.
    *   Sağ üstteki katman kontrolü ile **Isı Haritası (Heatmap)** katmanını açıp kapatabilirsiniz. Isı haritası, seçili parametreye (örn. PM2.5) göre kirlilik yoğunluğunu gösterir. Yoğunluk, harita yakınlaştırma seviyesine göre dinamik olarak hesaplanır.
    *   Anormal olarak işaretlenmiş okumalar haritada özel bir ikonla (örn. uyarı işareti) gösterilebilir.
2.  **Alan Seçimi ve Yoğunluk Hesaplama:**
    *   Harita üzerinde sol tarafta bulunan çizim araçlarını (genellikle dikdörtgen ikonu) kullanarak bir alan seçin.
    *   Alanı çizmeyi bitirdiğinizde, seçilen bölge içindeki ortalama kirlilik değerleri (PM2.5, PM10 vb.) ve o bölgedeki veri noktası sayısı hesaplanarak genellikle haritanın yanında veya altında bir panelde gösterilir.
3.  **Veri Gönderme (API Aracılığıyla):**
    *   Yeni hava kalitesi verileri göndermek için `POST /api/v1/air_quality/ingest` endpoint'ini kullanın. İstek gövdesi `AirQualityReading` modeline uygun olmalıdır (bkz. `backend/app/models.py` veya `/docs`).
    *   Örnek `curl` isteği:
      ```bash
      curl -X POST "http://localhost:8000/api/v1/air_quality/ingest" \
      -H "Content-Type: application/json" \
      -d '{
        "latitude": 40.7128,
        "longitude": -74.0060,
        "timestamp": "2025-05-05T12:00:00Z",
        "pm25": 15.5,
        "pm10": 25.2,
        "no2": 30.1,
        "so2": 5.8,
        "o3": 45.0
      }'
      ```
4.  **WebSocket Bağlantısı:**
    *   Frontend, `/ws/anomalies` endpoint'ine bir WebSocket bağlantısı kurar. Backend (Worker tarafından tetiklenerek) yeni bir anomali tespit ettiğinde, bu bağlantı üzerinden frontend'e anlık bildirim gönderir ve harita güncellenir.

## API Dokümantasyonu

API endpoint'lerinin tam listesi ve detayları (istek/yanıt modelleri, parametreler) için, çalışan uygulamanın `/docs` adresine gidin (örn. `http://localhost:8000/docs`). Başlıca endpoint'ler şunlardır:

*   `POST /api/v1/air_quality/ingest`: Yeni hava kalitesi okuması gönderir.
*   `GET /api/v1/air_quality/heatmap_data`: Belirli bir harita görünümü (sınırlar ve yakınlaştırma) için ısı haritası verilerini alır. Geohash tabanlı toplulaştırma kullanır.
*   `GET /api/v1/air_quality/points`: Belirli bir harita görünümü için ham veri noktalarını alır (limitli).
*   `GET /api/v1/anomalies`: Belirli bir zaman aralığındaki tespit edilmiş anomalileri listeler.
*   `GET /api/v1/pollution_density`: Seçilen bir sınırlayıcı kutu (bounding box) içindeki ortalama kirlilik yoğunluğunu hesaplar.
*   `GET /api/v1/air_quality/location`: Belirli bir enlem/boylam ve geohash hassasiyetine en yakın güncel hava kalitesi okumasını alır. Bulunamazsa yakın bölgedeki verilerden tahmin yapar.
*   `WS /ws/anomalies`: Anomali bildirimleri için WebSocket bağlantı noktası.

## Script'lerin Kullanımı

Proje kök dizininde bulunan bazı yardımcı script'ler ve dosyalar:

*   **`fast_ingest.cpp`:** (Derlenmiş hali varsa) Muhtemelen C++ ile yazılmış, yüksek hızda veri gönderme testi yapmak için kullanılan bir istemci. Kullanımı için derlenmesi ve çalıştırılması gerekir. Parametreleri (hedef API URL'si, gönderilecek veri sayısı vb.) kaynak koduna bakarak veya `-h`/`--help` argümanı ile (eğer implemente edilmişse) öğrenilebilir.
    *   Derleme (örnek): `g++ fast_ingest.cpp -o fast_ingest -lcurl` (libcurl kütüphanesi gerekebilir)
    *   Çalıştırma (örnek): `./fast_ingest http://localhost:8000/api/v1/air_quality/ingest 1000`
*   **`manual-input.sh`:** Manuel olarak tek bir veri noktası göndermek için kullanılabilecek bir shell script'i olabilir. İçeriğini inceleyerek nasıl kullanılacağını ve hangi parametreleri aldığını (örn. enlem, boylam, değerler) anlayabilirsiniz. Genellikle `curl` komutunu sarmalar.
    *   Kullanım (örnek): `./manual-input.sh 41.01 28.97 22.5 35.1`
*   **`auto-test.sh` / `turkey.sh` / `etst.sh`:** Otomatik testler, belirli senaryoları çalıştırmak (örn. Türkiye için veri gönderme) veya başka geliştirme/test görevleri için kullanılan script'ler olabilir. İçeriklerini inceleyerek amaçlarını ve kullanımlarını öğrenin.

**Not:** Bu script'lerin güncelliği ve işlevselliği garanti edilmez. Kullanmadan önce içeriklerini kontrol edin.

## Sorun Giderme (Troubleshooting)

*   **Konteynerler Başlamıyor / Hata Veriyor:**
    *   `docker-compose logs <servis_adı>` komutuyla ilgili servisin (örn. `backend`, `frontend`, `influxdb`) loglarını kontrol edin. Hata mesajları sorunun kaynağını gösterecektir.
    *   `.env` dosyasındaki yapılandırmaların (portlar, kimlik bilgileri, URL'ler) doğru olduğundan emin olun. Özellikle `VITE_API_BASE_URL` sık karşılaşılan bir sorundur.
    *   Port çakışması olup olmadığını kontrol edin. `.env` dosyasında tanımlı portların makinenizde başka bir uygulama tarafından kullanılmadığından emin olun.
    *   `docker-compose down -v` komutuyla mevcut konteynerleri ve volumeları tamamen kaldırıp `docker-compose up --build -d` ile tekrar deneyin (Bu işlem veritabanı verilerini silecektir!).
*   **Frontend Açılamıyor veya API'ye Bağlanamıyor:**
    *   Tarayıcının geliştirici konsolunu (F12) açarak ağ (Network) ve konsol (Console) sekmelerindeki hataları kontrol edin.
    *   `VITE_API_BASE_URL`'nin `.env` dosyasında doğru ayarlandığından ve backend API'sinin çalıştığından emin olun (`http://localhost:8000/docs` adresini kontrol edin).
    *   Backend loglarını (`docker-compose logs backend`) kontrol edin.
*   **Veriler Haritada Görünmüyor:**
    *   Veri gönderme işleminin başarılı olup olmadığını kontrol edin (API `/ingest` endpoint'i veya script'ler).
    *   Worker servisinin çalıştığını ve RabbitMQ'dan mesajları işlediğini kontrol edin (`docker-compose logs worker`). Loglarda InfluxDB'ye yazma hataları olup olmadığına bakın.
    *   RabbitMQ yönetim arayüzünden (`http://localhost:15672`) kuyrukta mesaj birikip birikmediğini kontrol edin.
    *   InfluxDB'ye verilerin yazılıp yazılmadığını kontrol edin (InfluxDB UI veya `influx` CLI kullanarak).
    *   Backend API'sinin (`/heatmap_data`, `/points`) doğru veri döndürüp döndürmediğini `/docs` üzerinden test edin.
    *   Tarayıcı konsolunda harita ile ilgili hatalar olup olmadığını kontrol edin.
*   **InfluxDB Bağlantı Hatası (Backend/Worker Loglarında):**
    *   `.env` dosyasındaki `INFLUXDB_URL`, `INFLUXDB_TOKEN`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET` ayarlarının doğru olduğundan emin olun.
    *   InfluxDB konteynerinin çalıştığını kontrol edin (`docker ps`).
    *   Docker ağ ayarlarında bir sorun olup olmadığını kontrol edin (servisler birbirleriyle iletişim kurabiliyor mu?).

## Geliştirme

*   **Backend:** `backend` servisi `uvicorn --reload` kullandığı için `backend/app` içindeki Python kodlarında yapılan değişiklikler konteyner içindeki sunucuyu otomatik olarak yeniden başlatacaktır.
*   **Frontend:** `frontend` servisi Vite'in HMR (Hot Module Replacement) özelliğini kullandığı için `frontend/src` içindeki React kodlarında yapılan değişiklikler tarayıcıda otomatik olarak güncellenmelidir.

## Uygulamayı Durdurma

```bash
docker-compose down
```
*   Veritabanı verileri, kuyruk mesajları gibi kalıcı verileri de silmek isterseniz:
    ```bash
    docker-compose down -v
    ```
