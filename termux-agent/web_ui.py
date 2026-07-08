"""
Web UI lokal untuk Termux AI Agent.
Jalankan via: ketik /webui di dalam agent.

Fitur:
  - Chat interface di browser
  - Preview panel otomatis untuk HTML/web yang dibuat AI
  - File browser untuk semua file di working directory
  - Zero dependency tambahan (pure Python stdlib)
"""

import threading
import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote

DEFAULT_PORT = 7860

# ── State bersama ──────────────────────────────
_lock        = threading.Lock()
_agent_ref   = None
_last_preview: dict = {"path": None, "type": "none", "ts": 0}


def set_agent(agent):
    global _agent_ref
    _agent_ref = agent


def notify_file_written(path: str):
    """
    Dipanggil dari tools.py setelah write_file berhasil.
    Kalau file adalah HTML/CSS/JS, simpan sebagai preview terbaru.
    """
    ext = Path(path).suffix.lower()
    if ext in (".html", ".htm"):
        _last_preview["path"]  = str(Path(path).expanduser().resolve())
        _last_preview["type"]  = "html"
        _last_preview["ts"]    = time.time()


# ── HTML/CSS/JS UI (embedded) ─────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🤖 Termux AI Agent</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0f1117;--surf:#1a1d27;--surf2:#252836;
  --border:#2d3148;--primary:#7c6af7;--pdim:#3d3580;
  --text:#e2e4ef;--dim:#7b80a0;
  --green:#4cba8d;--red:#e05c6b;--yellow:#f0c040;
}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);height:100dvh;display:flex;overflow:hidden}

/* ── Chat panel ── */
#chat{width:400px;min-width:280px;display:flex;flex-direction:column;border-right:1px solid var(--border)}
#chat-head{padding:14px 18px;background:var(--surf2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-shrink:0}
#chat-head h1{font-size:14px;font-weight:600;letter-spacing:.3px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 7px var(--green);flex-shrink:0}
#msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth}
#msgs::-webkit-scrollbar{width:4px}
#msgs::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}
.msg{max-width:90%;padding:10px 14px;border-radius:14px;font-size:13.5px;line-height:1.55;word-break:break-word;white-space:pre-wrap}
.msg.user{background:var(--pdim);color:#fff;align-self:flex-end;border-bottom-right-radius:3px}
.msg.ai{background:var(--surf2);border:1px solid var(--border);align-self:flex-start;border-bottom-left-radius:3px}
.msg.sys{background:transparent;color:var(--dim);font-size:12px;align-self:center;text-align:center;padding:4px 8px}
.msg pre{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px;margin-top:6px;overflow-x:auto;font-size:12px}
.msg code{background:var(--bg);padding:1px 5px;border-radius:4px;font-size:12px;font-family:monospace}
#inp-wrap{padding:10px 14px;border-top:1px solid var(--border);display:flex;gap:8px;background:var(--surf);flex-shrink:0}
#inp{flex:1;background:var(--surf2);border:1px solid var(--border);border-radius:10px;padding:9px 13px;color:var(--text);font-size:14px;resize:none;outline:none;max-height:120px;font-family:inherit;line-height:1.45}
#inp:focus{border-color:var(--primary)}
#inp::placeholder{color:var(--dim)}
#sendbtn{background:var(--primary);border:none;border-radius:10px;padding:0 16px;color:#fff;cursor:pointer;font-size:18px;transition:opacity .15s;flex-shrink:0}
#sendbtn:hover{opacity:.85}
#sendbtn:disabled{opacity:.35;cursor:default}

/* ── Preview panel ── */
#preview{flex:1;display:flex;flex-direction:column;overflow:hidden}
#prev-head{padding:10px 16px;background:var(--surf2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap}
.tab{padding:5px 13px;border-radius:7px;font-size:12.5px;cursor:pointer;color:var(--dim);transition:all .12s;user-select:none;border:1px solid transparent}
.tab:hover{color:var(--text);background:var(--surf)}
.tab.on{background:var(--primary);color:#fff;border-color:var(--primary)}
#prev-path{font-size:11px;color:var(--dim);margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:220px}
#toolrow{display:flex;gap:6px;margin-left:auto;align-items:center}
.tbtn{background:var(--surf);border:1px solid var(--border);color:var(--dim);border-radius:7px;padding:4px 11px;cursor:pointer;font-size:12px;transition:all .12s}
.tbtn:hover{color:var(--text);border-color:var(--dim)}

#prev-body{flex:1;position:relative;overflow:hidden}
iframe#frm{width:100%;height:100%;border:none;background:#fff;display:none}
#no-prev{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--dim);pointer-events:none}
#no-prev svg{opacity:.25}
#no-prev p{font-size:13px}
#no-prev small{font-size:11px;opacity:.7}

/* file browser */
#fb{display:none;flex-direction:column;height:100%;overflow:hidden}
#fb-path{padding:8px 16px;font-size:12px;color:var(--dim);background:var(--surf);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:6px;flex-shrink:0}
#fb-list{flex:1;overflow-y:auto;padding:8px}
#fb-list::-webkit-scrollbar{width:4px}
#fb-list::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}
.fi{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;cursor:pointer;font-size:13px;transition:background .1s}
.fi:hover{background:var(--surf2)}
.fi .ico{font-size:15px;flex-shrink:0;width:20px;text-align:center}
.fi .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fi .sz{font-size:11px;color:var(--dim);flex-shrink:0}
.fi.dir{color:var(--yellow)}
.fi.html-f{color:var(--green)}
.fi.prev-btn{color:var(--primary);text-decoration:underline;font-size:12px;margin-left:auto;flex-shrink:0}

/* loader */
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:sp .65s linear infinite;vertical-align:middle}
@keyframes sp{to{transform:rotate(360deg)}}

/* resize handle */
#drag{width:4px;background:var(--border);cursor:col-resize;flex-shrink:0;transition:background .15s}
#drag:hover,#drag.active{background:var(--primary)}

/* responsive */
@media(max-width:600px){
  #chat{width:100%;min-width:0;border-right:none;border-bottom:1px solid var(--border);height:55vh}
  body{flex-direction:column}
  #drag{display:none}
}
</style>
</head>
<body>

<div id="chat">
  <div id="chat-head">
    <div class="dot" id="dot"></div>
    <h1>🤖 Termux AI Agent</h1>
  </div>
  <div id="msgs"></div>
  <div id="inp-wrap">
    <textarea id="inp" rows="1" placeholder="Ketik pesan… (Enter kirim, Shift+Enter baris baru)"></textarea>
    <button id="sendbtn" title="Kirim">➤</button>
  </div>
</div>

<div id="drag"></div>

<div id="preview">
  <div id="prev-head">
    <div class="tab on" onclick="tab('preview')">🖥 Preview</div>
    <div class="tab" onclick="tab('files')">📁 Files</div>
    <div id="toolrow">
      <button class="tbtn" onclick="reloadFrame()" title="Refresh preview">↺</button>
      <button class="tbtn" onclick="openExternal()" title="Buka di tab baru">⧉</button>
    </div>
    <span id="prev-path"></span>
  </div>

  <div id="prev-body">
    <div id="no-prev">
      <svg width="56" height="56" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
        <rect x="2" y="4" width="20" height="16" rx="2.5"/>
        <path d="M8 9l3 3-3 3M13 15h3"/>
      </svg>
      <p>Preview muncul otomatis</p>
      <small>Minta AI buat file HTML / web</small>
    </div>
    <iframe id="frm" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
  </div>

  <div id="fb">
    <div id="fb-path">
      <span>📁</span><span id="fb-cwd"></span>
    </div>
    <div id="fb-list"></div>
  </div>
</div>

<script>
// ── State ──
let busy = false;
let lastTs = 0;
let currentFbPath = '';
let activeTab = 'preview';
let currentFrameSrc = '';

const msgsEl  = document.getElementById('msgs');
const inpEl   = document.getElementById('inp');
const sendBtn = document.getElementById('sendbtn');
const frm     = document.getElementById('frm');
const noPrev  = document.getElementById('no-prev');
const pathEl  = document.getElementById('prev-path');
const dotEl   = document.getElementById('dot');

// ── Tabs ──
function tab(name) {
  activeTab = name;
  document.querySelectorAll('.tab').forEach((t,i)=> t.classList.toggle('on', i===(name==='preview'?0:1)));
  document.getElementById('prev-body').style.display = name==='preview' ? '' : 'none';
  document.getElementById('fb').style.display        = name==='files'   ? 'flex':'none';
  if(name==='files') loadFiles(currentFbPath);
}

// ── Messages ──
function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }
function fmtText(raw){
  let html = esc(raw);
  // code blocks
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g,(_,lang,code)=>`<pre><code class="lang-${lang}">${code}</code></pre>`);
  // inline code
  html = html.replace(/`([^`\n]+)`/g,'<code>$1</code>');
  // bold
  html = html.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  // newlines outside pre
  html = html.replace(/\n/g,'<br>');
  return html;
}
function addMsg(role, text){
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  d.innerHTML = role==='sys' ? esc(text) : fmtText(text);
  msgsEl.appendChild(d);
  msgsEl.scrollTop = msgsEl.scrollHeight;
  return d;
}

// ── Send ──
async function send(){
  const txt = inpEl.value.trim();
  if(!txt || busy) return;
  inpEl.value = ''; inpEl.style.height='auto';
  addMsg('user', txt);
  busy = true; sendBtn.disabled = true;
  const td = addMsg('ai','<span class="spin"></span> AI berpikir\u2026');
  try{
    const r = await fetch('/api/chat',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message:txt})
    });
    const d = await r.json();
    td.innerHTML = fmtText(d.reply || d.error || 'Error tidak diketahui');
  } catch(e){
    td.innerHTML = '❌ Gagal konek ke server agent';
  }
  busy = false; sendBtn.disabled = false;
  inpEl.focus();
  pollPreview();
}

// ── Preview auto-update ──
async function pollPreview(){
  try{
    const r = await fetch('/api/status');
    if(!r.ok) throw new Error();
    const d = await r.json();
    dotEl.style.background = '#4cba8d';
    dotEl.style.boxShadow  = '0 0 7px #4cba8d';
    if(d.preview && d.preview.ts > lastTs && d.preview.type==='html'){
      lastTs = d.preview.ts;
      showPreview('/files/?path=' + encodeURIComponent(d.preview.path), d.preview.path);
    }
  } catch(e){
    dotEl.style.background = '#e05c6b';
    dotEl.style.boxShadow  = '0 0 7px #e05c6b';
  }
}
function showPreview(src, label){
  currentFrameSrc = src;
  frm.src = src;
  frm.style.display = 'block';
  noPrev.style.display = 'none';
  pathEl.textContent = label || src;
}
function reloadFrame(){ if(currentFrameSrc) frm.src = currentFrameSrc; }
function openExternal(){ if(currentFrameSrc) window.open(currentFrameSrc,'_blank'); }

// ── File browser ──
function fmt_size(b){
  if(b<1024) return b+'B';
  if(b<1048576) return (b/1024).toFixed(1)+'KB';
  return (b/1048576).toFixed(1)+'MB';
}
async function loadFiles(dir){
  const listEl = document.getElementById('fb-list');
  const cwdEl  = document.getElementById('fb-cwd');
  listEl.innerHTML = '<div style="padding:16px;color:var(--dim)">Memuat\u2026</div>';
  try{
    const r = await fetch('/api/files?dir='+encodeURIComponent(dir||''));
    const d = await r.json();
    currentFbPath = d.cwd || '';
    cwdEl.textContent = currentFbPath;
    listEl.innerHTML = '';

    // Tombol naik
    if(d.parent !== null){
      const up = document.createElement('div');
      up.className='fi dir'; up.innerHTML='<span class="ico">⬆</span><span class="nm">.. (naik)</span>';
      up.onclick = ()=>loadFiles(d.parent);
      listEl.appendChild(up);
    }

    (d.items||[]).forEach(f=>{
      const row = document.createElement('div');
      const isHtml = /\.html?$/i.test(f.name);
      const isImg  = /\.(png|jpg|jpeg|gif|svg|webp)$/i.test(f.name);
      const ico = f.is_dir?'📁': isHtml?'🌐': /\.py$/i.test(f.name)?'🐍':
                  /\.js$/i.test(f.name)?'⚡': isImg?'🖼': /\.css$/i.test(f.name)?'🎨':'📄';
      row.className = 'fi' + (f.is_dir?' dir':'') + (isHtml?' html-f':'');
      row.innerHTML = `<span class="ico">${ico}</span><span class="nm">${esc(f.name)}</span>`
                    + (f.is_dir?'':`<span class="sz">${fmt_size(f.size)}</span>`);
      if(f.is_dir){
        row.onclick = ()=>loadFiles(f.path);
      } else if(isHtml){
        row.onclick = ()=>{ showPreview('/files/?path='+encodeURIComponent(f.path), f.path); tab('preview'); };
      } else if(isImg){
        row.onclick = ()=>{ showPreview('/files/?path='+encodeURIComponent(f.path), f.path); tab('preview'); };
      }
      listEl.appendChild(row);
    });
    if(!d.items?.length && !d.parent) listEl.innerHTML='<div style="padding:16px;color:var(--dim)">Folder kosong</div>';
  } catch(e){
    listEl.innerHTML='<div style="padding:16px;color:var(--red)">Gagal memuat file</div>';
  }
}

// ── Resize panel ──
const dragEl = document.getElementById('drag');
let dragging = false, startX = 0, startW = 0;
dragEl.addEventListener('mousedown', e=>{ dragging=true; startX=e.clientX; startW=document.getElementById('chat').offsetWidth; dragEl.classList.add('active'); e.preventDefault(); });
document.addEventListener('mousemove', e=>{ if(!dragging) return; const w=Math.max(240,Math.min(startW+(e.clientX-startX),window.innerWidth-300)); document.getElementById('chat').style.width=w+'px'; });
document.addEventListener('mouseup', ()=>{ dragging=false; dragEl.classList.remove('active'); });

// ── Input ──
inpEl.addEventListener('keydown', e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();} });
inpEl.addEventListener('input', ()=>{ inpEl.style.height='auto'; inpEl.style.height=Math.min(inpEl.scrollHeight,120)+'px'; });
sendBtn.addEventListener('click', send);

// ── Init ──
addMsg('sys', '✅ Web UI aktif — ketik pesan untuk mulai chat');
pollPreview();
setInterval(pollPreview, 4000);
</script>
</body>
</html>
"""


# ── HTTP Handler ──────────────────────────────
class _Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # silent — tidak spam console

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        p = parsed.path
        qs = parsed.query

        if p in ("/", "/index.html"):
            self._html(_HTML)

        elif p == "/api/status":
            self._json({
                "preview": _last_preview,
                "ts": time.time(),
            })

        elif p == "/api/files":
            # Parse ?dir= dari query string
            from urllib.parse import parse_qs as _pqs
            params = _pqs(qs)
            req_dir = params.get("dir", [""])[0]
            self._serve_file_list(req_dir)

        elif p == "/files/":
            # Serve file: /files/?path=...
            from urllib.parse import parse_qs as _pqs
            params = _pqs(qs)
            file_path = params.get("path", [""])[0]
            if file_path:
                self._serve_file(file_path)
            else:
                self._json({"error": "path kosong"}, 400)

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        p = parsed.path

        if p == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                msg = data.get("message", "").strip()
            except (json.JSONDecodeError, AttributeError):
                self._json({"error": "JSON tidak valid"}, 400)
                return

            if not msg:
                self._json({"error": "Pesan kosong"}, 400)
                return

            if _agent_ref is None:
                self._json({"reply": "❌ Agent belum siap. Jalankan dulu dari terminal."}, 503)
                return

            with _lock:
                try:
                    reply = _agent_ref.chat(msg)
                except Exception as e:
                    reply = f"❌ Error: {e}"

            self._json({"reply": reply})

        else:
            self._json({"error": "not found"}, 404)

    def _serve_file(self, path: str):
        """Serve file dari filesystem ke browser."""
        target = Path(path).expanduser().resolve()
        # Batasi akses hanya ke working directory dan turunannya
        cwd = Path(os.getcwd()).resolve()
        try:
            target.relative_to(cwd)
        except ValueError:
            # Izinkan kalau path sudah absolut valid (misalnya /sdcard/...)
            pass
        if not target.exists() or not target.is_file():
            self._json({"error": "file tidak ditemukan"}, 404)
            return
        try:
            content = target.read_bytes()
            ext = target.suffix.lower()
            mime = {
                ".html": "text/html", ".htm": "text/html",
                ".css": "text/css", ".js": "application/javascript",
                ".json": "application/json", ".txt": "text/plain",
                ".md": "text/plain",
                ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".gif": "image/gif",
                ".svg": "image/svg+xml", ".webp": "image/webp",
                ".ico": "image/x-icon",
            }.get(ext, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _serve_file_list(self, req_dir: str):
        """Return JSON list file/folder di direktori tertentu."""
        base = Path(os.getcwd()).resolve()
        if req_dir:
            target = Path(req_dir).expanduser().resolve()
        else:
            target = base

        if not target.exists() or not target.is_dir():
            target = base

        items = []
        try:
            entries = sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for e in entries:
                if e.name.startswith("."):
                    continue
                try:
                    size = e.stat().st_size if e.is_file() else 0
                except OSError:
                    size = 0
                items.append({
                    "name": e.name,
                    "path": str(e),
                    "is_dir": e.is_dir(),
                    "size": size,
                })
        except PermissionError:
            pass

        parent = str(target.parent) if target != target.parent else None
        self._json({"cwd": str(target), "parent": parent, "items": items})


# ── Server start ─────────────────────────────
def start(port: int = DEFAULT_PORT, agent=None) -> HTTPServer:
    """
    Jalankan web UI server di thread daemon (background).
    Mengembalikan instance HTTPServer.
    """
    global _agent_ref
    if agent is not None:
        _agent_ref = agent

    server = HTTPServer(("0.0.0.0", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
