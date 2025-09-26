// history.js - 线程侧栏与历史回放
(function(global){
    const History = {
        renderThreads(app, threads) {
            const list = app.threadsList;
            if (!list) return;
            list.innerHTML = '';
            (threads || []).forEach(t => {
                const div = document.createElement('div');
                div.className = 'thread-item';
                const title = (t.first_user_input || 'New conversation').slice(0, 40);
                const meta = `${t.message_count || 0} msgs · ${new Date(t.last_time).toLocaleString()}`;
                div.innerHTML = `<div class="title">${app.escapeHtml(title)}</div><div class="meta"><span>${app.escapeHtml(meta)}</span><span class="delete-icon" title="Delete">🗑️</span></div>`;
                div.addEventListener('click', () => {
                    History.loadHistoryForConversation(app, t.session_id, t.conversation_id);
                });
                const del = div.querySelector('.delete-icon');
                del.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    if (!confirm('Delete this conversation?')) return;
                    try {
                        const apiUrl = global.configManager.getFullApiUrl(`/api/threads?session_id=${encodeURIComponent(t.session_id)}&conversation_id=${encodeURIComponent(t.conversation_id)}`);
                        const res = await fetch(apiUrl, { method: 'DELETE' });
                        const json = await res.json();
                        if (json && json.success) {
                            div.remove();
                        }
                    } catch (err) { console.warn('删除会话失败', err); }
                });
                list.appendChild(div);
            });
        },

        async loadHistoryForConversation(app, sessionId, conversationId) {
            try {
                if (typeof app.setActiveConversation === 'function') {
                    app.setActiveConversation(sessionId, conversationId);
                } else if (app.wsManager && typeof app.wsManager.send === 'function') {
                    try { app.wsManager.send({ type: 'resume_conversation', session_id: sessionId, conversation_id: conversationId }); } catch {}
                }
                app.clearChat();
                app.sessionId = sessionId;
                app.hideWelcomeMessage();
                const username = (global.Auth && Auth.getUsername && Auth.getUsername()) || '';
                const params = new URLSearchParams();
                if (sessionId) params.set('session_id', sessionId);
                if (conversationId != null) params.set('conversation_id', conversationId);
                const apiUrl = global.configManager.getFullApiUrl(`/api/history?${params.toString()}`);
                const token = (global.Auth && Auth.getToken && Auth.getToken()) || '';
                const res = await fetch(apiUrl, { cache: 'no-store', headers: token ? { 'Authorization': `Bearer ${token}` } : {} });
                const json = await res.json();
                if (!json.success) return;
                (json.data || []).forEach(r => {
                    const hasText = typeof r.user_input === 'string' && r.user_input.trim() !== '';
                    const files = Array.isArray(r.attachments) ? r.attachments : [];
                    if (hasText || files.length > 0) {
                        if (global.MessageActions && typeof global.MessageActions.addUserMessageWithActions === 'function') {
                            const contentWithAttachments = History.composeUserMessageWithAttachments(app, r.user_input, r.attachments);
                            global.MessageActions.addUserMessageWithActions(app, contentWithAttachments, { recordId: r.id, sessionId, conversationId });
                        } else {
                            // 回退：无模块时用基础渲染
                            app.addUserMessage(History.composeUserMessageWithAttachments(app, r.user_input, r.attachments));
                        }
                    }

                    app.thinkingFlow.createThinkingFlow();
                    const toolsCalled = Array.isArray(r.mcp_tools_called) ? r.mcp_tools_called : [];
                    const results = Array.isArray(r.mcp_results) ? r.mcp_results : [];
                    if (toolsCalled.length > 0) {
                        app.thinkingFlow.updateThinkingStage('tools_planned', `Planning to use ${toolsCalled.length} tool(s)`, 'Replaying recorded tool operations...', { toolCount: toolsCalled.length });
                        const idToResult = {};
                        results.forEach(x => { if (x && x.tool_id) idToResult[x.tool_id] = x; });
                        toolsCalled.forEach(tc => {
                            const toolId = tc.tool_id || tc.id || tc.name || Math.random().toString(36).slice(2);
                            const toolName = tc.tool_name || (tc.function && tc.function.name) || tc.name || 'tool';
                            const args = tc.tool_args || (tc.function && tc.function.arguments) || {};
                            app.thinkingFlow.addToolToThinking({ tool_id: toolId, tool_name: toolName, tool_args: args });
                            const matched = idToResult[toolId] || {};
                            if (matched && matched.result !== undefined) {
                                app.thinkingFlow.updateToolInThinking({ tool_id: toolId, tool_name: toolName, result: String(matched.result) }, 'completed');
                            } else if (matched && matched.error) {
                                app.thinkingFlow.updateToolInThinking({ tool_id: toolId, tool_name: toolName, error: String(matched.error) }, 'error');
                            } else {
                                app.thinkingFlow.updateToolInThinking({ tool_id: toolId, tool_name: toolName, result: '(no recorded result)' }, 'completed');
                            }
                        });
                        app.thinkingFlow.updateThinkingStage('responding', 'Preparing response', 'Organizing evidence-based conclusions and recommendations...');
                        app.thinkingFlow.completeThinkingFlow('success');
                    } else {
                        app.thinkingFlow.updateThinkingStage('responding', 'Preparing response', 'Organizing evidence-based conclusions and recommendations...');
                        app.thinkingFlow.completeThinkingFlow('success');
                    }

                    if (r.ai_response) {
                        app.startAIResponse();
                        app.appendAIResponse(r.ai_response);
                        app.endAIResponse();
                        // 若数据库有 usage，补上一行浅色用量提示（与在线一致）
                        try {
                            if (r.usage && (r.usage.input_tokens != null || r.usage.output_tokens != null)) {
                                app.appendTokenUsageFooter({
                                    input_tokens: r.usage.input_tokens,
                                    output_tokens: r.usage.output_tokens,
                                    total_tokens: r.usage.total_tokens
                                });
                            }
                        } catch {}
                    }
                });
                app.smartScrollToBottom(); // 历史回放使用智能滚动
            } catch (e) { console.warn('加载会话历史失败', e); }
        }
        ,
        composeUserMessageWithAttachments(app, userText, attachments) {
            const base = String(userText || '').trim();
            const files = Array.isArray(attachments) ? attachments : [];
            if (files.length === 0) return base;
            const list = files.map(a => {
                const name = app.escapeHtml(a && a.filename ? a.filename : 'file');
                const rawUrl = a && a.url ? app.makeFullApiUrl(a.url) : '';
                const url = app.escapeHtml(rawUrl);
                if (!url) return `• ${name}`;
                // 若为图片扩展名，展示缩略图
                const lower = url.toLowerCase();
                const isImg = lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.jpeg') || lower.endsWith('.webp') || lower.endsWith('.gif');
                if (isImg) {
                    return `• ${name}<br><img src="${url}" alt="${name}" style="max-width:180px;max-height:180px;border-radius:6px;border:1px solid #e2e8f0;margin:4px 0;"/>`;
                }
                return `• <a href="${url}" download target="_blank" rel="noopener noreferrer">${name}</a>`;
            }).join('<br>');
            const html = `${base}${base ? '<br><br>' : ''}<strong>Attachments:</strong><br>${list}`;
            return html;
        }
    };

    global.History = History;
})(window);


