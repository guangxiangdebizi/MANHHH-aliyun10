window.UserModels = (function(){
  let listEl, formWrap, formTitle;
  let editingId = null;

  function qs(id){ return document.getElementById(id); }
  function token(){ try { return (window.Auth && Auth.getToken && Auth.getToken()) || ''; } catch { return ''; } }

  function apiBase(path){ return window.configManager.getFullApiUrl(path); }

  async function loadList(){
    try {
      if (!window.configManager || !window.configManager.isLoaded) {
        await window.configManager.loadConfig();
      }
      listEl.innerHTML = '<div style="color:#718096;">加载中...</div>';
      const res = await fetch(apiBase('/api/user/models'), {
        headers: { 'Authorization': `Bearer ${token()}` },
        cache: 'no-store'
      });
      const json = await res.json();
      const arr = json && json.data ? json.data : [];
      renderList(arr);
    } catch (e) {
      listEl.innerHTML = `<div style="color:#ef4444;">加载失败：${e && e.message || e}</div>`;
    }
  }

  function renderList(items){
    if (!items || !items.length){
      listEl.innerHTML = '<div style="color:#718096;">暂无自定义模型，点击“新增模型”开始配置。</div>';
      return;
    }
    const rows = items.map(m => {
      const enabled = m.enabled ? '启用' : '停用';
      const base = (m.base_url || '').replace(/^https?:\/\//,'');
      return `<div class="row" style="display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:8px;align-items:center;border-bottom:1px solid #edf2f7;padding:8px 0;">
        <div><div style="font-weight:600;">${escapeHtml(m.label||'')}</div><div style="font-size:12px;color:#718096;">${escapeHtml(m.model||'')}</div></div>
        <div style="color:#4a5568;">${escapeHtml(base||'')}</div>
        <div><span class="badge" style="padding:2px 6px;border-radius:4px;background:${m.enabled?'#dcfce7':'#fee2e2'};color:${m.enabled?'#166534':'#991b1b'};">${enabled}</span></div>
        <div style="display:flex;gap:6px;justify-content:flex-end;">
          <button class="btn btn-secondary" data-act="edit" data-id="${m.id}">编辑</button>
          <button class="btn btn-secondary" data-act="toggle" data-id="${m.id}">${m.enabled?'停用':'启用'}</button>
          <button class="btn" style="background:#ef4444;color:#fff;" data-act="del" data-id="${m.id}">删除</button>
        </div>
      </div>`;
    }).join('');
    listEl.innerHTML = `<div class="table">${rows}</div>`;
    listEl.querySelectorAll('button[data-act]').forEach(btn => {
      btn.addEventListener('click', onRowAction);
    });
  }

  function onRowAction(e){
    const id = parseInt(e.currentTarget.getAttribute('data-id'));
    const act = e.currentTarget.getAttribute('data-act');
    if (act === 'edit') return startEdit(id);
    if (act === 'del') return onDelete(id);
    if (act === 'toggle') return toggleEnabled(id);
  }

  async function startEdit(id){
    try {
      // 复用列表数据（简化：重新加载列表并挑出目标）
      const res = await fetch(apiBase('/api/user/models'), { headers: { 'Authorization': `Bearer ${token()}` }, cache: 'no-store' });
      const arr = (await res.json()).data || [];
      const it = arr.find(x => +x.id === +id);
      if (!it) return alert('未找到该模型');
      editingId = id;
      formTitle.textContent = '编辑模型';
      showForm(true);
      qs('fm_label').value = it.label || '';
      qs('fm_model').value = it.model || '';
      qs('fm_base_url').value = it.base_url || '';
      qs('fm_api_key').value = '********';
      qs('fm_temperature').value = it.temperature ?? 0.2;
      qs('fm_timeout').value = it.timeout ?? 60;
      qs('fm_system_prompt').value = it.system_prompt || '';
      qs('fm_enabled').checked = !!it.enabled;
    } catch (e) { alert('加载失败：' + (e.message||e)); }
  }

  async function onDelete(id){
    if (!confirm('确定删除该模型？')) return;
    try {
      await fetch(apiBase(`/api/user/models/${id}`), { method: 'DELETE', headers: { 'Authorization': `Bearer ${token()}` } });
      await loadList();
    } catch (e) { alert('删除失败：' + (e.message||e)); }
  }

  async function toggleEnabled(id){
    try {
      // 查现状态
      const res = await fetch(apiBase('/api/user/models'), { headers: { 'Authorization': `Bearer ${token()}` }, cache: 'no-store' });
      const arr = (await res.json()).data || [];
      const it = arr.find(x => +x.id === +id);
      if (!it) return alert('未找到该模型');
      const payload = { enabled: it.enabled ? 0 : 1 };
      await fetch(apiBase(`/api/user/models/${id}`), { method: 'PUT', headers: { 'Authorization': `Bearer ${token()}`, 'Content-Type': 'application/json' }, body: JSON.stringify(payload)});
      await loadList();
    } catch (e) { alert('更新失败：' + (e.message||e)); }
  }

  function showForm(show){ formWrap.style.display = show ? 'block' : 'none'; }

  function readForm(){
    return {
      label: qs('fm_label').value.trim(),
      model: qs('fm_model').value.trim(),
      base_url: qs('fm_base_url').value.trim(),
      api_key: qs('fm_api_key').value.trim(),
      temperature: parseFloat(qs('fm_temperature').value || '0.2'),
      timeout: parseInt(qs('fm_timeout').value || '60', 10),
      system_prompt: qs('fm_system_prompt').value,
      enabled: qs('fm_enabled').checked ? 1 : 0,
    };
  }

  function clearForm(){ editingId = null; formTitle.textContent = '新增模型'; ['fm_label','fm_model','fm_base_url','fm_api_key','fm_system_prompt'].forEach(id => qs(id).value=''); qs('fm_temperature').value='0.2'; qs('fm_timeout').value='60'; qs('fm_enabled').checked=true; }

  async function saveForm(){
    try {
      const data = readForm();
      if (!data.label || !data.model || (!editingId && !data.api_key)){
        return alert('请填写必填项：显示名称、模型名、API Key（新增时）');
      }
      const url = editingId ? apiBase(`/api/user/models/${editingId}`) : apiBase('/api/user/models');
      const method = editingId ? 'PUT' : 'POST';
      if (editingId && data.api_key === '********') delete data.api_key; // 编辑时未改key则不更新
      await fetch(url, { method, headers: { 'Authorization': `Bearer ${token()}`, 'Content-Type': 'application/json' }, body: JSON.stringify(data)});
      showForm(false);
      clearForm();
      await loadList();
      alert('保存成功');
    } catch (e) { alert('保存失败：' + (e.message||e)); }
  }

  function escapeHtml(s){ try { return (s+'').replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); } catch { return s; } }

  function bindEvents(){
    const btnAdd = qs('btnAddModel');
    const btnSave = qs('btnSaveModel');
    const btnCancel = qs('btnCancelModel');
    btnAdd && btnAdd.addEventListener('click', ()=>{ clearForm(); showForm(true); });
    btnSave && btnSave.addEventListener('click', saveForm);
    btnCancel && btnCancel.addEventListener('click', ()=>{ showForm(false); });
  }

  async function init(){
    listEl = qs('modelsList');
    formWrap = qs('modelFormWrap');
    formTitle = qs('formTitle');
    if (!listEl) return;
    if (!window.configManager || !window.configManager.isLoaded){
      await window.configManager.loadConfig();
    }
    bindEvents();
    await loadList();
  }

  return { init };
})();

