# OmniVoice TTS Service

Microservice tổng hợp giọng nói tiếng Việt dùng [OmniVoice](https://github.com/k2-fsa/OmniVoice) với voice cloning. Chạy độc lập qua HTTP API, tích hợp được với bất kỳ backend nào.

## Demo Audio

File âm thanh mẫu kết quả chạy dự án: [example_result.wav](./example_result.wav)

<audio controls src="./example_result.wav">
  Trình duyệt hoặc nền tảng hiện tại không hỗ trợ phát audio trực tiếp. Bạn có thể mở file từ liên kết bên trên.
</audio>

**Stack:** Python · FastAPI · OmniVoice · CUDA

---

## Tính năng

- Voice cloning từ file audio mẫu bất kỳ
- API key authentication
- GPU serialize queue — nhiều request xếp hàng, không bị reject
- VoiceClonePrompt pre-computed khi startup → tiết kiệm ~200ms/request
- Warmup tự động để GPU JIT compile trước khi nhận request thật
- Cấu hình qua environment variables

---

## Yêu cầu phần cứng

| Thành phần | Tối thiểu | Khuyến nghị |
|---|---|---|
| GPU VRAM | 6GB | 8GB+ |
| CUDA | 12.x | 12.8 |
| RAM | 8GB | 16GB |
| Disk | 10GB | 20GB (model ~8GB) |

Chạy được trên CPU nhưng rất chậm (~30-60s/câu).

---

## Cài đặt

### Bước 1: Tạo môi trường ảo

```bash
python -m venv venv
```

### Bước 2: Cài PyTorch với CUDA

Kiểm tra CUDA version của bạn bằng `nvidia-smi`, rồi chọn lệnh phù hợp:

**CUDA 12.8:**
```bash
venv\Scripts\pip.exe install torch==2.7.1+cu128 torchaudio==2.7.1+cu128 --index-url https://download.pytorch.org/whl/cu128
```

**CUDA 12.4:**
```bash
venv\Scripts\pip.exe install torch==2.7.1+cu124 torchaudio==2.7.1+cu124 --index-url https://download.pytorch.org/whl/cu124
```

**CPU only (chậm):**
```bash
venv\Scripts\pip.exe install torch torchaudio
```

### Bước 3: Cài các package còn lại

```bash
venv\Scripts\pip.exe install -r requirements.txt
```

### Bước 4: Chuẩn bị file audio mẫu

Đặt file WAV giọng mẫu vào thư mục gốc, đặt tên `voice_sample.wav`.

Yêu cầu file audio:
- Định dạng: WAV (PCM)
- Sample rate: 16kHz hoặc 24kHz (tự động resample)
- Kênh: mono (stereo sẽ tự average)
- Thời lượng: 5-15 giây là tốt nhất
- Nội dung: giọng nói rõ ràng, ít tiếng ồn nền

### Bước 5: Cấu hình

Copy `.env.example` → `.env` và điền giá trị:

```bash
cp .env.example .env
```

```env
TTS_API_KEY=your-secret-key
TTS_REF_AUDIO=./voice_sample.wav
TTS_REF_TEXT=Nội dung text tương ứng với file audio mẫu
```

---

## Chạy

```bash
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8100
```

**Lần đầu chạy:** Model OmniVoice (~8GB) tự download từ HuggingFace. Chờ log:

```
OmniVoice ready in XX.Xs
VoiceClonePrompt ready in XX.Xs
Warmup done in XX.Xs — model ready for requests
```

Sau khi thấy `model ready for requests` thì service mới nhận request.

---

## API Reference

### GET /health

Kiểm tra trạng thái service và model.

**Response:**
```json
{
  "status": "ready",
  "device": "cuda:0",
  "cuda": true,
  "error": null,
  "ref_audio": "voice_sample.wav",
  "voice_prompt_ready": true,
  "auth_required": true
}
```

| Field | Mô tả |
|---|---|
| `status` | `"ready"` / `"loading"` / `"error"` |
| `device` | `"cuda:0"` hoặc `"cpu"` |
| `cuda` | GPU có sẵn không |
| `error` | Thông báo lỗi nếu model load thất bại |
| `voice_prompt_ready` | VoiceClonePrompt đã pre-compute xong chưa |
| `auth_required` | API key có được yêu cầu không |

---

### POST /synthesize

Tổng hợp giọng nói từ text.

**Header:**
```
X-TTS-API-Key: your-secret-key
```
*(Bỏ qua nếu `TTS_API_KEY` không được set)*

**Request body:**
```json
{
  "text": "Xin chào anh chị, tôi có thể giúp gì cho bạn?",
  "num_step": 32,
  "speed": 1.0
}
```

| Tham số | Kiểu | Mặc định | Mô tả |
|---|---|---|---|
| `text` | string | bắt buộc | Text cần đọc, tối đa 500 ký tự |
| `num_step` | int | `32` | Số bước diffusion. Cao hơn = chất lượng tốt hơn, chậm hơn. Dùng `16` để tăng tốc |
| `speed` | float | `1.0` | Tốc độ đọc. `0.85` = chậm, `1.0` = bình thường, `1.1` = nhanh |

**Response:**
- Content-Type: `audio/wav`
- Body: WAV bytes (PCM 24kHz mono)
- Header `X-Synthesis-Time`: thời gian xử lý (giây)
- Header `X-Text-Length`: độ dài text đầu vào

**Ví dụ với curl:**
```bash
curl -X POST http://localhost:8100/synthesize \
  -H "Content-Type: application/json" \
  -H "X-TTS-API-Key: your-secret-key" \
  -d '{"text": "Xin chào!", "num_step": 32, "speed": 1.0}' \
  --output output.wav
```

**Ví dụ với Python:**
```python
import httpx

resp = httpx.post(
    "http://localhost:8100/synthesize",
    json={"text": "Xin chào!", "num_step": 32, "speed": 1.0},
    headers={"X-TTS-API-Key": "your-secret-key"},
    timeout=30.0,
)
with open("output.wav", "wb") as f:
    f.write(resp.content)
```

**Ví dụ với JavaScript/fetch:**
```javascript
const resp = await fetch("http://localhost:8100/synthesize", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-TTS-API-Key": "your-secret-key",
  },
  body: JSON.stringify({ text: "Xin chào!", num_step: 32, speed: 1.0 }),
});
const audioBuffer = await resp.arrayBuffer();
// Phát audio qua Web Audio API
const ctx = new AudioContext();
const decoded = await ctx.decodeAudioData(audioBuffer);
const source = ctx.createBufferSource();
source.buffer = decoded;
source.connect(ctx.destination);
source.start();
```

---

## Tham số chất lượng (trong main.py)

Các tham số cố định trong `_synthesize_sync()` ảnh hưởng đến chất lượng âm thanh:

| Tham số | Giá trị | Mô tả |
|---|---|---|
| `guidance_scale` | `2.5` | Độ bám sát text. Tăng → rõ hơn nhưng cứng hơn. Giảm → tự nhiên hơn nhưng có thể sai từ |
| `class_temperature` | `0.3` | Độ ngẫu nhiên. `0` = greedy (đơn điệu), `1.0` = rất ngẫu nhiên |
| `postprocess_output` | `True` | Bật remove_silence + fade_and_pad. Tắt nếu muốn audio thô |
| `language` | `"vi"` | Ngôn ngữ. Đổi thành `"en"` cho tiếng Anh |

---

## Đổi giọng

Thay file `voice_sample.wav` bằng file audio giọng khác, cập nhật `TTS_REF_TEXT` tương ứng, rồi restart service.

Lưu ý: VoiceClonePrompt được pre-compute khi startup — mỗi lần đổi giọng cần restart.

---

## HTTP Status Codes

| Code | Mô tả |
|---|---|
| `200` | Thành công, trả về WAV bytes |
| `400` | Text rỗng hoặc không hợp lệ |
| `401` | API key sai hoặc thiếu |
| `500` | Lỗi model (xem field `error` trong `/health`) |
| `503` | Model đang load hoặc chưa sẵn sàng |

---

## Hiệu suất

Benchmark trên RTX 4060 8GB (CUDA 12.8, float16):

| num_step | Câu ngắn (~10 từ) | Câu dài (~30 từ) |
|---|---|---|
| 16 | ~0.8s | ~1.5s |
| 32 | ~1.5s | ~2.8s |

RTF (Real-Time Factor) ~0.1-0.3 — nhanh hơn realtime 3-10x.

---

## Tích hợp với backend khác

Service trả về WAV bytes thuần — tích hợp được với bất kỳ ngôn ngữ/framework nào hỗ trợ HTTP.

Proxy qua FastAPI backend:
```python
import httpx

async def call_tts(text: str, speed: float = 1.0) -> bytes:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "http://localhost:8100/synthesize",
            json={"text": text, "speed": speed, "num_step": 32},
            headers={"X-TTS-API-Key": "your-secret-key"},
        )
        resp.raise_for_status()
        return resp.content
```

---

## Tham khảo

- [OmniVoice model](https://huggingface.co/k2-fsa/OmniVoice)
- [OmniVoice source](https://github.com/k2-fsa/OmniVoice)
- [FastAPI docs](https://fastapi.tiangolo.com)
