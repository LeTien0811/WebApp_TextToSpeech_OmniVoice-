# Hướng dẫn chạy Web App bằng Docker & Chia sẻ qua zrok

Hệ thống đã được bổ sung thành công cấu hình Docker hóa và kênh đường hầm bảo mật `zrok` để chia sẻ dịch vụ web ra internet.

## Các tệp tin được tạo mới:
1. [Dockerfile](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/Dockerfile): Đóng gói ứng dụng Python FastAPI với các thư viện âm thanh cần thiết (`libsndfile1`, `ffmpeg`) và cài đặt sẵn PyTorch.
2. [docker-compose.yml](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/docker-compose.yml): Định nghĩa hai dịch vụ chạy song song:
   - `app`: Service chạy web TTS OmniVoice (mở cổng `8100`, mount thư mục `models/`, `voices/`, và `.env` để lưu dữ liệu trên máy Host).
   - `zrok-tunnel`: Sử dụng ảnh Docker chính thức của `zrok` để tạo một tunnel kết nối trực tiếp đến container `app`.

---

## Hướng dẫn chạy chi tiết (Từng bước):

### Bước 1: Đăng ký & Kích hoạt zrok trên máy Host
Nếu bạn chưa cài và kích hoạt `zrok`, hãy làm theo các bước sau trên máy tính của bạn (máy Host):
1. Truy cập [zrok.io](https://zrok.io/) để đăng ký một tài khoản miễn phí.
2. Tải công cụ `zrok` về máy tính của bạn và giải nén (hoặc cài đặt qua công cụ quản lý gói).
3. Lấy mã token kích hoạt trong trang quản trị zrok console của bạn.
4. Mở PowerShell/Terminal trên máy Host và chạy lệnh để liên kết máy tính của bạn với hệ thống zrok:
   ```bash
   zrok enable <mã-token-của-bạn>
   ```
   *(Lệnh này sẽ tạo thư mục cấu hình ẩn `.zrok` trong thư mục User của bạn, giúp container Docker có thể đọc và xác thực tự động).*

### Bước 2: Build & Khởi động Docker Containers
1. Mở Docker Desktop (hoặc Docker Engine) trên máy tính của bạn.
2. Mở terminal tại thư mục gốc của dự án (`e:\Document\TextToSpeech_Project\OmniVoice_TTS_Service_api`).
3. Thực hiện build Docker image cho ứng dụng:
   ```bash
   docker compose build
   ```
4. Khởi chạy các container dưới dạng chạy nền (detached mode):
   ```bash
   docker compose up -d
   ```

### Bước 3: Lấy đường dẫn Public chia sẻ ra bên ngoài
Khi các container đã chạy thành công, container `zrok-tunnel` sẽ tự động tạo một đường dẫn public.
1. Để xem đường dẫn này, bạn gõ lệnh xem log của container tunnel:
   ```bash
   docker logs omnivoice-zrok-tunnel
   ```
2. Trong dòng log hiển thị, bạn sẽ thấy thông tin dạng như:
   ```text
   access your share at: https://xxxxxxxx.share.zrok.io
   ```
3. Bạn có thể copy đường dẫn `https://xxxxxxxx.share.zrok.io` này và gửi cho máy khác hoặc điện thoại di động truy cập trực tiếp vào giao diện sinh giọng nói của bạn từ bất kỳ đâu trên Internet!

---

## Lưu ý về cấu hình GPU trong Docker
Theo mặc định, tệp `Dockerfile` đang build PyTorch ở chế độ **CPU** để tương thích tối đa và dễ cài đặt trên mọi máy. 
* Nếu bạn muốn sử dụng **GPU CUDA** để sinh giọng nhanh hơn bên trong Docker:
  1. Đảm bảo máy Host đã được cài đặt **NVIDIA Container Toolkit** (xem tài liệu Docker để cài đặt).
  2. Mở file [Dockerfile](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/Dockerfile), bỏ comment dòng cài CUDA PyTorch và comment dòng CPU PyTorch lại.
  3. Mở file [docker-compose.yml](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/docker-compose.yml), bỏ comment phần `deploy.resources.reservations.devices` để Docker cho phép container truy cập card đồ họa của máy Host.
  4. Chạy lại lệnh build và up.
