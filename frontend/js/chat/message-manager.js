// message-manager.js - 消息管理模块
class MessageManager {
    constructor(chatApp) {
        this.chatApp = chatApp;
        this.currentAIMessage = null;
        this.currentAIContent = '';
        this.markdownRenderer = new MarkdownRenderer();
        this.uiController = chatApp.uiController;
    }

    // 添加用户消息
    addUserMessage(chatMessagesEl, content) {
        if (!chatMessagesEl) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        
        // 尝试渲染markdown，如果失败则使用原始文本
        let renderedContent;
        try {
            if (typeof marked !== 'undefined') {
                renderedContent = marked.parse(content);
            } else {
                renderedContent = this.escapeHtml(content);
            }
        } catch (error) {
            console.warn('User message Markdown rendering error:', error);
            renderedContent = this.escapeHtml(content);
        }
        
        messageDiv.innerHTML = `
            <div class="message-bubble">
                ${renderedContent}
            </div>
        `;

        chatMessagesEl.appendChild(messageDiv);
        // Render diagrams (e.g., mermaid) after insertion
        if (this.markdownRenderer && typeof this.markdownRenderer.afterRender === 'function') {
            this.markdownRenderer.afterRender(messageDiv, true);
        }
        if (this.uiController) {
            this.uiController.smartScrollToBottom(chatMessagesEl, true); // 用户消息强制滚动
        }
    }

    // 带复制/编辑操作的用户消息（用于历史回放）
    addUserMessageWithActions(chatMessagesEl, content, meta = {}) {
        if (!chatMessagesEl) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        if (meta && meta.recordId != null) {
            try { messageDiv.dataset.recordId = String(meta.recordId); } catch {}
        }

        let renderedContent;
        try {
            if (typeof marked !== 'undefined') {
                renderedContent = marked.parse(content);
            } else {
                renderedContent = this.escapeHtml(content);
            }
        } catch (error) {
            renderedContent = this.escapeHtml(content);
        }

        const actionsHtml = `
            <div class="msg-actions">
                <button class="copy-btn" title="Copy">📋</button>
                <button class="edit-btn" title="Edit & regenerate">✏️</button>
            </div>
        `;

        messageDiv.innerHTML = `
            <div class="message-bubble">
                ${renderedContent}
                ${actionsHtml}
            </div>
        `;

        const copyBtn = messageDiv.querySelector('.copy-btn');
        const editBtn = messageDiv.querySelector('.edit-btn');

        this.setupCopyButton(copyBtn, content);
        this.setupEditButton(editBtn, content, meta);

        chatMessagesEl.appendChild(messageDiv);
        // Render diagrams (e.g., mermaid) after insertion
        if (this.markdownRenderer && typeof this.markdownRenderer.afterRender === 'function') {
            this.markdownRenderer.afterRender(messageDiv, true);
        }
        if (this.uiController) {
            this.uiController.smartScrollToBottom(chatMessagesEl); // 历史消息使用智能滚动
        }
    }

    // 设置复制按钮
    setupCopyButton(copyBtn, content) {
        if (!copyBtn) return;
        
        copyBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            try {
                if (navigator.clipboard && window.isSecureContext) {
                    await navigator.clipboard.writeText(content);
                } else {
                    const ta = document.createElement('textarea');
                    ta.value = content;
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                }
                copyBtn.textContent = '✅';
                setTimeout(() => { copyBtn.textContent = '📋'; }, 1000);
            } catch (err) {
                if (this.uiController) {
                    this.uiController.showError(this.chatApp.chatMessages, '复制失败');
                }
            }
        });
    }

    // 设置编辑按钮
    setupEditButton(editBtn, content, meta) {
        if (!editBtn) return;
        
        editBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            
            if (this.chatApp.messageInput) {
                this.chatApp.messageInput.value = content;
                if (this.uiController) {
                    this.uiController.adjustInputHeight(this.chatApp.messageInput);
                }
                if (this.chatApp.updateCharCount) {
                    this.chatApp.updateCharCount();
                }
                if (this.chatApp.updateSendButton) {
                    this.chatApp.updateSendButton();
                }
                
                this.chatApp.pendingEdit = {
                    sessionId: meta.sessionId,
                    conversationId: meta.conversationId,
                    fromRecordId: meta.recordId
                };
                
                try { this.chatApp.messageInput.focus(); } catch {}
            }
        });
    }

    // 开始AI回复
    startAIResponse(chatMessagesEl) {
        if (!chatMessagesEl) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ai';
        messageDiv.innerHTML = `
            <div class="message-bubble">
                <span class="ai-cursor">▋</span>
            </div>
        `;
        
        chatMessagesEl.appendChild(messageDiv);
        this.currentAIMessage = messageDiv.querySelector('.message-bubble');
        this.currentAIContent = ''; // 重置累积内容
        
        if (this.uiController) {
            this.uiController.smartScrollToBottom(chatMessagesEl, true); // AI回复开始时强制滚动
        }
    }

    // 追加AI回复内容
    appendAIResponse(content) {
        if (this.currentAIMessage) {
            // 累积内容
            this.currentAIContent += content;

            // 实时渲染markdown
            this.renderMarkdownContent();

            // AI回复内容更新时使用智能滚动（尊重用户查看历史）
            if (this.uiController && this.chatApp.chatMessages) {
                this.uiController.smartScrollToBottom(this.chatApp.chatMessages);
            }
        }
    }

    // 结束AI回复
    endAIResponse() {
        if (this.currentAIMessage) {
            // 最终渲染markdown（确保所有内容都被处理）
            this.renderMarkdownContent(true);
            // 完成后渲染 Mermaid 等高级 Markdown 扩展
            try {
                if (this.markdownRenderer && typeof this.markdownRenderer.afterRender === 'function') {
                    this.markdownRenderer.afterRender(this.currentAIMessage, true);
                }
            } catch {}
            
            // 移除光标
            const cursor = this.currentAIMessage.querySelector('.ai-cursor');
            if (cursor) {
                cursor.remove();
            }
            
            // 为AI消息添加复制按钮
            try {
                const rawFinal = this.currentAIContent || '';
                this.currentAIMessage.setAttribute('data-raw', rawFinal);
                this.attachAIActions(this.currentAIMessage, rawFinal);
            } catch {}
            
            this.currentAIMessage = null;
            this.currentAIContent = '';
        }
    }

    // 为AI消息添加操作按钮
    attachAIActions(bubbleEl, rawText) {
        try {
            if (!bubbleEl) return;
            if (bubbleEl.querySelector('.msg-actions')) return;
            
            const actions = document.createElement('div');
            actions.className = 'msg-actions';
            const copyBtn = document.createElement('button');
            copyBtn.className = 'copy-btn';
            copyBtn.title = 'Copy';
            copyBtn.textContent = '📋';
            actions.appendChild(copyBtn);
            bubbleEl.appendChild(actions);

            copyBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const text = rawText != null ? String(rawText) : (bubbleEl.innerText || '');
                try {
                    if (navigator.clipboard && window.isSecureContext) {
                        await navigator.clipboard.writeText(text);
                    } else {
                        const ta = document.createElement('textarea');
                        ta.value = text;
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        document.body.removeChild(ta);
                    }
                    copyBtn.textContent = '✅';
                    setTimeout(() => { copyBtn.textContent = '📋'; }, 1000);
                } catch (err) {
                    if (this.uiController) {
                        this.uiController.showError(this.chatApp.chatMessages, '复制失败');
                    }
                }
            });
        } catch {}
    }

    // 渲染markdown内容
    renderMarkdownContent(isFinal = false) {
        if (!this.currentAIMessage) return;
        
        const renderedContent = this.markdownRenderer.renderMarkdownContent(this.currentAIContent, isFinal);
        
        // 更新内容并添加光标
        this.currentAIMessage.innerHTML = renderedContent + 
            (!isFinal ? '<span class="ai-cursor">▋</span>' : '');
    }

    // 在最后一条AI消息下面插入用量提示，不纳入复制范围
    appendTokenUsageFooter(chatMessagesEl, usage) {
        try {
            const { input_tokens, output_tokens, total_tokens } = usage || {};
            if (!chatMessagesEl) return;
            
            // 找到最后一个AI消息气泡
            const nodes = Array.from(chatMessagesEl.querySelectorAll('.message.ai .message-bubble'));
            const last = nodes[nodes.length - 1];
            if (!last) return;
            
            // 如果已有footer则更新
            let footer = last.parentElement.querySelector('.ai-usage');
            if (!footer) {
                footer = document.createElement('div');
                footer.className = 'ai-usage';
                footer.style.cssText = 'margin-top:6px; font-size:12px; color:#94a3b8; user-select:none; -webkit-user-select:none;';
                last.parentElement.appendChild(footer);
            }
            const it = (input_tokens != null) ? input_tokens : '-';
            const ot = (output_tokens != null) ? output_tokens : '-';
            const tt = (total_tokens != null) ? total_tokens : ( (typeof it==='number'?it:0) + (typeof ot==='number'?ot:0) );
            footer.textContent = `Tokens: in ${it} | out ${ot} | total ${tt}`;
        } catch (e) {
            console.warn('渲染token用量提示失败', e);
        }
    }

    // 从指定记录ID对应的用户消息开始，删除其自身及后续的所有DOM节点
    truncateAfterRecord(chatMessagesEl, recordId) {
        try {
            if (!chatMessagesEl) return;
            
            const nodes = Array.from(chatMessagesEl.children);
            const anchor = nodes.find(el => el.classList && el.classList.contains('user') && String(el.dataset.recordId || '') === String(recordId));
            if (!anchor) return;
            
            let current = anchor;
            while (current) {
                const next = current.nextSibling;
                chatMessagesEl.removeChild(current);
                current = next;
            }
            
            // 清理AI状态
            this.currentAIMessage = null;
            this.currentAIContent = '';
            
            // 清理思维流状态
            if (this.chatApp.thinkingFlow && this.chatApp.thinkingFlow.clear) {
                this.chatApp.thinkingFlow.clear();
            }
        } catch (e) { 
            console.warn('截断历史失败', e); 
        }
    }

    // 清空聊天记录
    clearChat(chatMessagesEl) {
        if (!chatMessagesEl) return;
        
        // 清空消息区域，保留欢迎消息
        const welcomeMessage = chatMessagesEl.querySelector('.welcome-message');
        chatMessagesEl.innerHTML = '';
        
        if (welcomeMessage) {
            chatMessagesEl.appendChild(welcomeMessage);
            welcomeMessage.style.display = 'block';
        }
        
        // 清理状态
        this.currentAIMessage = null;
        this.currentAIContent = '';
        
        // 清理思维流状态
        if (this.chatApp.thinkingFlow && this.chatApp.thinkingFlow.clear) {
            this.chatApp.thinkingFlow.clear();
        }
    }

    // HTML转义
    escapeHtml(text) {
        if (text === null || text === undefined) {
            return '';
        }
        return text.toString()
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#039;");
    }
}
