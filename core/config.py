# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

# Khởi tạo base path tùy thuộc vào việc ứng dụng đang chạy ở dạng mã nguồn hay đã được đóng gói thành file .exe
if getattr(sys, 'frozen', False):
    # Nếu chạy từ file .exe được build bằng PyInstaller, BASE_DIR sẽ là thư mục chứa file .exe đó
    BASE_DIR = Path(os.path.dirname(os.path.abspath(sys.executable)))
else:
    # Nếu chạy từ file python thông thường, BASE_DIR sẽ là thư mục gốc của project (cha của thư mục core/)
    BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Xác định thư mục chứa static files (giao diện HTML/CSS/JS)
# Khi đóng gói bằng PyInstaller, các file static thường được nén vào thư mục tạm thời sys._MEIPASS
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    STATIC_DIR = Path(sys._MEIPASS) / "static"
else:
    STATIC_DIR = BASE_DIR / "static"

# Thư mục lưu trữ model weights của OmniVoice
MODELS_DIR = BASE_DIR / "models"
# Thư mục lưu trữ các file audio mẫu (.wav) dùng cho việc clone giọng
VOICES_DIR = BASE_DIR / "voices"
# Đường dẫn đến file cấu hình .env nằm cạnh thư mục chạy hoặc exe
ENV_FILE = BASE_DIR / ".env"

# Tự động tạo các thư mục lưu trữ nếu chúng chưa tồn tại
MODELS_DIR.mkdir(parents=True, exist_ok=True)
VOICES_DIR.mkdir(parents=True, exist_ok=True)

# Hàm phân tích và nạp file .env thủ công (để tránh cài thêm thư viện python-dotenv không cần thiết)
def load_custom_dotenv(env_path: Path):
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Bỏ qua dòng trống hoặc dòng bắt đầu bằng dấu # (comment)
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        # Loại bỏ khoảng trắng thừa của key và value
                        # Đồng thời gán vào os.environ nếu chưa được set từ ngoài hệ thống
                        os.environ[key.strip()] = val.strip()
        except Exception as e:
            print(f"Lỗi khi đọc file .env: {e}")

# Nạp các biến cấu hình từ file .env
load_custom_dotenv(ENV_FILE)

# Các cấu hình API Key và file mẫu giọng mặc định
TTS_API_KEY = os.getenv("TTS_API_KEY", "")
# Nếu file mẫu giọng cấu hình là tương đối, chuyển nó thành tuyệt đối dựa trên BASE_DIR hoặc VOICES_DIR
DEFAULT_REF_AUDIO = os.getenv("TTS_REF_AUDIO", "voice_sample.wav")
# Nếu ref audio là tên file đơn giản, ưu tiên tìm trong thư mục voices/
if not os.path.isabs(DEFAULT_REF_AUDIO):
    possible_path = VOICES_DIR / DEFAULT_REF_AUDIO
    if possible_path.exists() or not (BASE_DIR / DEFAULT_REF_AUDIO).exists():
        TTS_REF_AUDIO_PATH = str(possible_path.resolve())
    else:
        TTS_REF_AUDIO_PATH = str((BASE_DIR / DEFAULT_REF_AUDIO).resolve())
else:
    TTS_REF_AUDIO_PATH = DEFAULT_REF_AUDIO

# Nội dung text mặc định ứng với file audio mẫu giọng dùng để tạo voice prompt khi khởi động
TTS_REF_TEXT = os.getenv(
    "TTS_REF_TEXT",
    "Xin chào! Tôi là nhân viên hỗ trợ thủ tục hành chính. Tôi có thể giúp gì cho bạn hôm nay?"
)
