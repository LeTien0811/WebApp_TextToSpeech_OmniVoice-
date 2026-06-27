// -*- coding: utf-8 -*-

document.addEventListener("DOMContentLoaded", () => {
    // 1. Nạp danh sách các file audio mẫu từ thư mục voices/
    loadVoiceList();

    // 2. Lắng nghe và cập nhật đếm số ký tự văn bản thời gian thực
    const ttsText = document.getElementById("tts-text");
    const charCount = document.getElementById("char-count");
    ttsText.addEventListener("input", () => {
        charCount.textContent = ttsText.value.length;
    });

    // 3. Lắng nghe sự thay đổi các thanh trượt tham số
    const speedInput = document.getElementById("tts-speed");
    const speedVal = document.getElementById("speed-val");
    speedInput.addEventListener("input", () => {
        speedVal.textContent = `${parseFloat(speedInput.value).toFixed(1)}x`;
    });

    const stepsInput = document.getElementById("tts-steps");
    const stepsVal = document.getElementById("steps-val");
    stepsInput.addEventListener("input", () => {
        stepsVal.textContent = stepsInput.value;
    });

    const silenceInput = document.getElementById("tts-silence");
    const silenceVal = document.getElementById("silence-val");
    silenceInput.addEventListener("input", () => {
        silenceVal.textContent = `${silenceInput.value}ms`;
    });

    // 4. Xử lý Drag-and-Drop file .txt
    setupDragAndDrop();

    // 5. Đăng ký sự kiện click cho nút sinh sách nói "Generate MP3"
    document.getElementById("btn-generate").addEventListener("click", generateLongSpeech);

    // 6. Đăng ký sự kiện click nút thử lại
    document.getElementById("btn-retry").addEventListener("click", () => {
        document.getElementById("result-failed").classList.add("hidden");
        document.getElementById("result-placeholder").classList.remove("hidden");
    });

    // 7. Cấu hình hiệu ứng EQ sóng nhạc
    setupEqualizerAnimation();
});

// Biến lưu trữ đối tượng EventSource để dọn dẹp khi cần
let activeEventSource = null;

async function loadVoiceList() {
    const select = document.getElementById("voice-select");
    try {
        const response = await fetch("/api/voices");
        if (!response.ok) throw new Error("Không thể lấy danh sách giọng mẫu.");
        const data = await response.json();
        
        select.innerHTML = "";
        if (data.voices && data.voices.length > 0) {
            data.voices.forEach(voice => {
                const option = document.createElement("option");
                option.value = voice;
                option.textContent = voice;
                select.appendChild(option);
            });
        } else {
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

function setupDragAndDrop() {
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const fileInfo = document.getElementById("file-info");
    const ttsText = document.getElementById("tts-text");
    const charCount = document.getElementById("char-count");

    // Click vào dropzone kích hoạt input file
    dropzone.addEventListener("click", () => fileInput.click());

    // Thay đổi file từ input
    fileInput.addEventListener("change", handleFileSelect);

    // Sự kiện kéo thả dragover
    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("border-purple-500/80", "bg-white/[0.05]");
    });

    // Sự kiện kéo thả dragleave
    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("border-purple-500/80", "bg-white/[0.05]");
    });

    // Sự kiện drop file
    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("border-purple-500/80", "bg-white/[0.05]");
        
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            handleFileSelect();
        }
    });

    function handleFileSelect() {
        const file = fileInput.files[0];
        if (!file) return;

        if (file.type !== "text/plain" && !file.name.endsWith(".txt")) {
            alert("Chỉ chấp nhận tệp tin văn bản định dạng .txt");
            fileInput.value = "";
            return;
        }

        fileInfo.textContent = `Tệp đã chọn: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        
        // Đọc nội dung file
        const reader = new FileReader();
        reader.onload = (e) => {
            ttsText.value = e.target.result;
            charCount.textContent = ttsText.value.length;
        };
        reader.readAsText(file, "UTF-8");
    }
}

async function generateLongSpeech() {
    const text = document.getElementById("tts-text").value.trim();
    const voice = document.getElementById("voice-select").value;
    const speed = parseFloat(document.getElementById("tts-speed").value);
    const steps = parseInt(document.getElementById("tts-steps").value);
    const silence = parseInt(document.getElementById("tts-silence").value);
    
    if (!text) {
        alert("Vui lòng nhập văn bản hoặc tải lên tệp tin .txt!");
        return;
    }
    if (!voice) {
        alert("Vui lòng chuẩn bị và chọn 1 giọng mẫu .wav!");
        return;
    }

    // Các thành phần UI điều khiển hiển thị
    const btnGen = document.getElementById("btn-generate");
    const placeholder = document.getElementById("result-placeholder");
    const loading = document.getElementById("result-loading");
    const success = document.getElementById("result-success");
    const failed = document.getElementById("result-failed");
    const logConsole = document.getElementById("log-console");
    const progressBarFill = document.getElementById("progress-bar-fill");
    const progressPercent = document.getElementById("progress-percent");
    const progressDetails = document.getElementById("progress-details");

    // Khởi tạo trạng thái giao diện
    btnGen.disabled = true;
    placeholder.classList.add("hidden");
    success.classList.add("hidden");
    failed.classList.add("hidden");
    loading.classList.remove("hidden");
    
    // Đặt lại progress bar & logs
    progressBarFill.style.width = "0%";
    progressPercent.textContent = "0%";
    progressDetails.textContent = "Đang kết nối hệ thống...";
    logConsole.innerHTML = '<div class="text-gray-500">> Khởi tạo tác vụ...</div>';

    // Đóng EventSource cũ nếu có
    if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
    }

    function appendLog(message, colorClass = "text-gray-400") {
        const div = document.createElement("div");
        div.className = colorClass;
        div.textContent = `> ${message}`;
        logConsole.appendChild(div);
        logConsole.scrollTop = logConsole.scrollHeight;
    }

    try {
        // Bước 1: Gửi POST Init để lấy Task ID
        appendLog("Đang gửi văn bản lên máy chủ...");
        const formData = new FormData();
        formData.append("text", text);
        formData.append("voice_sample_name", voice);
        formData.append("num_step", steps);
        formData.append("speed", speed);
        formData.append("silence_duration", silence);

        const initResponse = await fetch("/api/generate-long-text/init", {
            method: "POST",
            body: formData
        });

        if (!initResponse.ok) {
            let errMsg = "Không thể khởi tạo tác vụ.";
            try {
                const errData = await initResponse.json();
                errMsg = errData.detail || errMsg;
            } catch (e) {}
            throw new Error(errMsg);
        }

        const initData = await initResponse.json();
        const taskId = initData.task_id;
        appendLog(`Khởi tạo thành công! ID tác vụ: ${taskId.substring(0, 8)}...`);

        // Bước 2: Thiết lập kết nối EventSource (SSE) với Task ID
        appendLog("Đang mở kết nối stream sự kiện SSE...");
        activeEventSource = new EventSource(`/api/generate-long-text/stream/${taskId}`);

        activeEventSource.onopen = () => {
            appendLog("Kết nối stream SSE thành công. Đang phân tách văn bản...");
        };

        activeEventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.status === "processing") {
                const progress = data.progress;
                progressBarFill.style.width = `${progress}%`;
                progressPercent.textContent = `${progress}%`;
                progressDetails.textContent = `Đang xử lý câu ${data.completed_chunks}/${data.total_chunks}...`;
                appendLog(`Đang xử lý câu ${data.completed_chunks}/${data.total_chunks}... (${progress}%)`);
            } 
            else if (data.status === "completed") {
                appendLog("Hệ thống hoàn thành tổng hợp toàn bộ văn bản!", "text-green-400");
                activeEventSource.close();
                activeEventSource = null;

                // Chuẩn bị URL tải xuống
                const downloadUrl = data.download_url;
                const player = document.getElementById("audio-player");
                player.src = downloadUrl;

                const downloadBtn = document.getElementById("btn-download-audio");
                downloadBtn.href = downloadUrl;
                const timestamp = new Date().toISOString().replace(/[-:.]/g, "");
                downloadBtn.download = `sach_noi_omnivoice_${timestamp}.mp3`;

                // Hiển thị giao diện thành công
                loading.classList.add("hidden");
                success.classList.remove("hidden");
                btnGen.disabled = false;
                
                player.play().catch(e => console.log("Không thể tự phát âm thanh:", e));
            }
            else if (data.status === "failed") {
                // Nhận thông điệp lỗi FATAL_ERROR từ server
                const errMsg = data.error || "Gặp lỗi xử lý không mong muốn.";
                appendLog(`LỖI HỆ THỐNG: ${errMsg}`, "text-red-400");
                
                activeEventSource.close();
                activeEventSource = null;

                document.getElementById("error-msg").textContent = errMsg;
                loading.classList.add("hidden");
                failed.classList.remove("hidden");
                btnGen.disabled = false;
            }
        };

        activeEventSource.onerror = (err) => {
            console.error("SSE stream error:", err);
            appendLog("Lỗi kết nối stream SSE. Kiểm tra log server hoặc kết nối mạng.", "text-red-400");
            
            if (activeEventSource) {
                activeEventSource.close();
                activeEventSource = null;
            }

            document.getElementById("error-msg").textContent = "Mất kết nối EventSource (SSE) với máy chủ hoặc tác vụ bị ngắt quãng.";
            loading.classList.add("hidden");
            failed.classList.remove("hidden");
            btnGen.disabled = false;
        };

    } catch (error) {
        console.error("Lỗi tác vụ sách nói:", error);
        appendLog(`Lỗi khởi tạo: ${error.message}`, "text-red-400");
        
        document.getElementById("error-msg").textContent = error.message;
        loading.classList.add("hidden");
        failed.classList.remove("hidden");
        btnGen.disabled = false;
    }
}

function setupEqualizerAnimation() {
    const player = document.getElementById("audio-player");
    const wave = document.getElementById("audio-wave");
    const bars = document.querySelectorAll(".wave-bar");
    
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
