#!/usr/bin/env python3
"""
╔══════════════════════════════════════╗
║   🤖  TERMUX AI AGENT               ║
║   Chat · Shell · Files · Web · Code ║
╚══════════════════════════════════════╝

Jalankan: python3 agent.py
Tidak butuh install apapun selain Python 3!
"""

import sys
import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

try:
    import readline  # noqa: F401 — aktifkan arrow keys & history di terminal
except ImportError:
    pass

from config import load_config, setup_wizard, save_config, PROVIDER_PRESETS
import tools as _tools_module
from tools import TOOL_DEFINITIONS, dispatch_tool

# ──────────────────────────────────────────────
# WARNA TERMINAL
# ──────────────────────────────────────────────

NO_COLOR = os.environ.get("NO_COLOR") or not sys.stdout.isatty()

def _c(text: str, code: str) -> str:
    if NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def cyan(t):    return _c(t, "96")
def green(t):   return _c(t, "92")
def yellow(t):  return _c(t, "93")
def red(t):     return _c(t, "91")
def bold(t):    return _c(t, "1")
def dim(t):     return _c(t, "2")
def magenta(t): return _c(t, "95")


def clear_screen():
    """Bersihkan layar terminal."""
    os.system("clear" if os.name != "nt" else "cls")


def typewriter(text: str, delay: float = 0.018):
    """
    Print teks per-huruf dengan efek ketik.
    Baris baru & spasi lebih cepat, huruf biasa pakai delay.
    """
    i = 0
    while i < len(text):
        ch = text[i]
        sys.stdout.write(ch)
        sys.stdout.flush()

        # Jeda antar karakter — tanda baca sedikit lebih lama
        if ch in (".", "!", "?", "\n"):
            time.sleep(delay * 5)
        elif ch in (",", ";", ":"):
            time.sleep(delay * 2)
        elif ch == " ":
            time.sleep(delay * 0.4)
        else:
            time.sleep(delay)
        i += 1
    print()  # newline di akhir


# ──────────────────────────────────────────────
# PERSISTENT CHAT HISTORY
# ──────────────────────────────────────────────

HISTORY_FILE = Path(__file__).parent / "chat_history.json"
_ALLOWED_HISTORY_ROLES = {"user", "assistant", "tool"}


def load_history() -> list:
    """Load riwayat chat dari file JSON, hanya terima entri valid."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [
                m for m in data
                if isinstance(m, dict) and m.get("role") in _ALLOWED_HISTORY_ROLES
            ]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _trim_history(history: list, max_hist: int) -> list:
    """Trim history dengan menjaga blok percakapan & tool call utuh."""
    if max_hist < 1:
        return history
    if len(history) <= max_hist:
        return history

    # Coba hapus turn/user-block terlama dari depan.
    while len(history) > max_hist:
        try:
            idx = next(i for i, m in enumerate(history[1:], start=1) if m.get("role") == "user")
        except StopIteration:
            break
        history = history[idx:]

    # Jika masih kepanjangan (satu turn besar), potong dari awal turn
    # tapi jangan pisahkan assistant tool_calls dengan tool result-nya.
    if len(history) > max_hist:
        excess = len(history) - max_hist
        cutoff = excess
        if history[cutoff].get("role") == "tool":
            tool_call_id = history[cutoff].get("tool_call_id")
            for i in range(cutoff - 1, -1, -1):
                msg = history[i]
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    ids = {tc.get("id") for tc in msg.get("tool_calls", [])}
                    if tool_call_id in ids:
                        cutoff = i
                        break
        history = history[cutoff:]

    return history


def save_history(history: list):
    """Simpan riwayat chat ke file JSON dengan permission ketat."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(HISTORY_FILE, 0o600)
        except OSError:
            pass
    except OSError as e:
        print(dim(f"[history] gagal simpan: {e}"))


# ──────────────────────────────────────────────
# HTTP CLIENT (pakai urllib bawaan Python)
# ──────────────────────────────────────────────

class APIError(Exception):
    def __init__(self, message: str, status_code: int = 0, retry_after: float = 0):
        super().__init__(message)
        self.status_code  = status_code
        self.retry_after  = retry_after  # detik dari Retry-After header


def _provider_label(cfg: dict) -> str:
    """Nama pendek provider dari base_url."""
    kind = cfg.get("kind", "")
    if kind == "custom":
        return "Custom API"
    if kind == "nexray":
        return "Nexray"
    url = cfg.get("base_url", "")
    if "groq"        in url: return "Groq"
    if "googleapis"  in url: return "Gemini"
    if "openai.com"  in url: return "OpenAI"
    if "together"    in url: return "Together AI"
    if "openrouter"  in url: return "OpenRouter"
    if "anthropic"   in url: return "Anthropic"
    if "localhost" in url or "127.0.0.1" in url: return "Ollama"
    host = url.split("/")[2] if url.count("/") >= 2 else url
    return host


def _raw_call(provider: dict, messages: list, tools: list, base_cfg: dict) -> dict:
    """
    Satu kali panggil API pakai provider tertentu.
    provider harus punya: base_url, api_key, model.
    base_cfg dipakai untuk max_tokens, temperature, dll.
    """
    base_url = provider.get("base_url", "").rstrip("/")
    api_key  = provider.get("api_key") or base_cfg.get("api_key", "no-key")
    model    = provider.get("model")   or base_cfg.get("model", "gemini-2.0-flash")

    payload = {
        "model"      : model,
        "messages"   : messages,
        "tools"      : tools,
        "tool_choice": "auto",
        "max_tokens" : int(base_cfg.get("max_tokens", 4096)),
        "temperature": float(base_cfg.get("temperature", 0.7)),
    }
    body    = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type" : "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent"   : "termux-agent/1.0",
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions", data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, dict):
                raise APIError(f"Response tidak terduga: {str(data)[:200]}")
            return data
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        # Coba baca Retry-After header
        retry_after = 0.0
        try:
            retry_after = float(e.headers.get("Retry-After", 0))
        except (ValueError, AttributeError):
            pass
        # Parse pesan error
        try:
            err_data = json.loads(raw)
            msg = (
                (err_data.get("error", {}).get("message") if isinstance(err_data, dict) else None)
                or (err_data.get("message") if isinstance(err_data, dict) else None)
                or raw[:300]
            )
        except json.JSONDecodeError:
            msg = raw[:300]
        raise APIError(msg, status_code=e.code, retry_after=retry_after) from e
    except urllib.error.URLError as e:
        raise APIError(f"Tidak bisa konek: {e.reason}")
    except TimeoutError:
        raise APIError("Request timeout.")


def _custom_api_call(provider: dict, messages: list, timeout: int = 45) -> dict:
    """
    Adapter untuk custom API yang bukan OpenAI-compatible.

    Format yang didukung saat ini:
      GET <base_url>?text=<url_encoded_prompt>
      Response JSON: { ..., "result": "jawaban", ... }

    Contoh: https://api.nexray.eu.cc/ai/gpt-3.5-turbo?text=Hay
    """
    base_url = provider.get("base_url", "").strip()
    if not base_url:
        raise APIError("Custom API base_url kosong.")
    parsed = urllib.parse.urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise APIError(
            "Custom API URL tidak valid. Harus lengkap dengan scheme dan host, "
            "contoh: https://api.nexray.eu.cc/ai/gpt-3.5-turbo"
        )

    # Bangun prompt dari seluruh conversation (system + user + assistant + tool results)
    parts = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if not isinstance(content, str):
            continue
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
        elif role == "tool":
            parts.append(f"Tool result: {content[:500]}")
    prompt = "\n\n".join(parts)

    # Cap agar URL tidak terlalu panjang (GET memiliki batas panjang)
    if len(prompt) > 6000:
        prompt = "...[riwayat dibatasi]...\n\n" + prompt[-4000:]

    # Bangun URL GET secara robust, handle query string yang sudah ada.
    # base_url dianggap sebagai URL lengkap endpoint (misal https://api.nexray.eu.cc/ai/claude).
    parsed = urllib.parse.urlsplit(base_url)
    query = urllib.parse.parse_qs(parsed.query)
    query["text"] = [prompt]
    new_query = urllib.parse.urlencode(query, doseq=True)
    url = urllib.parse.urlunsplit((
        parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment
    ))

    req = urllib.request.Request(
        url, headers={"User-Agent": "termux-agent/1.0"}, method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise APIError(f"Custom API HTTP {e.code}: {e.reason}", status_code=e.code) from e
    except urllib.error.URLError as e:
        raise APIError(f"Custom API tidak bisa konek: {e.reason}") from e
    except TimeoutError:
        raise APIError("Custom API timeout.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise APIError(f"Custom API response bukan JSON: {raw[:200]}")

    if not isinstance(data, dict):
        raise APIError(f"Custom API response tidak terduga: {raw[:200]}")

    # Ambil jawaban dari beberapa kemungkinan field populer
    result = (
        data.get("result")
        or data.get("response")
        or data.get("message")
        or data.get("content")
        or data.get("answer")
    )
    if result is None:
        raise APIError(f"Custom API tidak mengembalikan field jawaban: {list(data.keys())[:10]}")

    return {
        "choices": [{"message": {"role": "assistant", "content": str(result)}}],
        "usage": {},
    }


def call_api(cfg: dict, messages: list, tools: list,
             on_switch: "callable | None" = None) -> dict:
    """
    Panggil API dengan auto-retry + multi-provider fallback.

    Strategi per-provider:
      • 429 → tunggu Retry-After (atau backoff 2s/5s/10s), max 2 retry
              kalau masih gagal → provider berikutnya
      • 5xx → backoff 1s/3s, max 1 retry → provider berikutnya
      • network error → provider berikutnya langsung

    Provider dengan kind="custom" dipanggil pakai adapter GET, bukan OpenAI endpoint.
    on_switch(label) dipanggil saat beralih provider (untuk notif UI).
    """
    # Bangun daftar provider: utama dulu, lalu fallback
    primary = {
        "base_url": cfg.get("base_url", ""),
        "api_key" : cfg.get("api_key", ""),
        "model"   : cfg.get("model", ""),
        "kind"    : cfg.get("kind", "openai"),
        "nexray_urls": cfg.get("nexray_urls", []),
    }
    fallbacks  = cfg.get("fallback_providers", [])
    providers  = [primary] + list(fallbacks)

    last_error = None
    for i, provider in enumerate(providers):
        label = _provider_label(provider)
        if i > 0 and on_switch:
            on_switch(label)

        # Retry loop untuk provider ini
        wait_schedule = [2, 5, 10]   # detik tunggu saat 429
        server_sched  = [1, 3]       # detik tunggu saat 5xx

        attempt429 = 0
        attempt5xx = 0

        while True:
            try:
                kind = provider.get("kind", "")
                if kind == "custom":
                    return _custom_api_call(provider, messages)
                elif kind == "nexray":
                    urls = provider.get("nexray_urls") or []
                    if not urls:
                        urls = [provider.get("base_url", "")]
                    last_err = None
                    for idx, url in enumerate(urls):
                        if not url:
                            continue
                        sub = dict(provider)
                        sub["base_url"] = url
                        sub["kind"] = "custom"
                        try:
                            return _custom_api_call(sub, messages)
                        except APIError as e:
                            last_err = e
                            if idx < len(urls) - 1:
                                print(f"  {yellow(f'⚡ Nexray endpoint {idx+1} gagal, coba endpoint {idx+2}...')}")
                            continue
                    raise last_err or APIError("Semua endpoint Nexray gagal.")
                else:
                    return _raw_call(provider, messages, tools, cfg)
            except APIError as e:
                last_error = e
                if e.status_code == 429:
                    if attempt429 < len(wait_schedule):
                        wait = e.retry_after if e.retry_after > 0 else wait_schedule[attempt429]
                        wait = min(wait, 60)  # cap 60 detik
                        print(f"\n  {yellow(f'⏳ {label} rate limit — tunggu {wait:.0f}s...')}")
                        time.sleep(wait)
                        attempt429 += 1
                        continue
                    # Retries habis → coba provider berikutnya
                    print(f"  {yellow(f'⚡ {label} limit tercapai, coba provider cadangan...')}")
                    break
                elif e.status_code >= 500:
                    if attempt5xx < len(server_sched):
                        wait = server_sched[attempt5xx]
                        print(f"\n  {yellow(f'⚠️  {label} server error {e.status_code} — retry {wait}s...')}")
                        time.sleep(wait)
                        attempt5xx += 1
                        continue
                    print(f"  {yellow(f'⚡ {label} server error terus, coba provider cadangan...')}")
                    break
                elif e.status_code == 401:
                    # API key salah — langsung ke provider berikutnya
                    print(f"  {yellow(f'🔑 {label} API key ditolak, coba provider cadangan...')}")
                    break
                else:
                    # Error lain (network, parsing) — langsung ke provider berikutnya
                    break

    # Semua provider gagal
    if last_error:
        if last_error.status_code == 429:
            raise APIError(
                "Semua provider kena rate limit. Tunggu sebentar atau tambah provider cadangan (/fallback).",
                status_code=429,
            )
        raise last_error
    raise APIError("Semua provider gagal.")


# ──────────────────────────────────────────────
# BANNER & HELP
# ──────────────────────────────────────────────

BANNER = r"""
  ╔══════════════════════════════════════════╗
  ║  🤖  Termux AI Agent                    ║
  ║  Chat · Shell · File · Web · Code       ║
  ╚══════════════════════════════════════════╝
"""

HELP_TEXT = """
Perintah khusus:
  /help      — tampilkan bantuan ini
  /clear     — hapus riwayat percakapan
  /config    — ubah provider/model/API key utama
  /fallback  — kelola provider cadangan (auto-switch saat limit)
  /status    — info konfigurasi + provider aktif
  /tools     — daftar tools yang tersedia
  /history   — lihat riwayat chat
  /upgrade   — mode self-upgrade (AI edit kode dirinya sendiri)
  /exit      — keluar
  Ctrl+C     — keluar (atau batalkan input)

Contoh penggunaan:
  › buat file hello.py berisi "print('halo dunia')" lalu jalankan
  › search berita terbaru tentang AI di Indonesia
  › list isi folder Downloads
  › buat script backup otomatis ke /sdcard/backup
  › hitung fibonacci ke-50 pakai Python
  › install cowsay dan tampilkan pesan lucu
  › tambahkan fitur baru ke dirimu sendiri: tool untuk translate teks
  › perbaiki bug di tools.py baris 42
"""

UPGRADE_PROMPT = """\
Kamu adalah AI agent yang bisa memodifikasi source code dirimu sendiri.

File source code kamu ada di direktori: {agent_dir}
  - agent.py   — main loop, UI, HTTP client, kelas Agent
  - tools.py   — semua implementasi tool + TOOL_DEFINITIONS
  - config.py  — load/save konfigurasi

Instruksi user untuk upgrade/perbaikan:
{user_request}

Langkah yang harus kamu lakukan:
1. Baca file yang relevan dengan read_file (baca source code kamu sendiri)
2. Rencanakan perubahan — pastikan kamu paham struktur kodenya dulu
3. Terapkan perubahan dengan patch_file (JANGAN tulis ulang seluruh file)
4. Setelah semua patch berhasil, panggil reload_agent untuk restart

Aturan keselamatan:
- Selalu gunakan patch_file, bukan write_file, untuk mengedit source code agent
- Backup otomatis dibuat sebelum setiap patch (.bak)
- patch_file akan validasi syntax Python sebelum menyimpan
- Kalau tidak yakin, baca dulu kodenya sebelum edit
- Perubahan pada TOOL_DEFINITIONS harus diikuti perubahan di dispatch_tool()
"""


# ──────────────────────────────────────────────
# AGENT CLASS
# ──────────────────────────────────────────────

class Agent:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.history: list[dict] = load_history()
        self.total_tokens = 0
        self.active_provider: str = _provider_label(cfg)  # provider yg sedang dipakai

    def _system_message(self) -> dict:
        cwd = os.getcwd()
        python_ver = sys.version.split()[0]
        agent_dir = str(_tools_module.AGENT_DIR)
        return {
            "role": "system",
            "content": (
                f"{self.cfg.get('system_prompt', '')}\n\n"
                f"Informasi sistem:\n"
                f"- Working directory: {cwd}\n"
                f"- Python: {python_ver}\n"
                f"- Platform: {sys.platform}\n"
                f"- Shell tersedia: bash, sh\n\n"
                f"Kemampuan self-modification:\n"
                f"- Source code kamu ada di: {agent_dir}\n"
                f"- File utama: agent.py, tools.py, config.py\n"
                f"- Gunakan list_agent_files() untuk lihat semua file\n"
                f"- Gunakan read_file() untuk baca kode kamu sendiri\n"
                f"- Gunakan patch_file() untuk edit kode kamu sendiri (LEBIH AMAN dari write_file)\n"
                f"- Gunakan reload_agent() untuk restart setelah edit selesai"
            ),
        }

    def chat(self, user_input: str) -> str:
        """Kirim pesan ke AI dan jalankan tool calls jika ada."""
        # Reset ke provider utama di awal setiap request baru
        self.active_provider = _provider_label(self.cfg)
        self.history.append({"role": "user", "content": user_input})

        # Trim history agar tidak terlalu panjang, tapi jaga urutan tool call
        max_hist = int(self.cfg.get("max_history", 50))
        self.history = _trim_history(self.history, max_hist)

        messages = [self._system_message()] + self.history

        def _on_provider_switch(label: str):
            self.active_provider = label
            print(f"\n  {cyan(f'↪ Beralih ke {label}...')}")

        while True:
            try:
                response = call_api(self.cfg, messages, TOOL_DEFINITIONS,
                                    on_switch=_on_provider_switch)
            except APIError as e:
                if e.status_code == 401:
                    return red("❌ API key tidak valid. Ketik /config untuk atur ulang.")
                elif e.status_code == 429:
                    return red(
                        "❌ Semua provider kena rate limit.\n"
                        "  • Tunggu sebentar lalu coba lagi, atau\n"
                        "  • Ketik /fallback untuk tambah provider cadangan."
                    )
                elif e.status_code >= 500:
                    return red(f"❌ Server error ({e.status_code}). Coba lagi nanti.")
                return red(f"❌ API error: {e}")
            except Exception as e:
                return red(f"❌ Error: {e}")

            try:
                choice = response.get("choices", [{}])[0]
                msg    = choice.get("message", {})
            except (IndexError, AttributeError, KeyError) as e:
                return red(f"❌ Response API tidak terduga: {e}\nRaw: {str(response)[:200]}")

            usage = response.get("usage", {})
            self.total_tokens += usage.get("total_tokens", 0)

            tool_calls = msg.get("tool_calls") or []

            # Tidak ada tool call → jawaban final
            if not tool_calls:
                reply = msg.get("content") or ""
                self.history.append({"role": "assistant", "content": reply})
                save_history(self.history)
                return reply

            # Ada tool calls → jalankan semua
            messages.append(msg)
            self.history.append(msg)

            tool_results = []
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name", "")
                try:
                    fn_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                except json.JSONDecodeError:
                    fn_args = {}

                self._print_tool_call(fn_name, fn_args)

                try:
                    result = dispatch_tool(fn_name, fn_args, self.cfg)
                except (KeyError, TypeError) as e:
                    result = f"❌ Argumen tool tidak lengkap: {e}"
                except Exception as e:
                    result = f"❌ Tool error: {e}"

                self._print_tool_result(result)

                tr = {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result,
                }
                tool_results.append(tr)
                self.history.append(tr)

            messages.extend(tool_results)
            # Lanjut loop sampai AI selesai

    def _print_tool_call(self, name: str, args: dict):
        summary_map = {
            "execute_shell":   lambda a: a.get("command", ""),
            "run_python":      lambda a: a.get("code", "")[:60].replace("\n", "↵") + "...",
            "run_bash":        lambda a: a.get("code", "")[:60].replace("\n", "↵") + "...",
            "read_file":       lambda a: a.get("path", ""),
            "write_file":      lambda a: f"{a.get('path','')} ({len(a.get('content',''))} char)",
            "list_directory":  lambda a: a.get("path", "."),
            "web_search":      lambda a: a.get("query", ""),
            "fetch_url":       lambda a: a.get("url", ""),
            "patch_file":      lambda a: f"{a.get('path','')} — ganti {len(a.get('old_text',''))} char",
            "reload_agent":    lambda a: "restart agent...",
            "list_agent_files":lambda a: "source files",
        }
        icon_map = {
            "execute_shell": "🖥️ ", "run_python": "🐍", "run_bash": "📜",
            "read_file": "📖", "write_file": "✏️ ", "list_directory": "📁",
            "web_search": "🔍", "fetch_url": "🌐",
            "patch_file": "🔧", "reload_agent": "🔄", "list_agent_files": "📂",
        }
        icon = icon_map.get(name, "⚙️ ")
        try:
            summary = summary_map.get(name, lambda a: str(a)[:60])(args)
        except Exception:
            summary = ""
        print(f"\n{dim('┌─')} {icon} {yellow(name)} {dim(summary)}")

    def _print_tool_result(self, result: str):
        lines = result.strip().splitlines()
        if not lines:
            return
        for line in lines[:20]:
            print(f"  {dim('│')} {line}")
        if len(lines) > 20:
            print(f"  {dim('│')} {dim(f'... (+{len(lines)-20} baris)')}")
        print(f"{dim('└─')}")

    def clear_history(self):
        self.history.clear()
        try:
            HISTORY_FILE.unlink(missing_ok=True)
        except OSError as e:
            print(dim(f"[history] gagal hapus file: {e}"))
        print(green("✅ Riwayat percakapan dihapus."))

    def show_status(self):
        api_key = self.cfg.get("api_key", "")
        key_display = ("*" * 8 + api_key[-4:]) if len(api_key) > 4 else ("(kosong)" if not api_key else api_key)
        fallbacks = self.cfg.get("fallback_providers", [])
        fb_lines = ""
        for i, fb in enumerate(fallbacks, 1):
            fb_label = _provider_label(fb)
            fb_model = fb.get("model", "-")
            active_mark = green(" ← aktif") if self.active_provider == fb_label else ""
            fb_lines += f"\n  Fallback {i}: {cyan(fb_label)} / {fb_model}{active_mark}"
        active_mark = green(" ← aktif") if self.active_provider == _provider_label(self.cfg) else ""
        url_display = self.cfg.get('base_url', '-')
        if self.cfg.get("kind") == "nexray":
            urls = self.cfg.get("nexray_urls", [])
            url_display = ", ".join(urls) if urls else "(kosong)"
        print(f"""
{bold('Status Konfigurasi:')}
  Provider : {cyan(_provider_label(self.cfg))} / {self.cfg.get('model', '-')}{active_mark}
  URL      : {dim(url_display)}
  API Key  : {dim(key_display)}{fb_lines}
  Pesan    : {len(self.history)} dalam history
  Token    : {self.total_tokens:,} (sesi ini)
  Dir      : {os.getcwd()}
""")

    def show_tools(self):
        print(f"\n{bold('Tools yang tersedia:')}")
        for t in TOOL_DEFINITIONS:
            fn = t["function"]
            print(f"  {green('•')} {bold(fn['name'])} — {fn['description'][:70]}")
        print()

    def show_history(self):
        if not self.history:
            print(dim("(history kosong)"))
            return
        for msg in self.history:
            role    = msg.get("role", "")
            content = msg.get("content") or ""
            if role == "user":
                print(f"\n{bold(cyan('Kamu:'))} {content[:200]}")
            elif role == "assistant":
                if msg.get("tool_calls"):
                    names = [tc.get("function", {}).get("name", "") for tc in msg.get("tool_calls", [])]
                    print(f"{bold(green('AI:'))} [tool calls: {', '.join(names)}]")
                else:
                    print(f"{bold(green('AI:'))} {content[:200]}")
            elif role == "tool":
                print(f"{bold(yellow('Tool:'))} {content[:200]}")
        print()


# ──────────────────────────────────────────────
# FALLBACK PROVIDER WIZARD
# ──────────────────────────────────────────────

def _fallback_wizard(cfg: dict) -> dict:
    """Kelola daftar provider cadangan secara interaktif."""
    fallbacks = list(cfg.get("fallback_providers", []))

    while True:
        print(f"\n{bold(cyan('⚡ Provider Cadangan (Fallback)'))}")
        print(dim("─" * 44))
        print("Kalau provider utama kena rate limit, agent otomatis")
        print("pindah ke provider cadangan berikutnya.\n")

        # Tampilkan provider utama
        print(f"  {bold('0.')} {green('[UTAMA]')} {_provider_label(cfg)} / {cfg.get('model','-')}")
        if not fallbacks:
            print(f"  {dim('(belum ada provider cadangan)')}")
        else:
            for i, fb in enumerate(fallbacks, 1):
                label = _provider_label(fb)
                model = fb.get("model", "-")
                has_key = "🔑" if fb.get("api_key") else dim("(no key)")
                print(f"  {bold(str(i)+'.')} {cyan(label)} / {model}  {has_key}")

        print(f"\n  {bold('a')} — tambah provider cadangan")
        print(f"  {bold('h')} — hapus provider cadangan")
        print(f"  {bold('t')} — test urutan provider saat ini")
        print(f"  {bold('q')} — selesai")
        print(dim("─" * 44))

        try:
            choice = input(f"\n{bold(magenta('Pilihan: '))}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if choice == "q":
            break

        elif choice == "a":
            print(f"\n{bold('Pilih provider cadangan:')}")
            presets = PROVIDER_PRESETS
            for k, (name, url, model) in presets.items():
                # Nexray adalah provider utama dengan 3 endpoint, bukan fallback tunggal
                if "Nexray" in name:
                    continue
                note = ""
                if "OpenRouter" in name:
                    note = " ← ketik model ID manual"
                model_disp = dim(model) if model else dim("(ketik model ID)")
                print(f"  {k}. {name}  {model_disp}{note}")
            try:
                pc = input("Pilihan (atau Enter untuk custom): ").strip()
            except (KeyboardInterrupt, EOFError):
                continue

            preset = presets.get(pc)
            if preset:
                name, base_url, model = preset
                # Custom / preset dengan URL kosong → minta input manual
                if not base_url:
                    base_url = input("Base URL (contoh: https://api.example.com/v1): ").strip()
                    if not base_url:
                        print(yellow("Base URL tidak boleh kosong. Batal."))
                        continue
                if not model:
                    model = input("Nama model / model ID (wajib, contoh: openai/gpt-4o): ").strip()
                    if not model:
                        print(yellow("Nama model tidak boleh kosong. Batal."))
                        continue
                custom_m = input(f"Model [{model}]: ").strip()
                model = custom_m or model
                if not model:
                    print(yellow("Nama model tidak boleh kosong. Batal."))
                    continue
            else:
                # Enter ditekan tanpa pilih preset → full custom
                base_url = input("Base URL (contoh: https://api.example.com/v1): ").strip()
                if not base_url:
                    print(yellow("Base URL tidak boleh kosong. Batal."))
                    continue
                model = input("Nama model: ").strip()
                if not model:
                    print(yellow("Nama model tidak boleh kosong. Batal."))
                    continue

            # Tanya jenis endpoint
            print(f"\n{bold('Jenis endpoint:')}")
            print(f"  1. OpenAI-compatible (default) — pakai /chat/completions")
            print(f"  2. Custom API — pakai adapter GET ?text=<prompt>")
            try:
                kind_choice = input("Pilihan (1/2): ").strip()
            except (KeyboardInterrupt, EOFError):
                continue
            kind = "custom" if kind_choice == "2" else "openai"

            api_key = ""
            if "localhost" not in base_url and "127.0.0.1" not in base_url and kind != "custom":
                api_key = input("API Key: ").strip()
            if kind == "custom":
                print(dim("  (Custom API contoh: https://api.nexray.eu.cc/ai/gpt-3.5-turbo)"))

            fallbacks.append({"base_url": base_url, "api_key": api_key, "model": model, "kind": kind})
            cfg["fallback_providers"] = fallbacks
            save_config(cfg)
            # api_key sudah tersimpan di config.json (device lokal) — tidak perlu duplikasi ke .env

            print(green(f"✅ {_provider_label({'base_url': base_url, 'kind': kind})} ditambahkan sebagai fallback."))

        elif choice == "h":
            if not fallbacks:
                print(yellow("Belum ada provider cadangan."))
                continue
            try:
                idx = int(input("Hapus nomor berapa? ").strip()) - 1
                if 0 <= idx < len(fallbacks):
                    removed = fallbacks.pop(idx)
                    cfg["fallback_providers"] = fallbacks
                    save_config(cfg)
                    print(green(f"✅ {_provider_label(removed)} dihapus dari fallback."))
                else:
                    print(yellow("Nomor tidak valid."))
            except (ValueError, KeyboardInterrupt, EOFError):
                pass

        elif choice == "t":
            total = 1 + len(fallbacks)
            print(f"\n{bold('Urutan provider saat ini:')}")
            print(f"  1. {green('[UTAMA]')} {_provider_label(cfg)} / {cfg.get('model','-')}")
            for i, fb in enumerate(fallbacks, 2):
                print(f"  {i}. {cyan('[CADANGAN]')} {_provider_label(fb)} / {fb.get('model','-')}")
            print(f"\n  {dim(f'Total {total} provider. Agent akan coba urutan ini saat ada error.')}")

        else:
            print(yellow("Pilihan tidak dikenal."))

    return cfg


# ──────────────────────────────────────────────
# MAIN LOOP
# ──────────────────────────────────────────────

def main():
    # Beritahu tools module di mana letak source code agent ini
    _tools_module.AGENT_DIR = str(Path(__file__).parent.resolve())

    print(cyan(BANNER))

    cfg = load_config()

    def _needs_key(c: dict) -> bool:
        kind = c.get("kind", "openai")
        if kind in ("custom", "nexray"):
            return False
        url = c.get("base_url", "")
        return "localhost" not in url and "127.0.0.1" not in url

    if not cfg.get("api_key") and _needs_key(cfg):
        print(yellow("⚠️  API key belum dikonfigurasi."))
        cfg = setup_wizard()
        if not cfg.get("api_key") and _needs_key(cfg):
            print(red("❌ API key diperlukan. Keluar."))
            sys.exit(1)

    agent = Agent(cfg)

    fallbacks = cfg.get("fallback_providers", [])
    fb_info = (
        green(f"+ {len(fallbacks)} fallback")
        if fallbacks else dim("(ketik /fallback untuk tambah cadangan)")
    )
    print(f"  Provider: {bold(cyan(_provider_label(cfg)))} / {cfg.get('model', '-')}")
    print(f"  Fallback: {fb_info}")
    print(f"\n  Ketik {bold('/help')} untuk bantuan, {bold('/exit')} untuk keluar.\n")
    print(dim("─" * 44))

    while True:
        try:
            user_input = input(f"\n{bold(magenta('›'))} ").strip()
        except (KeyboardInterrupt, EOFError):
            save_history(agent.history)
            print(f"\n{dim('Sampai jumpa! 👋')}")
            sys.exit(0)

        if not user_input:
            continue

        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]
            if cmd in ("/exit", "/quit", "/q"):
                save_history(agent.history)
                print(dim("Sampai jumpa! 👋"))
                sys.exit(0)
            elif cmd == "/help":
                print(HELP_TEXT)
            elif cmd == "/clear":
                agent.clear_history()
            elif cmd == "/status":
                agent.show_status()
            elif cmd == "/tools":
                agent.show_tools()
            elif cmd == "/history":
                agent.show_history()
            elif cmd == "/config":
                cfg = setup_wizard()
                agent.cfg = cfg
                agent.active_provider = _provider_label(cfg)
            elif cmd == "/fallback":
                cfg = _fallback_wizard(cfg)
                agent.cfg = cfg
            elif cmd == "/upgrade":
                # Mode self-upgrade: AI edit kode dirinya sendiri
                rest = user_input[len("/upgrade"):].strip()
                if not rest:
                    print(f"""
{bold(cyan('🔧 Mode Self-Upgrade'))}
{dim('─' * 44)}
Dalam mode ini, AI akan membaca source code-nya sendiri,
membuat perubahan yang kamu minta, lalu restart otomatis.

{bold('Contoh:')}
  /upgrade tambahkan tool untuk translate teks
  /upgrade perbaiki typewriter animation biar lebih smooth
  /upgrade tambahkan perintah /save untuk export riwayat chat
  /upgrade buat history chat tersimpan ke file otomatis

{yellow('⚠️  AI akan menulis ulang bagian kodenya sendiri.')}
{dim('Backup .bak dibuat otomatis sebelum setiap perubahan.')}
{dim('─' * 44)}
""")
                    try:
                        rest = input(f"{bold(magenta('Apa yang mau diupgrade? '))} ").strip()
                    except (KeyboardInterrupt, EOFError):
                        print()
                        continue
                    if not rest:
                        continue

                agent_dir = str(_tools_module.AGENT_DIR)
                upgrade_request = UPGRADE_PROMPT.format(
                    agent_dir=agent_dir,
                    user_request=rest,
                )
                print(f"\n{dim('🔧 Memulai self-upgrade...')}\n")
                try:
                    reply = agent.chat(upgrade_request)
                    clear_screen()
                    print(dim("─" * 44))
                    print(f"{bold(cyan('Self-Upgrade:'))} {rest}\n")
                    print(f"{bold(green('AI:'))}")
                    typewriter(reply)
                    print(f"\n{dim('─' * 44)}")
                except KeyboardInterrupt:
                    print(f"\n{yellow('⚠️  Upgrade dibatalkan.')}")
            else:
                print(yellow(f"Perintah tidak dikenal: {cmd}. Ketik /help."))
            continue

        print()
        try:
            reply = agent.chat(user_input)

            # Bersihkan layar, tampilkan ulang konteks ringkas
            clear_screen()
            print(dim("─" * 44))
            print(f"{bold(cyan('Kamu:'))} {user_input}\n")
            print(f"{bold(green('AI:'))}")
            if reply.startswith("❌"):
                # Error — langsung print tanpa animasi
                print(reply)
            else:
                typewriter(reply)
            print(f"\n{dim('─' * 44)}")
        except KeyboardInterrupt:
            print(f"\n{yellow('⚠️  Dibatalkan.')}")
            if agent.history and agent.history[-1]["role"] == "user":
                agent.history.pop()


if __name__ == "__main__":
    main()
