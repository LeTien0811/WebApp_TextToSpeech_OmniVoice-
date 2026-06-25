// -*- coding: utf-8 -*-

document.addEventListener("DOMContentLoaded", () => {
    // 1. Tự động phục hồi API Key từ LocalStorage nếu người dùng đã nhập trước đó
    const apiKeyInput = document.getElementById("api-key-input");
    const savedKey = localStorage.getItem("tts_api_key");
    if (savedKey) {
        apiKeyInput.value = savedKey;
    }
    
    // Lưu lại API Key vào LocalStorage bất cứ khi nào người dùng thay đổi giá trị
    apiKeyInput.addEventListener("input", () => {
        localStorage.setItem("tts_api_key", apiKeyInput.value.trim());
    });

    // 2. Nạp danh sách các file audio mẫu từ thư mục voices/
    loadVoiceList();

    // 3. Lắng nghe và cập nhật đếm số ký tự văn bản thời gian thực
    const ttsText = document.getElementById("tts-text");
    const charCount = document.getElementById("char-count");
    ttsText.addEventListener("input", () => {
        charCount.textContent = ttsText.value.length;
    });

    // 4. Lắng nghe sự thay đổi của thanh trượt tốc độ (Speed) để cập nhật hiển thị số
    const speedInput = document.getElementById("tts-speed");
    const speedVal = document.getElementById("speed-val");
    speedInput.addEventListener("input", () => {
        speedVal.textContent = `${parseFloat(speedInput.value).toFixed(1)}x`;
    });

    // 5. Lắng nghe sự thay đổi của thanh trượt số bước (Steps) để cập nhật hiển thị số
    const stepsInput = document.getElementById("tts-steps");
    const stepsVal = document.getElementById("steps-val");
    stepsInput.addEventListener("input", () => {
        stepsVal.textContent = stepsInput.value;
    });

    // 6. Đăng ký sự kiện click cho nút sinh giọng nói "Generate Speech"
    document.getElementById("btn-generate").addEventListener("click", generateSpeech);

    // 7. Cấu hình hiệu ứng EQ nhảy theo nhạc khi audio thực sự phát
    setupEqualizerAnimation();
});

async function loadVoiceList() {
    /**
     * Gọi API GET /api/voices để lấy danh sách các file audio mẫu có sẵn.
     * Cập nhật danh sách này vào dropdown của người dùng.
     */
    const select = document.getElementById("voice-select");
    
    try {
        const response = await fetch("/api/voices");
        if (!response.ok) {
            throw new Error("Không thể lấy danh sách giọng mẫu.");
        }
        const data = await response.json();
        
        // Xóa thông báo đang nạp
        select.innerHTML = "";
        
        if (data.voices && data.voices.length > 0) {
            data.voices.forEach(voice => {
                const option = document.createElement("option");
                option.value = voice;
                option.textContent = voice;
                select.appendChild(option);
            });
        } else {
            // Trường hợp thư mục voices/ trống
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "Không tìm thấy file .wav nào trong thư mục voices/";
            select.appendChild(option);
        }
    } catch (error) {
        console.error("Lỗi nạp danh sách giọng mẫu:", error);
        select.innerHTML = '<option value="">Lỗi nạp danh sách giọng nói mẫu</option>';
    }
}

async function generateSpeech() {
    /**
     * Thu thập văn bản, giọng mẫu và các tham số cấu hình.
     * Gửi yêu cầu POST chứa JSON đến API /api/generate để sinh âm thanh bất đồng bộ.
     * Trình diễn kết quả bằng Audio Player và liên kết tải về.
     */
    const text = document.getElementById("tts-text").value.trim();
    const voice = document.getElementById("voice-select").value;
    const speed = parseFloat(document.getElementById("tts-speed").value);
    const steps = parseInt(document.getElementById("tts-steps").value);
    const apiKey = document.getElementById("api-key-input").value.trim();
    
    // Kiểm tra dữ liệu đầu vào cơ bản
    if (!text) {
        alert("Vui lòng nhập văn bản cần sinh giọng!");
        return;
    }
    if (!voice) {
        alert("Vui lòng chọn hoặc chuẩn bị tối thiểu 1 file giọng mẫu .wav!");
        return;
    }

    // Điều khiển trạng thái giao diện: Ẩn các hộp cũ, Hiện spinner loading
    const btnGen = document.getElementById("btn-generate");
    const placeholder = document.getElementById("result-placeholder");
    const loading = document.getElementById("result-loading");
    const success = document.getElementById("result-success");
    
    btnGen.disabled = true;
    placeholder.classList.add("hidden");
    success.classList.add("hidden");
    loading.classList.remove("hidden");

    try {
        // Cấu hình headers bao gồm cả API Key bảo mật nếu có
        const headers = {
            "Content-Type": "application/json"
        };
        if (apiKey) {
            headers["X-TTS-API-Key"] = apiKey;
        }

        const payload = {
            text: text,
            voice_sample_name: voice,
            num_step: steps,
            speed: speed
        };

        // Gửi request POST đến API sinh giọng
        const response = await fetch("/api/generate", {
            method: "POST",
            headers: headers,
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            // Đọc luồng dữ liệu trả về dưới dạng nhị phân Blob
            const audioBlob = await response.blob();
            // Tạo đường dẫn tạm thời cho file âm thanh
            const audioUrl = URL.createObjectURL(audioBlob);
            
            // Đưa đường dẫn vào trình phát audio
            const player = document.getElementById("audio-player");
            player.src = audioUrl;
            
            // Đưa đường dẫn vào liên kết tải về
            const downloadBtn = document.getElementById("btn-download-audio");
            downloadBtn.href = audioUrl;
            // Đặt tên file tải về đẹp đẽ chứa thời gian
            const timestamp = new Date().toISOString().replace(/[-:.]/g, "");
            downloadBtn.download = `omnivoice_synthesis_${timestamp}.wav`;
            
            // Lấy thời gian xử lý từ Header HTTP phản hồi
            const timeHeader = response.headers.get("X-Synthesis-Time") || "không rõ";
            document.getElementById("synthesis-duration").textContent = `Thời gian xử lý: ${timeHeader}`;
            
            // Chuyển hiển thị sang hộp kết quả thành công
            loading.classList.add("hidden");
            success.classList.remove("hidden");
            
            // Tự động phát âm thanh ngay lập tức
            player.play().catch(e => console.log("Không thể tự động phát do chính sách trình duyệt:", e));
            
        } else {
            // Đọc thông báo lỗi từ JSON trả về của backend
            let errMsg = "Lỗi không rõ nguồn gốc.";
            try {
                const errData = await response.json();
                errMsg = errData.detail || errMsg;
            } catch (e) {
                // Dự phòng nếu lỗi trả về dạng text thô
                errMsg = await response.text() || errMsg;
            }
            throw new Error(errMsg);
        }
    } catch (error) {
        console.error("Lỗi sinh giọng nói:", error);
        alert(`Lỗi sinh giọng: ${error.message}`);
        
        // Khôi phục lại giao diện ban đầu
        loading.classList.add("hidden");
        placeholder.classList.remove("hidden");
    } finally {
        // Luôn khôi phục lại nút bấm
        btnGen.disabled = false;
    }
}

function setupEqualizerAnimation() {
    /**
     * Lắng nghe sự kiện của trình phát nhạc HTML5 để làm động sóng nhạc (Equalizer).
     * Sóng nhạc chỉ nhấp nháy chuyển động khi nhạc đang chạy thực sự.
     */
    const player = document.getElementById("audio-player");
    const wave = document.getElementById("audio-wave");
    const bars = document.querySelectorAll(".wave-bar");
    
    // Ban đầu tắt hoạt họa
    bars.forEach(bar => bar.style.animationPlayState = 'paused');
    
    player.addEventListener("play", () => {
        wave.classList.remove("opacity-40");
        bars.forEach(bar => bar.style.animationPlayState = 'running');
    });
    
    player.addEventListener("pause", () => {
        wave.classList.add("opacity-40");
        bars.forEach(bar => bar.style.animationPlayState = 'paused');
    });
    
    player.addEventListener("ended", () => {
        wave.classList.add("opacity-40");
        bars.forEach(bar => bar.style.animationPlayState = 'paused');
    });
}
