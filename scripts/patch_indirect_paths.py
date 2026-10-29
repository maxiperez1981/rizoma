from pathlib import Path

p = Path("static/js/app.js")
s = p.read_text(encoding="utf-8")

old = """    <section class="card rizoma-people">
      <div class="card-top"><h4>Vinculá tu grafo con el resto</h4><span class="badge blue">IA + red humana</span></div>
      <p class="muted">La inteligencia artificial cruza tu grafo con otros grafos: no para rankear personas, sino para detectar complementariedades posibles.</p>
      <div id="rizomaPeopleGrid" class="rizoma-people-grid"><div class="spinner"></div></div>
    </section>
    <section class="card rizoma-projects">
"""
new = """    <section class="card rizoma-people">
      <div class="card-top"><h4>Vinculá tu grafo con el resto</h4><span class="badge blue">IA + red humana</span></div>
      <p class="muted">La inteligencia artificial cruza tu grafo con otros grafos: no para rankear personas, sino para detectar complementariedades posibles.</p>
      <div id="rizomaPeopleGrid" class="rizoma-people-grid"><div class="spinner"></div></div>
    </section>
    <section class="card rizoma-indirectos">
      <div class="card-top"><h4>Caminos indirectos</h4><span class="badge blue">Hallazgos rizomáticos</span></div>
      <p class="muted">Estos vínculos no nacen de compartir carrera o palabra clave. Aparecen porque una tercera persona o tema puente conecta trayectorias que probablemente no se encontrarían solas.</p>
      <div id="rizomaCaminosGrid" class="rizoma-caminos-grid"><div class="spinner"></div></div>
    </section>
    <section class="card rizoma-projects">
"""
if old not in s:
    raise SystemExit("section marker not found")
s = s.replace(old, new)

old = """  cargarRizomaGrafo();

  const people = await loadPeopleConnections();
"""
new = """  cargarRizomaGrafo();
  cargarCaminosIndirectos();

  const people = await loadPeopleConnections();
"""
if old not in s:
    raise SystemExit("load marker not found")
s = s.replace(old, new)

insert = r"""
async function cargarCaminosIndirectos() {
  const el = document.getElementById('rizomaCaminosGrid');
  if (!el) return;
  el.innerHTML = '<div class="spinner"></div>';
  try {
    const caminos = await api('GET', '/api/users/me/rizoma-caminos?limite=8') || [];
    if (!caminos.length) {
      el.innerHTML = '<p class="muted">Todavía no hay caminos indirectos fuertes. A medida que la red sume perfiles diversos, aparecerán puentes más interesantes.</p>';
      return;
    }
    el.innerHTML = caminos.map(renderCaminoCard).join('');
  } catch (err) {
    el.innerHTML = `<p class="muted">No pude cargar caminos indirectos: ${escapeHtml(err.message || err)}</p>`;
  }
}

function renderCaminoCard(item) {
  const camino = item.camino || [];
  const origen = camino[0]?.label || 'Tu perfil';
  const destino = camino[4]?.label || item.persona || 'otra persona';
  const temaOrigen = camino[1]?.label || 'un tema propio';
  const intermedio = camino[2]?.label || 'una persona puente';
  const temaPuente = camino[3]?.label || 'un tema puente';
  return `
    <article class="camino-card">
      <div class="camino-card-head">
        <strong>${escapeHtml(destino)}</strong>
        <span class="badge">rareza ${escapeHtml(item.score ?? '')}</span>
      </div>
      ${renderCaminoIndirecto(camino)}
      <p>${escapeHtml(origen)} se conecta con ${escapeHtml(destino)} a través de ${escapeHtml(intermedio)}: el recorrido cruza ${escapeHtml(temaOrigen)} con ${escapeHtml(temaPuente)}. Ese puente puede abrir una conversación que no saldría de una búsqueda por carrera.</p>
    </article>`;
}

"""
marker = "async function renderYourRizoma() {"
if marker not in s:
    raise SystemExit("renderYourRizoma marker not found")
s = s.replace(marker, insert + marker)
p.write_text(s, encoding="utf-8")

css = Path("static/css/styles.css")
c = css.read_text(encoding="utf-8")
css_add = """

.rizoma-indirectos{border-color:rgba(43,112,179,.2)}
.rizoma-caminos-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:12px}
.camino-card{border:1px solid var(--line);border-radius:8px;background:var(--soft);padding:12px}
.camino-card-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
.camino-card-head strong{font-size:14px;color:var(--ink)}
.camino-card p{font-size:12.5px;line-height:1.45;color:var(--muted);margin:8px 0 0}
"""
if ".rizoma-caminos-grid" not in c:
    css.write_text(c.rstrip() + css_add + "\n", encoding="utf-8")

print("patched indirect paths")
