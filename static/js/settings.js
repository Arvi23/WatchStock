// Settings modal (OpenRouter key and model).
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

// ---- Settings modal ----
async function openSettings() {
    document.getElementById('settingsModal').style.display = 'flex';
    try {
        const data = await api('/api/settings');
        const keyEl = document.getElementById('settingsLlmKey');
        keyEl.value = '';
        keyEl.placeholder = data.llm_api_key_set ? 'Saved. Leave blank to keep it' : 'sk-or-...';
        document.getElementById('settingsLlmModel').value = data.llm_model || data.default_llm_model;
    } catch(e) { showToast(e.message); }
}

function closeSettings() {
    document.getElementById('settingsModal').style.display = 'none';
}

function toggleVis(inputId, btn) {
    const el = document.getElementById(inputId);
    const showing = el.type === 'text';
    el.type = showing ? 'password' : 'text';
    btn.textContent = showing ? 'SHOW' : 'HIDE';
}

async function saveSettings() {
    const llmKey   = document.getElementById('settingsLlmKey').value.trim();
    const llmModel = document.getElementById('settingsLlmModel').value.trim();
    const payload  = {};
    if (llmKey)   payload.llm_api_key = llmKey;
    if (llmModel) payload.llm_model   = llmModel;
    try {
        await api('/api/settings', { method: 'PUT', body: payload });
        await refreshLlmStatus();
        closeSettings();
        showToast('Settings saved.');
    } catch(e) { showToast(t('Could not save settings: {msg}', { msg: e.message })); }
}

document.getElementById('settingsModal').addEventListener('click', function(e) {
    if (e.target === this) closeSettings();
});
