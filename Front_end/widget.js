/**
 * Lyraa Chat Widget
 * Embeddable script for tenant websites.
 * 
 * Usage:
 * <script src="https://lyraa-widget.vercel.app/widget.js" data-api-key="YOUR_API_KEY"></script>
 */

(function () {
    // Prevent multiple initializations
    if (window.LyraaWidgetInitialized) return;
    window.LyraaWidgetInitialized = true;

    // Extract API Key from script tag
    const currentScript = document.currentScript;
    const apiKey = currentScript.getAttribute('data-api-key');

    if (!apiKey) {
        console.error('[Lyraa Widget] Missing data-api-key attribute on script tag.');
        return;
    }

    // Configuration
    // TODO: Change this to production backend URL when deploying
    const API_BASE_URL = 'http://localhost:8000/api'; 
    
    // Generate a unique session ID for this user's browser session
    let sessionId = sessionStorage.getItem('lyraa_session_id');
    if (!sessionId) {
        sessionId = 'sess_' + Math.random().toString(36).substring(2, 15);
        sessionStorage.setItem('lyraa_session_id', sessionId);
    }

    // Add styles to head
    const style = document.createElement('style');
    style.innerHTML = `
        /* Widget Container */
        .lyraa-widget-container {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 2147483647; /* Max z-index to stay on top */
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 16px;
            pointer-events: none; /* Let clicks pass through container */
        }

        /* Launcher Button */
        .lyraa-launcher {
            width: 60px;
            height: 60px;
            border-radius: 30px;
            background-color: #000;
            color: #fff;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: transform 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            pointer-events: auto;
        }

        .lyraa-launcher:hover {
            transform: scale(1.05);
        }

        .lyraa-launcher svg {
            width: 32px;
            height: 32px;
            fill: currentColor;
            transition: transform 0.3s;
        }
        
        .lyraa-widget-open .lyraa-launcher svg {
            transform: rotate(90deg) scale(0);
        }

        /* Chat Window */
        .lyraa-chat-window {
            width: 380px;
            height: 600px;
            max-height: calc(100vh - 100px);
            background: #fff;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.04);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            opacity: 0;
            transform: translateY(20px) scale(0.95);
            transform-origin: bottom right;
            transition: opacity 0.3s, transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.1);
            pointer-events: none;
            border: 1px solid rgba(0,0,0,0.05);
        }

        .lyraa-widget-open .lyraa-chat-window {
            opacity: 1;
            transform: translateY(0) scale(1);
            pointer-events: auto;
        }

        /* Header */
        .lyraa-header {
            background: #000;
            color: #fff;
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .lyraa-title {
            font-size: 18px;
            font-weight: 600;
            margin: 0;
        }

        .lyraa-subtitle {
            font-size: 14px;
            opacity: 0.8;
            margin: 0;
        }

        /* Messages Area */
        .lyraa-messages {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 16px;
            background: #faf9f6;
        }

        .lyraa-message {
            max-width: 85%;
            font-size: 14px;
            line-height: 1.5;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .lyraa-message.bot {
            align-self: flex-start;
        }

        .lyraa-message.user {
            align-self: flex-end;
            align-items: flex-end;
        }

        .lyraa-bubble {
            padding: 12px 16px;
            border-radius: 12px;
        }

        .lyraa-message.bot .lyraa-bubble {
            background: #fff;
            color: #111;
            border: 1px solid rgba(0,0,0,0.08);
            border-bottom-left-radius: 4px;
        }

        .lyraa-message.user .lyraa-bubble {
            background: #000ce1; /* Intercom Blue */
            color: #fff;
            border-bottom-right-radius: 4px;
        }

        /* Input Area */
        .lyraa-input-area {
            padding: 16px;
            background: #fff;
            border-top: 1px solid rgba(0,0,0,0.08);
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .lyraa-input {
            flex: 1;
            border: 1px solid rgba(0,0,0,0.12);
            border-radius: 20px;
            padding: 12px 16px;
            font-size: 14px;
            font-family: inherit;
            outline: none;
            transition: border-color 0.2s;
        }

        .lyraa-input:focus {
            border-color: #000ce1;
        }

        .lyraa-send-btn {
            background: #000ce1;
            color: #fff;
            border: none;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: background 0.2s;
        }

        .lyraa-send-btn:hover {
            background: #0000bd;
        }

        .lyraa-send-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }

        /* Typing Indicator */
        .lyraa-typing {
            display: none;
            align-self: flex-start;
            background: #fff;
            padding: 12px 16px;
            border-radius: 12px;
            border-bottom-left-radius: 4px;
            border: 1px solid rgba(0,0,0,0.08);
            gap: 4px;
            align-items: center;
        }

        .lyraa-typing span {
            width: 6px;
            height: 6px;
            background: #aaa;
            border-radius: 50%;
            display: inline-block;
            animation: lyraa-bounce 1.4s infinite ease-in-out both;
        }

        .lyraa-typing span:nth-child(1) { animation-delay: -0.32s; }
        .lyraa-typing span:nth-child(2) { animation-delay: -0.16s; }

        @keyframes lyraa-bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1.0); }
        }

        /* Mobile adjustments */
        @media (max-width: 480px) {
            .lyraa-chat-window {
                position: fixed;
                inset: 0;
                width: 100%;
                height: 100%;
                max-height: 100%;
                border-radius: 0;
            }
            .lyraa-launcher {
                display: none; /* Hide launcher when chat is open on mobile */
            }
        }
    `;
    document.head.appendChild(style);

    // Build DOM
    const container = document.createElement('div');
    container.className = 'lyraa-widget-container';

    // Chat Window
    const chatWindow = document.createElement('div');
    chatWindow.className = 'lyraa-chat-window';
    chatWindow.innerHTML = `
        <div class="lyraa-header">
            <h2 class="lyraa-title">Support</h2>
            <p class="lyraa-subtitle">We typically reply in a few minutes.</p>
        </div>
        <div class="lyraa-messages" id="lyraa-messages">
            <div class="lyraa-message bot">
                <div class="lyraa-bubble" id="lyraa-greeting">Hello! How can we help you today?</div>
            </div>
            <div class="lyraa-typing" id="lyraa-typing">
                <span></span><span></span><span></span>
            </div>
        </div>
        <form class="lyraa-input-area" id="lyraa-form">
            <input type="text" class="lyraa-input" id="lyraa-input" placeholder="Type a message..." autocomplete="off">
            <button type="submit" class="lyraa-send-btn" id="lyraa-send-btn" disabled>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M2.01 21L23 12L2.01 3L2 10l15 2-15 2z" fill="currentColor"/>
                </svg>
            </button>
        </form>
    `;

    // Launcher
    const launcher = document.createElement('div');
    launcher.className = 'lyraa-launcher';
    launcher.innerHTML = `
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <!-- Intercom-like chat icon -->
            <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
        </svg>
    `;

    container.appendChild(chatWindow);
    container.appendChild(launcher);
    document.body.appendChild(container);

    // Elements
    const messagesArea = document.getElementById('lyraa-messages');
    const inputArea = document.getElementById('lyraa-input');
    const form = document.getElementById('lyraa-form');
    const sendBtn = document.getElementById('lyraa-send-btn');
    const typingIndicator = document.getElementById('lyraa-typing');

    // Toggle logic
    let isOpen = false;
    launcher.addEventListener('click', () => {
        isOpen = !isOpen;
        if (isOpen) {
            container.classList.add('lyraa-widget-open');
            inputArea.focus();
            
            // Re-render icon to X when open
            launcher.innerHTML = `
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/>
                </svg>
            `;
        } else {
            container.classList.remove('lyraa-widget-open');
            // Re-render icon to chat bubble when closed
            launcher.innerHTML = `
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
                </svg>
            `;
        }
    });

    // Input state
    inputArea.addEventListener('input', () => {
        sendBtn.disabled = inputArea.value.trim().length === 0;
    });

    function appendMessage(text, isUser) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `lyraa-message ${isUser ? 'user' : 'bot'}`;
        msgDiv.innerHTML = `<div class="lyraa-bubble">${text}</div>`;
        
        // Insert before typing indicator
        messagesArea.insertBefore(msgDiv, typingIndicator);
        messagesArea.scrollTop = messagesArea.scrollHeight;
    }

    // Submit handler
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = inputArea.value.trim();
        if (!text) return;

        // Reset input
        inputArea.value = '';
        sendBtn.disabled = true;

        // Show user message
        appendMessage(text, true);

        // Show typing indicator
        typingIndicator.style.display = 'flex';
        messagesArea.scrollTop = messagesArea.scrollHeight;

        try {
            const response = await fetch(`${API_BASE_URL}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': apiKey // Auths the tenant and loads their RAG engine!
                },
                body: JSON.stringify({
                    message: text,
                    session_id: sessionId
                })
            });

            const data = await response.json();
            typingIndicator.style.display = 'none';

            if (response.ok) {
                appendMessage(data.response, false);
            } else {
                appendMessage(data.detail || "I'm having trouble connecting right now. Please try again later.", false);
            }
        } catch (error) {
            typingIndicator.style.display = 'none';
            appendMessage("Network error. Please check your connection and try again.", false);
            console.error('[Lyraa Widget] Error:', error);
        }
    });

})();
