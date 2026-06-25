# -*- coding: utf-8 -*-
import os
import time
import asyncio
import httpx
from pathlib import Path
from core.config import MODELS_DIR
from core.logger import logger

# Danh sách toàn bộ các file của repo k2-fsa/OmniVoice cần tải để model chạy offline tự quản lý hoàn toàn
FILES_TO_DOWNLOAD = [
    (".gitattributes", 1570),
    ("README.md", 9270),
    ("audio_tokenizer/.gitattributes", 1519),
    ("audio_tokenizer/LICENSE", 9171),
    ("audio_tokenizer/README.md", 5174),
    ("audio_tokenizer/config.json", 2531),
    ("audio_tokenizer/model.safetensors", 805665628),
    ("audio_tokenizer/preprocessor_config.json", 206),
    ("chat_template.jinja", 4168),
    ("config.json", 2238),
    ("model.safetensors", 2450344112),
    ("tokenizer.json", 11423986),
    ("tokenizer_config.json", 533),
]

# Tổng số dung lượng của tất cả các file cần tải (~3.27 GB)
TOTAL_BYTES = sum(size for _, size in FILES_TO_DOWNLOAD)

# Khởi tạo trạng thái tải xuống mặc định
_download_state = {
    "status": "idle",           # Trạng thái: idle (rảnh), downloading (đang tải), completed (hoàn thành), failed (lỗi)
    "progress": 0.0,            # Tiến độ tải xuống (%)
    "speed": 0.0,               # Tốc độ tải xuống (MB/s)
    "eta": 0,                   # Thời gian dự kiến hoàn thành còn lại (giây)
    "current_file": "",         # Tên file hiện tại đang được tải xuống
    "downloaded_bytes": 0,      # Tổng số bytes đã tải (bao gồm cả dữ liệu cũ đã có trên disk)
    "total_bytes": TOTAL_BYTES, # Tổng dung lượng toàn bộ model
    "error": None               # Thông tin lỗi nếu quá trình tải thất bại
}

# Khóa để đồng bộ hóa quá trình tải, tránh việc kích hoạt nhiều luồng tải đồng thời
_download_lock = asyncio.Lock()
# Tác vụ tải xuống chạy nền bằng asyncio
_download_task = None

def check_models_exist() -> bool:
    """
    Hàm kiểm tra xem toàn bộ các file model cần thiết đã được tải và tồn tại đầy đủ
    trên đĩa cứng với kích thước chính xác chưa.
    """
    for filename, expected_size in FILES_TO_DOWNLOAD:
        local_path = MODELS_DIR / filename
        if not local_path.exists() or local_path.stat().st_size != expected_size:
            return False
    return True

def calculate_initial_progress():
    """
    Quét qua thư mục models để tính toán dung lượng hiện tại đã tải xuống trên đĩa.
    Giúp khởi động tiến trình tải tiếp tục mà không cần tính lại từ 0%.
    """
    downloaded = 0
    for filename, expected_size in FILES_TO_DOWNLOAD:
        local_path = MODELS_DIR / filename
        if local_path.exists():
            size = local_path.stat().st_size
            # Nếu dung lượng file hiện tại hợp lệ (bé hơn hoặc bằng file thật)
            if size <= expected_size:
                downloaded += size
            else:
                # Nếu file lớn hơn dự kiến (bị lỗi ghi đè dư), coi như chưa tải để viết đè
                pass
    _download_state["downloaded_bytes"] = downloaded
    _download_state["progress"] = round((downloaded / TOTAL_BYTES) * 100, 2)
    logger.info(f"Đã quét thư mục models: ban đầu có sẵn {downloaded}/{TOTAL_BYTES} bytes ({_download_state['progress']}%)")

async def download_model_task():
    """
    Tiến trình tải model bất đồng bộ chạy nền, tích hợp cơ chế Range Request để Resume.
    """
    global _download_state
    
    # Thiết lập trạng thái ban đầu là đang tải xuống
    _download_state["status"] = "downloading"
    _download_state["error"] = None
    
    # Tính toán trước lượng dữ liệu đã có sẵn trên đĩa
    calculate_initial_progress()
    
    start_time = time.time()
    session_downloaded = 0  # Lượng bytes tải được trong phiên (session) này để tính tốc độ
    
    # Sử dụng httpx.AsyncClient hỗ trợ tự động follow redirect của Hugging Face
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        try:
            for filename, expected_size in FILES_TO_DOWNLOAD:
                _download_state["current_file"] = filename
                local_path = MODELS_DIR / filename
                
                # Tạo thư mục cha của file nếu chưa có (ví dụ: audio_tokenizer/)
                local_path.parent.mkdir(parents=True, exist_ok=True)
                
                local_size = local_path.stat().st_size if local_path.exists() else 0
                
                # Nếu file đã được tải đầy đủ kích thước, bỏ qua không tải lại
                if local_size == expected_size:
                    logger.info(f"File {filename} đã đầy đủ. Bỏ qua tải xuống.")
                    continue
                
                # Nếu file hiện tại lớn hơn size dự kiến, xóa đi để tải lại từ đầu
                if local_size > expected_size:
                    logger.warning(f"File {filename} bị dư dung lượng ({local_size} > {expected_size}). Xóa để tải lại.")
                    local_path.unlink(missing_ok=True)
                    local_size = 0
                
                # URL tải trực tiếp từ Hugging Face Hub
                url = f"https://huggingface.co/k2-fsa/OmniVoice/resolve/main/{filename}"
                headers = {}
                write_mode = "wb"
                
                # Nếu đã có dữ liệu một phần, cấu hình headers Range để tải tiếp (resume)
                if local_size > 0:
                    headers["Range"] = f"bytes={local_size}-"
                    write_mode = "ab"  # Chế độ ghi nối tiếp (append binary)
                    logger.info(f"Yêu cầu tải tiếp file {filename} từ byte {local_size}...")
                else:
                    logger.info(f"Bắt đầu tải file {filename} mới hoàn toàn...")
                
                # Bắt đầu stream dữ liệu bất đồng bộ từ HTTP server
                async with client.stream("GET", url, headers=headers) as response:
                    # Kiểm tra mã phản hồi HTTP
                    # 206: Hỗ trợ Range (Partial Content)
                    # 200: Không hỗ trợ Range hoặc tải từ đầu
                    if response.status_code not in (200, 206):
                        raise httpx.HTTPStatusError(
                            f"HTTP lỗi {response.status_code} khi tải {filename}",
                            request=response.request,
                            response=response
                        )
                    
                    # Nếu server không đồng ý ghi nối tiếp (trả về 200 thay vì 206), phải viết đè từ đầu
                    if response.status_code == 200 and write_mode == "ab":
                        logger.warning(f"Server không hỗ trợ Resume cho {filename}. Tải lại từ đầu.")
                        # Reset lại số bytes đã tính trước cho file này trong tiến trình tổng
                        _download_state["downloaded_bytes"] -= local_size
                        write_mode = "wb"
                        local_size = 0
                    
                    # Tiến hành mở file để ghi dữ liệu nhị phân
                    with open(local_path, write_mode) as f:
                        # Đọc dữ liệu theo từng chunk 1MB để tránh tràn bộ nhớ RAM
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                            # Ghi chunk nhị phân vào đĩa
                            f.write(chunk)
                            chunk_len = len(chunk)
                            
                            # Cập nhật số liệu tiến trình
                            _download_state["downloaded_bytes"] += chunk_len
                            session_downloaded += chunk_len
                            
                            # Tính phần trăm hoàn thành tổng thể
                            pct = (_download_state["downloaded_bytes"] / TOTAL_BYTES) * 100
                            _download_state["progress"] = round(pct, 2)
                            
                            # Tính tốc độ trung bình dựa trên thời gian trôi qua của phiên tải hiện tại
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                speed_bps = session_downloaded / elapsed
                                _download_state["speed"] = round(speed_bps / (1024 * 1024), 2)  # chuyển sang MB/s
                                
                                # Tính thời gian hoàn thành dự kiến (ETA)
                                remaining = TOTAL_BYTES - _download_state["downloaded_bytes"]
                                if _download_state["speed"] > 0:
                                    _download_state["eta"] = int(remaining / speed_bps)
                                else:
                                    _download_state["eta"] = 0
                            
                            # Trả quyền điều khiển cho event loop để tránh block FastAPI thread
                            await asyncio.sleep(0.001)
                            
            # Kết thúc thành công toàn bộ danh sách file
            _download_state["status"] = "completed"
            _download_state["current_file"] = ""
            _download_state["speed"] = 0.0
            _download_state["eta"] = 0
            logger.info("Tải xuống toàn bộ model weights của OmniVoice thành công!")
            
        except Exception as e:
            # Ghi nhận lỗi và đổi trạng thái tải
            _download_state["status"] = "failed"
            _download_state["error"] = str(e)
            logger.error(f"Lỗi xảy ra trong quá trình tải model: {e}")

async def start_download() -> bool:
    """
    Kích hoạt tiến trình tải xuống nền nếu nó chưa chạy.
    Trả về True nếu bắt đầu thành công hoặc đang chạy, ngược lại là False.
    """
    global _download_task
    
    async with _download_lock:
        # Nếu đang tải rồi thì không khởi chạy thêm task khác
        if _download_state["status"] == "downloading":
            return True
            
        # Khởi tạo một task chạy nền mới của asyncio
        _download_task = asyncio.create_task(download_model_task())
        return True
