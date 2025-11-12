// chat.js - 聊天界面主逻辑
class ChatApp {
    constructor() {
        this.wsManager = new WebSocketManager();
        this.thinkingFlow = new ThinkingFlow(this); // 思维流管理器
        this.sessionId = null; // 当前会话ID，由后端分配
        this.shareId = null; // 只读分享ID
        this.readonly = false; // 是否只读模式
        this.isStreaming = false; // 是否正在生成（用于切换发送/暂停）
        this.resumedSessionId = null;
        this.resumedConversationId = null;
        this.activeConversation = null; // 跟踪续聊绑定的历史会话
        this.resumeBindingConnectionId = null; // 记录完成续聊绑定的连接会话ID
        this.pendingResumeRequest = null; // 正在进行的续聊绑定请求
        
        // 初始化子模块
        this.uiController = new UIController(this);
        this.fileUploadManager = new FileUploadManager(this);
        this.modelManager = new ModelManager(this);
        this.messageManager = new MessageManager(this);
        
        this.pendingEdit = null; // 回溯编辑状态
        
        this.quickPromptContainer = document.querySelector('.quick-prompt-list');
        this.quickPromptRefreshKey = null;
        
        // DOM 元素
        this.chatMessages = document.getElementById('chatMessages');
        // 缓存欢迎卡片模板，供“Start New Chat”复用
        this.welcomeHTML = (this.chatMessages.querySelector('.welcome-message')?.outerHTML) || '';
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.clearChatBtn = document.getElementById('clearChatBtn');
        this.startNewChatBtn = document.getElementById('startNewChatBtn');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.connectionText = document.getElementById('connectionText');
        this.charCount = document.getElementById('charCount');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.modelDropdownBtn = document.getElementById('modelDropdownBtn');
        this.modelDropdown = document.getElementById('modelDropdown');
        this.threadsList = document.getElementById('threadsList');
        this.toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
        this.openSidebarBtn = document.getElementById('openSidebarBtn');
        this.uploadBtn = document.getElementById('uploadBtn');
        this.fileInput = document.getElementById('fileInput');
        this.attachmentChips = document.getElementById('attachmentChips');
        
        this.init();
    }

    // 在最后一条AI消息下面插入用量提示
    appendTokenUsageFooter(usage) {
        this.messageManager.appendTokenUsageFooter(this.chatMessages, usage);
    }
    
    async init() {
        try {
            // 首先确保配置已加载
            // this.showLoading('正在加载系统配置...'); // 已移除页面加载时的加载提示
            
            if (!window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            // 检测只读分享模式 (?share= 或兼容 ?session=)
            try {
                const params = new URLSearchParams(window.location.search || '');
                this.shareId = params.get('share');
                const legacySession = params.get('session');
                if (this.shareId || legacySession) {
                    this.readonly = true;
                    // 调整UI为只读
                    this.enterReadonlyMode();
                    // 加载分享内容
                    if (this.shareId) {
                        await this.loadSnapshotChat(this.shareId);
                    } else if (legacySession) {
                        await this.loadLegacySharedChat(legacySession);
                    }
                    this.hideLoading();
                    return;
                }
            } catch {}
            
            // 若未登录，则不建立连接，显示友好的登录引导
            try {
                const token = (window.Auth && Auth.getToken && Auth.getToken()) || '';
                if (!token) {
                    this.setupEventListeners();
                    this.updateConnectionStatus('offline');
                    this.hideLoading();
                    // 使用友好的登录引导替代红色错误提示
                    this.uiController.showLoginGuide(this.chatMessages);
                    return;
                }
            } catch {}

            // 配置加载成功后再初始化其他组件
            this.setupEventListeners();
            // 先加载Model并设置本地选择（确保首连就携带 model）
            await this.modelManager.loadModelsAndRenderDropdown(this.modelDropdownBtn, this.modelDropdown, this.wsManager);
            await this.loadQuickPrompts();
            this.setupWebSocket();
            await this.connectWebSocket();
        } catch (error) {
            console.error('❌ 应用初始化失败:', error);
            this.hideLoading();
            // 配置加载失败时，错误已经在configManager中显示，这里不需要额外处理
        }
    }
    
    async loadQuickPrompts(force = false) {
        if (!this.quickPromptContainer) {
            return;
        }
        try {
            const data = await window.configManager.fetchPrompts({ limit: 4 });
            if (!force && this.quickPromptRefreshKey && this.quickPromptRefreshKey === data.refresh_key) {
                return;
            }
            this.quickPromptRefreshKey = data.refresh_key;
            const prompts = Array.isArray(data.prompts) ? data.prompts : [];
            this.renderQuickPrompts(prompts);
        } catch (error) {
            console.warn('加载示例问句失败:', error);
        }
    }
    
    renderQuickPrompts(prompts) {
        if (!this.quickPromptContainer) {
            return;
        }
        this.quickPromptContainer.innerHTML = '';
        if (!Array.isArray(prompts) || prompts.length === 0) {
            this.quickPromptContainer.innerHTML = '<div class="quick-prompt-empty">暂无示例问题，请稍后重试。</div>';
            return;
        }
        const fragment = document.createDocumentFragment();
        prompts.forEach((promptText) => {
            const btn = document.createElement('button');
            btn.className = 'quick-prompt-btn';
            btn.dataset.prompt = promptText;
            btn.textContent = promptText;
            btn.title = promptText;
            fragment.appendChild(btn);
        });
        this.quickPromptContainer.appendChild(fragment);
        this.bindQuickPromptEvents();
    }
    
    bindQuickPromptEvents() {
        if (!this.quickPromptContainer) {
            return;
        }
        this.quickPromptContainer.onclick = (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) {
                return;
            }
            const promptText = target.dataset && target.dataset.prompt;
            if (!promptText) {
                return;
            }
            if (!this.wsManager || !this.wsManager.isConnected()) {
                this.showError('请先连接服务器后再使用示例问题。');
                return;
            }
            this.uiController.insertTextAtCursor(this.messageInput, promptText);
            this.updateSendButton();
            this.smartScrollToBottom(true);
        };
    }

    enterReadonlyMode() {
        try {
            // 顶部加只读徽标
            const header = document.querySelector('.header .header-actions');
            if (header && !document.getElementById('readonlyBadge')) {
                const badge = document.createElement('span');
                badge.id = 'readonlyBadge';
                badge.className = 'readonly-badge';
                badge.textContent = '只读分享';
                badge.style.cssText = 'background:#ed8936;color:#fff;padding:0.25rem 0.5rem;border-radius:12px;margin-right:8px;';
                try { header.insertBefore(badge, header.firstChild); } catch { header.appendChild(badge); }
            }
            // 隐藏输入区与交互按钮
            const input = document.querySelector('.chat-input-container');
            if (input) input.style.display = 'none';
            const shareBtn = document.getElementById('shareChatBtn');
            if (shareBtn) shareBtn.style.display = 'none';
            const modelSwitcher = document.querySelector('.model-switcher');
            if (modelSwitcher) modelSwitcher.style.display = 'none';
            const status = document.querySelector('.status-indicator');
            if (status) status.style.display = 'none';
        } catch {}
    }

    async loadSnapshotChat(shareId) {
        try {
            this.clearChat();
            this.hideWelcomeMessage();
            const t = Date.now();
            const url = window.configManager.getFullApiUrl(`/api/share/s/${encodeURIComponent(shareId)}?t=${t}`);
            let res = await fetch(url, { cache: 'no-store' }).catch(() => null);
            if (!res || !res.ok) {
                const fallback = `/api/share/s/${encodeURIComponent(shareId)}?t=${t}`;
                res = await fetch(fallback, { cache: 'no-store' });
            }
            const json = await res.json();
            const records = (json && json.data) || [];
            this.renderSnapshotRecords(records);
        } catch (e) {
            this.showError('加载分享失败');
        }
    }

    async loadLegacySharedChat(sessionId) {
        try {
            this.clearChat();
            this.hideWelcomeMessage();
            const t = Date.now();
            const url = window.configManager.getFullApiUrl(`/api/share/${encodeURIComponent(sessionId)}?t=${t}`);
            let res = await fetch(url, { cache: 'no-store' }).catch(() => null);
            if (!res || !res.ok) {
                const fallback = `/api/share/${encodeURIComponent(sessionId)}?t=${t}`;
                res = await fetch(fallback, { cache: 'no-store' });
            }
            const json = await res.json();
            const records = (json && json.data) || [];
            this.renderSnapshotRecords(records);
        } catch (e) {
            this.showError('加载分享失败');
        }
    }

    renderSnapshotRecords(records) {
        try {
            const arr = Array.isArray(records) ? records : [];
            arr.forEach(r => {
                const hasText = typeof r.user_input === 'string' && r.user_input.trim() !== '';
                const files = Array.isArray(r.attachments) ? r.attachments : [];
                if (hasText || files.length > 0) {
                    const content = (window.History && History.composeUserMessageWithAttachments)
                        ? History.composeUserMessageWithAttachments(this, r.user_input, r.attachments)
                        : String(r.user_input || '');
                    this.addUserMessage(content);
                }
                this.thinkingFlow.createThinkingFlow();
                const toolsCalled = Array.isArray(r.mcp_tools_called) ? r.mcp_tools_called : [];
                const results = Array.isArray(r.mcp_results) ? r.mcp_results : [];
                if (toolsCalled.length > 0) {
                    this.thinkingFlow.updateThinkingStage('tools_planned', `Planning to use ${toolsCalled.length} tool(s)`, 'Replaying recorded tool operations...', { toolCount: toolsCalled.length });
                    const idToResult = {};
                    results.forEach(x => { if (x && x.tool_id) idToResult[x.tool_id] = x; });
                    toolsCalled.forEach(tc => {
                        const toolId = tc.tool_id || tc.id || tc.name || Math.random().toString(36).slice(2);
                        const toolName = tc.tool_name || (tc.function && tc.function.name) || tc.name || 'tool';
                        const args = tc.tool_args || (tc.function && tc.function.arguments) || {};
                        this.thinkingFlow.addToolToThinking({ tool_id: toolId, tool_name: toolName, tool_args: args });
                        const matched = idToResult[toolId] || {};
                        if (matched && matched.result !== undefined) {
                            this.thinkingFlow.updateToolInThinking({ tool_id: toolId, tool_name: toolName, result: String(matched.result) }, 'completed');
                        } else if (matched && matched.error) {
                            this.thinkingFlow.updateToolInThinking({ tool_id: toolId, tool_name: toolName, error: String(matched.error) }, 'error');
                        } else {
                            this.thinkingFlow.updateToolInThinking({ tool_id: toolId, tool_name: toolName, result: '(no recorded result)' }, 'completed');
                        }
                    });
                    this.thinkingFlow.updateThinkingStage('responding', 'Preparing response', 'Organizing evidence-based conclusions and recommendations...');
                    this.thinkingFlow.completeThinkingFlow('success');
                } else {
                    this.thinkingFlow.updateThinkingStage('responding', 'Preparing response', 'Organizing evidence-based conclusions and recommendations...');
                    this.thinkingFlow.completeThinkingFlow('success');
                }
                if (r.ai_response) {
                    this.startAIResponse();
                    this.appendAIResponse(r.ai_response);
                    this.endAIResponse();
                    try {
                        if (r.usage && (r.usage.input_tokens != null || r.usage.output_tokens != null)) {
                            this.appendTokenUsageFooter({
                                input_tokens: r.usage.input_tokens,
                                output_tokens: r.usage.output_tokens,
                                total_tokens: r.usage.total_tokens
                            });
                        }
                    } catch {}
                }
            });
            this.smartScrollToBottom();
        } catch (e) { console.warn('渲染快照失败', e); }
    }
    
    setupEventListeners() {
        // 发送/暂停 按钮点击
        this.sendBtn.addEventListener('click', () => {
            if (this.isStreaming) {
                // 发送暂停指令
                this.wsManager.send({ type: 'pause' });
                // 立即将按钮恢复为Send，等待后端结束当前流
                this.isStreaming = false;
                this.updateSendButton();
                return;
            }
            this.sendMessage();
        });
        
        // 输入框事件
        this.messageInput.addEventListener('input', () => {
            this.uiController.updateCharCount(this.messageInput, this.charCount);
            this.uiController.adjustInputHeight(this.messageInput);
            this.updateSendButton();
        });
        
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                if (e.shiftKey) {
                    // Shift + Enter 换行
                    return;
                } else {
                    // Enter 发送
                    e.preventDefault();
                    this.sendMessage();
                }
            }
        });
        
        // 兼容旧按钮（如存在）
        if (this.clearChatBtn) {
            this.clearChatBtn.addEventListener('click', () => {
                // 仅清UI
                this.clearChat();
                // 明确用户点击清空时，才请求后端删除
                this.clearServerHistory();
            });
        }
        // 新建对话：仅清屏，不删除历史
        if (this.startNewChatBtn) {
            this.startNewChatBtn.addEventListener('click', () => {
                // 改为刷新页面，确保彻底重置连接与状态
                try { window.location.reload(); } catch (e) { try { window.location.href = window.location.href; } catch (_) {} }
            });
        }
        
        // 初始化分享模块
        this.shareModule = new ShareModule(this);

        
        // 页面卸载时关闭连接
        window.addEventListener('beforeunload', () => {
            this.wsManager.close();
        });

        // 侧栏开关
        if (this.toggleSidebarBtn) {
            this.toggleSidebarBtn.addEventListener('click', () => {
                const sidebar = document.getElementById('historySidebar');
                if (!sidebar) return;
                const isOpen = sidebar.classList.toggle('open');
                // 推拉主容器
                const app = document.querySelector('.app-container');
                if (app) {
                    app.classList.toggle('sidebar-open', isOpen);
                }
                this.toggleSidebarBtn.textContent = isOpen ? 'Hide' : 'Show';
            });
        }
        if (this.openSidebarBtn) {
            this.openSidebarBtn.addEventListener('click', async () => {
                const sidebar = document.getElementById('historySidebar');
                if (!sidebar) return;
                const isOpen = sidebar.classList.toggle('open');
                // 推拉主容器
                const app = document.querySelector('.app-container');
                if (app) {
                    app.classList.toggle('sidebar-open', isOpen);
                }
                // 打开时刷新；关闭时不动
                if (isOpen) {
                    await this.loadThreadsByMsidFromUrl();
                }
                // 可选：按钮文案提示
                this.openSidebarBtn.textContent = isOpen ? 'History (Open)' : 'History';
            });
        }

        // Model下拉
        if (this.modelDropdownBtn) {
            this.modelDropdownBtn.addEventListener('click', () => {
                if (!this.modelDropdown) return;
                this.modelDropdown.style.display = this.modelDropdown.style.display === 'none' || this.modelDropdown.style.display === '' ? 'block' : 'none';
            });
            // 点击页面其他地方关闭
            document.addEventListener('click', (e) => {
                if (!this.modelDropdownBtn.contains(e.target) && !this.modelDropdown.contains(e.target)) {
                    this.modelDropdown.style.display = 'none';
                }
            });
        }

        // 上传按钮与文件选择
        if (this.uploadBtn && this.fileInput) {
            this.uploadBtn.addEventListener('click', () => {
                try { this.fileInput.click(); } catch {}
            });
            this.fileInput.addEventListener('change', async (e) => {
                const files = Array.from(e.target.files || []);
                if (!files.length) return;
                try {
                    const items = await this.fileUploadManager.uploadFilesAndGetLinks(files);
                    this.fileUploadManager.addAttachmentChips(items, this.attachmentChips);
                    const currentAttachments = this.fileUploadManager.getPendingAttachments();
                    this.fileUploadManager.setPendingAttachments([...currentAttachments, ...items]);
                    this.updateSendButton();
                } catch (err) {
                    console.warn('文件上传失败', err);
                    this.uiController.showError(this.chatMessages, 'File upload failed');
                } finally {
                    try { this.fileInput.value = ''; } catch {}
                }
            });
        }

        // 粘贴图片支持
        if (this.messageInput) {
            this.messageInput.addEventListener('paste', async (event) => {
                try {
                    const clipboard = event.clipboardData || window.clipboardData;
                    if (!clipboard || !clipboard.items) return;
                    const imageItems = [];
                    for (const item of clipboard.items) {
                        if (item.kind === 'file' && item.type && item.type.startsWith('image/')) {
                            const blob = item.getAsFile();
                            if (blob) {
                                // 为粘贴内容生成文件名
                                const ext = (blob.type.split('/')[1] || 'png').toLowerCase();
                                const fname = `pasted-${Date.now()}.${ext}`;
                                const file = new File([blob], fname, { type: blob.type });
                                imageItems.push(file);
                            }
                        }
                    }
                    if (!imageItems.length) return;
                    event.preventDefault();
                    const items = await this.fileUploadManager.uploadFilesAndGetLinks(imageItems);
                    this.fileUploadManager.addAttachmentChips(items, this.attachmentChips);
                    const currentAttachments = this.fileUploadManager.getPendingAttachments();
                    this.fileUploadManager.setPendingAttachments([...currentAttachments, ...items]);
                    this.updateSendButton();
                } catch (e) {
                    console.warn('处理粘贴图片失败', e);
                }
            });
        }
    }
    
    setupWebSocket() {
        // WebSocket 事件回调
        this.wsManager.onOpen = () => {
            this.updateConnectionStatus('online');
            this.hideLoading();
        };
        
        this.wsManager.onMessage = (data) => {
            this.handleWebSocketMessage(data);
        };
        
        this.wsManager.onClose = () => {
            this.uiController.updateConnectionStatus(this.connectionStatus, this.connectionText, 'offline');
            this.resumeBindingConnectionId = null;
            if (this.pendingResumeRequest && typeof this.pendingResumeRequest.reject === 'function') {
                this.pendingResumeRequest.reject(new Error('Connection closed'));
            }
            this.pendingResumeRequest = null;
        };
        
        this.wsManager.onError = () => {
            this.uiController.updateConnectionStatus(this.connectionStatus, this.connectionText, 'offline');
            this.uiController.showError(this.chatMessages, '金融数据连接失败，请检查网络');
            this.uiController.hideLoading(this.loadingOverlay);
            this.resumeBindingConnectionId = null;
            if (this.pendingResumeRequest && typeof this.pendingResumeRequest.reject === 'function') {
                this.pendingResumeRequest.reject(new Error('Connection error'));
            }
            this.pendingResumeRequest = null;
        };
        
        this.wsManager.onReconnecting = (attempt, maxAttempts) => {
            this.uiController.updateConnectionStatus(this.connectionStatus, this.connectionText, 'connecting');
            this.showStatus(`正在重新连接... (${attempt}/${maxAttempts})`);
        };
    }
    
    setActiveConversation(sessionId, conversationId) {
        if (this.pendingResumeRequest && typeof this.pendingResumeRequest.reject === 'function') {
            this.pendingResumeRequest.reject(new Error('Conversation selection changed'));
        }
        this.pendingResumeRequest = null;
        if (!sessionId || conversationId === undefined || conversationId === null) {
            this.activeConversation = null;
            this.resumedSessionId = sessionId || null;
            this.resumedConversationId = null;
            this.resumeBindingConnectionId = null;
            return;
        }
        this.activeConversation = { sessionId, conversationId };
        this.resumedSessionId = sessionId;
        this.resumedConversationId = conversationId;
        this.resumeBindingConnectionId = null;
        if (this.wsManager && this.wsManager.isConnected()) {
            this.requestResumeBinding().catch((err) => {
                console.warn('续聊绑定请求发送失败:', err);
            });
        }
    }

    requestResumeBinding(force = false) {
        if (!this.activeConversation || !this.activeConversation.sessionId || this.activeConversation.conversationId === undefined || this.activeConversation.conversationId === null) {
            return Promise.resolve();
        }
        if (!this.wsManager || !this.wsManager.isConnected()) {
            return Promise.reject(new Error('WebSocket not connected'));
        }
        if (this.pendingResumeRequest && this.pendingResumeRequest.connectionId !== this.sessionId) {
            if (typeof this.pendingResumeRequest.reject === 'function') {
                this.pendingResumeRequest.reject(new Error('Connection changed'));
            }
            this.pendingResumeRequest = null;
        }
        if (!force && this.resumeBindingConnectionId === this.sessionId) {
            return Promise.resolve();
        }
        if (this.pendingResumeRequest && this.pendingResumeRequest.connectionId === this.sessionId) {
            return this.pendingResumeRequest.promise;
        }
        const { sessionId: resumeSession, conversationId: resumeConversation } = this.activeConversation;
        let resolveFn;
        let rejectFn;
        const promise = new Promise((resolve, reject) => {
            resolveFn = resolve;
            rejectFn = reject;
        });
        this.pendingResumeRequest = {
            connectionId: this.sessionId,
            resolve: resolveFn,
            reject: rejectFn,
            promise
        };
        const success = this.wsManager.send({
            type: 'resume_conversation',
            session_id: resumeSession,
            conversation_id: resumeConversation
        });
        if (!success) {
            const error = new Error('Resume request failed to send');
            if (this.pendingResumeRequest && this.pendingResumeRequest.reject === rejectFn) {
                rejectFn(error);
            }
            this.pendingResumeRequest = null;
            return Promise.reject(error);
        }
        return promise;
    }

    async ensureActiveConversationBinding() {
        if (!this.activeConversation || !this.activeConversation.sessionId || this.activeConversation.conversationId === undefined || this.activeConversation.conversationId === null) {
            return true;
        }
        if (!this.wsManager || !this.wsManager.isConnected()) {
            return false;
        }
        if (this.resumeBindingConnectionId === this.sessionId) {
            return true;
        }
        try {
            await this.requestResumeBinding();
            return true;
        } catch (error) {
            console.warn('确保续聊绑定失败:', error);
            this.showError('无法恢复与历史会话的连接，请稍后重试');
            return false;
        }
    }

    async connectWebSocket() {
        // this.uiController.showLoading(this.loadingOverlay, '正在连接金融数据服务器...'); // 已移除页面加载时的加载提示
        this.uiController.updateConnectionStatus(this.connectionStatus, this.connectionText, 'connecting');
        await this.wsManager.connect();
        // 加载左侧线程列表（如果URL中有msid）
        this.loadThreadsByMsidFromUrl();
    }

    async loadThreadsByMsidFromUrl() {
        try {
            const username = (window.Auth && Auth.getUsername && Auth.getUsername()) || '';
            if (!username) return;
            const apiUrl = window.configManager.getFullApiUrl(`/api/threads`);
            const token = (window.Auth && Auth.getToken && Auth.getToken()) || '';
            const res = await fetch(apiUrl, { cache: 'no-store', headers: token ? { 'Authorization': `Bearer ${token}` } : {} });
            const json = await res.json();
            if (!json.success) return;
            this.renderThreads(json.data || []);
        } catch (e) { console.warn('加载线程列表失败', e); }
    }

    renderThreads(threads) {
        if (window.History && typeof window.History.renderThreads === 'function') {
            return window.History.renderThreads(this, threads);
        }
        // 回退：无模块时走旧逻辑（略）
    }

    async loadHistoryForConversation(sessionId, conversationId) {
        if (window.History && typeof window.History.loadHistoryForConversation === 'function') {
            return window.History.loadHistoryForConversation(this, sessionId, conversationId);
        }
    }

    async loadModelsAndRenderDropdown() {
        try {
            const apiUrl = window.configManager.getFullApiUrl('/api/models');
            const token = (window.Auth && Auth.getToken && Auth.getToken()) || '';
            const res = await fetch(apiUrl, { cache: 'no-store', headers: token ? { 'Authorization': `Bearer ${token}` } : {} });
            const json = await res.json();
            if (!json.success) throw new Error('加载模型列表失败');
            const { models, default: def } = json.data || { models: [], default: 'default' };

            let selected = localStorage.getItem('mcp_selected_model') || def;
            // 如果本地无记录，写入一次，保证首连就有 model
            if (!localStorage.getItem('mcp_selected_model')) {
                localStorage.setItem('mcp_selected_model', selected);
            }
            this.updateModelButtonLabel(models, selected);

            // 渲染菜单
            if (this.modelDropdown) {
                this.modelDropdown.innerHTML = '';
                models.forEach(m => {
                    const item = document.createElement('div');
                    item.className = 'dropdown-item';
                    item.textContent = `${m.label || m.id} (${m.model || ''})`;
                    item.addEventListener('click', async () => {
                        try {
                            // 改为通过WS指令切换模型，避免断开重连
                            localStorage.setItem('mcp_selected_model', m.id);
                            this.updateModelButtonLabel(models, m.id);
                            this.modelDropdown.style.display = 'none';
                            if (this.wsManager && this.wsManager.isConnected()) {
                                const ok = this.wsManager.send({ type: 'switch_model', model: m.id });
                                if (!ok) throw new Error('数据连接中断');
                            } else {
                                // 若尚未连接，保留旧逻辑：初始化时会带上 model 参数
                                await this.connectWebSocket();
                            }
                        } catch (e) {
                            console.warn('切换模型失败，回退为重连方式', e);
                            try { this.wsManager.close(); } catch {}
                            this.wsManager.isInitialized = false;
                            await this.connectWebSocket();
                        }
                    });
                    this.modelDropdown.appendChild(item);
                });
            }
        } catch (e) {
            console.warn('⚠️ 无法加载Model列表:', e);
        }
    }



    insertTextAtCursor(text) {
        this.uiController.insertTextAtCursor(this.messageInput, text);
    }




    
    handleWebSocketMessage(data) {
        console.log('📨 收到消息:', data);
        
        switch (data.type) {
            case 'model_switched':
                try {
                    const newModel = data.model;
                    if (newModel) {
                        // 更新本地选择与按钮展示
                        localStorage.setItem('mcp_selected_model', newModel);
                        if (this.modelManager) {
                            this.modelManager.selectedModel = newModel;
                            this.modelManager.updateModelButtonLabel(this.modelDropdownBtn, newModel);
                        }
                        // 自动路由提示（当 reason=auto_route_quant 时弹轻提示）
                        if (data.reason === 'auto_route_quant') {
                            try {
                                this.uiController.showStatusToast && this.uiController.showStatusToast('已为你切换到量化专员档位');
                            } catch {}
                        }
                    }
                } catch (e) { console.warn('处理 model_switched 失败', e); }
                break;
            case 'session_info':
                // 接收会话ID
                this.sessionId = data.session_id;
                console.log('🆔 收到会话ID:', this.sessionId);
                if (this.activeConversation) {
                    this.requestResumeBinding().catch((err) => {
                        console.warn('续聊绑定恢复失败:', err);
                    });
                }
                break;
            case 'resume_ok':
                // 后端确认续聊绑定成功
                try {
                    // 记录续聊目标，便于UI或后续逻辑使用（此处复用 sessionId 仅作显示，不影响底层WS）
                    this.resumedSessionId = data.session_id;
                    this.resumedConversationId = data.conversation_id;
                    this.activeConversation = { sessionId: data.session_id, conversationId: data.conversation_id };
                    this.resumeBindingConnectionId = this.sessionId;
                    if (this.pendingResumeRequest && this.pendingResumeRequest.connectionId === this.sessionId) {
                        this.pendingResumeRequest.resolve();
                        this.pendingResumeRequest = null;
                    }
                    console.log('✅ 续聊绑定成功 ->', this.resumedSessionId, this.resumedConversationId);
                } catch {}
                break;
            case 'resume_error':
                if (this.pendingResumeRequest && typeof this.pendingResumeRequest.reject === 'function') {
                    this.pendingResumeRequest.reject(new Error(data.content || 'resume error'));
                    this.pendingResumeRequest = null;
                }
                this.resumeBindingConnectionId = null;
                this.showError(`恢复对话失败: ${data.content || '未知错误'}`);
                break;
            case 'edit_ok':
                // 回溯截断成功
                console.log('✂️ 回溯截断成功，开始重生');
                break;
            case 'edit_error':
                this.showError(`编辑失败: ${data.content || '未知错误'}`);
                break;
                
            case 'user_msg_received':
                // 用户消息已收到确认
                break;
                
            case 'status':
                // 移除硬编码的status处理，让AI思考内容自然显示
                break;
                
            case 'ai_thinking_start':
                // 开始AI思考流式显示
                this.thinkingFlow.startThinkingContent(data.iteration);
                break;
                
            case 'ai_thinking_chunk':
                // AI思考内容片段
                this.thinkingFlow.appendThinkingContent(data.content, data.iteration);
                break;
                
            case 'ai_thinking_end':
                // 结束AI思考
                this.thinkingFlow.endThinkingContent(data.iteration);
                break;
                
            case 'tool_plan':
                this.thinkingFlow.updateThinkingStage(
                    'tools_planned', 
                    `Planning to use ${data.tool_count} tool(s)`, 
                    'Preparing clinical data operations...',
                    { toolCount: data.tool_count }
                );
                break;
                
            case 'tool_start':
                this.thinkingFlow.addToolToThinking(data);
                break;
                
            case 'tool_end':
                this.thinkingFlow.updateToolInThinking(data, 'completed');
                break;
                
            case 'tool_error':
                this.thinkingFlow.updateToolInThinking(data, 'error');
                break;
                
            case 'fallback_triggered':
                // 工具调用失败兜底机制触发
                try {
                    console.log('🛟 触发兜底机制:', data);
                    // 显示友好提示
                    this.uiController.showStatusToast('工具调用遇到问题，正在为您生成替代方案...', 4000);
                    // 在思维流中显示兜底提示
                    this.thinkingFlow.updateThinkingStage(
                        'fallback', 
                        'Tool execution fallback', 
                        `遇到${data.error_count || 0}次工具调用失败，正在生成替代回复...`
                    );
                } catch (e) {
                    console.warn('处理 fallback_triggered 失败', e);
                }
                break;
                
            case 'ai_response_start':
                this.thinkingFlow.updateThinkingStage('responding', 'Preparing response', 'Organizing evidence-based conclusions and recommendations...');
                
                // 确保思维流可见 - 智能滚动策略
                const currentFlow = this.thinkingFlow.getCurrentFlow();
                if (currentFlow && !this.isUserViewingContent()) {
                    // 只有用户不在查看历史内容时才滚动到思维流
                    setTimeout(() => {
                        currentFlow.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start',
                            inline: 'nearest'
                        });
                    }, 100);
                }

                this.messageManager.startAIResponse(this.chatMessages);
                // 进入流式阶段，切换按钮为暂停
                this.isStreaming = true;
                this.updateSendButton();
                break;
                
            case 'ai_response_chunk':
                this.messageManager.appendAIResponse(data.content);
                break;
                
            case 'ai_response_end':
                this.messageManager.endAIResponse();
                this.thinkingFlow.completeThinkingFlow('success');
                // 结束流式，恢复按钮
                this.isStreaming = false;
                this.updateSendButton();
                break;
            case 'token_usage':
                // 在AI消息下方追加一行浅色用量提示，不进入复制范围
                this.appendTokenUsageFooter(data);
                break;
            case 'record_saved':
                // 后端返回新插入的记录ID，将最后一条用户消息补上操作按钮和recordId，避免刷新
                MessageActions.attachActionsToLastUserMessage(this, data);
                if (data && data.session_id && data.conversation_id !== undefined && data.conversation_id !== null) {
                    this.activeConversation = { sessionId: data.session_id, conversationId: data.conversation_id };
                    this.resumedSessionId = data.session_id;
                    this.resumedConversationId = data.conversation_id;
                    this.resumeBindingConnectionId = this.sessionId;
                }
                break;
                
            case 'error':
                this.uiController.showError(this.chatMessages, data.content);
                this.thinkingFlow.completeThinkingFlow('error');
                this.isStreaming = false;
                this.updateSendButton();
                break;
                
            default:
                console.warn('未知消息类型:', data.type);
        }
    }

    
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        const pendingAttachments = this.fileUploadManager.getPendingAttachments();
        const hasAttachments = (pendingAttachments && pendingAttachments.length > 0);
        if (!message && !hasAttachments) {
            return;
        }
        if (!this.wsManager.isConnected()) return;
        const resumeReady = await this.ensureActiveConversationBinding();
        if (!resumeReady) {
            return;
        }

        // 发送到服务器（若为回溯编辑，则发 replay_edit）。
        let payload;
        if (this.pendingEdit && this.pendingEdit.sessionId && this.pendingEdit.conversationId && this.pendingEdit.fromRecordId) {
            // 只有在真正发送时，才在前端截断（提高交互体验）
            this.truncateAfterRecord(this.pendingEdit.fromRecordId);
            payload = {
                type: 'replay_edit',
                session_id: this.pendingEdit.sessionId,
                conversation_id: this.pendingEdit.conversationId,
                from_record_id: this.pendingEdit.fromRecordId,
                new_user_input: message
            };
        } else {
            // 构建多模态内容：若包含图片，则将其作为 image_url 发送给模型
            const imageItems = (pendingAttachments || []).filter(a => a && a.isImage);
            if (imageItems.length > 0) {
                const parts = [];
                if (message) {
                    parts.push({ type: 'text', text: message });
                }
                imageItems.forEach(a => {
                    const urlForModel = a.dataUrl || a.fullUrl || a.urlPath;
                    parts.push({ type: 'image_url', image_url: { url: urlForModel } });
                });
                payload = {
                    type: 'user_msg',
                    content_parts: parts,
                    // 仍保留附件元信息，便于历史与下载
                    attachments: (pendingAttachments || []).map(a => ({ filename: a.filename, url: a.urlPath }))
                };
            } else {
                payload = { type: 'user_msg', content: message, attachments: (pendingAttachments || []).map(a => ({ filename: a.filename, url: a.urlPath })) };
            }
        }

        // 现在再把用户消息插入到UI，并立即附上复制/编辑动作（recordId 稍后由 record_saved 回填）
        const userDisplay = this.fileUploadManager.composeUserDisplayMessage(message, pendingAttachments);
        MessageActions.addUserMessageWithActions(this, userDisplay, {
            recordId: null,
            sessionId: this.resumedSessionId || this.sessionId,
            conversationId: this.resumedConversationId
        });

        // 清空输入框并重置状态
        this.messageInput.value = '';
        this.uiController.updateCharCount(this.messageInput, this.charCount);
        this.uiController.adjustInputHeight(this.messageInput);
        this.updateSendButton();
        this.fileUploadManager.clearAttachmentChips(this.attachmentChips);
        this.fileUploadManager.clearPendingAttachments();

        // 隐藏欢迎消息
        this.uiController.hideWelcomeMessage(this.chatMessages);

        // 创建思维流
        this.thinkingFlow.createThinkingFlow();

        const success = this.wsManager.send(payload);
        
        if (!success) {
            this.showError('消息发送失败，请检查网络连接');
            this.thinkingFlow.completeThinkingFlow('error');
        } else {
            if (payload.type === 'replay_edit') {
                this.pendingEdit = null;
            }
        }
    }
    
    // 用户消息相关方法已移至MessageManager
    addUserMessage(content) {
        this.messageManager.addUserMessage(this.chatMessages, content);
    }

    addUserMessageWithActions(content, meta = {}) {
        this.messageManager.addUserMessageWithActions(this.chatMessages, content, meta);
    }

    truncateAfterRecord(recordId) {
        this.messageManager.truncateAfterRecord(this.chatMessages, recordId);
    }
    
    showStatus(content) {
        // 可以在这里显示状态信息，暂时用console.log
        console.log('📊 状态:', content);
    }
    
    
    // AI响应相关方法已移至MessageManager
    startAIResponse() {
        this.messageManager.startAIResponse(this.chatMessages);
    }
    
    appendAIResponse(content) {
        this.messageManager.appendAIResponse(content);
    }
    
    endAIResponse() {
        this.messageManager.endAIResponse();
    }
    
    // Markdown渲染方法已移至MarkdownRenderer模块
    
    showError(message) {
        this.uiController.showError(this.chatMessages, message);
    }
    
    clearChat() {
        this.messageManager.clearChat(this.chatMessages);
    }
    
    async clearServerHistory() {
        try {
            if (!window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            let apiUrl = window.configManager.getFullApiUrl('/api/history');
            if (this.sessionId) {
                apiUrl += `?session_id=${encodeURIComponent(this.sessionId)}`;
            }
            await fetch(apiUrl, { method: 'DELETE' });
        } catch (error) {
            console.warn('清空服务器历史失败:', error);
        }
    }
    
    hideWelcomeMessage() {
        this.uiController.hideWelcomeMessage(this.chatMessages);
    }
    
    updateConnectionStatus(status) {
        this.uiController.updateConnectionStatus(this.connectionStatus, this.connectionText, status);
    }

    setConnectionExtra(text) {
        this.uiController.setConnectionExtra(this.connectionText, text);
    }
    
    updateCharCount() {
        this.uiController.updateCharCount(this.messageInput, this.charCount);
    }
    
    adjustInputHeight() {
        this.uiController.adjustInputHeight(this.messageInput);
    }
    
    updateSendButton() {
        const pendingAttachments = this.fileUploadManager.getPendingAttachments();
        this.uiController.updateSendButton(this.messageInput, this.sendBtn, pendingAttachments, this.wsManager, this.isStreaming);
    }
    
    scrollToBottom() {
        this.uiController.scrollToBottom(this.chatMessages);
    }

    smartScrollToBottom(force = false) {
        this.uiController.smartScrollToBottom(this.chatMessages, force);
    }

    isUserViewingContent() {
        return this.uiController.isUserViewingContent(this.chatMessages);
    }
    
    showLoading(text = '加载中...') {
        this.uiController.showLoading(this.loadingOverlay, text);
    }
    
    hideLoading() {
        this.uiController.hideLoading(this.loadingOverlay);
    }
    
    escapeHtml(text) {
        return this.uiController.escapeHtml(text);
    }
}
// 实例化并初始化
const chatApp = new ChatApp();
