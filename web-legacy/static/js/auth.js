'use strict';
/* Authentication — login, sudo, logout, password change */

async function refreshAuthStatus() {
  const s = await fetchJson('/api/auth/status');
  State.authEnabled  = s.auth_enabled;
  State.authenticated = s.authenticated;
  State.sudo          = s.sudo;
  State.passwordSet   = s.password_set;
  return s;
}

function showLogin(setupMode) {
  $('#login-overlay').style.display = 'flex';
  $('#app').classList.remove('ready');
  $('#login-title').textContent = setupMode ? '首次设置密码' : 'Enhanced Memory';
  $('#login-sub').textContent   = setupMode ? '请为 WebUI 设置管理密码（≥4 字符）' : '三轴长期记忆面板';
  $('#login-pw').placeholder    = setupMode ? '新密码' : '管理密码';
  $('#login-pw2').style.display = setupMode ? 'block' : 'none';
  $('#login-btn').textContent   = setupMode ? '设置并登录' : '登录';
  $('#login-pw').value  = '';
  $('#login-pw2').value = '';
  $('#login-err').textContent = '';
  setTimeout(() => $('#login-pw').focus(), 50);
}

function hideLogin() {
  $('#login-overlay').style.display = 'none';
  $('#app').classList.add('ready');
}

async function handleLoginSubmit() {
  const pw  = $('#login-pw').value;
  const pw2 = $('#login-pw2').value;
  $('#login-err').textContent = '';
  try {
    if (!State.passwordSet) {
      if (pw !== pw2)    throw { body: '两次输入不一致' };
      if (pw.length < 4) throw { body: '密码至少 4 字符' };
      await fetchJson('/api/auth/setup', { method: 'POST', body: JSON.stringify({ password: pw }) });
    } else {
      await fetchJson('/api/auth/login', { method: 'POST', body: JSON.stringify({ password: pw }) });
    }
    await boot();
  } catch (e) {
    $('#login-err').textContent = e.body || '登录失败';
  }
}

async function logout() {
  await fetchJson('/api/auth/logout', { method: 'POST' }).catch(() => {});
  await refreshAuthStatus();
  showLogin(!State.passwordSet);
}

async function toggleSudo() {
  if (State.sudo) {
    await fetchJson('/api/auth/sudo/exit', { method: 'POST' }).catch(() => {});
    State.sudo = false;
    updateSudoUI(0);
    toast('已退出 Sudo');
    return;
  }
  const pw = prompt('再次输入密码以进入 Sudo 模式：');
  if (!pw) return;
  try {
    const r = await fetchJson('/api/auth/sudo', {
      method: 'POST', body: JSON.stringify({ password: pw }),
    });
    State.sudo = true;
    updateSudoUI(r.sudo_remaining_seconds || 1800);
    toast('已进入 Sudo 模式');
  } catch (e) {
    const reason = e.body || (e.status === 401 ? '密码错误或会话失效' : `HTTP ${e.status || '?'}`);
    toast(`Sudo 失败：${reason}`, 4000);
  }
}

function updateSudoUI(remaining) {
  const btn = $('#btn-sudo');
  if (!btn) return;
  if (State.sudo && remaining > 0) {
    btn.classList.add('sudo-active');
    btn.innerHTML = `<i data-lucide="unlock" class="icon-btn-svg"></i> ${Math.floor(remaining / 60)}m`;
  } else {
    State.sudo = false;
    btn.classList.remove('sudo-active');
    btn.innerHTML = `<i data-lucide="lock" class="icon-btn-svg"></i> Sudo`;
  }
  renderIcons();
}

setInterval(async () => {
  if (!State.authenticated) return;
  const s = await refreshAuthStatus().catch(() => null);
  if (s) updateSudoUI(s.sudo_remaining_seconds || 0);
}, 30_000);

async function changePassword() {
  if (!State.sudo) { toast('请先进入 Sudo 模式'); return; }
  const oldP = $('#pw-old').value;
  const newP = $('#pw-new').value;
  if (!oldP || !newP) { toast('请填写两个字段'); return; }
  try {
    await fetchJson('/api/auth/password', {
      method: 'POST', body: JSON.stringify({ old_password: oldP, new_password: newP }),
    });
    toast('密码已更新，请重新登录');
    setTimeout(() => location.reload(), 1500);
  } catch (e) {
    toast(`修改失败：${e.body || e.status}`, 4000);
  }
}
