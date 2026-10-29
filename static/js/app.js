// ── State ──────────────────────────────────────────────────────────────────────
let authToken = localStorage.getItem('aa_token');
let currentUser = null;
let latestCopilotMatches = [];
let latestPeopleConnections = [];
let latestKnowledgeGraph = null;
try { latestCopilotMatches = JSON.parse(localStorage.getItem('rizoma_latest_matches') || '[]'); } catch { latestCopilotMatches = []; }
try { latestKnowledgeGraph = JSON.parse(localStorage.getItem('rizoma_latest_graph') || 'null'); } catch { latestKnowledgeGraph = null; }
let pendingApplyProjectId = null;
let currentFeedFilter = 'all';
let latestSearchResults = [];

// ── Base URL (supports sub-path deployment, e.g. /rizoma/) ─────────────
const BASE_URL = (() => {
  const src = document.currentScript?.src;
  if (!src) return '';
  return new URL(src).pathname.replace(/\/static\/js\/app\.js$/, '');
})();

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, '&#96;');
}

// Sin conexión, fetch falla con un mensaje en inglés ("Failed to fetch").
async function pedir(url, opts) {
  try {
    return await fetch(BASE_URL + url, opts);
  } catch {
    throw new Error('No pude conectar con Rizoma. Revisá tu conexión y probá de nuevo.');
  }
}

// Un 401 fuera de /auth/ es una sesión vencida: vuelve al ingreso con un aviso.
// En /auth/ (ingreso, registro) no: el error ("Email o contraseña incorrectos")
// tiene que llegar a la pantalla.
function sesionVencida(r, url) {
  if (r.status !== 401 || url.startsWith('/auth/')) return false;
  const habiaSesion = Boolean(authToken);
  logout();
  if (habiaSesion) showAuthError('Tu sesión venció. Ingresá de nuevo.');
  return true;
}

function apiErrorMessage(data, status) {
  const detail = data && data.detail;
  if (!detail) return `Error ${status}`;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(d => (d && typeof d === 'object') ? (d.msg || JSON.stringify(d)) : String(d)).join(' · ');
  }
  return typeof detail === 'object' ? (detail.msg || JSON.stringify(detail)) : String(detail);
}

function safeUrl(value) {
  const url = String(value || '').trim();
  if (!url) return '';
  try {
    const parsed = new URL(url, location.origin);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '';
  } catch {
    return '';
  }
}

// ── API helper ─────────────────────────────────────────────────────────────────
async function api(method, url, body = null) {
  const opts = { method, headers: {} };
  if (authToken) opts.headers['Authorization'] = `Bearer ${authToken}`;
  if (body !== null) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const r = await pedir(url, opts);
  if (sesionVencida(r, url)) return null;
  const data = await r.json().catch(() => ({}));
  if (r.status === 428) abrirAvisoPrivacidad();
  if (!r.ok) throw new Error(apiErrorMessage(data, r.status));
  return data;
}


async function apiForm(url, formData) {
  const opts = { method: 'POST', headers: {} };
  if (authToken) opts.headers['Authorization'] = `Bearer ${authToken}`;
  opts.body = formData;
  const r = await pedir(url, opts);
  if (sesionVencida(r, url)) return null;
  const data = await r.json().catch(() => ({}));
  if (r.status === 428) abrirAvisoPrivacidad();
  if (!r.ok) throw new Error(apiErrorMessage(data, r.status));
  return data;
}

// ── Privacidad ────────────────────────────────────────────────────────────────
// Debe coincidir con NOTICE_VERSION (services/privacy_notice.py). Si no
// coincide, el registro no deja constancia y el aviso se pide al ingresar.
const AVISO_PRIVACIDAD_VERSION = '2026-10-25.2';
let avisoPrivacidadVersion = AVISO_PRIVACIDAD_VERSION;

// Lo que esta aplicación deja en el navegador y se borra al salir o al cambiar de cuenta.
function limpiarDatosLocales() {
  const claves = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k && (k === 'aa_token' || k.startsWith('rizoma_'))) claves.push(k);
  }
  claves.forEach(k => localStorage.removeItem(k));
  latestCopilotMatches = [];
  latestKnowledgeGraph = null;
  latestPeopleConnections = [];
  for (const k of Object.keys(peopleExplicaciones)) delete peopleExplicaciones[k];
}

function abrirAvisoPrivacidad() {
  const el = document.getElementById('avisoOverlay');
  if (!el || !currentUser) return;
  document.getElementById('avisoVersion').textContent = avisoPrivacidadVersion;
  document.getElementById('avisoLeido').checked = false;
  document.getElementById('avisoConfirmar').disabled = true;
  el.classList.add('open');
}

function cerrarAvisoPrivacidad() {
  document.getElementById('avisoOverlay')?.classList.remove('open');
}

async function verificarAvisoPrivacidad() {
  try {
    const estado = await api('GET', '/api/privacidad/estado');
    if (!estado) return;
    avisoPrivacidadVersion = estado.version;
    const badge = document.getElementById('misDatosAviso');
    if (badge) {
      badge.textContent = estado.leida ? `Aviso ${estado.version} leído` : 'Aviso pendiente';
      badge.className = 'badge ' + (estado.leida ? 'green' : 'alerta');
    }
    if (!estado.leida) abrirAvisoPrivacidad();
  } catch { /* si falla, las funciones con IA lo vuelven a pedir */ }
}

async function confirmarAvisoPrivacidad() {
  try {
    await api('POST', '/api/privacidad/lectura', { version: avisoPrivacidadVersion });
    cerrarAvisoPrivacidad();
    toast('Lectura del aviso registrada.', 'success');
    verificarAvisoPrivacidad();
  } catch (e) {
    toast('No pude registrar la lectura: ' + e.message, 'warn');
  }
}

async function pedirPrivacidad(tipo) {
  const textos = {
    acceso: '¿Pedir una copia de lo que Rizoma guarda de vos? Una persona la prepara, la revisa y te la envía por correo.',
    supresion: '¿Pedir la baja de tu cuenta? Una persona va a contactarte para confirmarla antes de borrar tus datos. La baja no se puede deshacer.',
  };
  if (!confirm(textos[tipo])) return;
  const detalle = prompt('Si querés, agregá un detalle para el pedido (opcional):', '') || '';
  try {
    await api('POST', '/api/privacidad/solicitudes', { tipo, detalle });
    toast('Pedido registrado. Te vamos a contactar por correo.', 'success');
    cargarSolicitudesPrivacidad();
  } catch (e) {
    toast('No pude registrar el pedido: ' + e.message, 'warn');
  }
}

async function cargarSolicitudesPrivacidad() {
  const el = document.getElementById('misSolicitudes');
  if (!el) return;
  try {
    const items = await api('GET', '/api/privacidad/solicitudes') || [];
    const nombres = { acceso: 'Copia de mis datos', rectificacion: 'Corrección', supresion: 'Baja de la cuenta', otra: 'Otro pedido' };
    const estados = { pendiente: 'pendiente', en_curso: 'en curso', resuelta: 'resuelto', rechazada: 'no corresponde' };
    el.innerHTML = items.length
      ? items.map(s => `<p style="font-size:12px;margin:4px 0">${escapeHtml(nombres[s.tipo] || s.tipo)} · ${new Date(s.created_at).toLocaleDateString('es-AR')} · <strong>${escapeHtml(estados[s.estado] || s.estado)}</strong>${s.resolucion ? ' · ' + escapeHtml(s.resolucion) : ''}</p>`).join('')
      : '';
  } catch { el.innerHTML = ''; }
}

// Qué ven los demás de mí (services/visibilidad.py).
function renderVisibilidad() {
  if (!currentUser) return;
  const v = currentUser.visibilidad || {};
  const fijar = (id, prop, valor) => { const el = document.getElementById(id); if (el) el[prop] = valor; };
  fijar('visNombre', 'value', v.nombre || 'abreviado');
  fijar('visNombre', 'disabled', currentUser.role === 'org');
  fijar('visBio', 'value', v.bio || 'conjunto');
  fijar('visSugerencias', 'checked', v.sugerencias !== false);
  fijar('visBusqueda', 'checked', v.busqueda !== false);
  fijar('visInstitucion', 'checked', v.institucion !== false);
  fijar('visComoTeVen', 'textContent', currentUser.nombre_para_otros || currentUser.name || '—');
}

async function guardarVisibilidad(cambio) {
  try {
    const u = await api('PUT', '/api/users/me/visibilidad', cambio);
    if (!u) return;
    currentUser = u;
    toast('Listo: así te ven desde ahora.', 'success');
  } catch (e) {
    toast('No pude guardar la preferencia: ' + e.message, 'warn');
  } finally {
    renderVisibilidad();
  }
}

// ── Auth ───────────────────────────────────────────────────────────────────────
function switchAuthTab(tab) {
  document.querySelectorAll('.auth-tab').forEach((t, i) => t.classList.toggle('active', (i === 0) === (tab === 'login')));
  document.getElementById('loginForm').style.display = tab === 'login' ? '' : 'none';
  document.getElementById('registerForm').style.display = tab === 'register' ? '' : 'none';
  document.getElementById('authError').classList.remove('show');
}

function showAuthError(msg) {
  const el = document.getElementById('authError');
  el.textContent = msg;
  el.classList.add('show');
}

async function doLogin() {
  const email = document.getElementById('loginEmail').value.trim();
  const pass = document.getElementById('loginPass').value;
  if (!email || !pass) { showAuthError('Completá email y contraseña'); return; }
  try {
    const data = await api('POST', '/auth/login', { email, password: pass });
    if (!data) return;
    limpiarDatosLocales();
    authToken = data.access_token;
    localStorage.setItem('aa_token', authToken);
    await bootApp();
  } catch (e) {
    showAuthError(e.message);
  }
}

async function doRegister() {
  const name = document.getElementById('regName').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const pass = document.getElementById('regPass').value;
  const role = document.getElementById('regRole').value;
  const inst = document.getElementById('regInst').value.trim();
  if (!name || !email || !pass) { showAuthError('Completá todos los campos'); return; }
  if (!document.getElementById('regAviso').checked) { showAuthError('Para crear la cuenta, confirmá que leíste el aviso de privacidad.'); return; }
  try {
    const data = await api('POST', '/auth/register', { name, email, password: pass, role, institution: inst, aviso_version: AVISO_PRIVACIDAD_VERSION });
    if (!data) return;
    limpiarDatosLocales();
    authToken = data.access_token;
    localStorage.setItem('aa_token', authToken);
    await bootApp();
  } catch (e) {
    showAuthError(e.message);
  }
}

function logout() {
  authToken = null;
  currentUser = null;
  // No solo el token: también el grafo y las coincidencias guardadas para mostrar
  // rápido, para que no queden en una computadora compartida.
  limpiarDatosLocales();
  cerrarAvisoPrivacidad();
  document.getElementById('authOverlay').style.display = 'flex';
}

// ── Boot ───────────────────────────────────────────────────────────────────────
async function bootApp() {
  if (!authToken) { document.getElementById('authOverlay').style.display = 'flex'; return; }
  try {
    currentUser = await api('GET', '/api/users/me');
    if (!currentUser) return;
    document.getElementById('authOverlay').style.display = 'none';
    const navObs = document.getElementById('navObservatorio');
    if (navObs) navObs.style.display = ["teacher", "org", "admin"].includes(currentUser.role) ? '' : 'none';
    renderSidebar();
    renderYourRizoma();
    loadFeed();
    loadStats();
    const tab = tabFromPath();
    showTab(tab, document.querySelector(`[data-nav="${tab === 'proyectoDetalle' ? 'proyectos' : tab}"]`), false);
    verificarAvisoPrivacidad();
  } catch {
    logout();
  }
}

// ── Sidebar ────────────────────────────────────────────────────────────────────
function initials(name) {
  return (name || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
}

function renderSidebar() {
  const u = currentUser;
  document.getElementById('sidebarName').textContent = u.name;
  document.getElementById('sidebarRole').textContent = `${roleLabel(u.role)} · ${u.institution || 'Sin institución'}`;
  let conjuntoEl = document.getElementById('sidebarConjunto');
  if (!conjuntoEl) {
    conjuntoEl = document.createElement('span');
    conjuntoEl.id = 'sidebarConjunto';
    document.getElementById('sidebarRole').after(conjuntoEl);
  }
  conjuntoEl.className = `badge conjunto conjunto-${u.conjunto || 'general'}`;
  conjuntoEl.textContent = u.conjunto_etiqueta || 'Red general';
  conjuntoEl.title = 'Las sugerencias y el grafo se calculan solo dentro de este conjunto de perfiles.';
  document.getElementById('sidebarAvatar').textContent = initials(u.name);
  document.getElementById('composerAvatar').textContent = initials(u.name);
  document.getElementById('heroAvatar').textContent = initials(u.name);
  document.getElementById('kpiCreds').textContent = u.credentials_count;
  document.getElementById('kpiProjects').textContent = u.projects_count;
  document.getElementById('kpiConns').textContent = u.connections_count;
  document.getElementById('kpiComp').textContent = u.profile_completeness + '%';

  const pct = u.profile_completeness;
  document.getElementById('progPct').textContent = pct + '%';
  document.getElementById('progFill').style.width = pct + '%';

  const hints = [];
  if (!u.bio) hints.push('agregar bio');
  if (!u.institution) hints.push('agregar institución');
  if (!u.can_offer || u.can_offer.length === 0) hints.push('contar qué podés aportar');
  if (!u.wants_to_learn || u.wants_to_learn.length === 0) hints.push('contar qué querés aprender');
  if (!u.ai_summary) hints.push('subir CV o trayectoria para generar el grafo');
  document.getElementById('progHints').textContent = hints.length ? 'Falta: ' + hints.join(' · ') : '¡Perfil completo!';

  // Notif count
  if (u.unread_messages > 0) {
    const el = document.getElementById('notifCount');
    el.textContent = u.unread_messages;
    el.style.display = '';
  }
  if (u.unread_notifications > 0) {
    const el = document.getElementById('matchNotifCount');
    el.textContent = u.unread_notifications;
    el.style.display = '';
  }

  // Profile tab
  document.getElementById('heroName').textContent = u.name;
  document.getElementById('heroBio').textContent = u.bio || 'Sin descripción todavía. Editá tus datos base para agregar contexto.';
  document.getElementById('heroInst').textContent = u.institution || '—';
  if (u.ai_summary) document.getElementById('heroSummary').textContent = u.ai_summary;
  const tagsEl = document.getElementById('heroTags');
  tagsEl.innerHTML = (u.ai_tags || []).map(t => `<span class="chip">${escapeHtml(t)}</span>`).join('');
}

function roleLabel(role) {
  return { student: 'Estudiante', teacher: 'Docente', org: 'Organización', admin: 'Admin' }[role] || role;
}

// ── Stats ──────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const projects = await api('GET', '/api/projects?status=all');
    document.getElementById('statProjects').textContent = projects?.length || '—';
    const heroMetric = document.getElementById('heroMetricProjects');
    if (heroMetric) heroMetric.textContent = projects?.filter(p => p.status === 'open').length || projects?.length || '—';
  } catch {}
}

// ── Bitácora ───────────────────────────────────────────────────────────────────────
async function loadFeed(filter) {
  currentFeedFilter = filter || 'all';
  const el = document.getElementById('mainFeed');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const items = await api('GET', `/api/feed?filter_type=${currentFeedFilter}`);
    if (!items || items.length === 0) {
      el.innerHTML = '<p style="color:var(--muted);font-size:13px">La bitácora está vacía. Sumá la primera señal de conocimiento, búsqueda o evidencia.</p>';
      return;
    }
    el.innerHTML = items.map(renderFeedItem).join('');
  } catch (e) {
    el.innerHTML = `<p style="color:var(--muted);font-size:13px">Error cargando la bitácora: ${escapeHtml(e.message)}</p>`;
  }
}

function typeLabel(type) {
  return { opportunity: 'Territorio', advance: 'Aprendizaje', portfolio: 'Experiencia', mentorship: 'Acompañamiento', project: 'Proyecto', credential: 'Evidencia' }[type] || type;
}

function typeBadgeClass(type) {
  return { opportunity: 'green', advance: 'blue', mentorship: 'green', portfolio: 'amber' }[type] || '';
}

function renderFeedItem(item) {
  const badgeCls = typeBadgeClass(item.type);
  const timeAgo = formatDate(item.created_at);
  const tags = item.tags || [];
  return `
    <article class="card" data-type="${item.type}">
      <div class="post-author">
        <div class="avatar">${escapeHtml(initials(item.user_name))}</div>
        <div><strong>${escapeHtml(item.user_name)}</strong><span>${escapeHtml([roleLabel(item.user_role), item.user_institution].filter(Boolean).join(' · '))} · señal ${escapeHtml(timeAgo)}</span></div>
        <span class="badge ${badgeCls}">${typeLabel(item.type)}</span>
      </div>
      <div class="post-body">${escapeHtml(item.content)}</div>
      ${item.credential_generated ? `
        <div class="post-proof"><strong>Evidencia posible</strong><span>${escapeHtml(item.credential_generated)}</span></div>
      ` : ''}
      ${tags.length ? `
        <div class="chips">${tags.map(t => `<span class="chip">${escapeHtml(t)}</span>`).join('')}</div>
      ` : ''}
      <div class="social-actions">
        <button onclick="toggleBtn(this,'Señal reconocida','Reconocimiento quitado')">Reconocer evidencia</button>
        <button onclick="showTab('rizoma',document.querySelector('[data-nav=rizoma]'))">Buscar conexión</button>
        <button onclick="showTab('mensajes',document.querySelector('[data-nav=mensajes]'))">Conversar</button>
      </div>
    </article>`;
}

function filterFeed(type, btn) {
  document.querySelectorAll('.fpill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  loadFeed(type);
}

// ── Projects ───────────────────────────────────────────────────────────────────
async function loadProjects() {
  const el = document.getElementById('projectsFeed');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const projects = await api('GET', '/api/projects');
    if (!projects || projects.length === 0) {
      el.innerHTML = '<p style="color:var(--muted);font-size:13px">No hay proyectos abiertos en este momento.</p>';
      return;
    }
    el.innerHTML = `<div class="grid-2">${projects.map(renderProjectCard).join('')}</div>`;
  } catch (e) {
    el.innerHTML = `<p style="color:var(--muted)">Error: ${escapeHtml(e.message)}</p>`;
  }
}

function renderProjectCard(p) {
  const coverUrl = safeUrl(p.cover_url);
  const cover = coverUrl ? `<img class="cover" src="${escapeAttr(coverUrl)}" alt="">` : '';
  const needs = p.needs_skills && p.needs_skills.length ? p.needs_skills : (p.roles_available || []);
  const learns = p.teaches_skills || [];
  return `
    <article class="card">
      ${cover}
      <div class="card-top"><h4>${escapeHtml(p.title)}</h4><span class="badge green">Abierto</span></div>
      <p>${escapeHtml((p.description || '').slice(0, 170))}...</p>
      <div class="post-proof"><strong>El proyecto necesita</strong><span>${needs.length ? needs.map(escapeHtml).join(' · ') : 'colaboradores con interés real'}</span></div>
      <div class="post-proof"><strong>Podés aprender</strong><span>${learns.length ? learns.map(escapeHtml).join(' · ') : 'aprendizajes a definir con el equipo'}</span></div>
      <div class="chips">
        ${p.area ? `<span class="chip">${escapeHtml(p.area)}</span>` : ''}
        ${p.modality ? `<span class="chip">${escapeHtml(p.modality)}</span>` : ''}
        ${p.accepts_learners ? `<span class="chip">acepta personas aprendiendo</span>` : ''}
        ${p.offers_mentorship ? `<span class="chip">ofrece mentoría</span>` : ''}
      </div>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        <button class="btn" onclick="openApplyById('${escapeAttr(p.id)}')">Quiero explorar</button>
        <button class="btn secondary" onclick="showTab('rizoma',document.querySelector('[data-nav=rizoma]'))">Ver grafos afines</button>
      </div>
    </article>`;
}

// ── Apply ──────────────────────────────────────────────────────────────────────
function openApply(projectId, title, institution, credTitle) {
  pendingApplyProjectId = projectId;
  document.getElementById('applyProjectPreview').innerHTML = `
    <strong>${escapeHtml(title)}</strong>
    <span>${escapeHtml(institution)}</span>
    ${credTitle ? `<span style="margin-top:6px;display:block;font-size:11px;color:var(--primary);font-weight:700">Genera: ${escapeHtml(credTitle)}</span>` : ''}`;
  document.getElementById('applyMsg').value = '';
  document.getElementById('applyResult').style.display = 'none';
  document.getElementById('applyBtn').disabled = false;
  document.getElementById('applyOverlay').classList.add('open');
}

async function confirmApply() {
  if (!pendingApplyProjectId) return;
  const btn = document.getElementById('applyBtn');
  const msg = document.getElementById('applyMsg').value.trim();
  btn.disabled = true;
  btn.textContent = 'Enviando…';
  try {
    const result = await api('POST', `/api/projects/${pendingApplyProjectId}/apply`, { message: msg });
    const resEl = document.getElementById('applyResult');
    resEl.style.display = '';
    resEl.innerHTML = `<strong>Interés enviado.</strong> El equipo recibió tu mensaje. La credencial queda para después: solo se valida si la experiencia efectivamente ocurre.`;
    btn.textContent = '¡Listo!';
    toast('Interés enviado. Si hay intercambio, podrán avanzar a conversación.', 'success');
    currentUser = await api('GET', '/api/users/me');
    renderSidebar();
    if (document.getElementById('credenciales').classList.contains('active')) loadCredentials();
  } catch (e) {
    toast(e.message, 'warn');
    btn.disabled = false;
    btn.textContent = 'Abrir conversación';
  }
}

// ── Credentials ────────────────────────────────────────────────────────────────
async function loadCredentials() {
  const el = document.getElementById('credsFeed');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const creds = await api('GET', '/api/credentials');
    if (!creds || creds.length === 0) {
      el.innerHTML = '<div class="safe-box">Aún no tenés credenciales. Primero vinculá tu grafo y construí una evidencia validable.</div>';
      return;
    }
    el.innerHTML = creds.map(renderCredential).join('');

    const profileEl = document.getElementById('profileCredsFeed');
    if (profileEl) profileEl.innerHTML = creds.map(renderCredential).join('') || '<p style="color:var(--muted);font-size:13px">Sin credenciales aún.</p>';
  } catch (e) {
    el.innerHTML = `<p style="color:var(--muted)">Error: ${escapeHtml(e.message)}</p>`;
  }
}

function renderCredential(c) {
  const typeMap = { extension: 'Extensión', portfolio: 'Portfolio', mentorship: 'Mentoría', course: 'Curso', application: 'Exploración' };
  const badgeCls = c.verified ? 'green' : 'amber';
  const badgeText = c.verified ? 'Verificada' : 'Pendiente';
  return `
    <div class="credential">
      <div style="display:flex;justify-content:space-between;align-items:start;gap:10px">
        <strong>${escapeHtml(c.title)}</strong>
        <span class="badge ${badgeCls}">${badgeText}</span>
      </div>
      <span>${escapeHtml(c.issuer_name || 'Rizoma')}${c.hours ? ` · ${escapeHtml(c.hours)} horas` : ''}</span>
      ${c.description ? `<p style="font-size:12px;color:var(--muted);margin:6px 0 0;line-height:1.4">${escapeHtml(c.description)}</p>` : ''}
      ${c.tags && c.tags.length ? `<div class="chips">${c.tags.map(t => `<span class="chip">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
      ${c.verified ? `<button class="btn secondary" style="margin-top:10px;font-size:12px;padding:7px 10px" onclick="shareCredential('${escapeAttr(c.id)}')">Compartir credencial</button>` : ''}
    </div>`;
}

function shareCredential(id) {
  const url = `${location.origin}${BASE_URL}/credenciales/${id}`;
  navigator.clipboard?.writeText(url).catch(() => {});
  toast('Enlace de credencial copiado.', 'success');
}

// Cada conjunto de perfiles lee sus propias corridas guardadas: la de prueba es
// la de la ponencia (Tablas 4 y demanda/puentes), sin recalcular nada.
const ALCANCE_POR_CONJUNTO = {
  prueba: '50 perfiles ficticios (demo.unq)',
  demostracion: '16 perfiles de demostración (demo.vivo)',
  general: 'red completa',
};
function alcanceActual() {
  return encodeURIComponent(ALCANCE_POR_CONJUNTO[currentUser?.conjunto] || 'red completa');
}

// Cifras del conjunto (personas, temas, vínculos) leídas del grafo, no escritas a mano.
async function cargarMetricasConjunto() {
  try {
    const r = await api('GET', '/api/users/red-completa');
    const resumen = r?.resumen || {};
    document.querySelectorAll('[data-metrica]').forEach(el => {
      if (resumen[el.dataset.metrica] !== undefined) el.textContent = resumen[el.dataset.metrica];
    });
  } catch { /* las cifras quedan en “…” */ }
}

// ── Actividades emergentes ─────────────────────────────────────────────────────
async function loadActividades() {
  const el = document.getElementById('actividadesBody');
  try {
    const items = await api('GET', `/api/actividades-emergentes?alcance=${alcanceActual()}`);
    if (!items || items.length === 0) {
      el.innerHTML = '<p style="color:var(--muted);font-size:13px">Todavía no se calcularon actividades emergentes.</p>';
      return;
    }
    el.innerHTML = items.map(a => `
      <div class="card" data-act="${escapeAttr(a.id)}">
        <div class="card-top"><h4>${escapeHtml(a.titulo)}</h4>
          <span class="badge ${a.estabilidad >= 0.8 ? 'green' : 'blue'}" title="Fracción de cálculos, con distintas particiones del grafo, en que reaparece">Estabilidad ${Math.round(a.estabilidad * 100)}%</span></div>
        <p style="font-size:13px">${escapeHtml(a.descripcion)}</p>
        <p style="font-size:12px;color:var(--muted)">${a.temas.map(t => `<span class="chip">${escapeHtml(t)}</span>`).join(' ')}</p>
        <p style="font-size:12px;color:var(--muted)">Cruza: ${escapeHtml(a.areas[0])} ↔ ${escapeHtml(a.areas[1])} · ${a.n_personas} personas · demanda ${a.demanda} · oferta ${a.oferta}</p>
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="btn secondary" style="font-size:12px" onclick="valorarActividad('${escapeAttr(a.id)}','useful',this)">Útil</button>
          <button class="btn secondary" style="font-size:12px" onclick="valorarActividad('${escapeAttr(a.id)}','not_useful',this)">No útil</button>
          <button class="btn secondary" style="font-size:12px" onclick="armarEquipo('${escapeAttr(a.id)}',this)">Armar equipo</button>
        </div>
        <div class="equipo" style="margin-top:8px"></div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = '';
  }
}

async function valorarActividad(id, outcome, btn) {
  try {
    await api('POST', '/api/users/match-outcomes', { target_type: 'activity', target_id: id, outcome, source: 'actividades' });
    btn.parentElement.innerHTML = `<span class="badge green">Gracias: registrada como ${outcome === 'useful' ? 'útil' : 'no útil'}</span>`;
  } catch (e) {
    toast('No se pudo registrar la valoración.', 'error');
  }
}

async function armarEquipo(id, btn) {
  const out = btn.closest('.card').querySelector('.equipo');
  out.innerHTML = '<div class="spinner"></div>';
  try {
    const e = await api('GET', `/api/red/equipo/${encodeURIComponent(id)}`);
    out.innerHTML = `<p style="font-size:12px;color:var(--muted);margin:4px 0">Equipo sugerido · ${e.areas_distintas} áreas distintas${e.temas_sin_cubrir.length ? ' · sin cubrir: ' + e.temas_sin_cubrir.map(escapeHtml).join(', ') : ''}</p>` +
      e.miembros.map(m => `<p style="font-size:13px;margin:4px 0"><strong>${escapeHtml(m.persona)}</strong> — ${escapeHtml(m.rol)}</p>`).join('');
  } catch (err) {
    out.innerHTML = `<p style="color:var(--muted);font-size:13px">${escapeHtml(err.message)}</p>`;
  }
}

async function loadDemanda() {
  const el = document.getElementById('demandaBody');
  try {
    const items = await api('GET', `/api/red/demanda-latente?alcance=${alcanceActual()}`);
    if (!items || !items.length) { el.innerHTML = '<p style="color:var(--muted);font-size:13px">No hay demanda formativa latente para este conjunto: ningún tema que al menos dos personas quieran aprender y nadie ofrezca (o todavía no se calculó).</p>'; return; }
    el.innerHTML = items.map(i => `
      <div class="card">
        <div class="card-top"><h4>${escapeHtml(i.titulo)}</h4><span class="badge blue">${i.datos.demanda} quieren · ${i.datos.oferta} ofrecen</span></div>
        <p style="font-size:13px">${escapeHtml(i.descripcion)}</p>
        <p style="font-size:12px;color:var(--muted)">Tema: ${escapeHtml(i.datos.tema)} · demandan desde: ${(i.datos.areas_demandantes || []).map(escapeHtml).join(' | ')}</p>
      </div>`).join('');
  } catch (e) { el.innerHTML = ''; }
}

async function loadPuentes() {
  const el = document.getElementById('puentesBody');
  try {
    const r = await api('GET', `/api/red/puentes?alcance=${alcanceActual()}`);
    if (!r || !r.datos) { el.innerHTML = '<p style="color:var(--muted);font-size:13px">Todavía no se calculó.</p>'; return; }
    const pct = v => (v * 100).toFixed(1) + '%';
    const personas = r.datos.personas.map(p => `<p style="font-size:13px;margin:4px 0"><strong>${escapeHtml(p.persona)}</strong> — perdería ${pct(p.perdida_alcance)}${p.punto_de_articulacion ? ' · punto de articulación' : ''}<br><span style="color:var(--muted);font-size:12px">Conecta: ${(p.areas_que_conecta || []).map(escapeHtml).join(' | ') || '—'}</span></p>`).join('');
    const temas = r.datos.temas.map(t => `<p style="font-size:13px;margin:4px 0"><strong>${escapeHtml(t.tema)}</strong> — perdería ${pct(t.perdida_alcance)} · ${t.personas} personas · ${t.n_areas} áreas</p>`).join('');
    el.innerHTML = `<div class="card"><div class="card-top"><h4>Personas puente</h4></div>${personas}</div><div class="card"><div class="card-top"><h4>Temas puente</h4></div>${temas}</div>`;
  } catch (e) { el.innerHTML = ''; }
}

async function preguntarRed() {
  const q = document.getElementById('preguntaInput').value.trim();
  const out = document.getElementById('preguntaOut');
  if (q.length < 3) { toast('Escribí una pregunta.', 'error'); return; }
  out.innerHTML = '<div class="spinner"></div>';
  try {
    const r = await api('POST', '/api/red/preguntar', { pregunta: q });
    out.innerHTML = `<p style="font-size:13px">${escapeHtml(r.respuesta)}</p>` +
      (r.personas || []).map(p => `<p style="font-size:13px;margin:6px 0"><strong>${escapeHtml(p.nombre)}</strong>${p.institucion ? ' · ' + escapeHtml(p.institucion) : ''}<br><span style="color:var(--muted)">${escapeHtml(p.motivo)} (${escapeHtml(p.detalle)})</span></p>`).join('');
  } catch (e) { out.innerHTML = `<p style="color:var(--muted)">${escapeHtml(e.message)}</p>`; }
}

function _lista(id) { return document.getElementById(id).value.split(',').map(s => s.trim()).filter(Boolean); }

async function simularRed() {
  const out = document.getElementById('simOut');
  const body = { nombre: 'Persona simulada', can_offer: _lista('simOfrece'), wants_to_learn: _lista('simQuiere'), interests: _lista('simIntereses') };
  if (!body.can_offer.length && !body.wants_to_learn.length && !body.interests.length) { toast('Completá al menos un campo.', 'error'); return; }
  out.innerHTML = '<div class="spinner"></div>';
  try {
    const s = await api('POST', '/api/red/simular', body);
    const li = arr => arr.length ? arr.map(escapeHtml).join(', ') : '—';
    out.innerHTML = `
      <p style="font-size:13px"><strong>Área en la que cae:</strong> ${escapeHtml(s.area_asignada || '—')} · <strong>Conexiones directas:</strong> ${s.conexiones_directas} · Áreas de la red: ${s.areas_antes} → ${s.areas_despues}</p>
      <p style="font-size:12px;color:var(--muted)">Temas existentes: ${li(s.temas_vinculados)} · Temas nuevos: ${li(s.temas_nuevos)}</p>
      <p style="font-size:13px;margin-top:8px"><strong>Directos:</strong></p>${s.directos.map(d => `<p style="font-size:12px;margin:2px 0">${escapeHtml(d.persona)} — ${d.temas_compartidos.map(escapeHtml).join(', ')}</p>`).join('') || '—'}
      <p style="font-size:13px;margin-top:8px"><strong>Indirectos:</strong></p>${s.indirectos.map(d => `<p style="font-size:12px;margin:2px 0">${escapeHtml(d.camino)}</p>`).join('') || '—'}
      <p style="font-size:13px;margin-top:8px"><strong>Actividades nuevas:</strong> ${s.actividades_nuevas.length ? s.actividades_nuevas.map(a => escapeHtml(a.join(' + '))).join('; ') : 'ninguna'} · <strong>Que dejan de aparecer:</strong> ${s.actividades_perdidas.length ? s.actividades_perdidas.map(a => escapeHtml(a.join(' + '))).join('; ') : 'ninguna'}</p>`;
  } catch (e) { out.innerHTML = `<p style="color:var(--muted)">${escapeHtml(e.message)}</p>`; }
}

async function loadTriangulacion() {
  const el = document.getElementById('triangBody');
  try {
    const t = await api('GET', '/api/red/triangulacion');
    if (!t || !t.datos || !t.datos.tasa_de_si_por_tipo) { el.innerHTML = '<p style="color:var(--muted);font-size:13px">Todavía no se corrió.</p>'; return; }
    const pct = v => v === null || v === undefined ? '—' : Math.round(v * 100) + '%';
    const cols = t.datos.votantes || [];
    const filas = Object.entries(t.datos.tasa_de_si_por_tipo).map(([tipo, r]) =>
      `<tr><td>${escapeHtml(tipo)} (n=${r.n})</td>${cols.map(v => `<td align="center">${pct(r[v])}</td>`).join('')}<td align="center">${pct(r.consenso)}</td></tr>`).join('');
    el.innerHTML = `<div class="card"><table style="width:100%;font-size:13px"><tr><th align="left">Tipo de par</th>${cols.map(v => `<th>${escapeHtml(v)}</th>`).join('')}<th>Consenso</th></tr>${filas}</table>
      <p style="font-size:12px;color:var(--muted);margin-top:8px">Pares evaluados: ${t.datos.n_total} · votos unánimes: ${pct(t.datos.unanimes)}</p></div>`;
  } catch (e) { el.innerHTML = ''; }
}

function _perfilEval(p) {
  const f = (t, a) => a && a.length ? `<div style="font-size:13px"><strong>${t}:</strong> ${a.map(escapeHtml).join(', ')}</div>` : '';
  return `<div style="flex:1;min-width:220px;padding:8px;border:1px solid var(--border,#ddd);border-radius:8px"><strong>${escapeHtml(p.etiqueta)}</strong>${f('Puede aportar', p.can_offer)}${f('Quiere aprender', p.wants_to_learn)}${f('Intereses', p.interests)}</div>`;
}

async function cargarEvaluacion() {
  const el = document.getElementById('evalBody');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const d = await api('GET', '/api/red/evaluacion/siguiente');
    if (!d || !d.pair_id) { el.innerHTML = '<p style="font-size:13px;color:var(--muted)">No hay más pares para evaluar. ¡Gracias!</p>'; return; }
    el.innerHTML = `<div style="display:flex;gap:12px;flex-wrap:wrap">${_perfilEval(d.persona_a)}${_perfilEval(d.persona_b)}</div>
      <p style="font-size:13px;margin:10px 0 4px">¿Qué tan útil sería que estas dos personas conversen? (1 = nada, 5 = muchísimo) · quedan ${d.pendientes}</p>
      <div style="display:flex;gap:6px;margin-bottom:8px">${[1,2,3,4,5].map(n => `<button class="btn secondary" onclick="enviarEvaluacion('${escapeAttr(d.pair_id)}',${n})">${n}</button>`).join('')}</div>
      <input type="text" id="evalComentario" maxlength="500" placeholder="Comentario opcional">`;
  } catch (e) { el.innerHTML = `<p style="color:var(--muted)">${escapeHtml(e.message)}</p>`; }
}

async function enviarEvaluacion(pairId, rating) {
  const comentario = (document.getElementById('evalComentario') || {}).value || '';
  try {
    await api('POST', '/api/red/evaluacion', { pair_id: pairId, rating, comentario });
    resumenEvaluacion();
    cargarEvaluacion();
  } catch (e) { toast(e.message, 'error'); }
}

async function resumenEvaluacion() {
  const el = document.getElementById('evalResumen');
  try {
    const r = await api('GET', '/api/red/evaluacion/resumen');
    if (!r) return;
    const tipos = Object.entries(r.media_por_tipo).map(([t, v]) => `${escapeHtml(t)}: ${v.media} (n=${v.n})`).join(' · ') || 'sin datos todavía';
    el.innerHTML = `<p style="font-size:12px;color:var(--muted)">${r.calificaciones} calificaciones de ${r.evaluadores} evaluadores sobre ${r.pares_totales} pares${r.simuladas_excluidas ? ' (' + r.simuladas_excluidas + ' simuladas excluidas)' : ''} · media por tipo: ${tipos} · AUC indirecto vs control: ${r.auc.indirecto_vs_control ?? '—'} · similitud vs control: ${r.auc.similitud_vs_control ?? '—'}</p>`;
  } catch (e) { el.innerHTML = ''; }
}

// ── Notifications ──────────────────────────────────────────────────────────────
async function loadNotifications() {
  const el = document.getElementById('notificationsFeed');
  try {
    const notifs = await api('GET', '/api/notifications');
    const sinLeer = notifs.filter(n => !n.read);
    if (sinLeer.length === 0) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML = `<div class="card"><div class="card-top"><h4>Novedades</h4><span class="badge green">${sinLeer.length} nuevo${sinLeer.length === 1 ? '' : 's'}</span></div>` +
      sinLeer.map(n => `<p style="font-size:13px;margin:6px 0"><strong>${escapeHtml(n.title)}</strong>${n.body ? ' — ' + escapeHtml(n.body) : ''}</p>`).join('') +
      `</div>`;
    notifs.forEach(n => { if (!n.read) api('POST', `/api/notifications/${n.id}/read`).catch(() => {}); });
    currentUser.unread_notifications = 0;
    const badge = document.getElementById('matchNotifCount');
    if (badge) badge.style.display = 'none';
  } catch (e) {
    el.innerHTML = '';
  }
}

// ── Messages ───────────────────────────────────────────────────────────────────
async function loadMessages() {
  const el = document.getElementById('msgsFeed');
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const msgs = await api('GET', '/api/messages');
    if (!msgs || msgs.length === 0) {
      el.innerHTML = '<p style="color:var(--muted);font-size:13px">No tenés mensajes todavía.</p>';
      return;
    }
    el.innerHTML = msgs.map(m => `
      <div class="message" onclick="markRead('${escapeAttr(m.id)}',this)">
        <div class="avatar">${escapeHtml(initials(m.from_user_name))}</div>
        <div><strong>${escapeHtml(m.from_user_name)}</strong><span>${escapeHtml(m.last_message)}</span></div>
        <span class="badge ${m.unread ? 'green' : ''}">${m.unread ? 'Nuevo' : 'Leído'}</span>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = `<p style="color:var(--muted)">Error: ${escapeHtml(e.message)}</p>`;
  }
}

async function markRead(msgId, row) {
  try {
    await api('POST', `/api/messages/${msgId}/read`);
    row.querySelector('.badge')?.classList.remove('green');
    currentUser.unread_messages = Math.max(0, (currentUser.unread_messages || 0) - 1);
    const notif = document.getElementById('notifCount');
    if (currentUser.unread_messages === 0) notif.style.display = 'none';
    else notif.textContent = currentUser.unread_messages;
  } catch {}
}

// ── AI Copilot ─────────────────────────────────────────────────────────────────
const PATH_LABELS = ['Subir CV', 'Generar grafo', 'Vincular con IA', 'Validar evidencia'];

function demoProfile() {
  reiniciarVistaPrevia();
  document.getElementById('cv').value ='CV demo: Educación virtual, gestión de equipos y escritura de informes. Experiencia en diseño de prototipos, coordinación de proyectos y análisis institucional. Quiero aprender análisis de datos, Python y visualización. Intereses: IA educativa, permanencia estudiantil, trayectorias verificables e investigación aplicada. Disponibilidad remota de 4 a 6 horas semanales.';
  buildProfile();
}


// Vista previa del CV: primero se muestra la copia seudonimizada (sin IA, sin
// guardar nada) y recién con la confirmación se envía al modelo.
let cvVistaPrevia = null; // { archivo } mientras el cuadro tiene una copia para revisar
const RETIRADO_NOMBRES = {
  nombre: ['mención de tu nombre', 'menciones de tu nombre'], correos: ['correo', 'correos'],
  enlaces: ['enlace', 'enlaces'], telefonos: ['teléfono', 'teléfonos'], documentos: ['documento', 'documentos'],
  direcciones: ['dirección', 'direcciones'], usuarios: ['usuario de redes', 'usuarios de redes'],
};

function describirRetirado(retirado = {}) {
  const partes = Object.entries(retirado).filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${(RETIRADO_NOMBRES[k] || [k, k])[n === 1 ? 0 : 1]}`);
  return partes.length ? partes.join(', ') : 'nada que reconozcamos como dato de contacto';
}

function mostrarVistaPrevia(res, origen) {
  const cv = document.getElementById('cv');
  cv.value = res.texto;
  cv.classList.add('cv-revision');
  cvVistaPrevia = { archivo: res.archivo || '' };
  const nota = document.getElementById('cvRevision');
  nota.innerHTML = `<strong>Revisá esta copia antes de enviarla.</strong> ${escapeHtml(origen)}. Retiramos: ${escapeHtml(describirRetirado(res.retirado))}.`
    + `${res.recortado ? ' El texto era largo y quedó recortado.' : ''} Podés borrar o cambiar lo que quieras. Todavía no se envió nada al modelo.`;
  nota.hidden = false;
  const btn = document.getElementById('buildBtn');
  if (btn) btn.textContent = 'Confirmar y generar grafo';
  cv.focus();
}

function reiniciarVistaPrevia() {
  cvVistaPrevia = null;
  document.getElementById('cv')?.classList.remove('cv-revision');
  const nota = document.getElementById('cvRevision');
  if (nota) { nota.hidden = true; nota.innerHTML = ''; }
  const btn = document.getElementById('buildBtn');
  if (btn) btn.textContent = 'Revisar y generar grafo';
}

async function handleCvFile(file) {
  if (!file) return;
  reiniciarVistaPrevia();
  const nameEl = document.getElementById('cvFileName');
  if (nameEl) nameEl.textContent = file.name;
  const btn = document.getElementById('buildBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Leyendo CV…'; }
  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiForm('/api/copilot/vista-previa', formData);
    if (res) mostrarVistaPrevia(res, `Leímos ${file.name} (el archivo no se guarda)`);
    else reiniciarVistaPrevia();
  } catch (e) {
    reiniciarVistaPrevia();
    toast('No pude leer el CV: ' + e.message, 'warn');
  } finally {
    if (btn) btn.disabled = false;
    const input = document.getElementById('cvFile');
    if (input) input.value = '';
  }
}

function graphNodeId(kind, label) {
  return `${kind}-${String(label || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'nodo'}`;
}

function buildGraphFromResult(result = {}) {
  const nodes = [{ id: 'cv', label: result.source_filename ? `CV: ${result.source_filename}` : 'CV / trayectoria', kind: 'source' }];
  const edges = [];
  const seen = new Set(['cv']);
  const add = (kind, label, edgeLabel) => {
    if (!label) return;
    const id = graphNodeId(kind, label);
    if (!seen.has(id)) {
      nodes.push({ id, label: String(label), kind });
      seen.add(id);
    }
    edges.push({ source: 'cv', target: id, label: edgeLabel });
  };
  (result.can_offer || []).slice(0, 8).forEach(v => add('knowledge', v, 'conocimiento'));
  (result.wants_to_learn || result.gaps || []).slice(0, 8).forEach(v => add('learning', v, 'aprendizaje'));
  (result.interests || result.tags || []).slice(0, 8).forEach(v => add('interest', v, 'interés'));
  (result.matches || []).slice(0, 4).forEach(m => add('project', m.title, m.match_level || 'vínculo'));
  return { nodes, edges };
}

function rememberGraph(result) {
  latestKnowledgeGraph = result.graph && result.graph.nodes?.length ? result.graph : buildGraphFromResult(result);
  localStorage.setItem('rizoma_latest_graph', JSON.stringify(latestKnowledgeGraph));
}

async function applyCopilotResult(result, successMsg) {
  latestCopilotMatches = result.matches || [];
  localStorage.setItem('rizoma_latest_matches', JSON.stringify(latestCopilotMatches));
  rememberGraph(result);
  renderCopilotResult(result);
  renderMatches(result.matches);
  currentUser = await api('GET', '/api/users/me');
  renderSidebar();
  renderYourRizoma();
  toast(successMsg || 'Grafo generado. Revisá vínculos posibles con otras personas y proyectos.', 'success');
}

async function buildProfile() {
  const raw = document.getElementById('cv').value.trim();
  if (!raw) { toast('Subí un CV o pegá tu trayectoria primero.', 'warn'); return; }
  const btn = document.getElementById('buildBtn');

  // Paso 1: la copia para revisar (sin IA). Paso 2, con la confirmación: el modelo.
  if (!cvVistaPrevia) {
    btn.disabled = true; btn.textContent = 'Preparando la copia…';
    try {
      const formData = new FormData();
      formData.append('texto', raw);
      const res = await apiForm('/api/copilot/vista-previa', formData);
      if (res) mostrarVistaPrevia(res, 'Esta es la copia de tu texto');
      else reiniciarVistaPrevia();
    } catch (e) {
      reiniciarVistaPrevia();
      toast('No pude preparar la copia: ' + e.message, 'warn');
    } finally {
      btn.disabled = false;
    }
    return;
  }

  btn.disabled = true; btn.textContent = 'Generando grafo…';
  document.getElementById('aiProfile').innerHTML = `
    <div class="card-top"><h4>Generando grafo desde CV</h4><span class="badge">IA</span></div>
    <div class="spinner"></div>
    <p style="text-align:center;color:var(--muted);font-size:12px;margin:0 0 10px">Extrayendo nodos de conocimiento, aprendizajes e intereses…</p>`;

  try {
    const result = await api('POST', '/api/copilot', { text: raw, archivo: cvVistaPrevia.archivo });
    if (!result) return;
    reiniciarVistaPrevia();
    await applyCopilotResult(result, 'Grafo generado. Revisá vínculos posibles con otras personas y proyectos.');
  } catch (e) {
    document.getElementById('aiProfile').innerHTML = `
      <div class="card-top"><h4>Generador de grafo</h4><span class="badge">IA</span></div>
      <p style="color:var(--primary);font-size:13px">Error: ${escapeHtml(e.message)}</p>`;
    toast('Error generando el grafo: ' + e.message, 'warn');
  } finally {
    btn.disabled = false;
    btn.textContent = cvVistaPrevia ? 'Confirmar y generar grafo' : 'Revisar y generar grafo';
  }
}


function renderGraphPreview(graph) {
  const nodes = (graph && graph.nodes) || [];
  const edges = (graph && graph.edges) || [];
  if (!nodes.length) return '';
  const labels = { knowledge: 'Conocimientos', learning: 'Por desarrollar', interest: 'Intereses', project: 'Conexiones' };
  const groups = ['knowledge', 'learning', 'interest', 'project'].map(kind => {
    const items = nodes.filter(n => n.kind === kind).slice(0, 4);
    if (!items.length) return '';
    return `<div><strong>${labels[kind]}</strong>${items.map(n => `<span>${escapeHtml(n.label)}</span>`).join('')}</div>`;
  }).join('');
  return `
    <div class="graph-mini">
      <div class="graph-mini-head"><strong>Grafo de conocimientos</strong><span>${nodes.length} nodos · ${edges.length} vínculos</span></div>
      <div class="graph-mini-grid">${groups}</div>
    </div>`;
}

function renderGraphNodeList(graph) {
  const nodes = (graph && graph.nodes) || [];
  const edges = (graph && graph.edges) || [];
  if (!nodes.length) return '';
  const labelByKind = { source: 'Base', knowledge: 'Conocimientos', learning: 'Aprendizajes', interest: 'Intereses', project: 'Vínculos posibles' };
  const kindOrder = ['source', 'knowledge', 'learning', 'interest', 'project'];
  const columns = kindOrder.map(kind => {
    const items = nodes.filter(n => n.kind === kind);
    if (!items.length) return '';
    return `<div class="graph-node-group"><strong>${labelByKind[kind]}</strong>${items.slice(0, 6).map(n => `<span class="graph-node kind-${escapeAttr(kind)}">${escapeHtml(n.label)}</span>`).join('')}</div>`;
  }).join('');
  const sampleEdges = edges.slice(0, 8).map(e => `<span>${escapeHtml(e.label || 'vínculo')}</span>`).join('');
  return `<div class="graph-node-list">${columns}</div>${sampleEdges ? `<div class="graph-edge-list"><strong>Tipos de relación</strong>${sampleEdges}</div>` : ''}`;
}

function renderCopilotResult(result) {
  const pathHTML = `
    <div class="path-box">
      <strong>Camino de acción sugerido</strong>
      <div class="path-steps">
        ${PATH_LABELS.map((label, i) => `
          <div class="path-step ${i < result.path_step ? 'done' : i === result.path_step ? 'current' : ''}">
            <div class="step-dot">${i < result.path_step ? '✓' : i + 1}</div>
            <div class="step-label">${escapeHtml(label)}</div>
          </div>`).join('')}
      </div>
    </div>`;

  const offerHTML = `
    <div class="gap-box">
      <strong>Vos podés aportar</strong>
      ${(result.can_offer || []).map(s => `<div class="gap-row"><span class="gap-have">✓</span> <span>${escapeHtml(s)}</span></div>`).join('') || '<div class="gap-row"><span>Completá más información para detectarlo.</span></div>'}
    </div>`;
  const learnHTML = `
    <div class="gap-box">
      <strong>Querés aprender / explorar</strong>
      ${(result.wants_to_learn || result.gaps || []).map(s => `<div class="gap-row"><span class="gap-need">+</span> <span>${escapeHtml(s)}</span></div>`).join('') || '<div class="gap-row"><span>Completá más información para detectarlo.</span></div>'}
    </div>`;

  document.getElementById('aiProfile').innerHTML = `
    <div class="card-top"><h4>Grafo generado</h4><span class="badge green">IA</span></div>
    <p>${escapeHtml(result.summary)}</p>
    <div class="chips">${(result.interests || result.tags || []).map(t => `<span class="chip">${escapeHtml(t)}</span>`).join('')}</div>
    ${offerHTML}
    ${learnHTML}
    ${pathHTML}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px">
      <button class="btn" style="font-size:12px" onclick="showTab('rizoma',document.querySelector('[data-nav=rizoma]'))">Vincular mi grafo</button>
      <button class="btn secondary" style="font-size:12px" onclick="showTab('matches',document.querySelector('[data-nav=matches]'))">Ver conexiones IA →</button>
    </div>`;

  const matchesTabEl = document.getElementById('matchesFeed');
  if (matchesTabEl && result.matches) {
    matchesTabEl.innerHTML = result.matches.map(m => renderMatchCard(m, true)).join('');
  }
}

async function openApplyById(projectId) {
  try {
    const p = await api('GET', `/api/projects/${projectId}`);
    if (p) openApply(p.id, p.title, p.institution, p.credential_title);
  } catch (e) {
    toast('Error cargando el proyecto: ' + e.message, 'warn');
  }
}

function renderMatchCard(m, withAction) {
  return `
    <article class="card">
      <div class="card-top"><h4>${escapeHtml(m.title)}</h4><span class="badge blue">${escapeHtml(m.match_level || 'Exploratoria')}</span></div>
      <p>${escapeHtml(m.text)}</p>
      <div class="post-proof"><strong>Vos aportás</strong><span>${escapeHtml(m.you_contribute || 'Una capacidad o experiencia que puede servir al proyecto.')}</span></div>
      <div class="post-proof"><strong>Podés aprender</strong><span>${escapeHtml(m.you_can_learn || 'Un aprendizaje posible a conversar con el equipo.')}</span></div>
      <div class="post-proof"><strong>El proyecto necesita</strong><span>${escapeHtml(m.project_needs || 'Una necesidad del proyecto que podría complementarse con lo que vos aportás.')}</span></div>
      <button class="why-toggle" onclick="toggleWhy(this)">Por qué los conectamos ▼</button>
      <div class="why-body">${escapeHtml(m.why_connect || m.why || '')}</div>
      ${withAction && m.project_id ? `<button class="btn" style="margin-top:10px;width:100%" onclick="openApplyById('${escapeAttr(m.project_id)}')">${escapeHtml(m.suggested_action || 'Quiero explorar esta oportunidad')}</button>${outcomeButtons('project', m.project_id)}` : ''}
    </article>`;
}

// ── Matches sidebar ────────────────────────────────────────────────────────────
function renderMatches(items) {
  const el = document.getElementById('matchesList');
  if (!items || items.length === 0) {
    el.innerHTML = '<p style="color:var(--muted);font-size:12px">Generá tu grafo para ver vínculos posibles.</p>';
    return;
  }
  el.innerHTML = items.map(m => `
    <div class="match">
      <div class="score">${escapeHtml((m.match_level || 'Expl.').slice(0,4))}</div>
      <div>
        <strong>${escapeHtml(m.title)}</strong>
        <span>${escapeHtml(m.text)}</span>
        <button class="why-toggle" onclick="toggleWhy(this)">Por qué ▼</button>
        <div class="why-body">${escapeHtml(m.why_connect || m.why || '')}</div>
      </div>
    </div>`).join('');
}

function renderRizomaList(items, emptyText) {
  if (!items || items.length === 0) return `<li class="muted">${escapeHtml(emptyText)}</li>`;
  return items.slice(0, 5).map(item => `<li>${escapeHtml(item)}</li>`).join('');
}

// Orden de las sugerencias de personas: lo calcula el grafo, nunca el modelo.
let peopleOrden = 'rareza';
let peopleSemilla = null;
let peopleVerTodas = {};
const peopleExplicaciones = {};

async function loadPeopleConnections() {
  const q = new URLSearchParams({ orden: peopleOrden });
  if (peopleOrden === 'azar' && peopleSemilla) q.set('semilla', peopleSemilla);
  try {
    latestPeopleConnections = await api('GET', `/api/users/people/complementary?${q}`) || [];
  } catch {
    latestPeopleConnections = [];
  }
  if (peopleOrden === 'azar' && latestPeopleConnections[0]?.semilla) peopleSemilla = latestPeopleConnections[0].semilla;
  return latestPeopleConnections;
}

function renderOrdenControles() {
  return `
    <div class="orden-controles">
      <label>Ordenar por
        <select id="peopleOrden" onchange="cambiarOrdenPersonas()">
          <option value="rareza"${peopleOrden === 'rareza' ? ' selected' : ''}>Rareza de los temas</option>
          <option value="cruces"${peopleOrden === 'cruces' ? ' selected' : ''}>Cantidad de cruces</option>
          <option value="azar"${peopleOrden === 'azar' ? ' selected' : ''}>Al azar</option>
        </select>
      </label>
      <label id="peopleSemillaWrap"${peopleOrden === 'azar' ? '' : ' hidden'}>Semilla
        <input id="peopleSemilla" type="number" min="1" max="999999" value="${escapeAttr(peopleSemilla || '')}" onchange="cambiarOrdenPersonas()">
      </label>
    </div>`;
}

async function cambiarOrdenPersonas() {
  const nuevoOrden = document.getElementById('peopleOrden')?.value || 'rareza';
  const semillaEl = document.getElementById('peopleSemilla');
  // al pasar a "azar" sin semilla, el servidor elige una y la muestra
  peopleSemilla = nuevoOrden === 'azar' && peopleOrden === 'azar' ? (parseInt(semillaEl?.value, 10) || null) : null;
  peopleOrden = nuevoOrden;
  peopleVerTodas = {};
  const grid = document.getElementById('rizomaPeopleGrid');
  if (grid) grid.innerHTML = '<div class="spinner"></div>';
  await loadPeopleConnections();
  const wrap = document.getElementById('peopleSemillaWrap');
  if (wrap) wrap.hidden = peopleOrden !== 'azar';
  if (semillaEl) semillaEl.value = peopleSemilla || '';
  renderPeopleGrid();
}

// Dos bloques ordenados por separado con el criterio elegido, y los perfiles
// sin camino en el grafo aparte, colapsados.
const PEOPLE_BLOQUES = [
  { id: 'comun', titulo: 'Temas en común', ayuda: 'Comparten al menos un tema declarado.' },
  { id: 'puente', titulo: 'Caminos puente', ayuda: 'No comparten temas: se conectan a través de otra persona y dos temas puente.' },
];

function renderPeopleGrid() {
  const el = document.getElementById('rizomaPeopleGrid');
  if (!el) return;
  const people = latestPeopleConnections || [];
  if (!people.length) {
    el.innerHTML = '<p class="muted">Todavía no hay otros grafos con datos suficientes para trazar vínculos. A medida que más personas suban CVs o trayectorias, la red se vuelve visible.</p>';
    return;
  }
  if (typeof peopleVerTodas !== 'object' || !peopleVerTodas) peopleVerTodas = {};
  const secciones = PEOPLE_BLOQUES.map(b => {
    const items = people.filter(p => (p.bloque || 'comun') === b.id);
    const visibles = peopleVerTodas[b.id] ? items : items.slice(0, 8);
    return `
      <section class="people-bloque" data-bloque="${b.id}">
        <div class="people-bloque-head"><h5>${escapeHtml(b.titulo)} <span class="badge">${items.length}</span></h5><small>${escapeHtml(b.ayuda)}</small></div>
        ${items.length ? `<div class="rizoma-people-grid">${visibles.map(renderPersonCard).join('')}</div>` : '<p class="muted">No hay sugerencias en este bloque.</p>'}
        ${items.length > 8 ? `<button class="btn secondary ver-mas" onclick="peopleVerTodas['${b.id}']=!peopleVerTodas['${b.id}'];renderPeopleGrid()">${peopleVerTodas[b.id] ? 'Ver solo las primeras 8' : `Ver las ${items.length}`}</button>` : ''}
      </section>`;
  }).join('');
  const otros = people.filter(p => p.bloque === 'otros');
  el.innerHTML = secciones + (otros.length ? `
    <details class="people-bloque people-otros" data-bloque="otros">
      <summary>Otros perfiles (sin camino en el grafo) <span class="badge">${otros.length}</span></summary>
      <small>Aparecen solo por afinidad de perfiles: el grafo no los conecta con vos.</small>
      <div class="rizoma-people-grid">${otros.map(renderPersonCard).join('')}</div>
    </details>` : '');
}

async function cargarExplicacion(details, personId) {
  if (!details.open) return;
  const destino = details.querySelector('.explicacion-ia');
  const pintar = r => {
    destino.innerHTML = `<p>${escapeHtml(r.explicacion || 'El modelo no devolvió una explicación para este par.')}</p>
      ${r.degradado ? '<span class="badge alerta" title="El servicio de IA no respondió; la explicación la produjo el respaldo local.">Explicación preliminar</span>' : ''}
      ${renderRelationshipEdges(r.relationship_edges)}`;
  };
  if (peopleExplicaciones[personId]) return pintar(peopleExplicaciones[personId]);
  destino.innerHTML = '<p class="muted">Redactando la explicación…</p>';
  try {
    peopleExplicaciones[personId] = await api('GET', `/api/users/people/${encodeURIComponent(personId)}/explicacion`);
    pintar(peopleExplicaciones[personId]);
  } catch (e) {
    destino.innerHTML = `<p class="muted">No pude traer la explicación: ${escapeHtml(e.message || e)}</p>`;
  }
}

async function recordMatchOutcome(targetType, targetId, outcome, notes = '') {
  const labels = { started: 'en curso', useful: 'útil', not_useful: 'no sirvió', collaboration: 'colaboración real' };
  try {
    await api('POST', '/api/users/match-outcomes', {
      target_type: targetType,
      target_id: String(targetId),
      outcome,
      source: 'rizoma-ui',
      notes
    });
    toast(`Resultado registrado: ${labels[outcome] || outcome}.`, 'success');
  } catch (e) {
    toast('No pude registrar el resultado: ' + e.message, 'warn');
  }
}

function outcomeButtons(targetType, targetId) {
  const id = escapeAttr(targetId);
  const type = escapeAttr(targetType);
  return `
    <div class="outcome-actions" aria-label="Registrar resultado de la conexión">
      <button onclick="recordMatchOutcome('${type}','${id}','started')">En curso</button>
      <button onclick="recordMatchOutcome('${type}','${id}','useful')">Sirvió</button>
      <button onclick="recordMatchOutcome('${type}','${id}','collaboration')">Colaboró</button>
    </div>`;
}

function renderRelationshipEdges(edges) {
  if (!edges || !edges.length) return '';
  return `<div class="relationship-edges">${edges.slice(0, 4).map(e => `
    <div class="relationship-edge kind-${escapeAttr(e.kind || 'link')}">
      <span>${escapeHtml(e.label || 'vínculo')}</span>
      <strong>${escapeHtml(e.source_node || '')}</strong>
      <em>${escapeHtml(e.text || '')}</em>
    </div>`).join('')}</div>`;
}

async function loadRizomaSnapshots() {
  try {
    return await api('GET', '/api/users/me/rizoma-snapshots') || [];
  } catch {
    return [];
  }
}

function renderSnapshotStrip(items) {
  if (!items || !items.length) return '';
  return `
    <div class="snapshot-strip">
      <div class="snapshot-head"><strong>Memoria del rizoma</strong><span>${items.length} versiones guardadas</span></div>
      <div class="snapshot-list">${items.slice(0, 4).map((s, idx) => `
        <article>
          <span>v${items.length - idx}</span>
          <strong>${new Date(s.created_at).toLocaleDateString('es-AR')}</strong>
          <p>${escapeHtml(s.summary || 'Snapshot de conocimientos, intereses y aprendizajes.')}</p>
        </article>`).join('')}</div>
    </div>`;
}

async function sendPersonMessage(personId) {
  const person = (latestPeopleConnections || []).find(p => String(p.id) === String(personId));
  const name = person?.name || '';
  const greeting = name ? `Hola ${name}, ` : 'Hola, ';
  const defaultMsg = `${greeting}vi una complementariedad posible en Rizoma. Me gustaría conversar para ver qué podríamos aprender o construir en conjunto.`;
  const body = prompt('Mensaje para iniciar conversación', defaultMsg);
  if (!body || !body.trim()) return;
  try {
    await api('POST', '/api/messages', { to_id: personId, body: body.trim() });
    toast('Mensaje enviado para explorar complementariedad.', 'success');
  } catch (e) {
    toast('No pude enviar el mensaje: ' + e.message, 'warn');
  }
}

function renderPersonCard(p) {
  const learn = p.you_can_learn_from_them || [];
  const offer = p.you_can_offer_them || [];
  const shared = p.shared_interests || [];
  const feedbackType = p.ai_suggestion_id ? 'ai_suggestion' : 'person';
  const feedbackId = p.ai_suggestion_id || p.id;
  const razonCorta = shared.length ? `Comparte ${shared.slice(0, 2).join(' y ')}` : learn.length && offer.length ? 'Hay intercambio de aprendizaje y aporte' : p.camino?.length ? 'Aparece por un camino indirecto' : 'Afinidad semántica entre trayectorias';
  return `
    <article class="rizoma-person">
      <div class="person-head">
        <div class="avatar">${escapeHtml(initials(p.name))}</div>
        <div><strong>${escapeHtml(p.name)}</strong><span>${escapeHtml([roleLabel(p.role), p.institution].filter(Boolean).join(' · '))}</span></div>
      </div>
      <div class="person-badges">
        <span class="badge blue">${escapeHtml(p.connection_type || 'Complementariedad posible')}</span>
      </div>
      ${p.dato_estructural ? `<p class="dato-estructural" title="Dato del grafo que ubica a esta sugerencia en su lugar"><strong>#${escapeHtml(p.posicion || '')}</strong> ${escapeHtml(p.dato_estructural)}</p>` : ''}
      ${renderCaminoIndirecto(p.camino)}
      <details class="explain-card" ontoggle="cargarExplicacion(this, '${escapeAttr(p.id)}')">
        <summary>Por qué aparece esta persona</summary>
        <div class="explicacion-ia"><p class="muted">Abrí para que la IA redacte la explicación de este vínculo.</p></div>
        <small>${escapeHtml(razonCorta)}. El orden sale del grafo; la IA solo redacta la explicación. La sugerencia no ordena mérito: abre una conversación posible.</small>
      </details>
      ${learn.length ? `<div class="post-proof"><strong>Podrías aprender</strong><span>${escapeHtml(learn.join(', '))}</span></div>` : ''}
      ${offer.length ? `<div class="post-proof"><strong>Podrías aportar</strong><span>${escapeHtml(offer.join(', '))}</span></div>` : ''}
      ${shared.length ? `<div class="post-proof"><strong>Intereses compartidos</strong><span>${escapeHtml(shared.join(', '))}</span></div>` : ''}
      ${renderRelationshipEdges(p.relationship_edges)}
      <button class="btn" style="margin-top:10px;width:100%" onclick="sendPersonMessage('${escapeAttr(p.id)}')">Conversar</button>
      ${outcomeButtons(feedbackType, feedbackId)}
    </article>`;
}


async function cargarCaminosIndirectos() {
  const el = document.getElementById('rizomaCaminosGrid');
  if (!el) return;
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const caminos = await api('GET', '/api/users/me/rizoma-caminos?limite=8') || [];
    const metricaCaminos = document.getElementById('metricaCaminos');
    if (metricaCaminos) metricaCaminos.textContent = caminos.length;
    if (!caminos.length) {
      el.innerHTML = '<p class="muted">Todavía no hay caminos indirectos fuertes. A medida que la red sume perfiles diversos, aparecerán puentes más interesantes.</p>';
      return;
    }
    const hallazgo = document.getElementById('rizomaHallazgo');
    if (hallazgo) hallazgo.innerHTML = renderHallazgoDestacado(caminos[0]);
    el.innerHTML = caminos.map(renderCaminoCard).join('');
  } catch (err) {
    el.innerHTML = `<p class="muted">No pude cargar caminos indirectos: ${escapeHtml(err.message || err)}</p>`;
  }
}

function caminoResumen(item) {
  const camino = item?.camino || [];
  return {
    origen: camino[0]?.label || 'Tu perfil',
    destino: camino[4]?.label || item?.persona || 'otra persona',
    temaOrigen: camino[1]?.label || 'un tema propio',
    intermedio: camino[2]?.label || 'una persona puente',
    temaPuente: camino[3]?.label || 'un tema puente',
    score: item?.score ?? ''
  };
}

function renderHallazgoDestacado(item) {
  if (!item) return '<p class="muted">Cargá caminos indirectos para construir una tarjeta de hallazgo.</p>';
  const r = caminoResumen(item);
  const actividad = `${r.temaOrigen} + ${r.temaPuente}`;
  return `
    <article class="hallazgo-card">
      <div>
        <span class="panel-kicker">Hallazgo para narrar en jornadas</span>
        <h4>${escapeHtml(r.origen)} → ${escapeHtml(r.destino)}</h4>
        <p>No comparten necesariamente carrera ni búsqueda directa. Rizoma los encuentra porque ${escapeHtml(r.intermedio)} funciona como puente entre <strong>${escapeHtml(r.temaOrigen)}</strong> y <strong>${escapeHtml(r.temaPuente)}</strong>.</p>
      </div>
      <div class="hallazgo-result">
        <span>Actividad emergente posible</span>
        <strong>${escapeHtml(actividad)}</strong>
        <button class="btn secondary" onclick="rgSetFiltro('indirectos');document.getElementById('rgCanvas')?.scrollIntoView({behavior:'smooth',block:'center'})">Ver en el grafo</button>
      </div>
    </article>`;
}

function renderCaminoCard(item) {
  const camino = item.camino || [];
  const r = caminoResumen(item);
  return `
    <article class="camino-card">
      <div class="camino-card-head">
        <strong>${escapeHtml(r.destino)}</strong>
        <span class="badge">rareza ${escapeHtml(r.score)}</span>
      </div>
      ${renderCaminoIndirecto(camino)}
      <p>${escapeHtml(r.origen)} se conecta con ${escapeHtml(r.destino)} a través de ${escapeHtml(r.intermedio)}: el recorrido cruza ${escapeHtml(r.temaOrigen)} con ${escapeHtml(r.temaPuente)}. Ese puente puede abrir una conversación que no saldría de una búsqueda por carrera.</p>
    </article>`;
}

function renderDemoNarrativa() {
  const pasos = [
    ['1', 'Perfil ficticio', 'Lucía Medina carga una trayectoria de informática con datos y visualización.'],
    ['2', 'Grafo personal', 'Rizoma separa capacidades, aprendizajes buscados e intereses; no lo reduce a un cargo.'],
    ['3', 'Puente indirecto', 'El sistema encuentra una persona puente y cruza temas que no estaban en la misma carrera.'],
    ['4', 'Actividad emergente', 'Del cruce aparece una hipótesis de taller, proyecto, práctica o línea de formación.'],
    ['5', 'Validación humana', 'La institución observa señales agregadas; las personas deciden si conversan.']
  ];
  return `
    <section class="demo-story card" id="demoStory">
      <div class="card-top"><h4>Recorrido guiado de 5 minutos</h4><span class="badge blue">Caso ficticio UNQ</span></div>
      <div class="story-steps">${pasos.map(p => `
        <button class="story-step" onclick="demoPaso('${p[0]}')" aria-label="Paso ${p[0]}: ${escapeAttr(p[1])}">
          <strong>${p[0]}</strong><span>${escapeHtml(p[1])}</span><small>${escapeHtml(p[2])}</small>
        </button>`).join('')}</div>
    </section>`;
}

function demoPaso(n) {
  const acciones = {
    '1': () => document.querySelector('.rizoma-map')?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
    '2': () => { rgSetFiltro('temas'); document.getElementById('rgCanvas')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); },
    '3': () => { rgSetFiltro('indirectos'); document.getElementById('rgCanvas')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); },
    '4': () => document.getElementById('rizomaHallazgo')?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
    '5': () => showTab('observatorio', document.querySelector('[data-nav=observatorio]'))
  };
  document.querySelectorAll('.story-step').forEach(b => b.classList.toggle('active', b.textContent.trim().startsWith(n)));
  acciones[n]?.();
}

async function renderYourRizoma() {
  const el = document.getElementById('rizomaView');
  if (!el || !currentUser) return;

  const offers = currentUser.can_offer || [];
  const learns = currentUser.wants_to_learn || [];
  const interests = currentUser.interests || currentUser.ai_tags || [];
  const matches = latestCopilotMatches || [];
  const snapshots = await loadRizomaSnapshots();
  const hasMap = offers.length || learns.length || interests.length || currentUser.ai_summary || matches.length || snapshots.length;

  if (!hasMap) {
    el.innerHTML = `
      <div class="rizoma-empty card">
        <div class="card-top"><h4>Grafo generado desde CV</h4><span class="badge blue">Mapa vivo</span></div>
        <p>Rizoma transforma tu CV o trayectoria en un grafo propio. Después la IA vincula ese grafo con el resto de la red para encontrar complementariedades útiles.</p>
        <button class="btn" style="margin-top:10px" onclick="showTab('inicio',document.querySelector('[data-nav=inicio]'));setTimeout(()=>document.getElementById('cv').focus(),200)">Subir CV y generar grafo</button>
      </div>`;
    return;
  }

  el.innerHTML = `
    <section class="demo-panel card">
      <div class="demo-panel-main">
        <span class="panel-kicker">Modo jornadas</span>
        <h4>De trayectoria individual a actividad emergente</h4>
        <p>Usá esta capa para contar Rizoma en vivo: CV, grafo, puente indirecto y oportunidad verificable.</p>
      </div>
      <div class="demo-metrics">
        <div><strong data-metrica="personas">…</strong><span>perfiles del conjunto</span></div>
        <div><strong data-metrica="temas">…</strong><span>temas</span></div>
        <div><strong data-metrica="aristas">…</strong><span>vínculos</span></div>
        <div><strong id="metricaCaminos">…</strong><span>caminos</span></div>
      </div>
      <div class="demo-actions">
        <button class="btn" onclick="toggleModoPresentacion(this)">Modo presentación</button>
        <button class="btn secondary" onclick="demoPaso('3')">Ver puente</button>
        <button class="btn secondary" onclick="exportarGrafo()">Exportar grafo</button>
      </div>
    </section>
    ${renderDemoNarrativa()}
    <section class="card hallazgo-panel" id="rizomaHallazgo"><div class="spinner"></div></section>
    <section class="rizoma-map card">
      <div class="card-top"><h4>Grafo generado desde CV</h4><span class="badge green">Base personal</span></div>
      <p>${escapeHtml(currentUser.ai_summary || 'Tu grafo de conocimientos: nodos de saber, aprendizajes buscados e intereses desde los que la IA puede vincularte con otras personas.')}</p>
      <div class="rg-wrap">
        <div class="rg-tools">
          <button class="rg-btn" onclick="rizomaZoom(1.35)" title="Acercar" aria-label="Acercar">+</button>
          <button class="rg-btn" onclick="rizomaZoom(0.74)" title="Alejar" aria-label="Alejar">−</button>
          <button class="rg-btn wide" onclick="rizomaCentrar()" title="Centrar">Centrar</button>
          <button class="rg-btn wide" onclick="abrirRedCompleta()" title="Ver la red entera a pantalla completa">Red completa</button>
          <button class="rg-btn wide" onclick="rgToggleLeyenda(this)" title="Mostrar u ocultar referencias">Ocultar leyenda</button>
          <button class="rg-btn wide" id="rgVivoBtn" data-off="1" title="Pausar o reanudar el movimiento" onclick="const on=this.dataset.off==='1';rizomaVivo(on);this.dataset.off=on?'0':'1';this.textContent=on?'Pausar':'Animar'">Animar</button>
        </div>
        <div class="rg-filter" aria-label="Filtro del grafo">
          <button class="active" data-rg-filter="todos" onclick="rgSetFiltro('todos',this)">Todo</button>
          <button data-rg-filter="personas" onclick="rgSetFiltro('personas',this)">Personas</button>
          <button data-rg-filter="temas" onclick="rgSetFiltro('temas',this)">Temas</button>
          <button data-rg-filter="indirectos" onclick="rgSetFiltro('indirectos',this)">Indirectos</button>
        </div>
        <canvas id="rgCanvas" class="rg-canvas" aria-label="Mapa de conocimientos y personas vinculadas"></canvas>
        <div id="rgTip" class="rg-tip"></div>
        <div id="rgLeyenda" class="rg-legend"></div>
        <p class="rg-hint">Los nodos se agrupan por área temática · rueda para zoom · arrastrá el fondo o un nodo · clic para aislar sus vínculos</p>
      </div>
      <p class="rg-counts">Conocimientos <strong>${offers.length || 0}</strong> · Aprendizajes <strong>${learns.length || 0}</strong> · Intereses <strong>${interests.length || 0}</strong> · Vínculos <strong id="peopleBridgeCount">…</strong></p>
    </section>
    <div class="rizoma-columns">
      <section class="card"><h4>Nodos de conocimiento</h4><ul>${renderRizomaList(offers, 'Falta cargar conocimientos o capacidades concretas.')}</ul></section>
      <section class="card"><h4>Nodos por desarrollar</h4><ul>${renderRizomaList(learns, 'Falta cargar aprendizajes buscados.')}</ul></section>
      <section class="card"><h4>Territorios de interés</h4><ul>${renderRizomaList(interests, 'Falta cargar intereses.')}</ul></section>
    </div>
    <section class="card rizoma-people">
      <div class="card-top"><h4>Vinculá tu grafo con el resto</h4><span class="badge blue">Orden del grafo</span></div>
      <p class="muted">Las sugerencias salen de la estructura de la red, no de un puntaje de la IA: elegís el criterio de orden y cada tarjeta muestra el dato que la ubica en su lugar. La IA solo redacta la explicación cuando abrís una sugerencia.</p>
      ${renderOrdenControles()}
      <div id="rizomaPeopleGrid" class="rizoma-people-bloques"><div class="spinner"></div></div>
    </section>
    <section class="card rizoma-indirectos">
      <div class="card-top"><h4>Caminos indirectos</h4><span class="badge blue">Hallazgos rizomáticos</span></div>
      <p class="muted">Estos vínculos no nacen de compartir carrera o palabra clave. Aparecen porque una tercera persona o tema puente conecta trayectorias que probablemente no se encontrarían solas.</p>
      <div id="rizomaCaminosGrid" class="rizoma-caminos-grid"><div class="spinner"></div></div>
    </section>
    <section class="card rizoma-projects">
      <div class="card-top"><h4>Proyectos donde la conexión puede tomar forma</h4><button class="btn secondary" onclick="showTab('matches',document.querySelector('[data-nav=matches]'))">Ver detalle IA</button></div>
      <div class="rizoma-project-grid">${renderRizomaProjectCards(matches)}</div>
    </section>`;

  cargarRizomaGrafo();
  cargarCaminosIndirectos();
  cargarMetricasConjunto();

  const people = await loadPeopleConnections();
  const countEl = document.getElementById('peopleBridgeCount');
  if (countEl) countEl.textContent = people.length || '—';
  const semillaEl = document.getElementById('peopleSemilla');
  if (semillaEl) semillaEl.value = peopleSemilla || '';
  renderPeopleGrid();
}

function renderRizomaProjectCards(matches) {
  return (matches || []).slice(0, 3).map(m => `
    <article class="rizoma-project">
      <span>${escapeHtml(m.match_level || 'Exploratoria')}</span>
      <strong>${escapeHtml(m.title)}</strong>
      <p>${escapeHtml(m.why_connect || m.text || 'Proyecto posible para conversar complementariedad.')}</p>
      ${m.project_id ? `<button class="why-toggle" onclick="openApplyById('${escapeAttr(m.project_id)}')">Explorar oportunidad →</button>${outcomeButtons('project', m.project_id)}` : ''}
    </article>`).join('') || '<p class="muted">Generá tu grafo para ver proyectos posibles.</p>';
}

function toggleWhy(btn) {
  const body = btn.nextElementSibling;
  const open = body.classList.toggle('open');
  btn.textContent = open ? 'Ocultar ▲' : '¿Por qué esta conexión? ▼';
}

// ── Profile edit ───────────────────────────────────────────────────────────────
function openEditProfile() {
  document.getElementById('editName').value = currentUser.name;
  document.getElementById('editInst').value = currentUser.institution;
  document.getElementById('editBio').value = currentUser.bio;
  document.getElementById('editOverlay').classList.add('open');
}

async function saveProfile() {
  const name = document.getElementById('editName').value.trim();
  const institution = document.getElementById('editInst').value.trim();
  const bio = document.getElementById('editBio').value.trim();
  try {
    currentUser = await api('PUT', '/api/users/me', { name, institution, bio });
    renderSidebar();
    document.getElementById('editOverlay').classList.remove('open');
    toast('Datos base actualizados.', 'success');
  } catch (e) {
    toast('Error guardando: ' + e.message, 'warn');
  }
}

// ── Search ─────────────────────────────────────────────────────────────────────
let srchTimeout;
function openSrch() {
  document.getElementById('sOverlay').classList.add('open');
  setTimeout(() => document.getElementById('sInput').focus(), 40);
  filterSrch();
}
function closeSrch() {
  document.getElementById('sOverlay').classList.remove('open');
  document.getElementById('sInput').value = '';
}
async function filterSrch() {
  clearTimeout(srchTimeout);
  const q = document.getElementById('sInput').value.trim();
  const el = document.getElementById('sResults');
  if (!q) { el.innerHTML = ''; return; }
  srchTimeout = setTimeout(async () => {
    try {
      const data = await api('GET', `/api/feed/search?q=${encodeURIComponent(q)}`);
      const all = [
        ...(data.projects || []),
        ...(data.users || []),
        ...(data.credentials || []),
      ];
        latestSearchResults = all;
        el.innerHTML = all.length
          ? all.map((r, i) => `<div class="s-result" onclick="openSearchResult(${i})"><span class="badge blue" style="flex-shrink:0">${escapeHtml(r.type)}</span><strong>${escapeHtml(r.title)}</strong><span class="s-detail">— ${escapeHtml(r.detail)}</span></div>`).join('')
          : '<p style="color:var(--muted);font-size:13px;padding:8px 0">Sin resultados.</p>';
    } catch {}
  }, 250);
}

function openSearchResult(index) {
  const item = latestSearchResults[index] || {};
  closeSrch();
  if (item.url) { location.href = item.url; return; }
  toast(item.title || 'Resultado seleccionado');
}

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); openSrch(); return; }
  if (e.key === 'Escape') {
    closeSrch();
    document.getElementById('cOverlay').classList.remove('open');
    document.getElementById('applyOverlay').classList.remove('open');
    document.getElementById('editOverlay').classList.remove('open');
  }
});

// ── Composer ───────────────────────────────────────────────────────────────────
function openComposer(type) {
  document.getElementById('cOverlay').classList.add('open');
  if (type) document.querySelectorAll('.modal-type').forEach(b => b.classList.toggle('sel', b.textContent === type));
  setTimeout(() => document.getElementById('cText').focus(), 40);
}
function selType(btn) {
  document.querySelectorAll('.modal-type').forEach(b => b.classList.remove('sel'));
  btn.classList.add('sel');
}
async function submitPost() {
  const txt = document.getElementById('cText').value.trim();
  if (!txt) { toast('Escribí una señal antes de enviarla.', 'warn'); return; }
  const type = document.querySelector('.modal-type.sel')?.textContent || 'Avance';
  const typeMap = { 'Avance': 'advance', 'Proyecto': 'project', 'Evidencia': 'credential', 'Acompañamiento': 'mentorship', 'Credencial': 'credential', 'Mentoría': 'mentorship' };
  try {
    await api('POST', '/api/feed', { type: typeMap[type] || 'advance', content: txt });
    document.getElementById('cOverlay').classList.remove('open');
    document.getElementById('cText').value = '';
    toast('Señal enviada para revisión institucional.', 'success');
    if (document.getElementById('inicio').classList.contains('active')) loadFeed();
  } catch (e) {
    toast('Error enviando la señal: ' + e.message, 'warn');
  }
}

// ── Tabs ───────────────────────────────────────────────────────────────────────
const ROUTES = {
  inicio: BASE_URL + '/', perfil: BASE_URL + '/perfil', rizoma: BASE_URL + '/tu-rizoma', proyectos: BASE_URL + '/proyectos',
  credenciales: BASE_URL + '/credenciales', matches: BASE_URL + '/matches', manual: BASE_URL + '/manual',
  mensajes: BASE_URL + '/mensajes', observatorio: BASE_URL + '/observatorio', recursos: BASE_URL + '/recursos',
};
const HELP = {
  inicio: 'Subí tu CV y generá un grafo de conocimientos, aprendizajes e intereses.',
  perfil: 'Datos base para sostener tu grafo con información clara y verificable.',
  rizoma: 'Vinculá tu grafo con otros grafos mediante inteligencia artificial.',
  proyectos: 'Espacios donde las conexiones pueden transformarse en colaboración y evidencia.',
  credenciales: 'Evidencias que muestran lo que se construyó después de una conexión.',
  matches: 'La IA cruza grafos para sugerir complementariedades explicables.',
  manual: 'Guía práctica del flujo: subir CV, generar grafo, vincular con IA y construir evidencia.',
  mensajes: 'Conversaciones para explorar complementariedades entre grafos.',
  observatorio: 'Seguimiento institucional de qué conexiones sugeridas por la IA se volvieron útiles.',
  recursos: 'Lo que cada persona pone a disposición de la red, aunque no sepa para qué servirá.',
};

function showTab(id, btn, push = true) {
  document.querySelectorAll('.tabs').forEach(t => t.classList.remove('active'));
  document.getElementById(id)?.classList.add('active');
  document.querySelectorAll('button[data-nav]').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('tabHelp').textContent = HELP[id] || '';
  if (push && ROUTES[id]) history.pushState({ tab: id }, '', ROUTES[id]);

  if (id === 'rizoma') renderYourRizoma();
  if (id === 'proyectos') loadProjects();
  if (id === 'credenciales') loadCredentials();
  if (id === 'mensajes') loadMessages();
  if (id === 'perfil') { loadCredentialsForProfile(); cargarSolicitudesPrivacidad(); verificarAvisoPrivacidad(); renderVisibilidad(); }
  if (id === 'observatorio') { loadObservatorio(); loadActividades(); loadDemanda(); loadPuentes(); loadTriangulacion(); resumenEvaluacion(); }
  if (id === 'matches') loadNotifications();
  if (id === 'recursos') { loadRecursos(); cargarSeguimiento(); }
  if (id === 'perfil') cargarMisRecursos();
}

async function loadCredentialsForProfile() {
  try {
    const creds = await api('GET', '/api/credentials');
    const el = document.getElementById('profileCredsFeed');
    if (!el) return;
    if (!creds || creds.length === 0) {
      el.innerHTML = '<p style="color:var(--muted);font-size:13px">Aún no tenés credenciales. Primero vinculá tu grafo y construí una evidencia validable.</p>';
      return;
    }
    el.innerHTML = creds.map(renderCredential).join('');
  } catch {}
}

function tabFromPath() {
  const p = location.pathname.slice(BASE_URL.length).replace(/\/$/, '') || '/';
  return { '/perfil': 'perfil', '/tu-rizoma': 'rizoma', '/proyectos': 'proyectos', '/credenciales': 'credenciales', '/matches': 'matches', '/manual': 'manual', '/mensajes': 'mensajes', '/observatorio': 'observatorio', '/recursos': 'recursos' }[p] || 'inicio';
}

window.addEventListener('popstate', () => {
  const id = tabFromPath();
  showTab(id, document.querySelector(`[data-nav="${id}"]`), false);
});

// ── Helpers ────────────────────────────────────────────────────────────────────
function toggleBtn(btn, onMsg, offMsg) {
  const on = btn.dataset.on === '1';
  btn.dataset.on = on ? '' : '1';
  btn.classList.toggle('on', !on);
  toast(on ? offMsg : onMsg);
}
function doAction(msg, type) { toast(msg, type || 'ok'); }

function toast(msg, type) {
  const el = document.createElement('div');
  el.className = 'toast ' + (type || 'ok');
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 3400);
}

function formatDate(iso) {
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return 'hace menos de 1 h';
  if (h < 24) return `hace ${h} h`;
  return `hace ${Math.floor(h / 24)} días`;
}

// ── Dark mode ──────────────────────────────────────────────────────────────────
function toggleDark() {
  const next = document.documentElement.dataset.theme === 'dark' ? '' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('aa-theme', next);
  document.getElementById('darkBtn').textContent = next === 'dark' ? '☀️' : '🌙';
}
(function () {
  const t = localStorage.getItem('aa-theme') || '';
  document.documentElement.dataset.theme = t;
  if (t === 'dark') document.getElementById('darkBtn').textContent = '☀️';
})();

// ── Start ──────────────────────────────────────────────────────────────────────
bootApp();

// Institutional review UI
function canReviewApplications() {
  return currentUser && ["teacher", "org", "admin"].includes(currentUser.role);
}

const _rizomaBaseRenderProjectCard = renderProjectCard;
renderProjectCard = function(p) {
  const html = _rizomaBaseRenderProjectCard(p);
  if (!canReviewApplications()) return html;
  const projectId = escapeAttr(p.id);
  const review = '<div class="review-actions"><button class="btn secondary" onclick="toggleProjectApplications(\'' + projectId + '\',this)">Revisar conversaciones</button></div><div class="review-panel" id="review-' + projectId + '"></div>';
  return html.replace('</article>', review + '</article>');
};

async function toggleProjectApplications(projectId, btn) {
  const panel = document.getElementById("review-" + projectId);
  if (!panel) return;
  if (panel.dataset.open === "1") {
    panel.dataset.open = "";
    panel.innerHTML = "";
    return;
  }
  btn.disabled = true;
  try {
    const apps = await api("GET", "/api/projects/" + projectId + "/applications");
    panel.dataset.open = "1";
    panel.innerHTML = renderApplicationsPanel(apps || []);
  } catch (e) {
    toast("No pude cargar conversaciones: " + e.message, "warn");
  } finally {
    btn.disabled = false;
  }
}

function renderApplicationsPanel(apps) {
  if (!apps.length) return '<div class="review-empty">Sin conversaciones abiertas todavía.</div>';
  return apps.map(function(a) {
    const status = a.status === "accepted" ? "Validada" : a.status === "rejected" ? "No aprobada" : "Pendiente";
    const badge = a.status === "accepted" ? "green" : a.status === "rejected" ? "amber" : "blue";
    let actions = "";
    if (a.status === "pending") {
      actions = '<div class="review-buttons"><button class="btn" onclick="acceptApplication(\'' + escapeAttr(a.id) + '\',this)">Validar</button><button class="btn secondary" onclick="rejectApplication(\'' + escapeAttr(a.id) + '\',this)">No aprobar</button></div>';
    }
    return '<div class="review-row"><div><strong>' + escapeHtml(a.user_name) + '</strong><span>' + escapeHtml(a.user_institution || a.user_email) + '</span></div><span class="badge ' + badge + '">' + status + '</span><p>' + escapeHtml(a.message || "Sin mensaje.") + '</p>' + actions + '</div>';
  }).join("");
}

async function acceptApplication(applicationId, btn) {
  const evidence = prompt("Nota de evidencia institucional (rol, entregable o aprendizaje validado):", "Participación validada por el equipo responsable del proyecto.");
  if (evidence === null) return;
  const hoursRaw = prompt("Horas acreditadas (opcional):", "0");
  if (hoursRaw === null) return;
  const hours = Math.max(0, parseInt(hoursRaw, 10) || 0);
  btn.disabled = true;
  try {
    await api("POST", "/api/projects/applications/" + applicationId + "/accept", { evidence_note: evidence, hours, tags: [] });
    toast("Credencial verificada institucionalmente.", "success");
    if (document.getElementById("proyectos").classList.contains("active")) loadProjects();
    if (document.getElementById("credenciales").classList.contains("active")) loadCredentials();
  } catch (e) {
    toast("No pude validar: " + e.message, "warn");
    btn.disabled = false;
  }
}

async function rejectApplication(applicationId, btn) {
  if (!confirm("Marcar esta conversación como no aprobada?")) return;
  btn.disabled = true;
  try {
    await api("POST", "/api/projects/applications/" + applicationId + "/reject");
    toast("Exploración marcada como no aprobada.", "success");
    if (document.getElementById("proyectos").classList.contains("active")) loadProjects();
  } catch (e) {
    toast("No pude actualizar: " + e.message, "warn");
    btn.disabled = false;
  }
}



/* ---------- Mapa del rizoma ----------
   Canvas 2D con layout por clusters: cada nodo se ancla al area tematica a la
   que pertenece, asi la posicion dice algo. La simulacion se ve acomodarse y
   despues queda una deriva minima, para que el mapa no parezca una foto.
   Sigue el patron del mapa del observatorio.                                  */

const RG = {
  canvas: null, ctx: null, tip: null,
  nodos: [], aristas: [], porId: new Map(), anclas: new Map(), clusters: [],
  zoom: 1, panX: 0, panY: 0, w: 0, h: 0, escala: 1,
  sel: null, hover: null, filtro: 'todos', leyendaPlegada: false,
  corriendo: false, ticks: 0, vivo: false, bucle: false,
  arrastrando: false, movio: false, lastX: 0, lastY: 0, nodoArrastrado: null,
};

const RG_PALETA = ['#c8102e', '#2b70b3', '#3f8a59', '#b57914', '#7b5ea7',
                   '#0f8c8c', '#b8556f', '#5c7a2e', '#8a6a3d', '#4a6fa5', '#8b8f96'];
const RG_REL = { offers: 'rgba(200,16,46,.55)', wants: 'rgba(43,112,179,.55)', interest: 'rgba(63,138,89,.5)' };

function rgArea(n) { return n.macro || 'Sin clasificar'; }

function rgColorArea(n) {
  const i = RG.clusters.indexOf(rgArea(n));
  return RG_PALETA[(i < 0 ? RG_PALETA.length - 1 : i) % RG_PALETA.length];
}

function rgRadio(n) {
  if (n.kind === 'yo') return 17;
  if (n.kind === 'tema') return Math.min(13, 6.5 + (n.rareza || 0) * 2.6);
  return Math.min(14, 7 + (n.grado || 0) * 1.2);
}

function rgCorto(t, max) {
  t = String(t || '');
  return t.length > max ? t.slice(0, max - 1) + '…' : t;
}

/* Presupuesto de etiquetas: siempre las personas y los temas mas raros; el
   resto aparece al acercar o al seleccionar. Evita la sopa de texto. */
function rgLleva(n, activo) {
  if (activo || n === RG.hover || n === RG.sel) return true;
  if (n.kind === 'yo') return true;
  if (RG.zoom > 1.22) return true;
  if (RG.filtro === 'indirectos') return n.kind !== 'tema' || (n.rareza || 0) >= 1.45;
  if (n.kind === 'tema') return (n.rareza || 0) >= 1.8;
  if (n.kind === 'persona' || n.kind === 'indirecto') return RG.nodos.length <= 28 || (n.grado || 0) >= 3;
  return false;
}

function rgNodoVisible(n) {
  if (!n) return false;
  if (RG.filtro === 'todos') return true;
  if (n.kind === 'yo') return true;
  if (RG.filtro === 'personas') return n.kind === 'persona' || n.kind === 'indirecto';
  if (RG.filtro === 'temas') return n.kind === 'tema';
  if (RG.filtro === 'indirectos') {
    if (n.kind === 'indirecto') return true;
    return RG.aristas.some(l => {
      const a = RG.porId.get(l.source), b = RG.porId.get(l.target);
      return (a && b) && (a.kind === 'indirecto' || b.kind === 'indirecto') && (a === n || b === n);
    });
  }
  return true;
}

function rgAristaVisible(l) {
  const a = RG.porId.get(l.source), b = RG.porId.get(l.target);
  return !!(a && b && rgNodoVisible(a) && rgNodoVisible(b));
}

function rgSyncFiltro() {
  document.querySelectorAll('[data-rg-filter]').forEach(b => {
    const activo = b.dataset.rgFilter === RG.filtro;
    b.classList.toggle('active', activo);
    b.setAttribute('aria-pressed', activo ? 'true' : 'false');
  });
}

function rgSetFiltro(modo, btn) {
  RG.filtro = modo || 'todos';
  RG.sel = null; RG.hover = null;
  rgSyncFiltro();
  rgEncuadrar();
}

function rgToggleLeyenda(btn) {
  RG.leyendaPlegada = !RG.leyendaPlegada;
  document.querySelectorAll('.rg-legend').forEach(el => el.classList.toggle('plegada', RG.leyendaPlegada));
  if (btn) btn.textContent = RG.leyendaPlegada ? 'Leyenda' : 'Ocultar leyenda';
}

function rgPrepararClusters() {
  const peso = new Map();
  RG.nodos.forEach(n => peso.set(rgArea(n), (peso.get(rgArea(n)) || 0) + 1));
  RG.clusters = [...peso.entries()].sort((a, b) => b[1] - a[1]).map(x => x[0]);

  const total = RG.clusters.length;
  const cols = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(total * 1.6))));
  const filas = Math.max(1, Math.ceil(total / cols));
  RG.anclas.clear();
  RG.clusters.forEach((c, i) => {
    const col = i % cols, fila = Math.floor(i / cols);
    const anchoCelda = RG.w * RG.escala / (cols + 0.05), altoCelda = RG.h * RG.escala / (filas + 0.2);
    RG.anclas.set(c, {
      x: anchoCelda * 0.55 + col * anchoCelda + ((fila % 2) - 0.5) * anchoCelda * 0.22,
      y: altoCelda * 0.65 + fila * altoCelda,
    });
  });
}

function rgLayout(alpha) {
  const nodos = RG.nodos;
  for (const l of RG.aristas) {
    const a = RG.porId.get(l.source), b = RG.porId.get(l.target);
    if (!a || !b || !rgAristaVisible(l)) continue;
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
    const mismaArea = rgArea(a) === rgArea(b);
    const ideal = (mismaArea ? 112 : 180) * RG.escala;
    const f = (d - ideal) * 0.055 * alpha;
    a.vx += dx / d * f; a.vy += dy / d * f;
    b.vx -= dx / d * f; b.vy -= dy / d * f;
  }
  for (let i = 0; i < nodos.length; i++) {
    for (let j = i + 1; j < nodos.length; j++) {
      const a = nodos[i], b = nodos[j];
      const dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy + 1;
      const min = a.r + b.r + (rgArea(a) === rgArea(b) ? 46 : 66) * RG.escala;
      const f = Math.min(120, (min * min / d2)) * 0.02 * alpha;
      const d = Math.sqrt(d2);
      a.vx -= dx / d * f; a.vy -= dy / d * f;
      b.vx += dx / d * f; b.vy += dy / d * f;
    }
  }
  for (const n of nodos) {
    if (n === RG.nodoArrastrado) { n.vx = n.vy = 0; continue; }
    const ancla = RG.anclas.get(rgArea(n)) || { x: RG.w / 2, y: RG.h / 2 };
    const tira = n.kind === 'yo' ? 0.05 : n.kind === 'tema' ? 0.016 : 0.011;
    n.vx += (ancla.x - n.x) * tira * alpha;
    n.vy += (ancla.y - n.y) * tira * alpha;
    if (RG.vivo) {
      n.vx += Math.cos(Date.now() / 1300 + n.fase) * 0.006;
      n.vy += Math.sin(Date.now() / 1500 + n.fase) * 0.006;
    }
    const tope = RG.vivo && !RG.corriendo ? 1.6 : 4.5;
    n.vx = Math.max(-tope, Math.min(tope, n.vx));
    n.vy = Math.max(-tope, Math.min(tope, n.vy));
    n.vx *= 0.86; n.vy *= 0.86;
    n.x += n.vx; n.y += n.vy;
  }
}

function rgConectado(n) {
  if (!RG.sel) return true;
  if (n === RG.sel) return true;
  return RG.aristas.some(l => (l.source === RG.sel.id && l.target === n.id) ||
                              (l.target === RG.sel.id && l.source === n.id));
}

function rgPintar() {
  const ctx = RG.ctx;
  if (!ctx) return;
  ctx.clearRect(0, 0, RG.w, RG.h);
  ctx.save();
  ctx.translate(RG.panX, RG.panY);
  ctx.scale(RG.zoom, RG.zoom);

  for (const l of RG.aristas) {
    const a = RG.porId.get(l.source), b = RG.porId.get(l.target);
    if (!a || !b || !rgAristaVisible(l)) continue;
    const activa = RG.sel && (l.source === RG.sel.id || l.target === RG.sel.id);
    ctx.globalAlpha = RG.sel ? (activa ? 0.95 : 0.06) : 0.5;
    ctx.strokeStyle = RG_REL[l.relacion] || 'rgba(140,140,140,.4)';
    ctx.lineWidth = (activa ? 2.1 : 1.15) / RG.zoom;
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
    const curva = Math.min(22, 6 + d * 0.045);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.quadraticCurveTo((a.x + b.x) / 2 - dy / d * curva, (a.y + b.y) / 2 + dx / d * curva, b.x, b.y);
    ctx.stroke();
  }

  const orden = RG.nodos.filter(rgNodoVisible).sort((a, b) => (a === RG.sel ? 1 : 0) - (b === RG.sel ? 1 : 0) || a.r - b.r);
  for (const n of orden) {
    const activo = n === RG.sel, encima = n === RG.hover;
    const conectado = rgConectado(n);
    ctx.globalAlpha = (RG.sel && !conectado) ? 0.14 : 1;
    ctx.beginPath();
    ctx.fillStyle = n.kind === 'tema' ? '#fff' : rgColorArea(n);
    ctx.strokeStyle = n.kind === 'tema' ? rgColorArea(n) : (activo ? '#1f2937' : 'rgba(255,255,255,.9)');
    ctx.lineWidth = (n.kind === 'tema' ? 2.4 : activo ? 2.8 : 1.6) / RG.zoom;
    ctx.arc(n.x, n.y, n.r + (encima ? 2.5 / RG.zoom : 0), 0, Math.PI * 2);
    ctx.fill(); ctx.stroke();
    if (n.kind === 'indirecto') {
      ctx.beginPath();
      ctx.setLineDash([3 / RG.zoom, 3 / RG.zoom]);
      ctx.strokeStyle = rgColorArea(n);
      ctx.lineWidth = 1.6 / RG.zoom;
      ctx.arc(n.x, n.y, n.r + 4 / RG.zoom, 0, Math.PI * 2);
      ctx.stroke(); ctx.setLineDash([]);
    }

  }

  // Segunda pasada: las etiquetas se dibujan despues de todos los circulos y en
  // orden de importancia, descartando la que se solapa con una ya puesta. Sin
  // esto, en las zonas densas los nombres se pisan entre si.
  const prioridad = n => n === RG.sel ? 0 : n === RG.hover ? 1 : n.kind === 'yo' ? 2
    : n.kind === 'indirecto' ? 3 : n.kind === 'persona' ? 4 - Math.min(0.9, (n.grado || 0) / 12)
    : 6 - Math.min(1.5, n.rareza || 0);
  const puestas = [];
  const chocan = (a, b) => !(a.x2 < b.x1 || b.x2 < a.x1 || a.y2 < b.y1 || b.y2 < a.y1);

  for (const n of RG.nodos.filter(rgNodoVisible).sort((a, b) => prioridad(a) - prioridad(b))) {
    const activo = n === RG.sel, encima = n === RG.hover;
    if (!rgLleva(n, activo)) continue;
    const conectado = rgConectado(n);
    const texto = rgCorto(n.label, activo || encima ? 40 : n.kind === 'tema' ? 20 : 24);
    const tam = Math.max(9, Math.min(activo ? 14 : 12, 11 / RG.zoom));
    ctx.font = `${n.kind === 'tema' ? 600 : 800} ${tam}px ui-sans-serif, system-ui, sans-serif`;
    const ancho = ctx.measureText(texto).width;
    const y = n.y + n.r + 4 / RG.zoom;
    const caja = { x1: n.x - ancho / 2 - 2, x2: n.x + ancho / 2 + 2, y1: y - 1, y2: y + tam + 1 };
    if (!activo && !encima && puestas.some(p => chocan(caja, p))) continue;
    puestas.push(caja);
    ctx.globalAlpha = (RG.sel && !conectado) ? 0.12 : (activo || encima ? 1 : 0.78);
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.strokeStyle = 'rgba(255,255,255,.92)';
    ctx.lineWidth = 3.4 / RG.zoom;
    ctx.strokeText(texto, n.x, y);
    ctx.fillStyle = n.kind === 'tema' ? '#5a6472' : '#1f2937';
    ctx.fillText(texto, n.x, y);
  }
  ctx.globalAlpha = 1;
  ctx.restore();
}

function rgPaso() {
  if (!RG.corriendo) return;
  RG.ticks++;
  rgLayout(Math.max(0.03, 1 - RG.ticks / 260));
  rgPintar();
  if (RG.ticks < 270) requestAnimationFrame(rgPaso);
  else { RG.corriendo = false; rgEncuadrar(); }
}

function rgBucleVivo() {
  if (RG.vivo && !RG.corriendo && !RG.arrastrando) rgLayout(0.02);
  if (RG.vivo || RG.corriendo) rgPintar();
  requestAnimationFrame(rgBucleVivo);
}

function rgEncuadrar() {
  if (!RG.nodos.length) return;
  const visibles = RG.nodos.filter(rgNodoVisible);
  const base = visibles.length ? visibles : RG.nodos;
  const xs = base.map(n => n.x), ys = base.map(n => n.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const margen = 95;
  const k = Math.max(0.18, Math.min(1.25,
    Math.min(RG.w / (maxX - minX + margen * 2), RG.h / (maxY - minY + margen * 2))));
  RG.zoom = k;
  RG.panX = RG.w / 2 - (minX + maxX) / 2 * k;
  RG.panY = RG.h / 2 - (minY + maxY) / 2 * k;
  rgPintar();
}

function rizomaZoom(factor, cx, cy) {
  const px = cx === undefined ? RG.w / 2 : cx;
  const py = cy === undefined ? RG.h / 2 : cy;
  const k = Math.max(0.35, Math.min(3.5, RG.zoom * factor));
  RG.panX = px - (px - RG.panX) * (k / RG.zoom);
  RG.panY = py - (py - RG.panY) * (k / RG.zoom);
  RG.zoom = k;
  rgPintar();
}

function rizomaCentrar() { RG.sel = null; rgEncuadrar(); }

function rizomaVivo(on) { RG.vivo = !!on; if (RG.vivo) rgPintar(); }

function toggleModoPresentacion(btn) {
  const view = document.getElementById('rizomaView');
  if (!view) return;
  const on = !view.classList.contains('presentacion');
  view.classList.toggle('presentacion', on);
  if (btn) btn.textContent = on ? 'Salir presentación' : 'Modo presentación';
  if (on) {
    rgSetFiltro('indirectos');
    RG.leyendaPlegada = true;
    document.querySelectorAll('.rg-legend').forEach(el => el.classList.add('plegada'));
    setTimeout(() => { rgSetFiltro('indirectos'); rgDimensionar(); rgEncuadrar(); }, 180);
  } else {
    rgSetFiltro('todos');
    setTimeout(() => { rgDimensionar(); rgEncuadrar(); }, 120);
  }
}

function exportarGrafo() {
  const canvas = document.getElementById('rgCanvas');
  if (!canvas) return toast('No hay grafo para exportar.', 'warn');
  const tmp = document.createElement('canvas');
  tmp.width = canvas.width; tmp.height = canvas.height;
  const ctx = tmp.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, tmp.width, tmp.height);
  ctx.drawImage(canvas, 0, 0);
  const a = document.createElement('a');
  a.download = 'rizoma-grafo.png';
  a.href = tmp.toDataURL('image/png');
  a.click();
  toast('Grafo exportado como imagen.', 'success');
}

function rgNodoEn(mx, my) {
  const x = (mx - RG.panX) / RG.zoom, y = (my - RG.panY) / RG.zoom;
  for (let i = RG.nodos.length - 1; i >= 0; i--) {
    const n = RG.nodos[i];
    if (!rgNodoVisible(n)) continue;
    if (Math.hypot(x - n.x, y - n.y) <= n.r + 6 / RG.zoom) return n;
  }
  return null;
}

function rgLeyenda() {
  const cont = document.getElementById(RG.idLeyenda || 'rgLeyenda');
  if (!cont) return;
  const resumen = `<strong>Áreas</strong><em>${RG.nodos.length} nodos · ${RG.aristas.length} vínculos</em>`;
  cont.innerHTML = resumen + RG.clusters.slice(0, 7).map((c, i) =>
    `<span><i class="dot" style="background:${RG_PALETA[i % RG_PALETA.length]}"></i>${escapeHtml(c)}</span>`
  ).join('') +
  '<span class="sep"></span>' +
  '<span><i class="linea offers"></i>ofrece</span>' +
  '<span><i class="linea wants"></i>quiere aprender</span>' +
  '<span><i class="linea interest"></i>interés</span>';
  cont.classList.toggle('plegada', RG.leyendaPlegada);
}

function rgDimensionar() {
  const caja = RG.canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  RG.w = caja.width || 900;
  RG.h = caja.height || 620;
  RG.canvas.width = RG.w * dpr;
  RG.canvas.height = RG.h * dpr;
  RG.ctx = RG.canvas.getContext('2d');
  RG.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function rgDibujar(data, ids) {
  ids = ids || {};
  RG.canvas = document.getElementById(ids.canvas || 'rgCanvas');
  RG.tip = document.getElementById(ids.tip || 'rgTip');
  RG.idLeyenda = ids.leyenda || 'rgLeyenda';
  if (!RG.canvas) return;
  rgDimensionar();

  const grados = {};
  (data.edges || []).forEach(e => {
    grados[e.source] = (grados[e.source] || 0) + 1;
    grados[e.target] = (grados[e.target] || 0) + 1;
  });

  RG.nodos = (data.nodes || []).map((n, i) => ({
    ...n,
    grado: grados[n.id] || 0,
    fase: i * 1.7,
    vx: 0, vy: 0,
  }));
  RG.nodos.forEach(n => { n.r = rgRadio(n); });
  RG.aristas = data.edges || [];
  RG.porId = new Map(RG.nodos.map(n => [n.id, n]));

  // Con muchos nodos el lienzo se apelmaza: se expande el layout y el encuadre
  // compensa alejando, asi la separacion relativa se mantiene.
  RG.escala = Math.max(1.12, Math.sqrt(RG.nodos.length / 30));
  rgPrepararClusters();
  const totalPorCluster = new Map();
  RG.nodos.forEach(n => totalPorCluster.set(rgArea(n), (totalPorCluster.get(rgArea(n)) || 0) + 1));
  const vistosPorCluster = new Map();
  RG.nodos.forEach((n, i) => {
    const area = rgArea(n);
    const a = RG.anclas.get(area) || { x: RG.w / 2, y: RG.h / 2 };
    const total = totalPorCluster.get(area) || 1;
    const idx = vistosPorCluster.get(area) || 0;
    vistosPorCluster.set(area, idx + 1);
    const porAnillo = 7;
    const anillo = Math.floor(idx / porAnillo);
    const enAnillo = Math.min(porAnillo, Math.max(1, total - anillo * porAnillo));
    const ang = (idx % porAnillo) / enAnillo * Math.PI * 2 + anillo * 0.38 + i * 0.013;
    const radio = (n.kind === 'yo' ? 0 : 58 + anillo * 46) * RG.escala;
    n.x = a.x + Math.cos(ang) * radio;
    n.y = a.y + Math.sin(ang) * radio;
  });
  rgLeyenda();

  RG.zoom = 1; RG.panX = 0; RG.panY = 0; RG.sel = null; RG.vivo = false; RG.filtro = 'todos'; RG.leyendaPlegada = false;
  rgSyncFiltro();
  RG.corriendo = true; RG.ticks = 0;
  requestAnimationFrame(rgPaso);
  if (!RG.bucle) { RG.bucle = true; requestAnimationFrame(rgBucleVivo); }

  if (RG.canvas.dataset.listo) return;
  RG.canvas.dataset.listo = '1';

  RG.canvas.addEventListener('wheel', ev => {
    ev.preventDefault();
    const c = RG.canvas.getBoundingClientRect();
    rizomaZoom(ev.deltaY < 0 ? 1.12 : 0.89, ev.clientX - c.left, ev.clientY - c.top);
  }, { passive: false });

  RG.canvas.addEventListener('pointerdown', ev => {
    const c = RG.canvas.getBoundingClientRect();
    RG.arrastrando = true; RG.movio = false;
    RG.lastX = ev.clientX; RG.lastY = ev.clientY;
    RG.nodoArrastrado = rgNodoEn(ev.clientX - c.left, ev.clientY - c.top);
    RG.canvas.setPointerCapture && RG.canvas.setPointerCapture(ev.pointerId);
  });

  RG.canvas.addEventListener('pointermove', ev => {
    const c = RG.canvas.getBoundingClientRect();
    const mx = ev.clientX - c.left, my = ev.clientY - c.top;
    if (RG.arrastrando) {
      RG.movio = true;
      if (RG.nodoArrastrado) {
        RG.nodoArrastrado.x += (ev.clientX - RG.lastX) / RG.zoom;
        RG.nodoArrastrado.y += (ev.clientY - RG.lastY) / RG.zoom;
      } else {
        RG.panX += ev.clientX - RG.lastX;
        RG.panY += ev.clientY - RG.lastY;
      }
      RG.lastX = ev.clientX; RG.lastY = ev.clientY;
      rgPintar();
      return;
    }
    const n = rgNodoEn(mx, my);
    if (n !== RG.hover) { RG.hover = n; rgPintar(); }
    RG.canvas.style.cursor = n ? 'pointer' : 'grab';
    if (n && RG.tip) {
      RG.tip.innerHTML = `<strong>${escapeHtml(n.label)}</strong>` +
        (n.kind === 'tema'
          ? `<span>tema · ${n.personas} persona${n.personas === 1 ? '' : 's'} en la red</span>`
          : `<span>${n.kind === 'yo' ? 'vos' : n.kind === 'indirecto' ? 'vínculo indirecto' : 'persona'} · ${escapeHtml(rgArea(n))}</span>`);
      RG.tip.style.left = (mx + 14) + 'px';
      RG.tip.style.top = (my + 14) + 'px';
      RG.tip.classList.add('ver');
    } else if (RG.tip) RG.tip.classList.remove('ver');
  });

  const soltar = ev => {
    if (RG.arrastrando && !RG.movio) {
      const c = RG.canvas.getBoundingClientRect();
      const n = rgNodoEn(ev.clientX - c.left, ev.clientY - c.top);
      RG.sel = (RG.sel === n) ? null : n;
      rgPintar();
    }
    RG.arrastrando = false; RG.nodoArrastrado = null;
  };
  RG.canvas.addEventListener('pointerup', soltar);
  RG.canvas.addEventListener('pointerleave', () => {
    RG.arrastrando = false; RG.nodoArrastrado = null;
    RG.hover = null;
    if (RG.tip) RG.tip.classList.remove('ver');
    rgPintar();
  });
  window.addEventListener('resize', () => { rgDimensionar(); rgEncuadrar(); });
}

async function cargarRizomaGrafo() {
  if (!document.getElementById('rgCanvas')) return;
  try {
    const data = await api('GET', '/api/users/me/rizoma-grafo');
    if (!data || !data.nodes || !data.nodes.length) return;
    rgDibujar(data);
  } catch (err) {
    console.error('rizoma-grafo', err);
  }
}

/* Camino indirecto: por que dos personas que no comparten nada deberian conocerse. */
function renderCaminoIndirecto(camino) {
  if (!camino || camino.length < 5) return '';
  const paso = camino.map(n => `<span class="camino-nodo ${n.tipo}">${escapeHtml(n.label)}</span>`).join('<i>→</i>');
  return `<div class="camino-indirecto"><strong>Se conectan a través de</strong><div class="camino-pasos">${paso}</div></div>`;
}


/* ---------- Red completa: la vista de conjunto, a pantalla completa ----------
   Complementa al vecindario. Aca aparecen todas las personas con todos sus
   temas, no solo los que comparten con vos. Sirve para leer la forma de la
   red, no para decidir con quien hablar.                                      */

async function abrirRedCompleta() {
  let capa = document.getElementById('redCompleta');
  if (!capa) {
    capa = document.createElement('div');
    capa.id = 'redCompleta';
    capa.className = 'red-completa';
    capa.innerHTML = `
      <div class="rc-barra">
        <div><strong>Red completa</strong><span id="rcResumen">cargando…</span></div>
        <div class="rc-acciones">
          <button class="rg-btn" onclick="rizomaZoom(1.35)" title="Acercar">+</button>
          <button class="rg-btn" onclick="rizomaZoom(0.74)" title="Alejar">−</button>
          <button class="rg-btn wide" onclick="rizomaCentrar()">Centrar</button>
          <button class="rg-btn wide" onclick="rgToggleLeyenda(this)">Ocultar leyenda</button>
          <button class="rg-btn wide" id="rcVivoBtn" data-off="1" onclick="const on=this.dataset.off==='1';rizomaVivo(on);this.dataset.off=on?'0':'1';this.textContent=on?'Pausar':'Animar'">Animar</button>
          <button class="rg-btn wide rc-cerrar" onclick="cerrarRedCompleta()">Cerrar</button>
        </div>
      </div>
      <div class="rg-filter rc-filter" aria-label="Filtro de red completa">
        <button class="active" data-rg-filter="todos" onclick="rgSetFiltro('todos',this)">Todo</button>
        <button data-rg-filter="personas" onclick="rgSetFiltro('personas',this)">Personas</button>
        <button data-rg-filter="temas" onclick="rgSetFiltro('temas',this)">Temas</button>
        <button data-rg-filter="indirectos" onclick="rgSetFiltro('indirectos',this)">Indirectos</button>
      </div>
      <canvas id="rcCanvas" class="rc-canvas"></canvas>
      <div id="rcTip" class="rg-tip"></div>
      <div id="rcLeyenda" class="rg-legend"></div>`;
    document.body.appendChild(capa);
  }
  capa.classList.add('abierta');
  document.body.style.overflow = 'hidden';
  try {
    const data = await api('GET', '/api/users/red-completa');
    const r = data.resumen || {};
    const res = document.getElementById('rcResumen');
    if (res) res.textContent = `${r.personas} personas · ${r.temas} temas · ${r.aristas} vínculos`;
    rgDibujar(data, { canvas: 'rcCanvas', tip: 'rcTip', leyenda: 'rcLeyenda' });
  } catch (err) {
    console.error('red-completa', err);
  }
}

function cerrarRedCompleta() {
  const capa = document.getElementById('redCompleta');
  if (capa) capa.classList.remove('abierta');
  document.body.style.overflow = '';
  cargarRizomaGrafo();
}

document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape') {
    const capa = document.getElementById('redCompleta');
    if (capa && capa.classList.contains('abierta')) cerrarRedCompleta();
  }
});


// ── Observatorio de actividades emergentes ──────────────────────────────────────
// Las cifras y las actividades salen del sistema (grafo del conjunto y última
// corrida guardada), no de una lista escrita a mano.
function renderObservatorioDemo() {
  return `
    <section class="observatorio-demo">
      <div class="obs-alert"><strong>Modo demostrativo</strong><span>${escapeHtml(currentUser?.conjunto_etiqueta || 'Red general')}: perfiles ficticios que sirven para mostrar qué podría monitorear Rizoma con datos reales, consentimiento y revisión institucional.</span></div>
      <div class="obs-grid">
        <article><strong data-metrica="personas">…</strong><span>perfiles del conjunto</span></article>
        <article><strong data-metrica="temas">…</strong><span>temas detectados</span></article>
        <article><strong data-metrica="aristas">…</strong><span>vínculos persona-tema</span></article>
        <article><strong id="obsCantidadActividades">…</strong><span>actividades emergentes</span></article>
      </div>
      <div class="obs-table" id="obsActividades"><p class="muted">Cargando actividades…</p></div>
      <p class="muted">Estabilidad: fracción de cálculos con distintas particiones del grafo en que la actividad reaparece. Lectura institucional: Rizoma no predice el futuro laboral; registra señales tempranas para abrir preguntas, diseñar actividades y evaluar si los cruces producen valor real.</p>
    </section>`;
}

async function cargarObservatorioDemo() {
  cargarMetricasConjunto();
  const tabla = document.getElementById('obsActividades');
  const cantidad = document.getElementById('obsCantidadActividades');
  try {
    const items = await api('GET', `/api/actividades-emergentes?alcance=${alcanceActual()}`) || [];
    if (cantidad) cantidad.textContent = items.length;
    if (!tabla) return;
    tabla.innerHTML = items.length ? items.map(a => `
      <div class="obs-row">
        <span>${a.temas.map(escapeHtml).join(' + ')} · ${a.n_personas} personas · demanda ${a.demanda} · oferta ${a.oferta}</span>
        <strong>${escapeHtml(a.titulo)}</strong>
        <em>estabilidad ${Math.round((a.estabilidad || 0) * 100)}%</em>
      </div>`).join('') : '<p class="muted">Todavía no se calcularon actividades emergentes para este conjunto.</p>';
  } catch (e) {
    if (tabla) tabla.innerHTML = `<p class="muted">No pude cargar las actividades: ${escapeHtml(e.message || e)}</p>`;
  }
}

async function loadObservatorio() {
  const body = document.getElementById('observatorioBody');
  if (!body) return;
  body.innerHTML = '<p style="color:var(--muted);font-size:13px">Cargando…</p>';
  try {
    const rows = await api('GET', '/api/users/admin/dashboard/metricas');
    if (!rows || rows.length === 0) {
      body.innerHTML = renderObservatorioDemo();
      cargarObservatorioDemo();
      return;
    }
    body.innerHTML = rows.map(r => {
      const mes = new Date(r.mes).toLocaleDateString('es-AR', { month: 'long', year: 'numeric' });
      const utiles = r.vinculos_utiles || 0;
      const noUtiles = r.vinculos_no_utiles || 0;
      const colab = r.colaboraciones_generadas || 0;
      const total = r.sugerencias_totales || 0;
      const pctUtiles = total ? Math.round((utiles / total) * 100) : 0;
      return `
        <div class="observatorio-mes" style="margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--line, #e5e1dc)">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">
            <strong style="text-transform:capitalize">${escapeHtml(mes)}</strong>
            <span style="color:var(--muted);font-size:13px">${total} sugerencias · ${pctUtiles}% con resultado útil</span>
          </div>
          <div style="display:flex;height:10px;border-radius:6px;overflow:hidden;background:var(--line,#e5e1dc)">
            <div style="width:${total ? (utiles / total) * 100 : 0}%;background:#2f8f5b" title="Útiles: ${utiles}"></div>
            <div style="width:${total ? (colab / total) * 100 : 0}%;background:#1f5c99" title="Colaboraciones: ${colab}"></div>
            <div style="width:${total ? (noUtiles / total) * 100 : 0}%;background:#c8102e" title="No útiles: ${noUtiles}"></div>
          </div>
          <div style="display:flex;gap:14px;margin-top:6px;font-size:12px;color:var(--muted)">
            <span>🟢 Útiles: ${utiles}</span>
            <span>🔵 Colaboraciones: ${colab}</span>
            <span>🔴 No útiles: ${noUtiles}</span>
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    // Las métricas institucionales son solo para docentes, organizaciones y
    // administración; el resto ve el modo demostrativo de su conjunto.
    console.error('observatorio', e);
    body.innerHTML = renderObservatorioDemo();
    cargarObservatorioDemo();
  }
}

// ── Recursos que cada persona pone a disposición (traído de Rizoma Afadeco) ────
let misRecursos = [], tiposRecurso = {}, recursosRed = [], recFiltro = 'todos';

async function cargarMisRecursos() {
  const el = document.getElementById('misRecursosLista');
  if (!el) return;
  try {
    const r = await api('GET', '/api/recursos/mios');
    misRecursos = r.recursos || []; tiposRecurso = r.tipos || {};
    const sel = document.getElementById('recTipo');
    if (sel && !sel.options.length) {
      sel.innerHTML = Object.entries(tiposRecurso).map(([k, v]) => `<option value="${escapeAttr(k)}">${escapeHtml(v)}</option>`).join('');
      sel.onchange = () => { document.getElementById('recAceptoFila').hidden = sel.value !== 'persona'; };
      sel.onchange();
    }
    renderMisRecursos();
  } catch { el.innerHTML = '<p class="muted">No se pudieron cargar tus recursos.</p>'; }
}

function renderMisRecursos() {
  const el = document.getElementById('misRecursosLista');
  if (!el) return;
  el.innerHTML = misRecursos.length ? misRecursos.map((r, i) => `
    <div class="rec-mio"><div><span class="rec-tipo">${escapeHtml(tiposRecurso[r.tipo] || r.tipo)}</span>
      <strong>${escapeHtml(r.titulo)}</strong>${r.temas.length ? `<small>${r.temas.map(escapeHtml).join(', ')}</small>` : ''}</div>
      <button class="btn secondary" onclick="quitarRecurso(${i})">Quitar</button></div>`).join('')
    : '<p class="muted">Todavía no pusiste recursos a disposición.</p>';
}

async function guardarMisRecursos(lista) {
  const r = await api('PUT', '/api/recursos/mios', { recursos: lista });
  misRecursos = r.recursos || [];
  renderMisRecursos();
}

async function agregarRecurso() {
  const v = id => (document.getElementById(id)?.value || '').trim();
  const nuevo = { tipo: v('recTipo'), titulo: v('recTitulo'), detalle: v('recDetalle'), condiciones: v('recCondiciones'),
    temas: v('recTemas').split(',').map(s => s.trim()).filter(Boolean), acepto: !!document.getElementById('recAcepto')?.checked };
  if (nuevo.titulo.length < 4) { toast('Escribí qué ponés a disposición.', 'warn'); return; }
  try {
    await guardarMisRecursos([...misRecursos, nuevo]);
    ['recTitulo', 'recDetalle', 'recCondiciones', 'recTemas'].forEach(id => { const e = document.getElementById(id); if (e) e.value = ''; });
    toast('Recurso puesto a disposición de la red.', 'success');
  } catch (e) { toast('No se pudo guardar: ' + e.message, 'warn'); }
}

async function quitarRecurso(i) {
  try { await guardarMisRecursos(misRecursos.filter((_, j) => j !== i)); } catch (e) { toast('No se pudo quitar: ' + e.message, 'warn'); }
}

function recTarjeta(r) {
  const clave = `${r.de.id}-${r.id}`;
  const accion = r.propio ? `<span class="muted">Es tuyo · ${r.pedidos} ${r.pedidos === 1 ? 'aviso' : 'avisos'} de «me sirve»</span>`
    : r.ya_lo_pediste ? '<span class="rec-ok">Ya le avisaste que te sirve</span>'
    : `<button class="btn" onclick="document.getElementById('ms-${escapeAttr(clave)}').hidden=false;this.hidden=true">Me sirve</button>
       <div class="rec-ms" id="ms-${escapeAttr(clave)}" hidden><textarea maxlength="400" placeholder="¿Para qué te sirve? Una línea alcanza."></textarea>
       <button class="btn" onclick="enviarMeSirve('${escapeAttr(r.de.id)}','${escapeAttr(r.id)}',this)">Avisar</button></div>`;
  return `<article class="rec-card">
    <span class="rec-tipo">${escapeHtml(r.tipo_nombre)}</span>
    <strong>${escapeHtml(r.titulo)}</strong>
    ${r.detalle ? `<p>${escapeHtml(r.detalle)}</p>` : ''}
    ${r.temas.length ? `<div>${r.temas.map(t => `<span class="rec-tema">${escapeHtml(t)}</span>`).join(' ')}</div>` : ''}
    ${r.condiciones ? `<small>${escapeHtml(r.condiciones)}</small>` : ''}
    <div class="rec-de">${escapeHtml(r.de.nombre)}${r.de.institucion ? ` · ${escapeHtml(r.de.institucion)}` : ''}</div>
    ${r.motivo ? `<div class="rec-motivo">${escapeHtml(r.motivo)}</div>` : ''}
    ${!r.propio && r.pedidos ? `<small class="muted">A ${r.pedidos} ${r.pedidos === 1 ? 'persona le sirvió' : 'personas les sirvió'}</small>` : ''}
    <div class="rec-acciones">${accion}</div>
  </article>`;
}

function renderRecursosRed() {
  const el = document.getElementById('recRed');
  if (!el) return;
  const lista = recursosRed.filter(r => recFiltro === 'todos' || r.tipo === recFiltro);
  el.innerHTML = lista.length ? `<div class="rec-grid">${lista.map(recTarjeta).join('')}</div>` : '<p class="muted">Todavía no hay recursos de este tipo.</p>';
  const f = document.getElementById('recFiltros');
  if (f) {
    const tipos = [...new Set(recursosRed.map(r => r.tipo))];
    f.innerHTML = [['todos', 'Todos'], ...tipos.map(t => [t, recursosRed.find(r => r.tipo === t).tipo_nombre])]
      .map(([k, v]) => `<button class="fpill ${k === recFiltro ? 'active' : ''}" onclick="recFiltro='${escapeAttr(k)}';renderRecursosRed()">${escapeHtml(v)}</button>`).join('');
  }
}

async function loadRecursos() {
  const [paraMi, todos] = await Promise.all(['/api/recursos/para-mi', '/api/recursos'].map(u => api('GET', u).catch(() => null)));
  const elP = document.getElementById('recParaMi');
  if (elP) elP.innerHTML = !paraMi ? '<p class="muted">No se pudo cargar.</p>' : paraMi.length
    ? `<div class="rec-grid">${paraMi.map(recTarjeta).join('')}</div>`
    : '<p class="muted">Ningún recurso toca todavía lo que querés aprender o lo que te interesa.</p>';
  recursosRed = todos || [];
  renderRecursosRed();
}

async function enviarMeSirve(owner, rid, boton) {
  const texto = boton.parentElement.querySelector('textarea').value.trim();
  if (texto.length < 8) { toast('Contá en una línea para qué te sirve.', 'warn'); return; }
  try {
    await api('POST', `/api/recursos/${owner}/${rid}/me-sirve`, { para_que: texto });
    toast('Le avisamos por mensaje a quien lo puso a disposición.', 'success');
    loadRecursos();
  } catch (e) { toast('No se pudo avisar: ' + e.message, 'warn'); }
}

async function cargarSeguimiento() {
  const el = document.getElementById('recSeguimiento');
  if (!el) return;
  const items = await api('GET', '/api/recursos/seguimiento').catch(() => []) || [];
  el.innerHTML = items.length ? `<div class="seguimiento"><h5 class="rec-sub">¿Hablaron? ¿Sirvió?</h5>${items.map(s => `
    <div class="seg-item"><p>Hace ${s.dias} días ${s.pediste ? `avisaste que te servía «${escapeHtml(s.titulo)}», de ${escapeHtml(s.con)}` : `${escapeHtml(s.con)} avisó que le servía tu recurso «${escapeHtml(s.titulo)}»`}. ¿Cómo siguió?</p>
    <div class="seg-botones">${[['hablamos', 'Hablamos'], ['sirvio', 'Sirvió'], ['no_sirvio', 'No sirvió']].map(([k, v]) =>
      `<button class="btn secondary" onclick="registrarSeguimiento('${escapeAttr(s.id)}','${k}')">${v}</button>`).join('')}</div></div>`).join('')}
    <p class="rec-nota">Esas respuestas son la evidencia de si la red sirve: se cuentan sin nombres.</p></div>` : '';
}

async function registrarSeguimiento(id, resultado) {
  try { await api('POST', `/api/recursos/usos/${id}/resultado`, { resultado }); toast('Gracias: queda registrado.', 'success'); cargarSeguimiento(); }
  catch (e) { toast('No se pudo registrar: ' + e.message, 'warn'); }
}
