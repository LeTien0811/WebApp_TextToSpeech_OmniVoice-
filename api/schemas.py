# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field

class SynthesizeRequest(BaseModel):
    """
    Schema xác thực dữ liệu đầu vào khi người dùng yêu cầu tổng hợp giọng nói.
    """
    text: str = Field(
        ..., 
        description="Đoạn văn bản cần chuyển thành giọng nói, tối đa 500 ký tự",
        min_length=1,
        max_length=500
    )
    voice_sample_name: str = Field(
        "voice_sample.wav", 
        description="Tên file audio mẫu giọng lưu trong thư mục voices/ dùng để clone"
    )
    num_step: int = Field(
        32, 
        ge=8, 
        le=64, 
        description="Số bước diffusion. Càng cao giọng đọc càng chất lượng nhưng xử lý lâu hơn"
    )
    speed: float = Field(
        1.0, 
        ge=0.5, 
        le=2.0, 
        description="Tốc độ đọc giọng nói (0.5: chậm, 1.0: bình thường, 2.0: nhanh)"
    )
