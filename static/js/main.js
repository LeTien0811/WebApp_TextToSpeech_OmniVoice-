// -*- coding: utf-8 -*-

// Lưu trữ đối tượng EventSource kết nối tới SSE stream để có thể đóng kết nối khi cần
let downloadEventSource = null;

// Chờ toàn bộ DOM được nạp xong mới kích hoạt logic
document.addEventListener("DOMContentLoaded", () => {
    // Gọi hàm kiểm tra trạng thái ban đầu của hệ thống
    checkSystemStatus();

    // Đăng ký sự kiện click cho các nút bấm trên giao diện
    document.getElementById("btn-download").addEventListener("click", startSSEDownload);
    document.getElementById("btn-load-model").addEventListener("click", loadModelToVRAM);
    document.getElementById("btn-unload-model").addEventListener("click", unloadModelFromVRAM);
    document.getElementById("btn-goto-tts").addEventListener("click", () => {
        window.location.href = "generate.html";
    });
    document.getElementById("btn-goto-long-tts").addEventListener("click", () => {
        window.location.href = "long_text.html";
    });
});

async function checkSystemStatus() {
    /**
     * Hàm gọi API GET /api/status để lấy thông tin trạng thái model hiện tại
     * và cập nhật trực tiếp lên giao diện Dashboard.
     */
    try {
        const response = await fetch("/api/status");
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        // 1. Cập nhật giao diện trạng thái tệp tin model trên ổ đĩa
        const existsText = document.getElementById("model-exists-text");
        const existsDot = document.getElementById("model-exists-dot");
        const existsDesc = document.getElementById("model-exists-desc");

        if (data.models_exist) {
            existsText.textContent = "Đã đầy đủ";
            existsText.className = "text-lg font-medium text-emerald-400";
            existsDot.className = "status-dot dot-active";
            existsDesc.textContent = "Sẵn sàng để nạp (3.27 GB)";

            // Ẩn hộp thoại bắt đầu tải vì đã có sẵn
            document.getElementById("download-box").classList.add("hidden");
        } else {
            existsText.textContent = "Chưa đầy đủ";
            existsText.className = "text-lg font-medium text-rose-400";
            existsDot.className = "status-dot dot-inactive";
            existsDesc.textContent = "Cần tải file trọng số";

            // Hiển thị hộp thoại yêu cầu tải model
            document.getElementById("download-box").classList.remove("hidden");
        }

        // 2. Cập nhật giao diện trạng thái nạp model lên RAM/VRAM
        const loadedText = document.getElementById("model-loaded-text");
        const loadedDot = document.getElementById("model-loaded-dot");
        const loadedDesc = document.getElementById("model-loaded-desc");
        const btnLoad = document.getElementById("btn-load-model");
        const btnUnload = document.getElementById("btn-unload-model");
        const btnGotoTts = document.getElementById("btn-goto-tts");
        const btnGotoLongTts = document.getElementById("btn-goto-long-tts");
        const loadBox = document.getElementById("load-box");

        if (data.model_loaded) {
            loadedText.textContent = "Đang chạy";
            loadedText.className = "text-lg font-medium text-emerald-400";
            loadedDot.className = "status-dot dot-active";
            loadedDesc.textContent = `Thiết bị: ${data.device.toUpperCase()}`;

            // Điều chỉnh nút bấm: ẩn Nạp, hiện Giải phóng
            btnLoad.classList.add("hidden");
            btnUnload.classList.remove("hidden");

            // Kích hoạt nút chuyển tiếp sang trang sinh giọng nói
            btnGotoTts.disabled = false;
            btnGotoTts.classList.remove("opacity-50");
            btnGotoLongTts.disabled = false;
            btnGotoLongTts.classList.remove("opacity-50");

            // Ẩn spinner loading
            document.getElementById("load-loading-spinner").classList.add("hidden");
        } else if (data.model_status === "loading") {
            loadedText.textContent = "Đang nạp...";
            loadedText.className = "text-lg font-medium text-amber-400";
            loadedDot.className = "status-dot dot-warning";
            loadedDesc.textContent = "Đang đưa trọng số lên GPU";

            btnLoad.disabled = true;
            btnLoad.textContent = "Đang nạp...";
            document.getElementById("load-loading-spinner").classList.remove("hidden");
            btnGotoTts.disabled = true;
            btnGotoLongTts.disabled = true;
        } else {
            loadedText.textContent = "Chưa nạp";
            loadedText.className = "text-lg font-medium text-gray-400";
            loadedDot.className = "status-dot dot-inactive";
            loadedDesc.textContent = "Chưa sử dụng VRAM";

            // Điều chỉnh nút bấm: hiện Nạp, ẩn Giải phóng
            btnLoad.classList.remove("hidden");
            btnLoad.disabled = !data.models_exist; // Chỉ cho phép nạp nếu model đã tồn tại
            btnLoad.textContent = "Nạp Model vào RAM/VRAM";
            btnUnload.classList.add("hidden");

            // Tắt nút chuyển tiếp sang trang sinh giọng nói
            btnGotoTts.disabled = true;
            btnGotoLongTts.disabled = true;
            document.getElementById("load-loading-spinner").classList.add("hidden");
        }

        // Chỉ hiển thị hộp quản lý bộ nhớ nếu model đã tồn tại đầy đủ trên ổ đĩa
        if (data.models_exist) {
            loadBox.classList.remove("hidden");
        } else {
            loadBox.classList.add("hidden");
        }

    } catch (error) {
        console.error("Lỗi khi kết nối API lấy trạng thái hệ thống:", error);
    }
}

function startSSEDownload() {
    /**
     * Hàm mở kết nối SSE tới API /api/download/stream.
     * Nhận dữ liệu cập nhật thời gian thực về tiến trình tải model,
     * tự động Resume tải từ byte bị ngắt nhờ cấu hình Range request từ backend.
     */

    // Ẩn nút bấm Download cũ để tránh người dùng nhấn lại
    document.getElementById("btn-download").disabled = true;
    document.getElementById("download-box").classList.add("hidden");

    // Hiển thị hộp tiến độ tải xuống
    const progressBox = document.getElementById("progress-box");
    progressBox.classList.remove("hidden");

    const errorBox = document.getElementById("download-error-box");
    errorBox.classList.add("hidden");

    // Khởi tạo EventSource lắng nghe dữ liệu đẩy từ backend
    downloadEventSource = new EventSource("/api/download/stream");

    downloadEventSource.onmessage = (event) => {
        // Parse dữ liệu JSON nhận được từ SSE
        const state = JSON.parse(event.data);

        // Cập nhật thông số tiến độ lên UI
        document.getElementById("download-percent").textContent = `${state.progress}%`;
        document.getElementById("progress-bar-fill").style.width = `${state.progress}%`;
        document.getElementById("download-speed").textContent = `${state.speed} MB/s`;

        // Format hiển thị ETA thân thiện (mm:ss)
        if (state.eta > 0) {
            const minutes = Math.floor(state.eta / 60);
            const seconds = state.eta % 60;
            document.getElementById("download-eta").textContent = `${minutes}p ${seconds}s`;
        } else {
            document.getElementById("download-eta").textContent = "đang tính...";
        }

        // Hiển thị kích thước dữ liệu đã tải dưới dạng GB
        const dlGB = (state.downloaded_bytes / (1024 * 1024 * 1024)).toFixed(2);
        const totalGB = (state.total_bytes / (1024 * 1024 * 1024)).toFixed(2);
        document.getElementById("download-bytes").textContent = `${dlGB} / ${totalGB} GB`;

        // Hiển thị tên file đang được tải
        if (state.current_file) {
            document.getElementById("download-file-name").textContent = `Đang tải: ${state.current_file}`;
        }

        // Xử lý các trạng thái hoàn thành hoặc lỗi từ luồng tải
        if (state.status === "completed") {
            downloadEventSource.close();
            loggerInfo("Tải model hoàn thành!");
            document.getElementById("download-file-name").textContent = "Tải model hoàn tất!";
            document.getElementById("download-eta").textContent = "0s";

            // Quét lại trạng thái hệ thống để kích hoạt bộ điều khiển nạp
            setTimeout(() => {
                progressBox.classList.add("hidden");
                checkSystemStatus();
            }, 1500);

        } else if (state.status === "failed") {
            downloadEventSource.close();
            errorBox.classList.remove("hidden");
            document.getElementById("download-error-msg").textContent = state.error || "Mạng bị ngắt quãng.";
            document.getElementById("download-file-name").textContent = "Tải xuống thất bại.";

            // Khôi phục lại nút tải để người dùng có thể nhấn thử lại (resume)
            document.getElementById("btn-download").disabled = false;
            document.getElementById("download-box").classList.remove("hidden");
        }
    };

    downloadEventSource.onerror = (error) => {
        // Đóng kết nối khi xảy ra lỗi mạng truyền tải EventSource
        console.error("Lỗi kết nối EventSource:", error);
        downloadEventSource.close();

        errorBox.classList.remove("hidden");
        document.getElementById("download-error-msg").textContent = "Mất kết nối với máy chủ.";

        document.getElementById("btn-download").disabled = false;
        document.getElementById("download-box").classList.remove("hidden");
    };
}

async function loadModelToVRAM() {
    /**
     * Gửi yêu cầu nạp model lên RAM/VRAM qua API POST /api/load.
     * Hiển thị loading spinner cho người dùng vì tiến trình warmup có thể mất vài giây.
     */
    const btnLoad = document.getElementById("btn-load-model");
    const spinner = document.getElementById("load-loading-spinner");

    btnLoad.disabled = true;
    btnLoad.textContent = "Đang nạp model...";
    spinner.classList.remove("hidden");

    try {
        const response = await fetch("/api/load", { method: "POST" });
        const result = await response.json();

        if (response.ok) {
            console.log("Nạp model thành công:", result.detail);
        } else {
            alert(`Lỗi nạp model: ${result.detail || "Không rõ nguyên nhân"}`);
        }
    } catch (error) {
        console.error("Lỗi khi kết nối API load model:", error);
        alert("Không thể kết nối đến máy chủ.");
    } finally {
        // Quét lại hệ thống để cập nhật giao diện
        checkSystemStatus();
    }
}

async function unloadModelFromVRAM() {
    /**
     * Gửi yêu cầu giải phóng model khỏi bộ nhớ qua API POST /api/unload.
     */
    if (!confirm("Bạn có chắc chắn muốn giải phóng model khỏi VRAM không?")) {
        return;
    }

    const btnUnload = document.getElementById("btn-unload-model");
    btnUnload.disabled = true;

    try {
        const response = await fetch("/api/unload", { method: "POST" });
        const result = await response.json();

        if (response.ok) {
            console.log("Giải phóng model thành công:", result.detail);
        } else {
            alert(`Lỗi khi giải phóng model: ${result.detail}`);
        }
    } catch (error) {
        console.error("Lỗi kết nối API unload:", error);
    } finally {
        checkSystemStatus();
        btnUnload.disabled = false;
    }
}

function loggerInfo(msg) {
    console.log(`[Dashboard] ${msg}`);
}
