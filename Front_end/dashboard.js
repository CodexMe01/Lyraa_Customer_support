document.addEventListener('DOMContentLoaded', async () => {
    let supabase;
    let token;
    
    try {
        const SUPABASE_URL = 'https://qxbsrlgyvelsppngqtsa.supabase.co';
        const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF4YnNybGd5dmVsc3BwbmdxdHNhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY5MzIyOTUsImV4cCI6MjEwMjUwODI5NX0.YOjhAEVgI-voP0VicFt7-kUSowHn85TYaMqb0EI4xiU';
        
        // Basic validation to prevent createClient from throwing if URL is invalid
        if (!SUPABASE_URL.startsWith('http')) {
            throw new Error("Invalid Supabase URL. Please configure Supabase.");
        }

        supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

        const { data: { session }, error } = await supabase.auth.getSession();
        if (error || !session) {
            window.location.href = 'auth.html';
            return;
        }
        
        token = session.access_token;
    } catch (err) {
        console.error("Auth initialization failed:", err);
        // Hide loading overlay so the user can at least see the dashboard UI (even if API calls fail)
        // Or redirect to auth.html. We will hide it to avoid the stuck screen.
        document.getElementById('loadingOverlay').classList.add('hidden');
        // Optionally redirect to auth:
        window.location.href = 'auth.html';
        return;
    }

    
    // API BASE URL
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:';
    const API_ORIGIN = isLocal ? 'http://localhost:8000' : window.location.origin;
    const API_BASE = `${API_ORIGIN}/api`;

    // Global fetch wrapper to include auth token
    async function apiFetch(path, options = {}) {
        const headers = {
            'Authorization': `Bearer ${token}`,
            ...options.headers
        };
        // Don't set Content-Type for FormData (browser sets it automatically with boundary)
        if (options.body instanceof FormData && headers['Content-Type']) {
            delete headers['Content-Type'];
        } else if (!headers['Content-Type'] && !(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }
        
        const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
        if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            try { const err = await response.json(); detail = err.detail || JSON.stringify(err); } catch(e) {
                try { detail = await response.text(); } catch(_) {}
            }
            throw new Error(detail);
        }
        return response.json();
    }

    // Hide Loading Overlay once auth is checked
    document.getElementById('loadingOverlay').classList.add('hidden');

    // 2. NAVIGATION (SPA Tabs)
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.page-section');
    
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Update active nav
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');
            
            // Show target section
            const targetId = item.getAttribute('data-target');
            sections.forEach(s => s.classList.remove('active'));
            document.getElementById(targetId).classList.add('active');

            // Lazy load specific section data
            if (targetId === 'apikeys') loadApiKeys();
            if (targetId === 'knowledge') loadDocuments();
            if (targetId === 'analytics') loadAnalytics();
        });
    });

    // 3. LOGOUT
    document.getElementById('logoutBtn').addEventListener('click', async () => {
        await supabase.auth.signOut();
        window.location.href = 'auth.html';
    });

    // 4. LOAD INITIAL DATA
    async function loadTenantProfile() {
        try {
            const tenant = await apiFetch('/admin/tenants/me');
            document.getElementById('tenantSelector').textContent = tenant.name;
            document.getElementById('settingName').value = tenant.name;
            document.getElementById('settingSlug').value = tenant.slug;
        } catch (err) {
            console.error('Failed to load profile:', err);
        }
    }

    async function loadOverview() {
        try {
            const data = await apiFetch('/admin/overview');
            document.getElementById('statMsgToday').textContent = data.messages_today;
            document.getElementById('statMsgMonth').textContent = data.messages_this_month;
            document.getElementById('statDocs').textContent = data.total_documents;
            document.getElementById('planName').textContent = data.plan.charAt(0).toUpperCase() + data.plan.slice(1);
            
            const usagePct = data.message_limit > 0 ? (data.messages_used / data.message_limit) * 100 : 0;
            document.getElementById('usageBar').style.width = `${Math.min(usagePct, 100)}%`;
            document.getElementById('usageText').textContent = `${data.messages_used} / ${data.message_limit} messages used`;
        } catch (err) {
            console.error('Failed to load overview:', err);
        }
    }

    async function loadAgentPersona() {
        try {
            const persona = await apiFetch('/admin/agent-config');
            document.getElementById('agentName').value = persona.agent_name || '';
            document.getElementById('agentGreeting').value = persona.greeting_message || '';
            document.getElementById('agentPrompt').value = persona.system_prompt || '';
            document.getElementById('agentSlack').value = persona.escalation_channel || '';
        } catch (err) {
            console.error('Failed to load persona:', err);
        }
    }

    // Call on load
    loadTenantProfile();
    loadOverview();
    loadAgentPersona();

    // 5. EVENT LISTENERS: PERSONA
    document.getElementById('personaForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('savePersonaBtn');
        btn.textContent = 'Saving...';
        btn.disabled = true;
        
        try {
            await apiFetch('/admin/agent-config', {
                method: 'PUT',
                body: JSON.stringify({
                    agent_name: document.getElementById('agentName').value,
                    greeting_message: document.getElementById('agentGreeting').value,
                    system_prompt: document.getElementById('agentPrompt').value,
                    escalation_channel: document.getElementById('agentSlack').value
                })
            });
            const msg = document.getElementById('personaSaveMsg');
            msg.style.display = 'inline';
            setTimeout(() => msg.style.display = 'none', 3000);
        } catch (err) {
            alert('Failed to save persona: ' + err.message);
        } finally {
            btn.textContent = 'Save Persona';
            btn.disabled = false;
        }
    });

    // 6. EVENT LISTENERS: SETTINGS
    document.getElementById('settingsForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('saveSettingsBtn');
        btn.textContent = 'Saving...';
        btn.disabled = true;

        try {
            const name = document.getElementById('settingName').value;
            await apiFetch('/admin/tenants/me', {
                method: 'PUT',
                body: JSON.stringify({ name })
            });
            document.getElementById('tenantSelector').textContent = name;
            const msg = document.getElementById('settingsSaveMsg');
            msg.style.display = 'inline';
            setTimeout(() => msg.style.display = 'none', 3000);
        } catch (err) {
            alert('Failed to save settings: ' + err.message);
        } finally {
            btn.textContent = 'Save Settings';
            btn.disabled = false;
        }
    });

    // 7. API KEYS
    async function loadApiKeys() {
        const tbody = document.getElementById('apiKeysTableBody');
        try {
            const keys = await apiFetch('/admin/api-keys');
            tbody.innerHTML = '';
            if (keys.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #5a5a5a;">No API Keys found.</td></tr>`;
                return;
            }
            keys.forEach(key => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><code>${key.key_prefix}...</code></td>
                    <td>${key.label || 'Default'}</td>
                    <td>${new Date(key.created_at).toLocaleDateString()}</td>
                    <td>${key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}</td>
                    <td><span class="badge" style="background: ${key.is_active ? '#dcfce7; color: #166534' : '#fee2e2; color: #991b1b'}">${key.is_active ? 'Active' : 'Revoked'}</span></td>
                    <td>
                        ${key.is_active ? `<button class="btn btn-outline revoke-key-btn" data-id="${key.id}" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;">Revoke</button>` : ''}
                    </td>
                `;
                tbody.appendChild(tr);
            });

            document.querySelectorAll('.revoke-key-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    if(!confirm('Are you sure you want to revoke this key? Any widget using it will stop working immediately.')) return;
                    const id = e.target.getAttribute('data-id');
                    try {
                        await apiFetch(`/admin/api-keys/${id}`, { method: 'DELETE' });
                        loadApiKeys();
                    } catch(err) {
                        alert('Failed to revoke key: ' + err.message);
                    }
                });
            });
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: red;">Failed to load API keys.</td></tr>`;
        }
    }

    document.getElementById('generateKeyBtn').addEventListener('click', async () => {
        const label = prompt("Enter a label for this API key (e.g., 'Production Website'):", "My Website");
        if (!label) return;

        try {
            const data = await apiFetch('/admin/api-keys', {
                method: 'POST',
                body: JSON.stringify({ label })
            });
            document.getElementById('newRawKey').textContent = data.raw_key;
            document.getElementById('newKeyAlert').classList.remove('hidden');
            loadApiKeys();
        } catch (err) {
            alert('Failed to generate key: ' + err.message);
        }
    });

    document.getElementById('copyKeyBtn').addEventListener('click', () => {
        const key = document.getElementById('newRawKey').textContent;
        navigator.clipboard.writeText(key).then(() => {
            const btn = document.getElementById('copyKeyBtn');
            btn.textContent = 'Copied!';
            setTimeout(() => btn.textContent = 'Copy', 2000);
        });
    });

    // 8. KNOWLEDGE BASE (Documents & Upload)
    async function loadDocuments() {
        const tbody = document.getElementById('documentsTableBody');
        try {
            const data = await apiFetch('/documents');
            const docs = data.documents;
            tbody.innerHTML = '';
            
            if (docs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: #5a5a5a;">No documents found. Upload a file or add a web URL above.</td></tr>`;
                return;
            }

            docs.forEach(doc => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${doc.filename}</td>
                    <td>${((doc.size || 0) / 1024).toFixed(1)} KB</td>
                    <td><button class="btn btn-outline delete-doc-btn" data-id="${doc.public_id}" style="padding: 0.25rem 0.5rem; color: var(--color-danger); border-color: var(--color-danger); font-size: 0.75rem;">Delete</button></td>
                `;
                tbody.appendChild(tr);
            });

            document.querySelectorAll('.delete-doc-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = e.target.getAttribute('data-id');
                    if(!confirm('Delete this document? You must Sync & Ingest afterwards to remove it from the AI knowledge base.')) return;
                    try {
                        await apiFetch(`/documents?public_id=${encodeURIComponent(id)}`, { method: 'DELETE' });
                        loadDocuments();
                    } catch(err) {
                        alert('Failed to delete document: ' + err.message);
                    }
                });
            });
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: red;">Failed to load documents.</td></tr>`;
        }
    }

    // File Upload Handlers
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const uploadStatus = document.getElementById('uploadStatus');

    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.style.borderColor = 'var(--color-primary)'; });
    dropzone.addEventListener('dragleave', () => { dropzone.style.borderColor = 'var(--color-border)'; });
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.style.borderColor = 'var(--color-border)';
        if (e.dataTransfer.files.length > 0) handleFileUpload(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) handleFileUpload(fileInput.files[0]);
    });

    async function handleFileUpload(file) {
        uploadStatus.style.color = '#000';
        uploadStatus.textContent = `Uploading ${file.name}...`;
        const formData = new FormData();
        formData.append('file', file);

        try {
            await apiFetch('/upload', { method: 'POST', body: formData });
            uploadStatus.style.color = 'green';
            uploadStatus.textContent = `Successfully uploaded ${file.name}. Don't forget to Sync & Ingest!`;
            loadDocuments();
        } catch (err) {
            uploadStatus.style.color = 'red';
            uploadStatus.textContent = `Upload failed: ${err.message}`;
        } finally {
            fileInput.value = '';  // Always reset so same file can be re-selected
        }
    }

    // Add Web URL
    document.getElementById('addUrlBtn').addEventListener('click', async () => {
        const url = document.getElementById('webUrlInput').value;
        const btn = document.getElementById('addUrlBtn');
        if (!url) return;
        
        btn.disabled = true;
        btn.textContent = 'Scraping...';
        try {
            await apiFetch('/add-link', {
                method: 'POST',
                body: JSON.stringify({ url })
            });
            document.getElementById('webUrlInput').value = '';
            alert('Successfully extracted web content. Remember to Sync & Ingest!');
            loadDocuments();
        } catch (err) {
            alert('Scraping failed: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Scrape & Add';
        }
    });

    // Ingest
    document.getElementById('triggerIngestBtn').addEventListener('click', async () => {
        const btn = document.getElementById('triggerIngestBtn');
        btn.disabled = true;
        btn.textContent = 'Syncing vectors...';
        try {
            const data = await apiFetch('/ingest', {
                method: 'POST',
                body: JSON.stringify({ mode: 'all' })
            });
            alert(data.message);
        } catch(err) {
            alert('Ingest failed: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Sync & Ingest';
        }
    });

    // 9. ANALYTICS
    async function loadAnalytics() {
        const tbody = document.getElementById('intentTableBody');
        try {
            const data = await apiFetch('/admin/analytics');
            tbody.innerHTML = '';
            
            if (!data.intent_breakdown || data.intent_breakdown.length === 0) {
                tbody.innerHTML = `<tr><td colspan="2" style="text-align: center; color: #5a5a5a;">No usage data yet.</td></tr>`;
                return;
            }

            data.intent_breakdown.forEach(intent => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><span class="badge" style="background: rgba(0,0,0,0.08);">${intent.intent}</span></td>
                    <td>${intent.count}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="2" style="text-align: center; color: red;">Failed to load analytics.</td></tr>`;
        }
    }
});
