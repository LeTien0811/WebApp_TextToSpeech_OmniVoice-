# Sử dụng Python 3.11-slim làm base image để giảm dung lượng
FROM python:3.11-slim

# Thiết lập thư mục làm việc trong container
WORKDIR /app

# Thiết lập các biến môi trường để Python chạy mượt mà trong Docker
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Cài đặt các thư viện hệ thống cần thiết cho âm thanh và Git
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libsndfile1 \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements.txt vào trước để tận dụng Docker cache cho pip install
COPY requirements.txt .

# Nâng cấp pip và cài đặt PyTorch, Torchaudio
# Mặc định cài bản CPU để nhẹ và tương thích cao nhất.
# NẾU MUỐN DÙNG GPU CUDA (yêu cầu host có NVIDIA Container Toolkit), hãy đổi dòng dưới thành:
# RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu121
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Cài đặt các thư viện phụ thuộc còn lại từ requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn của dự án vào container
COPY . .

# Expose cổng 8100 mà FastAPI sử dụng
EXPOSE 8100

# Lệnh khởi chạy server Uvicorn
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8100"]
