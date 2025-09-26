// model-manager.js - 模型管理模块
class ModelManager {
    constructor(chatApp) {
        this.chatApp = chatApp;
        this.selectedModel = null;
        this.models = [];
    }

    // 加载模型列表并渲染下拉菜单
    async loadModelsAndRenderDropdown(modelDropdownBtn, modelDropdown, wsManager) {
        try {
            const apiUrl = window.configManager.getFullApiUrl('/api/models');
            const token = (window.Auth && Auth.getToken && Auth.getToken()) || '';
            const res = await fetch(apiUrl, { cache: 'no-store', headers: token ? { 'Authorization': `Bearer ${token}` } : {} });
            const json = await res.json();
            if (!json.success) throw new Error('加载模型列表失败');
            const { models, default: def } = json.data || { models: [], default: 'default' };

            this.models = models;

            let selected = localStorage.getItem('mcp_selected_model') || def;
            // 如果本地无记录，写入一次，保证首连就有 model
            if (!localStorage.getItem('mcp_selected_model')) {
                localStorage.setItem('mcp_selected_model', selected);
            }
            this.selectedModel = selected;
            this.updateModelButtonLabel(modelDropdownBtn, selected);

            // 渲染菜单
            if (modelDropdown) {
                modelDropdown.innerHTML = '';
                models.forEach(m => {
                    const item = document.createElement('div');
                    item.className = 'dropdown-item';
                    item.textContent = `${m.label || m.id} (${m.model || ''})`;
                    item.addEventListener('click', async () => {
                        await this.switchModel(m.id, modelDropdownBtn, modelDropdown, wsManager);
                    });
                    modelDropdown.appendChild(item);
                });
            }
        } catch (e) {
            console.warn('⚠️ 无法加载Model列表:', e);
        }
    }

    // 切换模型
    async switchModel(modelId, modelDropdownBtn, modelDropdown, wsManager) {
        try {
            // 改为通过WS指令切换模型，避免断开重连
            localStorage.setItem('mcp_selected_model', modelId);
            this.selectedModel = modelId;
            this.updateModelButtonLabel(modelDropdownBtn, modelId);
            if (modelDropdown) {
                modelDropdown.style.display = 'none';
            }
            
            if (wsManager && wsManager.isConnected()) {
                const ok = wsManager.send({ type: 'switch_model', model: modelId });
                if (!ok) throw new Error('数据连接中断');
            } else {
                // 若尚未连接，保留旧逻辑：初始化时会带上 model 参数
                if (this.chatApp && this.chatApp.connectWebSocket) {
                    await this.chatApp.connectWebSocket();
                }
            }
        } catch (e) {
            console.warn('切换模型失败，回退为重连方式', e);
            try { 
                if (wsManager) wsManager.close(); 
            } catch {}
            if (wsManager) {
                wsManager.isInitialized = false;
            }
            if (this.chatApp && this.chatApp.connectWebSocket) {
                await this.chatApp.connectWebSocket();
            }
        }
    }

    // 更新模型按钮标签
    updateModelButtonLabel(modelDropdownBtn, selectedId) {
        try {
            if (!modelDropdownBtn) return;
            
            const picked = this.models.find(m => m.id === selectedId);
            const label = picked ? (picked.label || picked.id) : selectedId;
            modelDropdownBtn.textContent = `Model：${label} ▾`;
        } catch {}
    }

    // 获取当前选中的模型
    getSelectedModel() {
        return this.selectedModel || localStorage.getItem('mcp_selected_model');
    }

    // 获取模型列表
    getModels() {
        return this.models;
    }

    // 设置模型列表
    setModels(models) {
        this.models = models;
    }
}
