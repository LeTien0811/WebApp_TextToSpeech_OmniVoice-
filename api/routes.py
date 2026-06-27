# -*- coding: utf-8 -*-
import os
import time
import json
import shutil
import asyncio
from datetime import datetime
import uuid
import io
from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, HTTPException, Security, Depends, Request, Form, File, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.security import APIKeyHeader
from pydub import AudioSegment
import lameenc

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
from engines.text_splitter import split_vietnamese_text

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
    import sys
    dst_voice = VOICES_DIR / "voice_sample.wav"
    if not dst_voice.exists():
        # Danh sách các đường dẫn nguồn tiềm năng để tìm file voice mặc định
        potential_srcs = [
            BASE_DIR / "voice_sample.wav",
            BASE_DIR / "voices" / "voice_sample.wav"
        ]
        # Nếu chạy dạng PyInstaller frozen, thêm các đường dẫn trong thư mục tạm sys._MEIPASS
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            meipass_path = Path(sys._MEIPASS)
            potential_srcs.append(meipass_path / "voice_sample.wav")
            potential_srcs.append(meipass_path / "voices" / "voice_sample.wav")
            
        # Tìm file nguồn đầu tiên tồn tại
        found_src = None
        for src in potential_srcs:
            if src.exists() and src.resolve() != dst_voice.resolve():
                found_src = src
                break
                
        if found_src:
            shutil.copy(found_src, dst_voice)
            logger.info(f"Đã tự động chuẩn bị file voice_sample.wav mẫu từ {found_src.name} vào thư mục voices/")
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

# Khởi tạo các thư mục lưu trữ tệp đầu ra tĩnh và cấu hình tác vụ
OUTPUTS_DIR = Path(BASE_DIR) / "static" / "outputs"
TASKS_DIR = OUTPUTS_DIR / "tasks"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
TASKS_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/generate-long-text/init")
async def generate_long_text_init(
    text: Optional[str] = Form(None, description="Đoạn văn bản dài dạng chuỗi"),
    file: Optional[UploadFile] = File(None, description="Tệp tin văn bản .txt"),
    voice_sample_name: str = Form("voice_sample.wav"),
    num_step: int = Form(16),  # Mặc định dùng 16 bước cho văn bản dài nhằm tối ưu hiệu năng
    speed: float = Form(1.0),
    silence_duration: int = Form(300)
):
    """
    Tiếp nhận văn bản dài (qua form thô hoặc file upload .txt).
    Sinh task_id và lưu cấu hình tạm xuống đĩa. Trả về ngay lập tức để UI mở kết nối SSE.
    """
    # 1. Thu thập văn bản đầu vào
    if file:
        try:
            content_bytes = await file.read()
            input_text = content_bytes.decode("utf-8").strip()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Không thể đọc file văn bản tải lên: {e}")
    elif text:
        input_text = text.strip()
    else:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp văn bản hoặc tải lên tệp tin .txt")
        
    if not input_text:
        raise HTTPException(status_code=400, detail="Văn bản đầu vào trống.")
        
    # 2. Đảm bảo model đã sẵn sàng trước khi tiếp tục
    status = get_model_status()
    if status["status"] != "ready":
        raise HTTPException(
            status_code=400, 
            detail="Model chưa được nạp. Hãy nạp model trên bảng điều khiển trước."
        )

    # 3. Tạo task_id kết hợp ngày giờ tạo để người dùng dễ đọc và 4 ký tự ngẫu nhiên tránh trùng lặp
    task_id = f"sachnoi_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    config_data = {
        "text": input_text,
        "voice_sample_name": voice_sample_name,
        "num_step": num_step,
        "speed": speed,
        "silence_duration": silence_duration
    }
    
    config_path = TASKS_DIR / f"{task_id}_config.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Không thể ghi cấu hình tác vụ: {e}")
        raise HTTPException(status_code=500, detail="Lỗi hệ thống khi tạo cấu hình tác vụ.")
        
    logger.info(f"Đã tạo tác vụ văn bản dài: {task_id} (Độ dài: {len(input_text)} ký tự)")
    return {"task_id": task_id, "status": "initialized"}

@router.get("/generate-long-text/stream/{task_id}")
async def generate_long_text_stream(task_id: str, request: Request):
    """
    Endpoint SSE (Server-Sent Events) đẩy tiến trình tổng hợp về Client thời gian thực.
    Đọc câu -> Inference GPU -> Mã hóa MP3 ngay lập tức -> Ghi nhị phân nối tiếp ("ab") -> Giải phóng RAM.
    """
    config_path = TASKS_DIR / f"{task_id}_config.json"
    
    async def sse_event_generator():
        # 1. Đọc tệp cấu hình tạm thời
        if not config_path.exists():
            yield f"data: {json.dumps({'status': 'failed', 'error': 'Không tìm thấy thông tin tác vụ.'}, ensure_ascii=False)}\n\n"
            return
            
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            yield f"data: {json.dumps({'status': 'failed', 'error': f'Lỗi đọc cấu hình: {e}'}, ensure_ascii=False)}\n\n"
            return
            
        input_text = config["text"]
        voice_sample_name = config["voice_sample_name"]
        num_step = config["num_step"]
        speed = config["speed"]
        silence_duration = config["silence_duration"]
        
        # 2. Phân tách câu thông minh tránh tràn ngữ cảnh VRAM
        chunks = split_vietnamese_text(input_text)
        total_chunks = len(chunks)
        
        if total_chunks == 0:
            yield f"data: {json.dumps({'status': 'failed', 'error': 'Văn bản không chứa nội dung hợp lệ để xử lý.'}, ensure_ascii=False)}\n\n"
            return
            
        logger.info(f"Bắt đầu stream SSE cho task {task_id}. Tổng số chunks: {total_chunks}")
        
        # Đường dẫn tệp tin MP3 đầu ra và dọn dẹp nếu có sẵn
        mp3_path = OUTPUTS_DIR / f"{task_id}.mp3"
        if mp3_path.exists():
            try:
                mp3_path.unlink()
            except Exception:
                pass
                
        # Khởi tạo khoảng lặng nghỉ giữa các chunk bằng pydub (WAV 24kHz Mono 16-bit)
        silence_segment = AudioSegment.silent(duration=silence_duration, frame_rate=24000)
        
        # Đánh dấu dọn dẹp file MP3 dở dang nếu xảy ra lỗi
        should_cleanup_mp3 = True
        
        try:
            # Gửi sự kiện bắt đầu xử lý
            yield f"data: {json.dumps({'status': 'processing', 'progress': 0.0, 'completed_chunks': 0, 'total_chunks': total_chunks}, ensure_ascii=False)}\n\n"
            
            # 3. Vòng lặp xử lý tuần tự từng chunk
            for idx, chunk in enumerate(chunks):
                # Kiểm tra kết nối Client
                if await request.is_disconnected():
                    logger.warning(f"Client ngắt kết nối SSE đối với task {task_id}. Hủy xử lý ngay lập tức.")
                    break
                    
                # A. Inference sinh WAV bytes
                wav_bytes = await generate_tts_async(
                    text=chunk,
                    voice_sample_name=voice_sample_name,
                    num_step=num_step,
                    speed=speed
                )
                
                # B. Ghép khoảng lặng bằng pydub (WAV thuần Python) và trích xuất raw PCM
                chunk_audio = AudioSegment.from_wav(io.BytesIO(wav_bytes))
                combined_chunk = chunk_audio + silence_segment
                
                raw_pcm = combined_chunk.raw_data
                channels = combined_chunk.channels
                sample_rate = combined_chunk.frame_rate
                
                # C. Mã hóa sang MP3 bằng lameenc ngay trong RAM
                encoder = lameenc.Encoder()
                encoder.set_bit_rate(128)
                encoder.set_in_sample_rate(sample_rate)
                encoder.set_channels(channels)
                encoder.set_quality(2)
                
                mp3_bytes = encoder.encode(raw_pcm)
                mp3_bytes += encoder.flush()
                
                # D. Mở ghi nối tiếp nhị phân ("ab") và lưu xuống đĩa
                with open(mp3_path, "ab") as mp3_file:
                    mp3_file.write(mp3_bytes)
                    
                # E. Giải phóng RAM lập tức bằng cách thu hồi biến tạm
                wav_bytes = None
                chunk_audio = None
                combined_chunk = None
                raw_pcm = None
                mp3_bytes = None
                
                # F. yield tiến trình về UI
                progress = round(((idx + 1) / total_chunks) * 100, 1)
                yield f"data: {json.dumps({'status': 'processing', 'progress': progress, 'completed_chunks': idx + 1, 'total_chunks': total_chunks}, ensure_ascii=False)}\n\n"
                
            else:
                # Xử lý thành công toàn bộ, không bị ngắt quãng
                should_cleanup_mp3 = False
                # Đợi một chút để hệ thống tệp giải phóng I/O và đóng file hoàn toàn
                await asyncio.sleep(0.8)
                yield f"data: {json.dumps({'status': 'completed', 'progress': 100.0, 'download_url': f'/static/outputs/{task_id}.mp3'}, ensure_ascii=False)}\n\n"
                logger.info(f"Task {task_id} hoàn tất thành công. File MP3 đã được xuất.")
                
        except Exception as e:
            # Gửi thông điệp FATAL_ERROR cho UI để thông báo và dừng ngay
            logger.error(f"Lỗi nghiêm trọng trong quá trình xử lý Task {task_id}: {e}")
            yield f"data: {json.dumps({'status': 'failed', 'error': f'FATAL_ERROR: {str(e)}'}, ensure_ascii=False)}\n\n"
            
        finally:
            # Dọn dẹp tài nguyên
            # Xóa file cấu hình tạm
            if config_path.exists():
                try:
                    config_path.unlink()
                except Exception as ex:
                    logger.error(f"Không thể xóa file cấu hình tạm: {ex}")
            # Nếu tiến trình bị lỗi/ngắt giữa chừng, xóa tệp tin MP3 bị lỗi
            if should_cleanup_mp3 and mp3_path.exists():
                try:
                    mp3_path.unlink()
                    logger.info(f"Đã xóa tệp MP3 dở dang của task {task_id}")
                except Exception as ex:
                    logger.error(f"Lỗi khi xóa tệp MP3 dở dang: {ex}")

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")

