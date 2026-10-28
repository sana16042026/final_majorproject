// upload.js - File upload handling, validation & pipeline execution

document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('file-input');
    const btnBrowse = document.getElementById('btn-browse');
    const dropzone = document.getElementById('dropzone');
    const btnStart = document.getElementById('btn-start-process');
    const fileInfo = document.getElementById('selected-file-info');
    const btnLoadSample = document.getElementById('btn-load-sample');

    let selectedFile = null;

    btnBrowse.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelection(e.target.files[0]);
        }
    });

    // Drag & drop handlers
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });

    function handleFileSelection(file) {
        selectedFile = file;
        fileInfo.innerHTML = `<i class="bi bi-file-earmark-check-fill text-success me-1"></i> Selected: <strong>${file.name}</strong> (${(file.size / 1024).toFixed(1)} KB)`;
        fileInfo.classList.remove('d-none');
        btnStart.removeAttribute('disabled');
    }

    // Process & Save
    btnStart.addEventListener('click', () => {
        if (!selectedFile) return;
        uploadDatasetFile(selectedFile);
    });

    // Instant Sample Demo Loader
    btnLoadSample.addEventListener('click', () => {
        loadSampleDemoDataset();
    });
});

function uploadDatasetFile(file) {
    const processingBox = document.getElementById('processing-box');
    const statusBanner = document.getElementById('status-banner');
    const statusText = document.getElementById('status-text');
    const statusSpinner = document.getElementById('status-spinner');

    processingBox.classList.remove('d-none');
    statusBanner.className = 'alert alert-info d-flex align-items-center mb-4';
    statusSpinner.classList.remove('d-none');
    statusText.textContent = `Uploading and processing ${file.name}...`;

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/upload', {
        method: 'POST',
        body: formData
    })
    .then(async res => {
        let data;
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            data = await res.json();
        } else {
            const rawText = await res.text();
            throw new Error(`Server returned HTML error (${res.status} ${res.statusText}). Make sure python run.py is running.`);
        }

        if (!res.ok || !data.success) {
            throw new Error(data.message || 'Data processing failed');
        }
        return data;
    })
    .then(data => {
        statusSpinner.classList.add('d-none');
        statusBanner.className = 'alert alert-success d-flex align-items-center mb-4';
        // Required exact format: "Dataset uploaded successfully — X projects processed."
        statusText.innerHTML = `<strong>${data.message}</strong>`;
        showToast(data.message, 'success');
    })
    .catch(err => {
        statusSpinner.classList.add('d-none');
        statusBanner.className = 'alert alert-danger d-flex align-items-center mb-4';
        let errText = err.message;
        if (err.message.includes('Unexpected token') || err.message.includes('Failed to fetch')) {
            errText = 'Server connection error. Please make sure python run.py is running on http://127.0.0.1:5000.';
        }
        statusText.innerHTML = `<strong>Error:</strong> ${errText}`;
        showToast(`Upload failed: ${errText}`, 'danger');
    });
}

function loadSampleDemoDataset() {
    const processingBox = document.getElementById('processing-box');
    const statusBanner = document.getElementById('status-banner');
    const statusText = document.getElementById('status-text');
    const statusSpinner = document.getElementById('status-spinner');

    processingBox.classList.remove('d-none');
    statusBanner.className = 'alert alert-info d-flex align-items-center mb-4';
    statusSpinner.classList.remove('d-none');
    statusText.textContent = 'Loading master road-work dataset into MySQL...';

    fetch('/api/load-sample', {
        method: 'POST'
    })
    .then(async res => {
        let data;
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            data = await res.json();
        } else {
            const rawText = await res.text();
            throw new Error(`Server returned HTML error (${res.status} ${res.statusText}).`);
        }

        if (!res.ok || !data.success) {
            throw new Error(data.message || 'Failed to load master dataset');
        }
        return data;
    })
    .then(data => {
        statusSpinner.classList.add('d-none');
        statusBanner.className = 'alert alert-success d-flex align-items-center mb-4';
        statusText.innerHTML = `<strong>${data.message}</strong>`;
        showToast(data.message, 'success');
    })
    .catch(err => {
        statusSpinner.classList.add('d-none');
        statusBanner.className = 'alert alert-danger d-flex align-items-center mb-4';
        let errText = err.message;
        if (err.message.includes('Unexpected token') || err.message.includes('Failed to fetch')) {
            errText = 'Server connection error. Please make sure python run.py is running on http://127.0.0.1:5000.';
        }
        statusText.innerHTML = `<strong>Error:</strong> ${errText}`;
        showToast(`Master load failed: ${errText}`, 'danger');
    });
}
