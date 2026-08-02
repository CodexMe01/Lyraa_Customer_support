// Core Javascript for RAG Developer Dashboard Console
document.addEventListener('DOMContentLoaded', () => {

    // Automatically determine the backend base URL (fallback to localhost:8000 if opened directly as file)
    const isLocalFile = window.location.protocol === 'file:';
    const API_ORIGIN = isLocalFile ? 'http://localhost:8000' : window.location.origin;
    const BASE_URL = `${API_ORIGIN}/api`;

    // Elements
    const apiStatusDot = document.getElementById('api-status-dot');
    const apiStatusText = document.getElementById('api-status-text');
    
    const webUrlInput = document.getElementById('web-url-input');
    const addUrlBtn = document.getElementById('add-url-btn');
    
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const fileInfoBar = document.getElementById('file-info-bar');
    const selectedFileName = document.getElementById('selected-file-name');
    const clearFileBtn = document.getElementById('clear-file-btn');
    const uploadSubmitBtn = document.getElementById('upload-submit-btn');
    
    const ingestBtn = document.getElementById('ingest-btn');
    const documentsTableBody = document.getElementById('documents-table-body');

    const ingestModal = document.getElementById('ingest-modal');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const modalConfirmBtn = document.getElementById('modal-confirm-btn');
    const optAll = document.getElementById('opt-all');
    const optRecent = document.getElementById('opt-recent');
    
    const chatInput = document.getElementById('chat-input');
    const sendChatBtn = document.getElementById('send-chat-btn');
    const chatBox = document.getElementById('chat-box');
    const chatTyping = document.getElementById('chat-typing');
    
    const consoleBox = document.getElementById('console-box');

    let selectedFile = null;

    // Helper: Print to Console Widget
    function log(message, type = 'info') {
        const line = document.createElement('div');
        line.className = `console-line ${type}`;
        const time = new Date().toLocaleTimeString();
        line.textContent = `[${time}] ${message}`;
        consoleBox.appendChild(line);
        consoleBox.scrollTop = consoleBox.scrollHeight;
    }

    // Check API Connection Status
    async function checkBackendStatus() {
        try {
            // Check health
            const response = await fetch(`${API_ORIGIN}/health`);
            if (response.ok) {
                apiStatusDot.className = 'status-dot connected';
                apiStatusText.textContent = 'Backend Connected';
                log('Successfully connected to Lyraa Backend API.', 'system');
                fetchDocuments();
            } else {
                throw new Error('Health check returned non-200');
            }
        } catch (error) {
            apiStatusDot.className = 'status-dot';
            apiStatusText.textContent = 'Disconnected';
            log('Could not connect to Lyraa Backend. Ensure uvicorn server is running on port 8000.', 'error');
        }
    }

    // List Documents
    async function fetchDocuments() {
        try {
            const response = await fetch(`${BASE_URL}/documents`);
            if (!response.ok) throw new Error('Failed to retrieve documents');
            const data = await response.json();
            renderDocuments(data.documents);
        } catch (error) {
            log(`Error fetching documents: ${error.message}`, 'error');
        }
    }

    // Render Documents Table
    function renderDocuments(documents) {
        documentsTableBody.innerHTML = '';
        if (!documents || documents.length === 0) {
            documentsTableBody.innerHTML = `
                <tr>
                    <td colspan="3" class="empty-table-msg">No documents ingested in the data directory.</td>
                </tr>
            `;
            return;
        }

        documents.forEach(doc => {
            const sizeKB = (doc.size / 1024).toFixed(1);
            const row = document.createElement('tr');
            row.innerHTML = `
                <td title="${doc.name}">${doc.name}</td>
                <td>${sizeKB} KB</td>
                <td style="text-align: center;">
                    <button class="action-icon-btn delete-doc-btn" data-name="${doc.name}">🗑️</button>
                </td>
            `;
            documentsTableBody.appendChild(row);
        });

        // Add Delete Event Listeners
        document.querySelectorAll('.delete-doc-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const name = btn.getAttribute('data-name');
                deleteDocument(name);
            });
        });
    }

    // Delete Document
    async function deleteDocument(filename) {
        if (!confirm(`Are you sure you want to delete ${filename}?`)) return;
        try {
            log(`Deleting document: ${filename}...`, 'info');
            const response = await fetch(`${BASE_URL}/documents/${filename}`, {
                method: 'DELETE'
            });
            const data = await response.json();
            if (response.ok) {
                log(`Successfully deleted ${filename}.`, 'system');
                fetchDocuments();
            } else {
                throw new Error(data.detail || 'Delete failed');
            }
        } catch (error) {
            log(`Delete failed: ${error.message}`, 'error');
        }
    }

    // Extract Web URL (Tavily)
    async function extractWebUrl() {
        const url = webUrlInput.value.trim();
        if (!url) {
            alert('Please enter a valid URL.');
            return;
        }

        try {
            log(`Triggering Tavily extraction for: ${url}...`, 'info');
            addUrlBtn.disabled = true;
            addUrlBtn.textContent = 'Extracting...';

            const response = await fetch(`${BASE_URL}/add-link`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            });
            const data = await response.json();

            if (response.ok) {
                log(data.message, 'system');
                webUrlInput.value = '';
                fetchDocuments();
            } else {
                throw new Error(data.detail || 'Scraping failed');
            }
        } catch (error) {
            log(`Extraction failed: ${error.message}`, 'error');
        } finally {
            addUrlBtn.disabled = false;
            addUrlBtn.textContent = 'Extract';
        }
    }

    // File Selection & Drag-and-Drop Handlers
    dropzone.addEventListener('click', () => fileInput.click());

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.style.borderColor = 'var(--color-primary)';
        dropzone.style.backgroundColor = 'rgba(59, 130, 246, 0.05)';
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.style.borderColor = 'rgba(255, 255, 255, 0.15)';
        dropzone.style.backgroundColor = 'rgba(255, 255, 255, 0.02)';
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.style.borderColor = 'rgba(255, 255, 255, 0.15)';
        dropzone.style.backgroundColor = 'rgba(255, 255, 255, 0.02)';
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });

    function handleFileSelect(file) {
        selectedFile = file;
        selectedFileName.textContent = file.name;
        fileInfoBar.style.display = 'flex';
        uploadSubmitBtn.style.display = 'flex';
        log(`File selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB). Ready to upload.`, 'info');
    }

    clearFileBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        resetFileForm();
        log('File selection cleared.', 'info');
    });

    function resetFileForm() {
        selectedFile = null;
        fileInput.value = '';
        selectedFileName.textContent = 'No file selected';
        fileInfoBar.style.display = 'none';
        uploadSubmitBtn.style.display = 'none';
    }

    // Upload File
    document.getElementById('file-upload-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!selectedFile) return;

        const formData = new FormData();
        formData.append('file', selectedFile);

        try {
            log(`Uploading file ${selectedFile.name}...`, 'info');
            uploadSubmitBtn.disabled = true;
            uploadSubmitBtn.textContent = 'Uploading...';

            const response = await fetch(`${BASE_URL}/upload`, {
                method: 'POST',
                body: formData
            });
            const data = await response.json();

            if (response.ok) {
                log(data.message, 'system');
                resetFileForm();
                fetchDocuments();
            } else {
                throw new Error(data.detail || 'Upload failed');
            }
        } catch (error) {
            log(`Upload failed: ${error.message}`, 'error');
        } finally {
            uploadSubmitBtn.disabled = false;
            uploadSubmitBtn.textContent = 'Upload File';
        }
    });

    // MODAL: Ingest Mode Selection
    let selectedIngestMode = 'all';

    function openIngestModal() {
        // Reset to default selection
        selectedIngestMode = 'all';
        optAll.classList.add('selected');
        optRecent.classList.remove('selected');
        ingestModal.classList.add('visible');
    }

    function closeIngestModal() {
        ingestModal.classList.remove('visible');
    }

    [optAll, optRecent].forEach(opt => {
        opt.addEventListener('click', () => {
            optAll.classList.remove('selected');
            optRecent.classList.remove('selected');
            opt.classList.add('selected');
            selectedIngestMode = opt.dataset.mode;
        });
    });

    modalCancelBtn.addEventListener('click', () => {
        closeIngestModal();
        log('Ingestion cancelled by user.', 'info');
    });

    // Close modal when clicking on the backdrop
    ingestModal.addEventListener('click', (e) => {
        if (e.target === ingestModal) {
            closeIngestModal();
            log('Ingestion cancelled by user.', 'info');
        }
    });

    modalConfirmBtn.addEventListener('click', () => {
        closeIngestModal();
        ingestData(false, selectedIngestMode);
    });

    // Ingest Knowledge Base
    async function ingestData(isAuto = false, mode = 'all') {
        const modeLabel = mode === 'recent' ? 'recent files only (last 24 hours)' : 'all files';
        try {
            log(`Ingestion mode: ${modeLabel}`, 'system');
            log('Initializing Pinecone & Gemini vector database sync...', 'info');
            log('Starting document processing pipeline (identifying file types)...', 'info');
            ingestBtn.disabled = true;
            ingestBtn.textContent = 'Ingesting & Syncing...';

            const response = await fetch(`${BASE_URL}/ingest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: mode })
            });
            const data = await response.json();

            if (response.ok) {
                log(data.message, 'system');
                if (!isAuto) {
                    alert(data.message);
                }
            } else {
                throw new Error(data.detail || 'Ingestion failed');
            }
        } catch (error) {
            log(`Ingestion failed: ${error.message}`, 'error');
            if (!isAuto) {
                alert(`Ingestion failed: ${error.message}`);
            }
        } finally {
            ingestBtn.disabled = false;
            ingestBtn.textContent = '🚀 Sync & Ingest Knowledge Base';
        }
    }

    // Chat Interface Handlers
    function appendChatMessage(text, sender = 'bot') {
        const msg = document.createElement('div');
        msg.className = `chat-msg ${sender}`;
        msg.innerHTML = `<div class="msg-bubble">${text}</div>`;
        chatBox.appendChild(msg);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    async function sendChatMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        appendChatMessage(text, 'user');
        chatInput.value = '';
        chatTyping.style.display = 'flex';
        chatBox.scrollTop = chatBox.scrollHeight;

        log(`Sending query to RAG agent: "${text}"`, 'info');

        try {
            const response = await fetch(`${BASE_URL}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });
            const data = await response.json();

            chatTyping.style.display = 'none';

            if (response.ok) {
                appendChatMessage(data.response, 'bot');
                log('Agent responded successfully.', 'system');
            } else {
                throw new Error(data.detail || 'Chat query failed');
            }
        } catch (error) {
            chatTyping.style.display = 'none';
            appendChatMessage(`Error: ${error.message}. Make sure you ingested documents and configured your keys.`, 'bot');
            log(`Chat failed: ${error.message}`, 'error');
        }
    }

    // Bind Button Events
    addUrlBtn.addEventListener('click', extractWebUrl);
    webUrlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') extractWebUrl();
    });

    ingestBtn.addEventListener('click', openIngestModal);

    sendChatBtn.addEventListener('click', sendChatMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendChatMessage();
    });

    // Start status check
    checkBackendStatus();
});
