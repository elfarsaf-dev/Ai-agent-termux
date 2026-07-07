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
from pathlib import Path

try:
    import readline  # noqa: F401 — aktifkan arrow keys & history di terminal
except ImportError:
    pass

from config import load_config, setup_wizard
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
# HTTP CLIENT (pakai urllib bawaan Python)
# ──────────────────────────────────────────────

class APIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


def call_api(cfg: dict, messages: list, tools: list) -> dict:
    """
    Panggil OpenAI-compatible Chat Completions API pakai urllib.
    Tidak butuh library eksternal apapun.
    """
    base_url = cfg.get("base_url", "").rstrip("/")
    api_key  = cfg.get("api_key", "no-key")
    model    = cfg.get("model", "gemini-2.0-flash")

    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": int(cfg.get("max_tokens", 4096)),
        "temperature": float(cfg.get("temperature", 0.7)),
    }

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "termux-agent/1.0",
    }

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, dict):
                raise APIError(f"Response tidak terduga dari API: {str(data)[:200]}")
            return data
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(raw)
            if isinstance(err_data, dict):
                msg = (
                    err_data.get("error", {}).get("message")
                    or err_data.get("message")
                    or raw[:300]
                )
            else:
                msg = raw[:300]
        except json.JSONDecodeError:
            msg = raw[:300]
        raise APIError(msg, status_code=e.code) from e
    except urllib.error.URLError as e:
        raise APIError(f"Tidak bisa konek ke API: {e.reason}") from e
    except TimeoutError:
        raise APIError("Request timeout — cek koneksi internet kamu.")


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
  /config    — ubah provider/model/API key
  /status    — info konfigurasi saat ini
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
        self.history: list[dict] = []
        self.total_tokens = 0

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
        self.history.append({"role": "user", "content": user_input})

        # Trim history agar tidak terlalu panjang
        max_hist = int(self.cfg.get("max_history", 50))
        if len(self.history) > max_hist:
            self.history = self.history[-max_hist:]

        messages = [self._system_message()] + self.history

        while True:
            try:
                response = call_api(self.cfg, messages, TOOL_DEFINITIONS)
            except APIError as e:
                if e.status_code == 401:
                    return red("❌ API key tidak valid. Ketik /config untuk atur ulang.")
                elif e.status_code == 429:
                    return red("❌ Rate limit tercapai. Tunggu sebentar lalu coba lagi.")
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
                return reply

            # Ada tool calls → jalankan semua
            messages.append(msg)

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

                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result,
                })

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
        print(green("✅ Riwayat percakapan dihapus."))

    def show_status(self):
        api_key = self.cfg.get("api_key", "")
        key_display = ("*" * 8 + api_key[-4:]) if len(api_key) > 4 else ("(kosong)" if not api_key else api_key)
        print(f"""
{bold('Status Konfigurasi:')}
  Provider : {cyan(self.cfg.get('base_url', '-'))}
  Model    : {cyan(self.cfg.get('model', '-'))}
  API Key  : {dim(key_display)}
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
                print(f"{bold(green('AI:'))} {content[:200]}")
        print()


# ──────────────────────────────────────────────
# MAIN LOOP
# ──────────────────────────────────────────────

def main():
    # Beritahu tools module di mana letak source code agent ini
    _tools_module.AGENT_DIR = str(Path(__file__).parent.resolve())

    print(cyan(BANNER))

    cfg = load_config()

    def _is_local(c: dict) -> bool:
        url = c.get("base_url", "")
        return "localhost" in url or "127.0.0.1" in url

    if not cfg.get("api_key") and not _is_local(cfg):
        print(yellow("⚠️  API key belum dikonfigurasi."))
        cfg = setup_wizard()
        if not cfg.get("api_key") and not _is_local(cfg):
            print(red("❌ API key diperlukan. Keluar."))
            sys.exit(1)

    agent = Agent(cfg)

    print(f"  Model  : {bold(cyan(cfg.get('model', '-')))}")
    print(f"  Server : {dim(cfg.get('base_url', '-'))}")
    print(f"\n  Ketik {bold('/help')} untuk bantuan, {bold('/exit')} untuk keluar.\n")
    print(dim("─" * 44))

    while True:
        try:
            user_input = input(f"\n{bold(magenta('›'))} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{dim('Sampai jumpa! 👋')}")
            sys.exit(0)

        if not user_input:
            continue

        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]
            if cmd in ("/exit", "/quit", "/q"):
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
