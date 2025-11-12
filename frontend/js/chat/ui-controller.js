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

    // 显示友好的登录引导信息
    showLoginGuide(chatMessagesEl) {
        if (!chatMessagesEl) return;
        
        const guideDiv = document.createElement('div');
        guideDiv.className = 'message ai login-guide';
        guideDiv.innerHTML = `
            <div class="message-bubble" style="background: linear-gradient(135deg, rgba(66, 153, 225, 0.08) 0%, rgba(72, 187, 120, 0.08) 100%); 
                                                 border: 1px solid rgba(66, 153, 225, 0.2); 
                                                 color: #2d3748;
                                                 padding: 1.5rem;
                                                 border-radius: 12px;">
                <div style="display: flex; align-items: flex-start; gap: 1rem;">
                    <div style="font-size: 2rem; flex-shrink: 0;">👋</div>
                    <div style="flex: 1;">
                        <h3 style="margin: 0 0 0.75rem 0; font-size: 1.1rem; font-weight: 600; color: #2d3748;">
                            欢迎使用智能助手
                        </h3>
                        <p style="margin: 0 0 1rem 0; color: #4a5568; line-height: 1.6;">
                            为了提供更好的服务体验,请先登录您的账号。登录后您将享有:
                        </p>
                        <ul style="margin: 0 0 1rem 0; padding-left: 1.25rem; color: #4a5568; line-height: 1.8;">
                            <li>对话历史自动保存</li>
                            <li>个性化模型配置</li>
                            <li>多端数据同步</li>
                        </ul>
                        <div style="display: flex; gap: 0.75rem; margin-top: 1.25rem;">
                            <a href="login.html" style="display: inline-block; 
                                                        background: linear-gradient(135deg, #4299e1 0%, #48bb78 100%);
                                                        color: white; 
                                                        padding: 0.5rem 1.25rem; 
                                                        border-radius: 8px; 
                                                        text-decoration: none;
                                                        font-weight: 500;
                                                        transition: all 0.2s;
                                                        box-shadow: 0 2px 4px rgba(66, 153, 225, 0.2);">
                                立即登录 →
                            </a>
                            <a href="register.html" style="display: inline-block; 
                                                           color: #4299e1; 
                                                           padding: 0.5rem 1.25rem; 
                                                           border-radius: 8px; 
                                                           text-decoration: none;
                                                           border: 1px solid #4299e1;
                                                           font-weight: 500;
                                                           transition: all 0.2s;">
                                注册新账号
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;

        chatMessagesEl.appendChild(guideDiv);
        this.smartScrollToBottom(chatMessagesEl, true);
    }

    // 显示轻量级提示Toast (用于非阻塞式提示)
    showStatusToast(message, duration = 3000) {
        // 创建toast容器
        let toastContainer = document.getElementById('statusToastContainer');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'statusToastContainer';
            toastContainer.style.cssText = `
                position: fixed;
                top: 80px;
                right: 20px;
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 10px;
            `;
            document.body.appendChild(toastContainer);
        }

        // 创建toast元素
        const toast = document.createElement('div');
        toast.style.cssText = `
            background: rgba(45, 55, 72, 0.95);
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            font-size: 14px;
            max-width: 300px;
            animation: slideIn 0.3s ease-out;
        `;
        toast.textContent = message;

        // 添加动画样式
        if (!document.getElementById('toastAnimationStyle')) {
            const style = document.createElement('style');
            style.id = 'toastAnimationStyle';
            style.textContent = `
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                @keyframes slideOut {
                    from { transform: translateX(0); opacity: 1; }
                    to { transform: translateX(100%); opacity: 0; }
                }
            `;
            document.head.appendChild(style);
        }

        toastContainer.appendChild(toast);

        // 自动移除
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => {
                toast.remove();
                // 如果容器为空则移除容器
                if (toastContainer.children.length === 0) {
                    toastContainer.remove();
                }
            }, 300);
        }, duration);
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
