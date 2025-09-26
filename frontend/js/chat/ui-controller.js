// ui-controller.js - UI控制模块
class UIController {
    constructor(chatApp) {
        this.chatApp = chatApp;
    }

    // 更新发送按钮状态
    updateSendButton(messageInput, sendBtn, pendingAttachments, wsManager, isStreaming) {
        if (!sendBtn) return;
        
        const hasText = messageInput && messageInput.value.trim().length > 0;
        const hasAttachments = (pendingAttachments && pendingAttachments.length > 0);
        const isConnected = wsManager && wsManager.isConnected();

        if (isStreaming) {
            sendBtn.innerHTML = '⏸️';
            sendBtn.disabled = !isConnected; // 生成中允许点击暂停
        } else {
            sendBtn.innerHTML = '📤';
            sendBtn.disabled = (!hasText && !hasAttachments);
        }
    }

    // 更新字符计数
    updateCharCount(messageInput, charCountEl) {
        if (!messageInput || !charCountEl) return;
        
        const count = messageInput.value.length;
        charCountEl.textContent = count;
        
        if (count > 1800) {
            charCountEl.style.color = '#e53e3e';
        } else if (count > 1500) {
            charCountEl.style.color = '#ed8936';
        } else {
            charCountEl.style.color = '#a0aec0';
        }
    }

    // 调整输入框高度
    adjustInputHeight(messageInput) {
        if (!messageInput) return;
        
        // 保存滚动位置
        const scrollTop = messageInput.scrollTop;
        
        // 重置高度
        messageInput.style.height = 'auto';
        
        // 设置新高度
        const newHeight = Math.min(messageInput.scrollHeight, 150);
        messageInput.style.height = newHeight + 'px';
        
        // 恢复滚动位置
        messageInput.scrollTop = scrollTop;
        
        // 如果内容超出了可视区域，滚动到底部
        if (messageInput.scrollHeight > newHeight) {
            messageInput.scrollTop = messageInput.scrollHeight;
        }
    }

    // 滚动到底部
    scrollToBottom(chatMessagesEl) {
        if (!chatMessagesEl) return;
        
        // 使用requestAnimationFrame确保DOM更新完成后再滚动
        requestAnimationFrame(() => {
            chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
        });
    }

    // 智能滚动：只有在用户接近底部时才滚动
    smartScrollToBottom(chatMessagesEl, force = false) {
        if (!chatMessagesEl) return;

        const container = chatMessagesEl;
        const threshold = 100; // 底部100px范围内认为用户在底部
        const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;

        // 如果强制滚动或用户在底部附近，才滚动
        if (force || distanceFromBottom <= threshold) {
            this.scrollToBottom(chatMessagesEl);
        }
    }

    // 检查用户是否正在主动查看内容（用于决定是否滚动）
    isUserViewingContent(chatMessagesEl) {
        if (!chatMessagesEl) return false;

        const container = chatMessagesEl;
        const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;

        // 如果用户距离底部超过200px，认为正在查看历史内容
        return distanceFromBottom > 200;
    }

    // 显示加载中
    showLoading(loadingOverlay, text = '加载中...') {
        if (!loadingOverlay) return;
        
        loadingOverlay.style.display = 'flex';
        const textEl = loadingOverlay.querySelector('div');
        if (textEl) {
            textEl.textContent = text;
        }
    }

    // 隐藏加载中
    hideLoading(loadingOverlay) {
        if (!loadingOverlay) return;
        loadingOverlay.style.display = 'none';
    }

    // 更新连接状态
    updateConnectionStatus(connectionStatus, connectionText, status) {
        if (connectionStatus) {
            connectionStatus.className = `status-dot ${status}`;
        }
        
        if (connectionText) {
            switch (status) {
                case 'online':
                    connectionText.textContent = '已连接';
                    break;
                case 'offline':
                    connectionText.textContent = '离线';
                    break;
                case 'connecting':
                    connectionText.textContent = '连接中';
                    break;
            }
        }
    }

    // 设置连接额外信息
    setConnectionExtra(connectionText, text) {
        try {
            if (!connectionText) return;
            const base = connectionText.textContent.split(' | ')[0];
            if (text) {
                connectionText.textContent = `${base} | ${text}`;
            } else {
                connectionText.textContent = base;
            }
        } catch {}
    }

    // 隐藏欢迎消息
    hideWelcomeMessage(chatMessagesEl) {
        if (!chatMessagesEl) return;
        
        const welcomeMessage = chatMessagesEl.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.style.display = 'none';
        }
    }

    // 显示错误信息
    showError(chatMessagesEl, message) {
        if (!chatMessagesEl) return;
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'message ai';
        errorDiv.innerHTML = `
            <div class="message-bubble" style="background: rgba(245, 101, 101, 0.1); border-color: rgba(245, 101, 101, 0.3); color: #e53e3e;">
                ❌ ${this.escapeHtml(message)}
            </div>
        `;

        chatMessagesEl.appendChild(errorDiv);
        this.smartScrollToBottom(chatMessagesEl, true); // 错误消息强制滚动
    }

    // 在输入框光标位置插入文本
    insertTextAtCursor(messageInput, text) {
        if (!messageInput) return;
        
        const start = messageInput.selectionStart ?? messageInput.value.length;
        const end = messageInput.selectionEnd ?? messageInput.value.length;
        const before = messageInput.value.substring(0, start);
        const after = messageInput.value.substring(end);
        const needsSpace = before && !before.endsWith(' ');
        const insert = (needsSpace ? ' ' : '') + text;
        messageInput.value = before + insert + after;
        const caret = (before + insert).length;
        try { messageInput.setSelectionRange(caret, caret); } catch {}
        try { messageInput.focus(); } catch {}
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
