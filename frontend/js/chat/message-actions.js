// message-actions.js - 用户消息的复制/编辑操作与渲染
(function(global){
    const MessageActions = {
        addUserMessageWithActions(app, content, meta = {}) {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message user';
            if (meta && meta.recordId != null) {
                try { messageDiv.dataset.recordId = String(meta.recordId); } catch {}
            }

            // 渲染内容
            let renderedContent;
            try {
                if (typeof marked !== 'undefined') {
                    renderedContent = marked.parse(content);
                } else {
                    renderedContent = app.escapeHtml(content);
                }
            } catch (error) {
                renderedContent = app.escapeHtml(content);
            }

            const actionsHtml = `
                <div class="msg-actions">
                    <button class="copy-btn" title="Copy">📋</button>
                    <button class="edit-btn" title="Edit & regenerate">✏️</button>
                </div>
            `;

            messageDiv.innerHTML = `
                <div class="message-bubble" data-raw="${app.escapeHtml(String(content))}">
                    ${renderedContent}
                    ${actionsHtml}
                </div>
            `;

            const copyBtn = messageDiv.querySelector('.copy-btn');
            const editBtn = messageDiv.querySelector('.edit-btn');
            const bubble = messageDiv.querySelector('.message-bubble');
            const raw = bubble ? bubble.getAttribute('data-raw') || '' : content;

            // 复制
            copyBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                try {
                    if (navigator.clipboard && window.isSecureContext) {
                        await navigator.clipboard.writeText(raw);
                    } else {
                        const ta = document.createElement('textarea');
                        ta.value = raw;
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        document.body.removeChild(ta);
                    }
                    copyBtn.textContent = '✅';
                    setTimeout(() => { copyBtn.textContent = '📋'; }, 1000);
                } catch (err) {
                    app.showError('Copy failed');
                }
            });

            // 编辑并在该节点后重生（仅记录回溯点，实际截断在发送时做）
            editBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                app.messageInput.value = raw;
                app.adjustInputHeight();
                app.updateCharCount();
                app.updateSendButton();
                app.pendingEdit = {
                    sessionId: meta.sessionId,
                    conversationId: meta.conversationId,
                    fromRecordId: meta.recordId
                };
                try { app.messageInput.focus(); } catch {}
            });

            app.chatMessages.appendChild(messageDiv);
            // Post-render: mermaid + code copy buttons
            try {
                if (app.messageManager && app.messageManager.markdownRenderer && typeof app.messageManager.markdownRenderer.afterRender === 'function') {
                    app.messageManager.markdownRenderer.afterRender(messageDiv, true);
                }
            } catch {}
            app.scrollToBottom();
        },

        attachActionsToLastUserMessage(app, data) {
            try {
                const rid = data && data.record_id;
                if (!rid) return;
                const nodes = Array.from(app.chatMessages.querySelectorAll('.message.user'));
                if (nodes.length === 0) return;
                const last = nodes[nodes.length - 1];
                last.dataset.recordId = String(rid);
                if (!last.querySelector('.msg-actions')) {
                    const bubble = last.querySelector('.message-bubble');
                    const raw = bubble ? (bubble.getAttribute('data-raw') || bubble.innerText || '') : '';
                    if (bubble) {
                        const actions = document.createElement('div');
                        actions.className = 'msg-actions';
                        actions.innerHTML = '<button class="copy-btn" title="Copy">📋</button><button class="edit-btn" title="Edit & regenerate">✏️</button>';
                        bubble.appendChild(actions);
                        const copyBtn = actions.querySelector('.copy-btn');
                        const editBtn = actions.querySelector('.edit-btn');
                        copyBtn.addEventListener('click', async (e) => {
                            e.stopPropagation();
                            try {
                                if (navigator.clipboard && window.isSecureContext) {
                                    await navigator.clipboard.writeText(raw);
                                } else {
                                    const ta = document.createElement('textarea');
                                    ta.value = raw;
                                    document.body.appendChild(ta);
                                    ta.select();
                                    document.execCommand('copy');
                                    document.body.removeChild(ta);
                                }
                                copyBtn.textContent = '✅';
                                setTimeout(() => { copyBtn.textContent = '📋'; }, 1000);
                            } catch (err) { app.showError('Copy failed'); }
                        });
                        editBtn.addEventListener('click', (e) => {
                            e.stopPropagation();
                            app.messageInput.value = raw;
                            app.adjustInputHeight();
                            app.updateCharCount();
                            app.updateSendButton();
                            app.pendingEdit = {
                                sessionId: data.session_id || app.resumedSessionId || app.sessionId,
                                conversationId: data.conversation_id || app.resumedConversationId,
                                fromRecordId: rid
                            };
                            try { app.messageInput.focus(); } catch {}
                        });
                    }
                }
            } catch (e) { console.warn('attachActionsToLastUserMessage 失败', e); }
        }
    };

    global.MessageActions = MessageActions;
})(window);


