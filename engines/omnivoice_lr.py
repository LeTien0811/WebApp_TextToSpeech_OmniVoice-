# -*- coding: utf-8 -*-
import os
import gc
import time
import asyncio
import torch
import torchaudio
import io
from pathlib import Path
from typing import Optional, Dict

from core.config import MODELS_DIR, VOICES_DIR, TTS_REF_AUDIO_PATH, TTS_REF_TEXT
from core.logger import logger
from engines.downloader import check_models_exist

# Các biến trạng thái toàn cục điều khiển model
_model = None                      # Thực thể model OmniVoice sau khi load
_model_loaded = False              # Đánh dấu model đã load thành công hay chưa
_model_loading = False             # Đánh dấu đang trong quá trình load
_load_error: Optional[str] = None  # Ghi nhận lỗi nếu load thất bại

# Cache lưu trữ các VoiceClonePrompt đã được tính toán sẵn cho từng file giọng mẫu
# Nhằm tránh tính toán lại (tốn ~200-500ms) khi gọi nhiều lần cùng một giọng mẫu
_voice_prompt_cache: Dict[str, any] = {}

# Lock bất đồng bộ để tuần tự hóa quyền truy cập vào GPU (tránh việc nhiều request chạy đồng thời gây lỗi VRAM/OOM)
_gpu_lock = asyncio.Lock()

def get_model_status() -> dict:
    """
    Trả về trạng thái hiện tại của model: Đã sẵn sàng chưa, đang load, có lỗi gì không, sử dụng thiết bị nào.
    """
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    status = "ready" if _model_loaded else ("loading" if _model_loading else ("error" if _load_error else "not_loaded"))
    return {
        "status": status,
        "device": device,
        "cuda_available": torch.cuda.is_available(),
        "error": _load_error
    }

def _load_model_sync():
    """
    Hàm đồng bộ thực hiện việc tải model thực tế từ thư mục models/.
    """
    global _model, _model_loaded, _model_loading, _load_error, _voice_prompt_cache
    
    t0 = time.time()
    _model_loading = True
    _load_error = None
    
    try:
        # Kiểm tra sự tồn tại của các file model trước khi load
        if not check_models_exist():
            raise FileNotFoundError("Thư mục models/ chưa chứa đầy đủ file weights của OmniVoice. Vui lòng tải xuống trước.")
            
        from omnivoice import OmniVoice
        
        # Quyết định thiết bị chạy (ưu tiên CUDA/GPU)
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda:0" else torch.float32
        
        logger.info(f"Đang tải OmniVoice từ đường dẫn: {MODELS_DIR} lên thiết bị {device}...")
        
        # Load model từ thư mục models tuyệt đối cục bộ đã tải
        _model = OmniVoice.from_pretrained(
            str(MODELS_DIR.resolve()),
            device_map=device,
            dtype=dtype
        )
        logger.info(f"Đã tải OmniVoice thành công trong {time.time() - t0:.2f} giây.")
        
        # Khởi chạy một warmup nhẹ để ép PyTorch biên dịch CUDA kernels trước
        logger.info("Đang chạy warmup model với câu chào ngắn...")
        # Sử dụng audio mẫu mặc định để warmup
        if os.path.exists(TTS_REF_AUDIO_PATH):
            logger.info(f"Tính toán prompt warmup với giọng mặc định: {TTS_REF_AUDIO_PATH}")
            warmup_prompt = _model.create_voice_clone_prompt(
                ref_audio=TTS_REF_AUDIO_PATH,
                ref_text=TTS_REF_TEXT,
                preprocess_prompt=True
            )
            # Lưu luôn vào cache để tái sử dụng
            _voice_prompt_cache[Path(TTS_REF_AUDIO_PATH).name] = warmup_prompt
            
            # Thực hiện generate warmup
            _model.generate(
                text="Xin chào.",
                voice_clone_prompt=warmup_prompt,
                language="vi",
                num_step=16, # Warmup nhanh với 16 bước
                speed=1.0,
                postprocess_output=True
            )
            logger.info("Hoàn thành warmup. Model đã sẵn sàng phục vụ các yêu cầu thực tế.")
        else:
            logger.warning("Không tìm thấy file voice mẫu mặc định để chạy warmup.")
            
        _model_loaded = True
        
    except Exception as e:
        _load_error = str(e)
        _model_loaded = False
        _model = None
        logger.error(f"Lỗi khi load model OmniVoice: {e}")
    finally:
        _model_loading = False

async def load_model_async():
    """
    Tải model OmniVoice bất đồng bộ sử dụng run_in_executor của event loop,
    giúp giữ luồng chính FastAPI luôn mượt mà.
    """
    global _model_loading
    if _model_loaded:
        return
    if _model_loading:
        # Nếu đang load rồi thì đợi
        while _model_loading:
            await asyncio.sleep(0.5)
        return
        
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _load_model_sync)

def unload_model():
    """
    Hủy model OmniVoice giải phóng VRAM của GPU và RAM của hệ thống một cách triệt để.
    """
    global _model, _model_loaded, _voice_prompt_cache, _load_error
    
    logger.info("Đang thực hiện giải phóng model OmniVoice và thu hồi bộ nhớ...")
    _model = None
    _model_loaded = False
    _voice_prompt_cache.clear()
    _load_error = None
    
    # Gọi bộ dọn rác hệ thống (Garbage Collector) của Python
    gc.collect()
    
    # Giải phóng cache VRAM của CUDA
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        logger.info("Đã làm sạch CUDA VRAM cache.")
    else:
        logger.info("Không phát hiện GPU CUDA, bỏ qua giải phóng VRAM.")

def _get_voice_clone_prompt(voice_sample_name: str):
    """
    Lấy prompt clone giọng từ cache hoặc tính toán mới từ file âm thanh mẫu trong thư mục voices/.
    """
    global _voice_prompt_cache
    
    # Nếu đã tồn tại trong cache, trả về ngay lập tức
    if voice_sample_name in _voice_prompt_cache:
        return _voice_prompt_cache[voice_sample_name]
        
    # Xác định đường dẫn file âm thanh mẫu tuyệt đối
    voice_path = VOICES_DIR / voice_sample_name
    if not voice_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file audio mẫu giọng: {voice_sample_name}")
        
    # Xác định text phiên âm tương ứng
    # Quy tắc: nếu có file trùng tên đuôi .txt (ví dụ: sample1.txt cùng sample1.wav), đọc text từ đó.
    # Ngược lại, fallback về TTS_REF_TEXT mặc định.
    txt_path = voice_path.with_suffix(".txt")
    if txt_path.exists():
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                ref_text = f.read().strip()
                logger.info(f"Đọc thành công text phiên âm riêng từ {txt_path.name}")
        except Exception as e:
            logger.warning(f"Lỗi khi đọc file text phiên âm {txt_path.name}: {e}. Fallback về text mặc định.")
            ref_text = TTS_REF_TEXT
    else:
        ref_text = TTS_REF_TEXT
        
    logger.info(f"Đang sinh VoiceClonePrompt cho giọng {voice_sample_name}...")
    t_start = time.time()
    
    # Gọi hàm nội bộ của OmniVoice để sinh prompt
    prompt = _model.create_voice_clone_prompt(
        ref_audio=str(voice_path.resolve()),
        ref_text=ref_text,
        preprocess_prompt=True
    )
    
    logger.info(f"Đã sinh xong VoiceClonePrompt trong {time.time() - t_start:.2f} giây.")
    
    # Lưu vào cache để tái sử dụng
    _voice_prompt_cache[voice_sample_name] = prompt
    return prompt

def _synthesize_sync(text: str, voice_sample_name: str, num_step: int, speed: float) -> bytes:
    """
    Hàm xử lý đồng bộ việc chạy inference của model để sinh giọng nói từ văn bản.
    """
    if not _model_loaded or _model is None:
        raise RuntimeError("Model OmniVoice chưa được load vào bộ nhớ. Vui lòng load trước.")
        
    # Lấy prompt clone giọng tương ứng
    prompt = _get_voice_clone_prompt(voice_sample_name)
    
    # Đảm bảo văn bản đầu vào có khoảng trống đệm ở đầu/cuối để mô hình ổn định hơn khi khởi tạo phát âm,
    # tránh hiện tượng nuốt chữ/mất từ đầu tiên (đặc biệt hữu ích khi tách đoạn/câu nhỏ).
    processed_text = " " + text.strip() + " "
    
    # Sinh tensor âm thanh từ văn bản đầu vào
    audio_tensors = _model.generate(
        text=processed_text,
        voice_clone_prompt=prompt,
        language="vi",            # Cố định ngôn ngữ tiếng Việt để tăng độ chính xác
        num_step=num_step,
        speed=speed,
        guidance_scale=2.5,       # Cấu hình chất lượng cao để giọng đọc bám sát chữ
        class_temperature=0.3,    # Thêm chút biến đổi tự nhiên
        postprocess_output=True   # Loại bỏ im lặng thừa, fade và pad âm thanh tránh rè
    )
    
    # Ghi dữ liệu âm thanh thành định dạng WAV PCM 16-bit sử dụng module wave tích hợp của Python.
    # Bằng cách này ta hoàn toàn độc lập với các backend phức tạp như torchaudio.save, torchcodec hay ffmpeg.
    import numpy as np
    import wave
    
    # Chuyển đổi dữ liệu sang numpy array để xử lý
    audio_data = audio_tensors[0]
    if isinstance(audio_data, torch.Tensor):
        audio_np = audio_data.cpu().numpy()
    else:
        audio_np = audio_data
        
    # Đảm bảo mảng là 2D (channels, samples)
    if audio_np.ndim == 1:
        audio_np = np.expand_dims(audio_np, axis=0)
        
    # Chuẩn hóa biên độ âm thanh về khoảng [-1.0, 1.0] để tránh rè (clipping)
    audio_np = np.clip(audio_np, -1.0, 1.0)
    # Chuyển sang định dạng số nguyên 16-bit (PCM 16-bit)
    audio_int16 = (audio_np * 32767.0).astype(np.int16)
    
    # Tự động chèn thêm khoảng im lặng ngắn (~100ms ở đầu, ~50ms ở cuối) để trình duyệt/máy phát
    # không bị cắt cụt mất từ đầu tiên khi phát âm thanh (do độ trễ phần cứng âm thanh hoặc cơ chế fade-in).
    # Với tần số lấy mẫu 24kHz, 100ms tương đương 2400 samples, 50ms tương đương 1200 samples.
    silence_start_samples = 2400
    silence_end_samples = 1200
    n_channels = audio_int16.shape[0]
    
    silence_start = np.zeros((n_channels, silence_start_samples), dtype=np.int16)
    silence_end = np.zeros((n_channels, silence_end_samples), dtype=np.int16)
    
    audio_int16 = np.concatenate((silence_start, audio_int16, silence_end), axis=1)
    
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav_file:
        n_channels = audio_int16.shape[0]
        wav_file.setnchannels(n_channels)
        wav_file.setsampwidth(2) # 2 bytes = 16-bit
        wav_file.setframerate(24000) # Tần số lấy mẫu của OmniVoice là 24kHz
        
        # Nếu chỉ có 1 kênh (Mono), ghi trực tiếp bytes
        if n_channels == 1:
            wav_file.writeframes(audio_int16.tobytes())
        else:
            # Nếu có nhiều kênh, xếp chồng xen kẽ các kênh (interleaved)
            interleaved = audio_int16.T.flatten()
            wav_file.writeframes(interleaved.tobytes())
            
    buf.seek(0)
    return buf.read()

async def generate_tts_async(text: str, voice_sample_name: str, num_step: int, speed: float) -> bytes:
    """
    Wrapper bất đồng bộ cho tiến trình sinh âm thanh (inference), sử dụng khóa tuần tự GPU.
    """
    # Đảm bảo tại một thời điểm chỉ có 1 request được truy cập GPU để tránh tràn VRAM
    async with _gpu_lock:
        loop = asyncio.get_event_loop()
        # Chạy inference trên luồng riêng để tránh blocking event loop của FastAPI
        wav_bytes = await loop.run_in_executor(
            None, _synthesize_sync, text, voice_sample_name, num_step, speed
        )
        return wav_bytes
