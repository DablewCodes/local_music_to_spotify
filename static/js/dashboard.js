const AUDIO_EXTS = new Set(['mp3','flac','wav','m4a','ogg','aac','wma','opus','ape','alac','aiff','dsf']);

let selectedFiles = [];
let currentUser = null;

// ── API ───────────────────────────────────────────────────────────────────────

async function api(path, method = 'GET', body = null) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${localStorage.getItem('token')}`,
    },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(path, opts);
  if (res.status === 401) { logout(); return; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// ── Navigation ────────────────────────────────────────────────────────────────

function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + id)?.classList.add('active');
  document.querySelector(`[data-page="${id}"]`)?.classList.add('active');
  if (id === 'history') loadHistory();
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function toast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `show ${type}`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), 3500);
}

// ── Auth ──────────────────────────────────────────────────────────────────────

function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('username');
  window.location.href = '/';
}

// ── Spotify ───────────────────────────────────────────────────────────────────

async function connectSpotify() {
  try {
    const { url } = await api('/spotify/connect');
    window.location.href = url;
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function disconnectSpotify() {
  if (!confirm('Disconnect your Spotify account?')) return;
  try {
    await api('/spotify/disconnect', 'DELETE');
    toast('Spotify disconnected');
    await loadUser();
    renderSpotifyBanner();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ── User ──────────────────────────────────────────────────────────────────────

async function loadUser() {
  try {
    currentUser = await api('/auth/me');
    document.getElementById('sidebarUsername').textContent = currentUser.username;
    document.getElementById('sidebarAvatar').textContent = currentUser.username[0].toUpperCase();
  } catch { logout(); }
}

function renderSpotifyBanner() {
  const banner = document.getElementById('spotifyBanner');
  if (!currentUser) return;
  if (currentUser.spotify_connected) {
    banner.classList.add('connected');
    banner.innerHTML = `
      <div class="spotify-banner-left">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
        </svg>
        <div>
          <div class="title">Spotify connected</div>
          <div class="desc">Your account is linked and ready to use</div>
        </div>
      </div>
      <button class="btn btn-danger btn-sm" onclick="disconnectSpotify()">Disconnect</button>
    `;
  } else {
    banner.classList.remove('connected');
    banner.innerHTML = `
      <div class="spotify-banner-left">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
        </svg>
        <div>
          <div class="title">Connect Spotify</div>
          <div class="desc">Link your Spotify account to create playlists</div>
        </div>
      </div>
      <button class="btn btn-primary btn-sm" style="width:auto" onclick="connectSpotify()">Connect</button>
    `;
  }
}

// ── File selection ────────────────────────────────────────────────────────────

function handleFiles(fileList) {
  selectedFiles = Array.from(fileList).filter(f => {
    const ext = f.name.split('.').pop().toLowerCase();
    return AUDIO_EXTS.has(ext);
  });

  const zone = document.getElementById('dropZone');
  const countEl = document.getElementById('fileCount');

  if (selectedFiles.length > 0) {
    zone.classList.add('has-files');
    countEl.textContent = `${selectedFiles.length} audio file${selectedFiles.length !== 1 ? 's' : ''} selected`;
  } else {
    zone.classList.remove('has-files');
    countEl.textContent = '';
    toast('No audio files found in the selected folder', 'error');
  }

  document.getElementById('resultBox').classList.remove('show');
}

// ── Create playlist ───────────────────────────────────────────────────────────

async function createPlaylist() {
  if (!currentUser?.spotify_connected) {
    toast('Connect your Spotify account first', 'error');
    return;
  }
  if (!selectedFiles.length) {
    toast('Select a folder with audio files first', 'error');
    return;
  }

  const name = document.getElementById('playlistName').value.trim();
  if (!name) {
    toast('Enter a playlist name', 'error');
    document.getElementById('playlistName').focus();
    return;
  }

  const btn = document.getElementById('createBtn');
  const progressWrap = document.getElementById('progressWrap');
  const progressBar = document.getElementById('progressBar');
  const resultBox = document.getElementById('resultBox');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Creating…';
  progressWrap.style.display = 'block';
  resultBox.classList.remove('show');

  // Animate progress bar while waiting
  let pct = 0;
  const fakeProgress = setInterval(() => {
    pct = Math.min(pct + Math.random() * 4, 85);
    progressBar.style.width = pct + '%';
  }, 200);

  try {
    const filenames = selectedFiles.map(f => f.name);
    const result = await api('/playlists/create', 'POST', { name, filenames });

    clearInterval(fakeProgress);
    progressBar.style.width = '100%';

    // Render result
    resultBox.innerHTML = `
      <div class="result-stats">
        <div class="result-stat found">
          <span class="num">${result.found}</span> tracks added
        </div>
        <div class="result-stat missed">
          <span class="num">${result.not_found}</span> not found
        </div>
      </div>
      <a href="${result.playlist_url}" target="_blank" class="result-link">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
        </svg>
        Open in Spotify
      </a>
      ${result.not_found_tracks?.length ? `
        <div class="missed-list">
          <p style="font-size:0.8rem;color:var(--muted);margin-bottom:6px;">Not found on Spotify:</p>
          ${result.not_found_tracks.map(t => `<span>${escHtml(t)}</span>`).join('')}
        </div>
      ` : ''}
    `;
    resultBox.classList.add('show');
    toast(`Playlist "${name}" created!`);

    // Reset
    selectedFiles = [];
    document.getElementById('dropZone').classList.remove('has-files');
    document.getElementById('fileCount').textContent = '';
    document.getElementById('dirInput').value = '';

  } catch (e) {
    clearInterval(fakeProgress);
    progressBar.style.width = '0%';
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Create Playlist';
    setTimeout(() => { progressWrap.style.display = 'none'; progressBar.style.width = '0%'; }, 600);
  }
}

// ── History ───────────────────────────────────────────────────────────────────

async function loadHistory() {
  const list = document.getElementById('playlistHistory');
  list.innerHTML = '<div style="color:var(--muted);font-size:0.9rem;padding:16px">Loading…</div>';

  try {
    const playlists = await api('/playlists');
    if (!playlists.length) {
      list.innerHTML = `
        <div class="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
          </svg>
          <p>No playlists created yet.<br>Go to Create to get started.</p>
        </div>`;
      return;
    }

    list.innerHTML = playlists.map(p => `
      <div class="playlist-item">
        <div class="pl-info">
          <div class="pl-name">${escHtml(p.name)}</div>
          <div class="pl-meta">${formatDate(p.created_at)}</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <span class="badge badge-green">${p.track_count} tracks</span>
          ${p.not_found_count > 0 ? `<span class="badge badge-red">${p.not_found_count} missed</span>` : ''}
          <a href="https://open.spotify.com/playlist/${p.spotify_playlist_id}" target="_blank"
             class="btn btn-secondary btn-sm" style="width:auto">Open</a>
        </div>
      </div>
    `).join('');

    // update stats
    document.getElementById('statPlaylists').textContent = playlists.length;
    document.getElementById('statTracks').textContent = playlists.reduce((s, p) => s + p.track_count, 0);
  } catch (e) {
    list.innerHTML = `<div class="empty-state"><p>${escHtml(e.message)}</p></div>`;
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatDate(str) {
  const d = new Date(str + (str.endsWith('Z') ? '' : 'Z'));
  return d.toLocaleDateString(undefined, { year:'numeric', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
}

// ── Init ──────────────────────────────────────────────────────────────────────

(async () => {
  if (!localStorage.getItem('token')) { window.location.href = '/'; return; }

  await loadUser();
  renderSpotifyBanner();

  // Handle spotify callback params
  const params = new URLSearchParams(location.search);
  if (params.get('spotify') === 'connected') {
    toast('Spotify connected successfully!');
    currentUser.spotify_connected = true;
    renderSpotifyBanner();
    history.replaceState({}, '', '/dashboard');
  } else if (params.get('spotify') === 'error') {
    toast('Failed to connect Spotify', 'error');
    history.replaceState({}, '', '/dashboard');
  }

  showPage('create');
})();
