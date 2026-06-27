# -*- coding: utf-8 -*-
"""
OmniVoice TTS Web Application — Điểm khởi đầu chính của dịch vụ.
Chạy dịch vụ bằng lệnh:
    python -m uvicorn main:app --host 0.0.0.0 --port 8100
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from core.config import STATIC_DIR
from core.logger import logger
from api.routes import router as api_router

# Khởi tạo thực thể FastAPI với tiêu đề và mô tả mới
app = FastAPI(
    title="OmniVoice TTS Service", 
    description="Hệ thống tổng hợp giọng nói tiếng Việt và nhân bản giọng nói (Voice Cloning)", 
    version="1.1.0"
)

# Cấu hình CORS Middleware để cho phép gọi API từ mọi nguồn gốc (Origins),
# cực kỳ hữu ích cho việc phát triển và tích hợp hệ thống
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký router API chứa các endpoint /api/status, /api/download, /api/load, /api/generate
app.include_router(api_router)

# Mount static outputs and assets under /static prefix to avoid 404 Not Found errors
app.mount("/static", StaticFiles(directory=str(STATIC_DIR.resolve())), name="static_media")

# Mount thư mục chứa các tệp giao diện tĩnh (HTML/CSS/JS) lên đường dẫn gốc '/'
# Cấu hình html=True giúp tự động trả về file index.html khi người dùng truy cập địa chỉ gốc.
logger.info(f"Mounting static files from: {STATIC_DIR.resolve()}")
app.mount("/", StaticFiles(directory=str(STATIC_DIR.resolve()), html=True), name="static")

@app.on_event("startup")
def startup_event():
    """
    Sự kiện kích hoạt khi server FastAPI bắt đầu khởi động.
    """
    logger.info("OmniVoice TTS Web App started successfully on port 8100!")
    logger.info("Management UI: http://localhost:8100")
