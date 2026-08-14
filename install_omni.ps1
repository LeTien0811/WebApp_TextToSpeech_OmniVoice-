# =====================================================================
# OMNIVOICE TTS - AUTO INSTALLER SCRIPT (ENTERPRISE EDITION)
# Chức năng: Tự động phát hiện GPU, cài đặt Virtual Environment và PyTorch
# =====================================================================

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " BAT DAU TIEN TRINH CAI DAT OMNIVOICE TTS... " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Tạo môi trường ảo (Virtual Environment)
$venv_dir = "venv"
if (-Not (Test-Path $venv_dir)) {
    Write-Host "[1/4] Đang khởi tạo môi trường ảo (venv)..." -ForegroundColor Yellow
    python -m venv $venv_dir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "LỖI: Không tìm thấy Python. Vui lòng cài đặt Python 3.10+ và thêm vào PATH." -ForegroundColor Red
        exit
    }
} else {
    Write-Host "[1/4] Môi trường ảo 'venv' đã tồn tại. Bỏ qua bước tạo." -ForegroundColor Green
}

# 2. Phân tích phần cứng (NVIDIA CUDA)
Write-Host "[2/4] Đang phân tích cấu hình phần cứng..." -ForegroundColor Yellow
$cuda_version = ""
$pytorch_cmd = ".\venv\Scripts\pip.exe install torch torchaudio" # Mặc định là CPU (Chậm)

try {
    # Gọi nvidia-smi để lấy thông số card đồ họa
    $smi_output = & nvidia-smi 2>&1
    if ($LASTEXITCODE -eq 0) {
        # Dùng Regex bóc tách phiên bản CUDA
        if ($smi_output -match "CUDA Version:\s*(\d+\.\d+)") {
            $cuda_version = $Matches[1]
            Write-Host "  -> Đã phát hiện GPU NVIDIA. Cốt lõi CUDA Version: $cuda_version" -ForegroundColor Green

            # Tự động mapping phiên bản cài đặt dựa trên tài liệu hệ thống
            $major, $minor = $cuda_version.Split('.')
            if ($major -eq "12") {
                if ([int]$minor -ge 8) {
                    Write-Host "  -> Tương thích CUDA 12.8+. Đang chuẩn bị lệnh tải Pytorch tối ưu." -ForegroundColor Green
                    $pytorch_cmd = ".\venv\Scripts\pip.exe install torch==2.7.1+cu128 torchaudio==2.7.1+cu128 --index-url https://download.pytorch.org/whl/cu128"
                } elseif ([int]$minor -ge 4) {
                    Write-Host "  -> Tương thích CUDA 12.4. Đang chuẩn bị lệnh tải Pytorch." -ForegroundColor Green
                    $pytorch_cmd = ".\venv\Scripts\pip.exe install torch==2.7.1+cu124 torchaudio==2.7.1+cu124 --index-url https://download.pytorch.org/whl/cu124"
                } else {
                    Write-Host "  -> CUDA version 12.x nhưng quá cũ. Fallback về bản 12.4 để đảm bảo tương thích." -ForegroundColor DarkYellow
                    $pytorch_cmd = ".\venv\Scripts\pip.exe install torch==2.7.1+cu124 torchaudio==2.7.1+cu124 --index-url https://download.pytorch.org/whl/cu124"
                }
            } else {
                Write-Host "  -> CẢNH BÁO: Phiên bản CUDA ($cuda_version) không thuộc hệ 12.x." -ForegroundColor Red
                Write-Host "  -> Hệ thống sẽ cài bản CPU. Tốc độ sinh giọng nói sẽ rất chậm (~30-60s/câu)." -ForegroundColor Red
            }
        }
    } else {
        Write-Host "  -> Không tìm thấy Driver NVIDIA (nvidia-smi). Sẽ cài đặt bản CPU." -ForegroundColor DarkYellow
    }
} catch {
    Write-Host "  -> Lỗi khi truy xuất thông tin GPU. Đang chuyển về chế độ CPU an toàn." -ForegroundColor Red
}

# 3. Cài đặt lõi PyTorch
Write-Host "[3/4] Đang cài đặt lõi xử lý AI (PyTorch)... Quá trình này có thể mất vài phút." -ForegroundColor Yellow
Invoke-Expression $pytorch_cmd

# 4. Cài đặt các package phụ thuộc
Write-Host "[4/4] Đang nạp các thư viện từ requirements.txt..." -ForegroundColor Yellow
.\venv\Scripts\pip.exe install -r requirements.txt

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " CAI DAT HOAN TAT! " -ForegroundColor Green
Write-Host " Vui lòng chạy lệnh sau để kích hoạt môi trường:" -ForegroundColor White
Write-Host " .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "=============================================" -ForegroundColor Cyan