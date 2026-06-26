const form = document.querySelector("#uploadForm");
const fileInput = document.querySelector("#fileInput");
const fileLabel = document.querySelector("#fileLabel");
const dropzone = document.querySelector("#dropzone");
const submitButton = document.querySelector("#submitButton");
const reviewOption = document.querySelector("#reviewOption");
const autoFixOption = document.querySelector("#autoFixOption");
const visionOption = document.querySelector("#visionOption");
const globalStatus = document.querySelector("#globalStatus");
const taskIdLabel = document.querySelector("#taskId");
const taskMessage = document.querySelector("#taskMessage");
const fileTable = document.querySelector("#fileTable");
const archiveButton = document.querySelector("#archiveButton");
const refreshButton = document.querySelector("#refreshButton");
const steps = Array.from(document.querySelectorAll(".timeline-item"));

let currentTaskId = "";
let pollTimer = 0;

const statusLabels = {
  queued: "排队",
  running: "解析中",
  succeeded: "完成",
  failed: "失败",
};

function apiFetch(url, options = {}) {
  return fetch(url, {
    ...options,
    headers: {
      "ngrok-skip-browser-warning": "true",
      ...(options.headers || {}),
    },
  });
}

function setBusy(isBusy) {
  submitButton.disabled = isBusy;
  submitButton.textContent = isBusy ? "处理中" : "启动解析";
}

function formatBytes(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

function setArchiveEnabled(isEnabled) {
  archiveButton.classList.toggle("disabled", !isEnabled);
  archiveButton.setAttribute("aria-disabled", isEnabled ? "false" : "true");
  archiveButton.href = isEnabled ? `/api/tasks/${currentTaskId}/archive` : "#";
}

function renderFiles(files) {
  if (!files.length) {
    setArchiveEnabled(false);
    fileTable.innerHTML = '<p class="empty-state">暂无可下载文件。</p>';
    return;
  }
  setArchiveEnabled(Boolean(currentTaskId));
  fileTable.innerHTML = files
    .map(
      (file) => `
        <div class="file-row">
          <span class="file-path">${file.path}</span>
          <span class="file-size">${formatBytes(file.size)}</span>
          <a class="download-link" href="/api/tasks/${currentTaskId}/files/${encodePath(file.path)}">下载</a>
        </div>
      `,
    )
    .join("");
}

function setTimeline(status) {
  steps.forEach((step) => {
    step.classList.remove("active", "failed");
    const stepName = step.dataset.step;
    if (status === "queued" && stepName === "queued") step.classList.add("active");
    if (status === "running" && ["queued", "running"].includes(stepName)) {
      step.classList.add("active");
    }
    if (status === "succeeded") step.classList.add("active");
    if (status === "failed" && ["queued", "running"].includes(stepName)) {
      step.classList.add("active");
    }
    if (status === "failed" && stepName === "succeeded") step.classList.add("failed");
  });
}

async function loadFiles(taskId) {
  const response = await apiFetch(`/api/tasks/${taskId}/files`);
  if (!response.ok) return;
  renderFiles(await response.json());
}

async function pollTask(taskId) {
  const response = await apiFetch(`/api/tasks/${taskId}`);
  if (!response.ok) return;
  const task = await response.json();
  globalStatus.textContent = statusLabels[task.status] || task.status;
  taskMessage.textContent = task.message;
  setTimeline(task.status);
  if (task.status === "succeeded" || task.status === "failed") {
    clearInterval(pollTimer);
    setBusy(false);
    refreshButton.disabled = false;
    await loadFiles(taskId);
  }
}

fileInput.addEventListener("change", () => {
  fileLabel.textContent = fileInput.files[0]
    ? fileInput.files[0].name
    : "支持 ZIP / DOCX / PPTX / PDF / TXT";
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragging");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("dragging");
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragging");
  if (event.dataTransfer.files.length) {
    fileInput.files = event.dataTransfer.files;
    fileLabel.textContent = event.dataTransfer.files[0].name;
  }
});

autoFixOption.addEventListener("change", () => {
  if (autoFixOption.checked) reviewOption.checked = true;
});

reviewOption.addEventListener("change", () => {
  if (!reviewOption.checked) autoFixOption.checked = false;
});

refreshButton.addEventListener("click", () => {
  if (currentTaskId) {
    pollTask(currentTaskId);
    loadFiles(currentTaskId);
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) return;

  const data = new FormData();
  data.append("file", fileInput.files[0]);
  data.append("review", reviewOption.checked ? "true" : "false");
  data.append("auto_fix", autoFixOption.checked ? "true" : "false");
  data.append("vision", visionOption.checked ? "true" : "false");

  setBusy(true);
  refreshButton.disabled = true;
  setArchiveEnabled(false);
  fileTable.innerHTML = '<p class="empty-state">任务已提交，等待结果文件。</p>';
  globalStatus.textContent = "queued";
  taskMessage.textContent = "已提交任务。";
  setTimeline("queued");

  try {
    const response = await apiFetch("/api/tasks", { method: "POST", body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "上传失败");
    currentTaskId = payload.task_id;
    taskIdLabel.textContent = currentTaskId;
    pollTask(currentTaskId);
    clearInterval(pollTimer);
    pollTimer = window.setInterval(() => pollTask(currentTaskId), 1600);
  } catch (error) {
    clearInterval(pollTimer);
    setBusy(false);
    globalStatus.textContent = "failed";
    taskMessage.textContent = error.message;
    setTimeline("failed");
  }
});
