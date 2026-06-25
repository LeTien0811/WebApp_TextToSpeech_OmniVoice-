# -*- coding: utf-8 -*-
import logging
import sys

# Định dạng hiển thị log rõ ràng, bao gồm thời gian, mức độ log, và nội dung thông điệp
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

def setup_logger(name: str = "OmniVoice_TTS") -> logging.Logger:
    """
    Cài đặt cấu hình Logger cho dự án.
    Trả về một thực thể Logger dùng chung để in thông tin ra màn hình.
    """
    logger = logging.getLogger(name)
    
    # Chỉ cấu hình nếu logger chưa có handler nào (tránh bị lặp lại log)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Cấu hình xuất ra console (stdout) sử dụng định dạng LOG_FORMAT
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        
        logger.addHandler(console_handler)
        # Ngăn không cho log bị ghi đè hay chuyển tiếp lên root logger một cách mất kiểm soát
        logger.propagate = False
        
    return logger

# Tạo sẵn một logger mặc định dùng chung toàn bộ hệ thống
logger = setup_logger()
