// file-upload-manager.js - 文件上传管理模块
class FileUploadManager {
    constructor(chatApp) {
        this.chatApp = chatApp;
        this.pendingAttachments = [];
    }

    // 上传文件并获取链接
    async uploadFilesAndGetLinks(files) {
        if (!window.configManager || !window.configManager.isLoaded) {
            await window.configManager.loadConfig();
        }
        const apiUrl = window.configManager.getFullApiUrl('/api/upload');
        const results = [];
        
        for (const f of files) {
            const fd = new FormData();
            fd.append('file', f, f.name);
            const res = await fetch(apiUrl, { method: 'POST', body: fd });
            if (!res.ok) {
                const t = await res.text().catch(() => '');
                throw new Error(`Upload failed: ${res.status} ${t}`);
            }
            const json = await res.json();
            if (!json || !json.success || !json.data || !json.data.url) {
                throw new Error('文件上传响应异常');
            }
            const urlPath = json.data.url; // like /uploads/20240101/uuid.ext
            const fullUrl = this.makeFullApiUrl(urlPath);
            // 若是图片，生成 dataURL 以便直接传给具备视觉能力的模型
            let dataUrl = null;
            const isImage = !!(f && f.type && f.type.startsWith('image/'));
            if (isImage) {
                try {
                    dataUrl = await this.readFileAsDataURL(f);
                } catch {}
            }
            results.push({ filename: json.data.filename || f.name, urlPath, fullUrl, isImage, dataUrl });
        }
        return results;
    }

    // 读取文件为DataURL
    readFileAsDataURL(file) {
        return new Promise((resolve, reject) => {
            try {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = (e) => reject(e);
                reader.readAsDataURL(file);
            } catch (e) {
                reject(e);
            }
        });
    }

    // 添加附件芯片
    addAttachmentChips(items, attachmentChipsEl) {
        if (!attachmentChipsEl) return;
        items.forEach(item => {
            const chip = document.createElement('span');
            chip.className = 'attach-chip';
            chip.textContent = item.filename;
            const del = document.createElement('button');
            del.className = 'attach-chip-del';
            del.textContent = '×';
            del.addEventListener('click', (e) => {
                e.stopPropagation();
                chip.remove();
                this.pendingAttachments = (this.pendingAttachments || []).filter(x => x !== item);
                if (this.chatApp.updateSendButton) {
                    this.chatApp.updateSendButton();
                }
            });
            chip.addEventListener('click', (e) => {
                e.stopPropagation();
                this.downloadAttachment(item);
            });
            chip.appendChild(del);
            attachmentChipsEl.appendChild(chip);
        });
    }

    // 清空附件芯片
    clearAttachmentChips(attachmentChipsEl) {
        if (!attachmentChipsEl) return;
        attachmentChipsEl.innerHTML = '';
    }

    // 下载附件
    downloadAttachment(item) {
        try {
            const a = document.createElement('a');
            a.href = item.fullUrl;
            a.download = item.filename || '';
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        } catch (e) {
            console.warn('下载失败', e);
        }
    }

    // 生成用户显示消息
    composeUserDisplayMessage(text, attachments) {
        const base = (text || '').trim();
        if (!attachments || attachments.length === 0) return base;
        const list = attachments.map(a => {
            const safeName = this.escapeHtml(a.filename);
            const safeUrl = this.escapeHtml(a.fullUrl);
            if (a.isImage) {
                const thumb = this.escapeHtml(a.dataUrl || a.fullUrl);
                return `• ${safeName}<br><img src="${thumb}" alt="${safeName}" style="max-width:180px;max-height:180px;border-radius:6px;border:1px solid #e2e8f0;margin:4px 0;"/>`;
            }
            return `• <a href="${safeUrl}" download target="_blank" rel="noopener noreferrer">${safeName}</a>`;
        }).join('<br>');
        const html = `${this.escapeHtml(base)}${base ? '<br><br>' : ''}<strong>Attachments:</strong><br>${list}`;
        return html;
    }

    // 生成完整API URL
    makeFullApiUrl(path) {
        try {
            const base = window.configManager.getApiBaseUrl();
            if (!path.startsWith('/')) return base + '/' + path;
            return base + path;
        } catch (e) {
            return path;
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

    // 设置待发送附件
    setPendingAttachments(attachments) {
        this.pendingAttachments = attachments || [];
    }

    // 获取待发送附件
    getPendingAttachments() {
        return this.pendingAttachments || [];
    }

    // 清空待发送附件
    clearPendingAttachments() {
        this.pendingAttachments = [];
    }
}
