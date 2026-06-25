"""
OmniVoice TTS Microservice — standalone service for Vietnamese text-to-speech.

Chạy:
    python -m uvicorn main:app --host 0.0.0.0 --port 8100

Cấu hình chất lượng cao:
1. VoiceClonePrompt pre-computed 1 lần khi startup → tái sử dụng mọi request
2. language="vi" → model không cần tự detect ngôn ngữ
3. num_step=32 → default OmniVoice, chất lượng tốt hơn num_step=16 (~+1s/câu)
4. guidance_scale=2.5 → giọng rõ ràng, bám sát text
5. class_temperature=0.3 → thêm biến đổi tự nhiên
6. postprocess_output=True → remove_silence + fade_and_pad, tránh click/rè
"""
import asyncio
import io
import logging
import os
import time
from pathlib import Path
from typing import Optional

import torch
import torchaudio
from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="OmniVoice TTS Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── API Key ───────────────────────────────────────────────────────────────────
# Đặt TTS_API_KEY trong environment variable để bảo mật.
# Để trống → không cần auth (dev mode).
_API_KEY = os.getenv("TTS_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-TTS-API-Key", auto_error=False)


def verify_api_key(api_key: Optional[str] = Security(_api_key_header)):
    if not _API_KEY:
        return  # Dev mode
    if api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing TTS API key")


# ── Voice cloning config ──────────────────────────────────────────────────────
# Đặt đường dẫn đến file audio mẫu và text tương ứng
_REF_AUDIO = os.getenv("TTS_REF_AUDIO", str(Path(__file__).parent / "voice_sample.wav"))
_REF_TEXT  = os.getenv(
    "TTS_REF_TEXT",
    "Xin chào! Tôi là nhân viên hỗ trợ thủ tục hành chính. Tôi có thể giúp gì cho bạn hôm nay?"
)

# ── State ─────────────────────────────────────────────────────────────────────
_model = None
_voice_prompt = None
_model_error: Optional[str] = None
_model_loading = False

# Serialize GPU access — 1 request tại 1 thời điểm
_gpu_lock = asyncio.Lock()


def _load_model_sync():
    global _model, _voice_prompt, _model_error, _model_loading
    _model_loading = True
    t0 = time.time()
    try:
        from omnivoice import OmniVoice
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading OmniVoice on {device}...")
        _model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice",
            device_map=device,
            dtype=torch.float16 if device == "cuda:0" else torch.float32,
        )
        logger.info(f"OmniVoice ready in {time.time()-t0:.1f}s")

        logger.info("Pre-computing VoiceClonePrompt...")
        t1 = time.time()
        _voice_prompt = _model.create_voice_clone_prompt(
            ref_audio=_REF_AUDIO,
            ref_text=_REF_TEXT,
            preprocess_prompt=True,
        )
        logger.info(f"VoiceClonePrompt ready in {time.time()-t1:.1f}s")

        logger.info("Warming up model...")
        t2 = time.time()
        for warmup_text in [
            "Xin chào.",
            "Hồ sơ cần chuẩn bị gồm có đơn đề nghị, giấy chứng minh nhân dân và các giấy tờ liên quan.",
        ]:
            _model.generate(
                text=warmup_text,
                voice_clone_prompt=_voice_prompt,
                language="vi",
                num_step=32,
                speed=1.0,
                guidance_scale=2.5,
                class_temperature=0.3,
                postprocess_output=True,
            )
        logger.info(f"Warmup done in {time.time()-t2:.1f}s — model ready for requests")
    except Exception as e:
        _model_error = str(e)
        logger.error(f"Model load failed: {e}")
    finally:
        _model_loading = False


def _synthesize_sync(text: str, num_step: int, speed: float) -> bytes:
    audio_tensors = _model.generate(
        text=text,
        voice_clone_prompt=_voice_prompt,
        language="vi",
        num_step=num_step,
        speed=speed,
        guidance_scale=2.5,
        class_temperature=0.3,
        postprocess_output=True,
    )
    buf = io.BytesIO()
    torchaudio.save(buf, audio_tensors[0].cpu(), 24000, format="wav")
    buf.seek(0)
    return buf.read()


@app.on_event("startup")
async def startup():
    import threading
    threading.Thread(target=_load_model_sync, daemon=True).start()
    logger.info("TTS Service started. Model loading in background...")


class SynthesizeRequest(BaseModel):
    text: str
    num_step: int = 32
    speed: float = 1.0


@app.get("/health")
def health():
    status = "ready" if (_model and _voice_prompt) else ("loading" if _model_loading else "error")
    return {
        "status": status,
        "device": "cuda:0" if torch.cuda.is_available() else "cpu",
        "cuda": torch.cuda.is_available(),
        "error": _model_error,
        "ref_audio": Path(_REF_AUDIO).name,
        "voice_prompt_ready": _voice_prompt is not None,
        "auth_required": bool(_API_KEY),
    }


@app.post("/synthesize")
async def synthesize(req: SynthesizeRequest, _: None = Security(verify_api_key)):
    """
    Tổng hợp giọng nói từ text.
    - Header: X-TTS-API-Key (nếu TTS_API_KEY được set)
    - Body: { text, num_step, speed }
    - Response: audio/wav bytes
    """
    if _model_loading:
        raise HTTPException(503, "Model đang load, thử lại sau 30 giây")
    if _model_error:
        raise HTTPException(500, f"Model lỗi: {_model_error}")
    if _model is None or _voice_prompt is None:
        raise HTTPException(503, "Model chưa sẵn sàng")

    text = req.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Text không được để trống")

    t0 = time.time()
    logger.info(f"[queue] {text[:50]}...")

    async with _gpu_lock:
        logger.info(f"[gpu] synthesizing: {text[:50]}...")
        loop = asyncio.get_event_loop()
        wav_bytes = await loop.run_in_executor(
            None, _synthesize_sync, text, req.num_step, req.speed
        )

    elapsed = time.time() - t0
    logger.info(f"[done] {elapsed:.2f}s for {len(text)} chars")

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "X-Synthesis-Time": f"{elapsed:.2f}s",
            "X-Text-Length": str(len(text)),
        },
    )
