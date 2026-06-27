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

---

## 🎧 Tính năng mới: Tổng hợp văn bản dài sang MP3 (Sách Nói Creator)

Tính năng này cho phép bạn tải lên tệp tin văn bản dài `.txt` hoặc dán trực tiếp một văn bản lớn (tiểu thuyết, truyện ngắn, tài liệu...) để tổng hợp thành một tệp tin `.mp3` duy nhất mà không gây nghẽn máy chủ hay tràn bộ nhớ.

### 🌟 Các điểm cải tiến kiến trúc cốt lõi:
1. **Quản lý bộ nhớ RAM tối ưu (Chunk-to-MP3 Binary Append)**:
   * Ứng dụng **không giữ toàn bộ dữ liệu WAV của tất cả các câu trong RAM**.
   * Với từng câu được sinh ra dưới dạng WAV, hệ thống sử dụng `pydub` chỉ để thêm khoảng lặng tự nhiên cuối câu, sau đó chuyển đổi sang PCM thô và sử dụng bộ mã hóa **`lameenc`** dịch ngay lập tức sang MP3 bytes.
   * Dữ liệu MP3 bytes được ghi ngay xuống ổ đĩa bằng phương pháp **ghi nối tiếp nhị phân (Binary Append - `"ab"`)** vào file đầu ra, sau đó toàn bộ biến âm thanh trong RAM được giải phóng lập tức. RAM tiêu thụ luôn duy trì ở mức tối thiểu.
2. **Loại bỏ hoàn toàn sự phụ thuộc vào `ffmpeg` hệ thống**:
   * Thông thường, việc xuất MP3 yêu cầu cài đặt `ffmpeg` trên hệ điều hành. Bằng việc sử dụng thư viện **`lameenc`** (wrapper của bộ mã hóa LAME MP3 chạy trực tiếp trên bộ nhớ), ứng dụng có thể tự mã hóa MP3 chất lượng cao mà không cần cài đặt `ffmpeg` trên máy tính hoặc Docker container.
3. **Đồng bộ thời gian thực qua Server-Sent Events (SSE)**:
   * Loại bỏ hoàn toàn cơ chế Polling (liên tục gửi request đọc file JSON tĩnh).
   * Sử dụng kết nối luồng sự kiện SSE tĩnh (`text/event-stream`) qua `StreamingResponse` của FastAPI. Client chỉ cần mở kết nối một lần duy nhất bằng `EventSource` trong Javascript, server sẽ liên tục đẩy tiến trình xử lý thời gian thực (`progress`, số câu đã chạy, lỗi nếu có) trực tiếp về giao diện.
4. **Xử lý lỗi Fail-Fast & Bảo toàn tài nguyên**:
   * Toàn bộ tiến trình xử lý ngầm được bao bọc trong một khối `try-except-finally` nghiêm ngặt.
   * Nếu có lỗi phát sinh (OOM GPU, ký tự lỗi, timeout), worker ngầm lập tức gửi sự kiện `"FATAL_ERROR"` kèm mô tả lỗi chi tiết về UI, hủy bỏ (break) vòng lặp tức thì để tránh làm nghẽn GPU lock.
   * Khối `finally` đảm bảo xóa file config tạm và xóa tệp tin MP3 bị ghi dở dang để bảo vệ tài nguyên ổ đĩa.
   * Nếu client ngắt kết nối giữa chừng (đóng trình duyệt hoặc hủy tác vụ), server phát hiện thông qua `request.is_disconnected()` và lập tức dừng xử lý.

### 🛠️ Các tệp tin được tạo mới và chỉnh sửa:
* [text_splitter.py](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/engines/text_splitter.py) `[NEW]`: Giải thuật phân đoạn văn bản tiếng Việt thông minh dựa trên ranh giới tự nhiên (dấu chấm, dấu phẩy, dấu xuống dòng) giới hạn tối ưu 80-150 ký tự/chunk.
* [long_text.html](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/static/long_text.html) `[NEW]`: Giao diện kính mờ sang xịn hỗ trợ kéo thả file `.txt`, cấu hình tham số nghỉ câu, tốc độ và console log giám sát tiến trình.
* [long_text.js](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/static/js/long_text.js) `[NEW]`: Logic xử lý kết nối EventSource SSE, render ProgressBar động và dọn dẹp kết nối an toàn.
* [routes.py](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/api/routes.py) `[MODIFY]`: Thêm endpoint khởi tạo tác vụ `/generate-long-text/init` và endpoint stream tiến trình `/generate-long-text/stream/{task_id}` kèm cơ chế ghi nhị phân nối tiếp.
* [index.html](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/static/index.html) & [main.js](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/static/js/main.js) `[MODIFY]`: Thêm nút điều hướng và cập nhật trạng thái enable/disable theo model loaded.
* [requirements.txt](file:///e:/Document/TextToSpeech_Project/OmniVoice_TTS_Service_api/requirements.txt) `[MODIFY]`: Bổ sung thư viện `lameenc` vào danh sách cài đặt.

