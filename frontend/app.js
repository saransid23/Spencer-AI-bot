/* ==========================================================================
   Spencer AI — Frontend Application
   Features: SSE Streaming, Markdown Rendering, Syntax Highlighting,
             TTS, Session History Sidebar, Voice Input, Dark/Light Theme
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {

    // ── Intro Animation ──────────────────────────────────────────────────────
    const introOverlay = document.getElementById('introOverlay');
    const appContainer = document.querySelector('.app-container');

    if (introOverlay && appContainer) {
        setTimeout(() => {
            introOverlay.classList.add('hidden');
            appContainer.classList.add('visible');
        }, 2400);
    }

    // ── DOM References ──────────────────────────────────────────────────────
    const chatInput       = document.getElementById('chatInput');
    const sendBtn         = document.getElementById('sendBtn');
    const chatHistory     = document.getElementById('chatHistory');
    const chatArea        = document.getElementById('chatArea');
    const greetingContainer = document.getElementById('greetingContainer');
    const themeToggleBtn  = document.getElementById('themeToggle');
    const voiceBtn        = document.getElementById('voiceBtn');
    const ttsToggleBtn    = document.getElementById('ttsToggle');
    const newChatBtn      = document.getElementById('newChatBtn');
    const chatList        = document.getElementById('chatList');
    const refreshSessionsBtn = document.getElementById('refreshSessionsBtn');
    const sidebarToggleBtn   = document.getElementById('sidebarToggle');
    const sidebar            = document.getElementById('sidebar');
    const chipButtons        = document.querySelectorAll('.chip');

    const API_BASE = window.location.protocol === 'file:' ? 'http://localhost:8000' : window.location.origin;

    // ── State ────────────────────────────────────────────────────────────────
    let sessionId       = generateSessionId();
    let activeSessionId = sessionId;
    let isFirstMessage  = true;
    let isStreaming     = false;
    let ttsEnabled      = false;
    let mediaRecorder;
    let audioChunks     = [];
    let isRecording     = false;

    // ── Marked.js Configuration ──────────────────────────────────────────────
    marked.setOptions({
        highlight: null,  // We handle highlighting ourselves via postprocess
        gfm: true,
        breaks: true,
    });

    // Custom renderer to wrap code blocks in our styled wrapper
    const renderer = new marked.Renderer();
    renderer.code = (code, language) => {
        const lang = (language || 'plaintext').toLowerCase();
        const escapedCode = code
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        return `<div class="code-block-wrapper" data-lang="${lang}">
            <div class="code-block-header">
                <span>${lang}</span>
                <button class="copy-code-btn" onclick="copyCode(this)">
                    <i class="fa-regular fa-copy"></i> Copy
                </button>
            </div>
            <pre><code class="language-${lang}">${escapedCode}</code></pre>
        </div>`;
    };
    marked.use({ renderer });

    // ── Global copy helper (used by inline onclick in rendered code) ─────────
    window.copyCode = (btn) => {
        const pre = btn.closest('.code-block-wrapper').querySelector('pre code');
        const text = pre.innerText || pre.textContent;
        navigator.clipboard.writeText(text).then(() => {
            btn.innerHTML = '<i class="fa-solid fa-check"></i> Copied!';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.innerHTML = '<i class="fa-regular fa-copy"></i> Copy';
                btn.classList.remove('copied');
            }, 2000);
        }).catch(() => {
            btn.textContent = 'Error';
        });
    };

    // ── Theme ────────────────────────────────────────────────────────────────
    function initTheme() {
        const saved = localStorage.getItem('spencer-theme') || 'dark';
        applyTheme(saved);
    }

    function applyTheme(theme) {
        const isDark = theme === 'dark';
        document.body.classList.toggle('dark-theme', isDark);
        document.body.classList.toggle('light-theme', !isDark);

        // Swap highlight.js stylesheet
        const darkTheme  = document.getElementById('hljs-dark-theme');
        const lightTheme = document.getElementById('hljs-light-theme');
        if (darkTheme && lightTheme) {
            darkTheme.disabled  = !isDark;
            lightTheme.disabled = isDark;
        }
        localStorage.setItem('spencer-theme', theme);
    }

    themeToggleBtn.addEventListener('click', () => {
        const isDark = document.body.classList.contains('dark-theme');
        applyTheme(isDark ? 'light' : 'dark');
    });
    initTheme();

    // ── Sidebar Toggle ────────────────────────────────────────────────────────
    sidebarToggleBtn.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
    });

    // ── TTS ──────────────────────────────────────────────────────────────────
    ttsToggleBtn.addEventListener('click', () => {
        ttsEnabled = !ttsEnabled;
        ttsToggleBtn.classList.toggle('active', ttsEnabled);
        ttsToggleBtn.title = ttsEnabled ? 'TTS: On (click to disable)' : 'Toggle Text-to-Speech';
        if (!ttsEnabled) window.speechSynthesis?.cancel();
    });

    function speakText(text) {
        if (!ttsEnabled || !window.speechSynthesis) return;
        window.speechSynthesis.cancel();
        // Strip markdown symbols for cleaner TTS
        const clean = text
            .replace(/```[\s\S]*?```/g, 'code block')
            .replace(/`([^`]+)`/g, '$1')
            .replace(/\*\*(.+?)\*\*/g, '$1')
            .replace(/\*(.+?)\*/g, '$1')
            .replace(/#{1,6}\s/g, '')
            .replace(/\[(.+?)\]\(.+?\)/g, '$1')
            .trim();

        const utterance = new SpeechSynthesisUtterance(clean);
        utterance.rate = 1.05;
        utterance.pitch = 1;
        window.speechSynthesis.speak(utterance);
    }

    // ── Auto-resize Textarea ─────────────────────────────────────────────────
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + 'px';
    });

    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!isStreaming) sendMessage();
        }
    });

    sendBtn.addEventListener('click', () => { if (!isStreaming) sendMessage(); });

    // ── New Chat ─────────────────────────────────────────────────────────────
    newChatBtn.addEventListener('click', () => startNewChat());

    function startNewChat() {
        sessionId = generateSessionId();
        activeSessionId = sessionId;
        isFirstMessage = true;
        chatInput.value = '';
        chatInput.style.height = 'auto';
        chatHistory.innerHTML = '';
        chatHistory.style.display = 'none';
        greetingContainer.style.display = '';
        greetingContainer.classList.remove('fade-out');
        document.querySelectorAll('.chat-history-item').forEach(el => el.classList.remove('active'));
    }

    // ── Suggestion Chips ──────────────────────────────────────────────────────
    chipButtons.forEach(chip => {
        chip.addEventListener('click', () => {
            const prompt = chip.dataset.prompt;
            if (prompt && !isStreaming) {
                chatInput.value = prompt;
                sendMessage();
            }
        });
    });

    // ── Session ID ───────────────────────────────────────────────────────────
    function generateSessionId() {
        return 'session_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 6);
    }

    // ── Send Message (SSE Streaming) ─────────────────────────────────────────
    async function sendMessage() {
        const message = chatInput.value.trim();
        if (!message || isStreaming) return;

        // Transition from greeting to chat
        if (isFirstMessage) {
            greetingContainer.classList.add('fade-out');
            setTimeout(() => {
                greetingContainer.style.display = 'none';
                chatHistory.style.display = 'flex';
            }, 500);
            isFirstMessage = false;
        }

        // Append user message
        appendMessage(message, 'user');

        // Reset input
        chatInput.value = '';
        chatInput.style.height = 'auto';

        // Lock UI
        setStreaming(true);

        // Create a streaming bot bubble with SPENCER loader
        const { msgDiv, bubble } = createBotBubble();
        chatHistory.appendChild(msgDiv);
        scrollToBottom();
        let thinkingRemoved = false;

        let fullResponse = '';

        try {
            const response = await fetch(`${API_BASE}/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, message })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete line in buffer

                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    const jsonStr = line.slice(5).trim();
                    if (!jsonStr) continue;

                    try {
                        const event = JSON.parse(jsonStr);
                        if (event.type === 'token') {
                            fullResponse += event.content;
                            // Remove the SPENCER loader on first token
                            if (!thinkingRemoved) {
                                thinkingRemoved = true;
                                bubble.innerHTML = '';
                                bubble.classList.add('streaming-cursor', 'markdown-body');
                            }
                            // Re-render markdown as tokens arrive
                            renderMarkdown(bubble, fullResponse);
                            scrollToBottom();
                        } else if (event.type === 'done') {
                            break;
                        } else if (event.type === 'error') {
                            throw new Error(event.content);
                        }
                    } catch (parseErr) {
                        // Silently skip malformed SSE lines
                    }
                }
            }

        } catch (error) {
            console.error('Streaming error:', error);
            fullResponse = 'I am currently experiencing connection issues. Please make sure the backend server is running at `http://localhost:8000`.';
            renderMarkdown(bubble, fullResponse);
        } finally {
            bubble.classList.remove('streaming-cursor');
            setStreaming(false);
            scrollToBottom();

            // Apply syntax highlighting to all code blocks in this bubble
            bubble.querySelectorAll('pre code').forEach(el => {
                if (window.hljs) hljs.highlightElement(el);
            });

            // Speak the response if TTS is on
            if (fullResponse) speakText(fullResponse);

            // Refresh session list in sidebar
            loadSessions();
        }
    }

    // ── Markdown Rendering ────────────────────────────────────────────────────
    function renderMarkdown(element, rawText) {
        const dirty = marked.parse(rawText);
        element.innerHTML = DOMPurify.sanitize(dirty, {
            ADD_TAGS: ['button'],
            ADD_ATTR: ['onclick', 'class', 'data-lang']
        });
    }

    // ── UI Helpers ────────────────────────────────────────────────────────────
    function appendMessage(content, sender) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender === 'user' ? 'user-message' : ''}`;

        const avatar = document.createElement('div');
        avatar.className = `avatar ${sender === 'user' ? 'user-avatar' : 'bot-avatar'}`;
        avatar.textContent = sender === 'user' ? 'U' : 'S';

        const bubble = document.createElement('div');
        bubble.className = 'bubble';

        if (sender === 'user') {
            bubble.textContent = content;
        } else {
            bubble.classList.add('markdown-body');
            renderMarkdown(bubble, content);
            bubble.querySelectorAll('pre code').forEach(el => {
                if (window.hljs) hljs.highlightElement(el);
            });
        }

        msgDiv.appendChild(avatar);
        msgDiv.appendChild(bubble);
        chatHistory.appendChild(msgDiv);
        scrollToBottom();
        return { msgDiv, bubble };
    }

    function createBotBubble() {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message';

        const avatar = document.createElement('div');
        avatar.className = 'avatar bot-avatar';
        avatar.textContent = 'S';

        const bubble = document.createElement('div');
        bubble.className = 'bubble';

        // Static thinking indicator
        bubble.innerHTML = `<span class="thinking-static">Thinking...</span>`;

        msgDiv.appendChild(avatar);
        msgDiv.appendChild(bubble);
        return { msgDiv, bubble };
    }

    function setStreaming(val) {
        isStreaming = val;
        sendBtn.disabled = val;
        chatInput.disabled = val;
    }

    function scrollToBottom() {
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    // ── Voice Recording ───────────────────────────────────────────────────────
    voiceBtn.addEventListener('click', async () => {
        if (!isRecording) await startRecording();
        else stopRecording();
    });

    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                await sendAudioMessage(audioBlob);
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            isRecording = true;
            voiceBtn.classList.add('recording-active');
            voiceBtn.innerHTML = '<i class="fa-solid fa-stop"></i> Stop';
        } catch (error) {
            console.error('Microphone access error:', error);
            alert('Could not access microphone. Please grant permission and try again.');
        }
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
        isRecording = false;
        voiceBtn.classList.remove('recording-active');
        voiceBtn.innerHTML = '<i class="fa-solid fa-microphone"></i> Voice';
    }

    async function sendAudioMessage(audioBlob) {
        if (isFirstMessage) {
            greetingContainer.classList.add('fade-out');
            setTimeout(() => {
                greetingContainer.style.display = 'none';
                chatHistory.style.display = 'flex';
            }, 500);
            isFirstMessage = false;
        }

        appendMessage('🎙️ Voice message', 'user');
        setStreaming(true);

        const { msgDiv, bubble } = createBotBubble();
        bubble.classList.add('markdown-body');
        bubble.innerHTML = `<div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>`;
        chatHistory.appendChild(msgDiv);
        scrollToBottom();

        try {
            const formData = new FormData();
            formData.append('session_id', sessionId);
            formData.append('file', audioBlob, 'recording.webm');

            const response = await fetch(`${API_BASE}/chat/audio`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) throw new Error('Audio processing failed');

            const data = await response.json();
            renderMarkdown(bubble, data.response);
            bubble.querySelectorAll('pre code').forEach(el => {
                if (window.hljs) hljs.highlightElement(el);
            });
            if (data.response) speakText(data.response);

        } catch (error) {
            console.error('Audio error:', error);
            bubble.textContent = 'I could not process the audio. Please check the backend is running and try again.';
        } finally {
            setStreaming(false);
            scrollToBottom();
            loadSessions();
        }
    }

    // ── Session Sidebar ───────────────────────────────────────────────────────
    refreshSessionsBtn.addEventListener('click', loadSessions);

    async function loadSessions() {
        try {
            const res = await fetch(`${API_BASE}/sessions`);
            if (!res.ok) throw new Error('Could not load sessions');
            const data = await res.json();
            renderSessionList(data.sessions);
        } catch (err) {
            chatList.innerHTML = '<div class="sessions-empty">Could not load history</div>';
        }
    }

    function renderSessionList(sessions) {
        chatList.innerHTML = '';

        if (!sessions || sessions.length === 0) {
            chatList.innerHTML = '<div class="sessions-empty">No conversations yet</div>';
            return;
        }

        sessions.forEach(s => {
            const btn = document.createElement('button');
            btn.className = 'chat-history-item';
            if (s.session_id === activeSessionId) btn.classList.add('active');

            const span = document.createElement('span');
            span.className = 'item-text';
            span.textContent = s.title || 'Conversation';
            span.title = s.title;

            const delBtn = document.createElement('button');
            delBtn.className = 'delete-btn';
            delBtn.title = 'Delete conversation';
            delBtn.innerHTML = '<i class="fa-solid fa-trash-can"></i>';
            delBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await deleteSession(s.session_id);
            });

            btn.appendChild(span);
            btn.appendChild(delBtn);

            btn.addEventListener('click', () => loadSession(s.session_id, s.title));
            chatList.appendChild(btn);
        });
    }

    async function loadSession(id, title) {
        try {
            const res = await fetch(`${API_BASE}/sessions/${id}/history`);
            if (!res.ok) throw new Error('Failed to load session');
            const data = await res.json();

            // Switch to this session
            sessionId = id;
            activeSessionId = id;
            isFirstMessage = false;

            // Render the conversation
            chatHistory.innerHTML = '';
            chatHistory.style.display = 'flex';
            greetingContainer.style.display = 'none';
            greetingContainer.classList.add('fade-out');

            data.messages.forEach(msg => {
                appendMessage(msg.content, msg.role === 'user' ? 'user' : 'bot');
            });

            scrollToBottom();

            // Highlight active session in sidebar
            document.querySelectorAll('.chat-history-item').forEach(el => el.classList.remove('active'));
            const activeEl = [...chatList.querySelectorAll('.chat-history-item')]
                .find(el => el.querySelector('.item-text')?.textContent === (title || 'Conversation'));
            if (activeEl) activeEl.classList.add('active');

        } catch (err) {
            console.error('Load session error:', err);
        }
    }

    async function deleteSession(id) {
        try {
            await fetch(`${API_BASE}/sessions/${id}`, { method: 'DELETE' });
            // If it was the active session, start a new one
            if (id === activeSessionId) startNewChat();
            loadSessions();
        } catch (err) {
            console.error('Delete session error:', err);
        }
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    loadSessions();
});
