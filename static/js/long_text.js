// -*- coding: utf-8 -*-

document.addEventListener("DOMContentLoaded", () => {
    // 1. Nạp danh sách các file audio mẫu từ thư mục voices/
    loadVoiceList();

    // 2. Lắng nghe và cập nhật đếm số ký tự văn bản thời gian thực
    const ttsText = document.getElementById("tts-text");
    const charCount = document.getElementById("char-count");
    ttsText.addEventListener("input", () => {
        charCount.textContent = ttsText.value.length;
        localStorage.setItem("active_long_tts_text", ttsText.value);
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
    document.getElementById("btn-generate").addEventListener("click", startNewLongSpeech);

    // 6. Đăng ký sự kiện click nút thử lại
    document.getElementById("btn-retry").addEventListener("click", () => {
        // Xóa task bị lỗi để cho phép quay lại màn hình sẵn sàng
        clearTaskState();
        document.getElementById("result-failed").classList.add("hidden");
        document.getElementById("result-placeholder").classList.remove("hidden");
    });

    // 7. Cấu hình hiệu ứng EQ sóng nhạc
    setupEqualizerAnimation();

    // 8. KHÔI PHỤC TIẾN TRÌNH KHI RELOAD TRANG
    restoreTaskState();
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

    dropzone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", handleFileSelect);

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("border-purple-500/80", "bg-white/[0.05]");
    });

    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("border-purple-500/80", "bg-white/[0.05]");
    });

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
        
        const reader = new FileReader();
        reader.onload = (e) => {
            ttsText.value = e.target.result;
            charCount.textContent = ttsText.value.length;
            localStorage.setItem("active_long_tts_text", ttsText.value);
        };
        reader.readAsText(file, "UTF-8");
    }
}

// Ghi log ra màn hình và đồng thời lưu vào localStorage
function appendLog(message, colorClass = "text-gray-400") {
    const logConsole = document.getElementById("log-console");
    if (!logConsole) return;

    const div = document.createElement("div");
    div.className = colorClass;
    div.textContent = `> ${message}`;
    logConsole.appendChild(div);
    logConsole.scrollTop = logConsole.scrollHeight;

    // Cập nhật logs vào LocalStorage
    let localLogs = [];
    try {
        localLogs = JSON.parse(localStorage.getItem("active_long_tts_logs")) || [];
    } catch (e) {}
    localLogs.push({ message, colorClass });
    localStorage.setItem("active_long_tts_logs", JSON.stringify(localLogs));
}

function clearTaskState() {
    localStorage.removeItem("active_long_tts_task_id");
    localStorage.removeItem("active_long_tts_status");
    localStorage.removeItem("active_long_tts_download_url");
    localStorage.removeItem("active_long_tts_error");
    localStorage.removeItem("active_long_tts_progress");
    localStorage.removeItem("active_long_tts_completed_chunks");
    localStorage.removeItem("active_long_tts_total_chunks");
    localStorage.setItem("active_long_tts_logs", JSON.stringify([]));
}

async function startNewLongSpeech() {
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

    const btnGen = document.getElementById("btn-generate");
    const placeholder = document.getElementById("result-placeholder");
    const loading = document.getElementById("result-loading");
    const success = document.getElementById("result-success");
    const failed = document.getElementById("result-failed");
    const logConsole = document.getElementById("log-console");
    const progressBarFill = document.getElementById("progress-bar-fill");
    const progressPercent = document.getElementById("progress-percent");
    const progressDetails = document.getElementById("progress-details");

    // Dọn dẹp trạng thái cũ
    clearTaskState();

    // Khởi tạo giao diện bắt đầu mới
    btnGen.disabled = true;
    placeholder.classList.add("hidden");
    success.classList.add("hidden");
    failed.classList.add("hidden");
    loading.classList.remove("hidden");
    
    progressBarFill.style.width = "0%";
    progressPercent.textContent = "0%";
    progressDetails.textContent = "Đang kết nối hệ thống...";
    logConsole.innerHTML = "";

    // Lưu văn bản hiện tại
    localStorage.setItem("active_long_tts_text", text);
    appendLog("Đang khởi tạo tác vụ và tải dữ liệu lên máy chủ...");

    try {
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
        
        appendLog(`Khởi tạo thành công! ID tác vụ: ${taskId}`);
        
        // Mở kết nối stream SSE
        connectSSE(taskId);

    } catch (error) {
        console.error("Lỗi khởi tạo tác vụ sách nói:", error);
        appendLog(`Lỗi khởi tạo: ${error.message}`, "text-red-400");
        
        document.getElementById("error-msg").textContent = error.message;
        loading.classList.add("hidden");
        failed.classList.remove("hidden");
        btnGen.disabled = false;

        localStorage.setItem("active_long_tts_status", "failed");
        localStorage.setItem("active_long_tts_error", error.message);
    }
}

function connectSSE(taskId) {
    const btnGen = document.getElementById("btn-generate");
    const loading = document.getElementById("result-loading");
    const success = document.getElementById("result-success");
    const failed = document.getElementById("result-failed");
    const placeholder = document.getElementById("result-placeholder");
    const progressBarFill = document.getElementById("progress-bar-fill");
    const progressPercent = document.getElementById("progress-percent");
    const progressDetails = document.getElementById("progress-details");

    btnGen.disabled = true;
    placeholder.classList.add("hidden");
    success.classList.add("hidden");
    failed.classList.add("hidden");
    loading.classList.remove("hidden");

    if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
    }

    localStorage.setItem("active_long_tts_task_id", taskId);
    localStorage.setItem("active_long_tts_status", "processing");

    // Lắng nghe luồng SSE
    activeEventSource = new EventSource(`/api/generate-long-text/stream/${taskId}`);

    activeEventSource.onopen = () => {
        let savedLogs = [];
        try {
            savedLogs = JSON.parse(localStorage.getItem("active_long_tts_logs")) || [];
        } catch (e) {}
        // Tránh in lặp lại log kết nối nếu đã có lịch sử log trước đó khi reload
        if (savedLogs.length <= 2) {
            appendLog("Kết nối stream SSE thành công. Đang phân tách văn bản...");
        } else {
            appendLog("Tự động kết nối lại luồng stream SSE để tiếp tục theo dõi...");
        }
    };

    activeEventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.status === "processing") {
            const progress = data.progress;
            progressBarFill.style.width = `${progress}%`;
            progressPercent.textContent = `${progress}%`;
            progressDetails.textContent = `Đang xử lý câu ${data.completed_chunks}/${data.total_chunks}...`;
            
            appendLog(`Đang xử lý câu ${data.completed_chunks}/${data.total_chunks}... (${progress}%)`);

            localStorage.setItem("active_long_tts_status", "processing");
            localStorage.setItem("active_long_tts_progress", progress);
            localStorage.setItem("active_long_tts_completed_chunks", data.completed_chunks);
            localStorage.setItem("active_long_tts_total_chunks", data.total_chunks);
        } 
        else if (data.status === "completed") {
            appendLog("Hệ thống hoàn thành tổng hợp toàn bộ văn bản!", "text-green-400");
            
            // Đóng stream
            activeEventSource.close();
            activeEventSource = null;

            const downloadUrl = data.download_url;
            const player = document.getElementById("audio-player");
            player.src = downloadUrl;

            // Xử lý tên tệp tin theo ngày giờ lấy từ task_id (sachnoi_YYYYMMDD_HHMMSS_xxxx)
            const downloadBtn = document.getElementById("btn-download-audio");
            downloadBtn.href = downloadUrl;
            
            let filename = `sach_noi_omnivoice.mp3`;
            if (taskId.startsWith("sachnoi_")) {
                const parts = taskId.split("_");
                if (parts.length >= 3) {
                    filename = `sach_noi_${parts[1]}_${parts[2]}.mp3`;
                }
            }
            downloadBtn.download = filename;

            // Hiển thị giao diện thành công
            loading.classList.add("hidden");
            success.classList.remove("hidden");
            btnGen.disabled = false;

            // Lưu trạng thái thành công
            localStorage.setItem("active_long_tts_status", "completed");
            localStorage.setItem("active_long_tts_download_url", downloadUrl);
            
            player.play().catch(e => console.log("Không thể tự phát âm thanh:", e));
        }
        else if (data.status === "failed") {
            const errMsg = data.error || "Gặp lỗi xử lý không mong muốn.";
            appendLog(`LỖI HỆ THỐNG: ${errMsg}`, "text-red-400");
            
            activeEventSource.close();
            activeEventSource = null;

            document.getElementById("error-msg").textContent = errMsg;
            loading.classList.add("hidden");
            failed.classList.remove("hidden");
            btnGen.disabled = false;

            localStorage.setItem("active_long_tts_status", "failed");
            localStorage.setItem("active_long_tts_error", errMsg);
        }
    };

    activeEventSource.onerror = (err) => {
        console.error("SSE stream error:", err);
        
        // Đóng kết nối
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }

        const savedStatus = localStorage.getItem("active_long_tts_status");
        // Nếu đã hoàn thành từ trước, bỏ qua lỗi đóng kết nối tự nhiên của SSE
        if (savedStatus === "completed") {
            return;
        }

        appendLog("Lỗi kết nối stream SSE hoặc tác vụ bị ngắt kết nối.", "text-red-400");
        document.getElementById("error-msg").textContent = "Mất kết nối EventSource (SSE) với máy chủ hoặc tác vụ bị ngắt quãng.";
        loading.classList.add("hidden");
        failed.classList.remove("hidden");
        btnGen.disabled = false;

        localStorage.setItem("active_long_tts_status", "failed");
        localStorage.setItem("active_long_tts_error", "Mất kết nối với luồng SSE của máy chủ.");
    };
}

function restoreTaskState() {
    const ttsText = document.getElementById("tts-text");
    const charCount = document.getElementById("char-count");
    
    // 1. Khôi phục text dán trong textarea
    const savedText = localStorage.getItem("active_long_tts_text");
    if (savedText) {
        ttsText.value = savedText;
        charCount.textContent = savedText.length;
    }

    // 2. Khôi phục tác vụ đang chạy hoặc đã kết thúc
    const savedTaskId = localStorage.getItem("active_long_tts_task_id");
    const savedStatus = localStorage.getItem("active_long_tts_status");

    if (savedTaskId && savedStatus) {
        const placeholder = document.getElementById("result-placeholder");
        const loading = document.getElementById("result-loading");
        const success = document.getElementById("result-success");
        const failed = document.getElementById("result-failed");
        const logConsole = document.getElementById("log-console");

        // A. Khôi phục lịch sử logs console
        let savedLogs = [];
        try {
            savedLogs = JSON.parse(localStorage.getItem("active_long_tts_logs")) || [];
        } catch (e) {}

        logConsole.innerHTML = "";
        savedLogs.forEach(log => {
            const div = document.createElement("div");
            div.className = log.colorClass;
            div.textContent = `> ${log.message}`;
            logConsole.appendChild(div);
        });
        logConsole.scrollTop = logConsole.scrollHeight;

        // B. Khôi phục UI theo trạng thái tương ứng
        if (savedStatus === "processing" || savedStatus === "initialized") {
            const progress = localStorage.getItem("active_long_tts_progress") || "0";
            const completed = localStorage.getItem("active_long_tts_completed_chunks") || "0";
            const total = localStorage.getItem("active_long_tts_total_chunks") || "0";

            document.getElementById("progress-bar-fill").style.width = `${progress}%`;
            document.getElementById("progress-percent").textContent = `${progress}%`;
            document.getElementById("progress-details").textContent = `Đang xử lý câu ${completed}/${total}...`;

            // Tự động kết nối lại SSE để tiếp tục lắng nghe tiến độ
            connectSSE(savedTaskId);
        } 
        else if (savedStatus === "completed") {
            const downloadUrl = localStorage.getItem("active_long_tts_download_url");
            if (downloadUrl) {
                placeholder.classList.add("hidden");
                success.classList.remove("hidden");

                const player = document.getElementById("audio-player");
                player.src = downloadUrl;

                const downloadBtn = document.getElementById("btn-download-audio");
                downloadBtn.href = downloadUrl;
                
                let filename = `sach_noi_omnivoice.mp3`;
                if (savedTaskId.startsWith("sachnoi_")) {
                    const parts = savedTaskId.split("_");
                    if (parts.length >= 3) {
                        filename = `sach_noi_${parts[1]}_${parts[2]}.mp3`;
                    }
                }
                downloadBtn.download = filename;
            }
        } 
        else if (savedStatus === "failed") {
            const error = localStorage.getItem("active_long_tts_error") || "Gặp lỗi xử lý không mong muốn.";
            placeholder.classList.add("hidden");
            failed.classList.remove("hidden");
            document.getElementById("error-msg").textContent = error;
        }
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
