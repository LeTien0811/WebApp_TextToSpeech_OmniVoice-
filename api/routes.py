# -*- coding: utf-8 -*-
import os
import time
import json
import shutil
import asyncio
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Security, Depends
from fastapi.responses import Response, StreamingResponse
from fastapi.security import APIKeyHeader

from core.config import BASE_DIR, VOICES_DIR, TTS_API_KEY
from core.logger import logger
from api.schemas import SynthesizeRequest
from engines.downloader import check_models_exist, start_download, _download_state
from engines.omnivoice_lr import (
    get_model_status, 
    load_model_async, 
    unload_model, 
    generate_tts_async
)

# Khởi tạo API Router cho các endpoint
router = APIRouter(prefix="/api")

# Định nghĩa header bảo vệ API Key
_api_key_header = APIKeyHeader(name="X-TTS-API-Key", auto_error=False)

def verify_api_key(api_key: Optional[str] = Security(_api_key_header)):
    """
    Dependency kiểm tra quyền truy cập API qua API Key.
    Nếu cấu hình TTS_API_KEY trống thì bỏ qua kiểm tra (Dev Mode).
    """
    if not TTS_API_KEY:
        return
    if api_key != TTS_API_KEY:
        raise HTTPException(status_code=401, detail="API Key không chính xác hoặc bị thiếu")

# Tự động sao chép file voice mẫu mặc định vào thư mục voices/ nếu thư mục voices trống và file gốc tồn tại
# Giúp người dùng trải nghiệm ngay mà không cần cấu hình phức tạp
try:
    src_voice = BASE_DIR / "voice_sample.wav"
    dst_voice = VOICES_DIR / "voice_sample.wav"
    if src_voice.exists() and not dst_voice.exists():
        shutil.copy(src_voice, dst_voice)
        logger.info("Đã tự động chuẩn bị file voice_sample.wav mẫu vào thư mục voices/")
except Exception as e:
    logger.error(f"Lỗi khi tự động chuẩn bị file voice mặc định: {e}")

@router.get("/status")
def get_status():
    """
    Kiểm tra tình trạng toàn diện của hệ thống:
    - Model weights đã được tải về đầy đủ chưa.
    - Model đã được nạp (load) vào bộ nhớ RAM/VRAM chưa.
    - Thiết bị đang sử dụng (CUDA/CPU).
    """
    models_exist = check_models_exist()
    model_status = get_model_status()
    
    return {
        "models_exist": models_exist,
        "model_loaded": model_status["status"] == "ready",
        "model_status": model_status["status"],
        "device": model_status["device"],
        "cuda_available": model_status["cuda_available"],
        "error": model_status["error"]
    }

@router.get("/download/stream")
async def download_stream():
    """
    SSE Endpoint (Server-Sent Events) đẩy tiến độ tải xuống model thời gian thực về Client.
    Kích hoạt tải nền và stream dữ liệu JSON dạng text/event-stream mà KHÔNG cần client polling liên tục.
    """
    async def sse_event_generator():
        # Nếu model đã tồn tại sẵn từ trước, báo trạng thái hoàn thành ngay lập tức
        if check_models_exist():
            _download_state["status"] = "completed"
            _download_state["progress"] = 100.0
            _download_state["current_file"] = ""
            yield f"data: {json.dumps(_download_state)}\n\n"
            return

        # Bắt đầu kích hoạt tiến trình tải xuống nền (chỉ 1 tác vụ tải chạy nền duy nhất)
        await start_download()

        # Lặp vô hạn để theo dõi trạng thái tải và đẩy dữ liệu về cho client
        while True:
            # Tạo event SSE định dạng: data: <json_string>\n\n
            yield f"data: {json.dumps(_download_state)}\n\n"
            
            # Kết thúc stream nếu tải xong hoặc gặp lỗi
            if _download_state["status"] in ("completed", "failed"):
                break
                
            # Đợi 500ms trước khi gửi cập nhật tiếp theo để tiết kiệm băng thông mạng
            await asyncio.sleep(0.5)

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")

@router.post("/load")
async def load_model():
    """
    Nạp model vào RAM/VRAM bất đồng bộ.
    Yêu cầu model weights đã tải về đầy đủ trước đó.
    """
    # 1. Kiểm tra file model trên đĩa
    if not check_models_exist():
        raise HTTPException(
            status_code=400, 
            detail="Tập tin weights của model chưa được tải đầy đủ. Vui lòng tải trước."
        )
        
    status = get_model_status()
    if status["status"] == "ready":
        return {"status": "already_loaded", "detail": "Model đã được nạp sẵn."}
        
    try:
        # 2. Thực hiện nạp model bất đồng bộ
        await load_model_async()
        
        # 3. Kiểm tra lại kết quả nạp
        new_status = get_model_status()
        if new_status["status"] == "ready":
            return {"status": "success", "detail": "Nạp model vào VRAM thành công."}
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Nạp model thất bại: {new_status['error']}"
            )
    except Exception as e:
        logger.error(f"Lỗi khi gọi API load model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/unload")
def unload_model_route():
    """
    Giải phóng bộ nhớ GPU (VRAM) bằng cách hủy model và empty CUDA cache.
    Cực kỳ quan trọng để tránh lỗi OOM (Out Of Memory).
    """
    try:
        unload_model()
        return {"status": "success", "detail": "Đã giải phóng model khỏi bộ nhớ."}
    except Exception as e:
        logger.error(f"Lỗi khi giải phóng model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/voices")
def list_voices():
    """
    Trả về danh sách các tệp tin .wav mẫu giọng phục vụ clone giọng
    lấy từ thư mục voices/.
    """
    try:
        voices = [f.name for f in VOICES_DIR.glob("*.wav") if f.is_file()]
        return {"voices": sorted(voices)}
    except Exception as e:
        logger.error(f"Lỗi quét danh sách giọng mẫu: {e}")
        raise HTTPException(status_code=500, detail=f"Không thể lấy danh sách giọng mẫu: {e}")

@router.post("/generate")
async def generate_speech(req: SynthesizeRequest, _: None = Depends(verify_api_key)):
    """
    Thực hiện tổng hợp văn bản thành âm thanh tiếng Việt sử dụng OmniVoice.
    API sẽ trả về luồng dữ liệu WAV trực tiếp.
    """
    # 1. Đảm bảo model đã được load vào RAM/VRAM
    status = get_model_status()
    if status["status"] != "ready":
        raise HTTPException(
            status_code=400, 
            detail="Model chưa được nạp. Hãy nạp model trước khi sinh giọng nói."
        )
        
    try:
        logger.info(f"Đang sinh giọng cho văn bản dài {len(req.text)} ký tự...")
        t0 = time.time()
        
        # 2. Gọi tiến trình sinh âm thanh có khóa đồng bộ GPU
        wav_bytes = await generate_tts_async(
            text=req.text.strip(),
            voice_sample_name=req.voice_sample_name,
            num_step=req.num_step,
            speed=req.speed
        )
        
        elapsed = time.time() - t0
        logger.info(f"Sinh giọng nói thành công sau {elapsed:.2f} giây.")
        
        # 3. Trả về bytes âm thanh chất lượng cao định dạng audio/wav
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "X-Synthesis-Time": f"{elapsed:.2f}s",
                "X-Text-Length": str(len(req.text))
            }
        )
    except FileNotFoundError as fnf:
        # Nếu file audio mẫu không hợp lệ
        raise HTTPException(status_code=404, detail=str(fnf))
    except Exception as e:
        logger.error(f"Lỗi trong quá trình API sinh giọng: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống khi sinh giọng nói: {str(e)}")
