// auth.js - 简单前端鉴权管理
(function() {
    const STORAGE_TOKEN = 'auth_token';
    const STORAGE_USER = 'auth_username';

    async function postJson(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {})
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.success === false) {
            const msg = data.detail || data.message || (`HTTP ${res.status}`);
            throw new Error(msg);
        }
        return data;
    }

    const Auth = {
        getToken() {
            try { return localStorage.getItem(STORAGE_TOKEN) || ''; } catch { return ''; }
        },
        getUsername() {
            try { return localStorage.getItem(STORAGE_USER) || ''; } catch { return ''; }
        },
        setToken(token, username) {
            try {
                localStorage.setItem(STORAGE_TOKEN, token || '');
                if (username != null) localStorage.setItem(STORAGE_USER, username || '');
            } catch {}
        },
        async sendCode(email, purpose) {
            if (!window.configManager || !window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            const url = window.configManager.getFullApiUrl('/api/auth/send_code');
            return await postJson(url, { email, purpose: purpose || 'register' });
        },
        clear() {
            try {
                localStorage.removeItem(STORAGE_TOKEN);
                localStorage.removeItem(STORAGE_USER);
            } catch {}
        },
        isLoggedIn() {
            return !!this.getToken();
        },
        async login(username, password) {
            if (!window.configManager || !window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            const url = window.configManager.getFullApiUrl('/api/auth/login');
            const data = await postJson(url, { username, password });
            const token = (data && data.token) || '';
            if (token) this.setToken(token, username);
            return data;
        },
        async loginWithCode(email, code) {
            if (!window.configManager || !window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            const url = window.configManager.getFullApiUrl('/api/auth/login_with_code');
            const data = await postJson(url, { email, code });
            const token = (data && data.token) || '';
            const username = (data && data.user && data.user.username) || '';
            if (token && username) this.setToken(token, username);
            return data;
        },
        async register(email, username, password, confirmPassword, code) {
            if (!window.configManager || !window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            const url = window.configManager.getFullApiUrl('/api/auth/register');
            const payload = { email, username, password, confirm_password: confirmPassword };
            if (code && code.trim()) {
                payload.code = code.trim();
            }
            return await postJson(url, payload);
        },
        async resetPassword(email, code, newPassword, confirmPassword) {
            if (!window.configManager || !window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            const url = window.configManager.getFullApiUrl('/api/auth/reset_password');
            const payload = { email, code, new_password: newPassword };
            if (confirmPassword != null) payload.confirm_password = confirmPassword;
            return await postJson(url, payload);
        },
        async changePassword(oldPassword, newPassword) {
            if (!window.configManager || !window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            const url = window.configManager.getFullApiUrl('/api/auth/change_password');
            const token = this.getToken();
            const res = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                },
                body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || data.success === false) {
                const msg = data.detail || data.message || (`HTTP ${res.status}`);
                throw new Error(msg);
            }
            return data;
        },
        async updateProfile(username, newUsername) {
            if (!window.configManager || !window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            const url = window.configManager.getFullApiUrl('/api/auth/update_profile');
            return await postJson(url, { username, new_username: newUsername });
        }
        ,
        async updateEmail(newEmail, code) {
            if (!window.configManager || !window.configManager.isLoaded) {
                await window.configManager.loadConfig();
            }
            const url = window.configManager.getFullApiUrl('/api/auth/update_email');
            const token = this.getToken();
            const res = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                },
                body: JSON.stringify({ new_email: newEmail, code: code })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || data.success === false) {
                const msg = data.detail || data.message || (`HTTP ${res.status}`);
                throw new Error(msg);
            }
            return data;
        }
    };

    window.Auth = Auth;
})();


