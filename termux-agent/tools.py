"""
Tool implementations untuk AI agent.
Semua tool mengembalikan string (hasil operasi).
"""

import os
import sys
import subprocess
import tempfile
import textwrap
import json
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Optional

from ui import Spinner


# ──────────────────────────────────────────────
# SHELL
# ──────────────────────────────────────────────

def execute_shell(command: str, timeout: int = 30, working_dir: Optional[str] = None) -> str:
    """Jalankan shell command dan kembalikan output-nya."""
    cwd = working_dir or os.getcwd()
    try:
        with Spinner(f"menjalankan: {command[:50]}..."):
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env={**os.environ, "TERM": "xterm-256color"},
            )
        output_parts = []
        if result.stdout.strip():
            output_parts.append(result.stdout.strip())
        if result.stderr.strip():
            output_parts.append(f"[stderr]\n{result.stderr.strip()}")
        if result.returncode != 0:
            output_parts.append(f"[exit code: {result.returncode}]")

        return "\n".join(output_parts) if output_parts else "(perintah selesai, tidak ada output)"
    except subprocess.TimeoutExpired:
        return f"❌ Timeout: perintah tidak selesai dalam {timeout} detik."
    except Exception as e:
        return f"❌ Error menjalankan perintah: {e}"


# ──────────────────────────────────────────────
# FILE OPERATIONS
# ──────────────────────────────────────────────

def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """Baca konten file. Bisa spesifik baris dengan start_line/end_line."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"❌ File tidak ditemukan: {path}"
    if not p.is_file():
        return f"❌ Path bukan file: {path}"
    try:
        size = p.stat().st_size
        if size > 2 * 1024 * 1024:  # > 2MB
            return f"❌ File terlalu besar ({size // 1024}KB). Gunakan start_line/end_line."

        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)

        if start_line is not None or end_line is not None:
            s = (start_line or 1) - 1
            e = end_line or len(lines)
            lines = lines[s:e]
            header = f"[{path}] baris {s+1}–{min(e, len(lines)+s)}\n"
            return header + "".join(lines)

        if len(lines) > 500:
            preview = "".join(lines[:100])
            return (
                f"[{path}] ({len(lines)} baris, file besar)\n"
                f"💡 Gunakan execute_shell(grep/rg/sed/wc -l) untuk cari bagian relevan, "
                f"atau read_file(start_line, end_line) untuk baca snippet.\n"
                f"Preview 100 baris pertama:\n{preview}\n...(terpotong)"
            )
        return f"[{path}]\n{content}"
    except Exception as e:
        return f"❌ Error membaca file: {e}"


def write_file(path: str, content: str, append: bool = False) -> str:
    """Tulis konten ke file. append=True untuk menambah ke akhir file."""
    p = Path(path).expanduser().resolve()
    # Source code agent harus diedit pakai patch_file (lebih aman & hemat token)
    if p.name in {"agent.py", "tools.py", "config.py"} and p.parent == Path(__file__).parent.resolve():
        return f"❌ Untuk mengedit source code agent ({p.name}), gunakan patch_file, bukan write_file."
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(p, mode, encoding="utf-8") as f:
            f.write(content)
        action = "ditambahkan ke" if append else "ditulis ke"
        # Notifikasi web UI kalau sedang aktif
        try:
            import web_ui as _wui
            _wui.notify_file_written(str(p))
        except ImportError:
            pass
        return f"✅ Konten berhasil {action} {path} ({len(content)} karakter)"
    except Exception as e:
        return f"❌ Error menulis file: {e}"


def list_directory(path: str = ".", recursive: bool = False) -> str:
    """List isi direktori."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"❌ Direktori tidak ditemukan: {path}"
    try:
        if recursive:
            items = []
            for root, dirs, files in os.walk(p):
                # Skip hidden dirs
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                rel = Path(root).relative_to(p)
                for f in sorted(files):
                    items.append(str(rel / f) if str(rel) != "." else f)
            return f"[{path}] (rekursif)\n" + "\n".join(items[:200])
        else:
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            lines = []
            for item in items:
                if item.is_dir():
                    lines.append(f"📁 {item.name}/")
                else:
                    size = item.stat().st_size
                    size_str = f"{size}B" if size < 1024 else f"{size//1024}KB"
                    lines.append(f"📄 {item.name} ({size_str})")
            return f"[{path}]\n" + "\n".join(lines)
    except Exception as e:
        return f"❌ Error list direktori: {e}"


# ──────────────────────────────────────────────
# WEB SEARCH & FETCH
# ──────────────────────────────────────────────

def web_search(query: str, num_results: int = 5) -> str:
    """Search internet menggunakan DuckDuckGo (tidak perlu API key)."""
    try:
        # Coba pakai duckduckgo_search jika tersedia
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append(
                    f"**{r.get('title', '')}**\n"
                    f"URL: {r.get('href', '')}\n"
                    f"{r.get('body', '')}"
                )
        if not results:
            return "Tidak ada hasil ditemukan."
        return f"Hasil pencarian '{query}':\n\n" + "\n\n---\n\n".join(results)
    except ImportError:
        # Fallback: DuckDuckGo instant answer API
        return _ddg_fallback(query)
    except Exception as e:
        return f"❌ Error search: {e}\nCoba: pip install duckduckgo-search"


def _ddg_fallback(query: str) -> str:
    """Fallback menggunakan DuckDuckGo Instant Answer API."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "termux-agent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        parts = []
        if data.get("AbstractText"):
            parts.append(f"**{data.get('Heading', query)}**\n{data['AbstractText']}")
            if data.get("AbstractURL"):
                parts.append(f"Sumber: {data['AbstractURL']}")

        related = data.get("RelatedTopics", [])[:5]
        for item in related:
            if isinstance(item, dict) and item.get("Text"):
                parts.append(f"• {item['Text'][:200]}")

        if parts:
            return "\n".join(parts)
        return (
            f"Tidak ada hasil instant untuk '{query}'.\n"
            "Install duckduckgo-search untuk hasil lebih lengkap:\n"
            "  pip install duckduckgo-search"
        )
    except Exception as e:
        return f"❌ Error search fallback: {e}"


def fetch_url(url: str, max_chars: int = 8000) -> str:
    """Ambil konten dari URL (plaintext). Hanya http/https."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"❌ URL scheme '{parsed.scheme}' tidak didukung. Hanya http/https yang diperbolehkan."
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
            )
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()

        text = raw.decode("utf-8", errors="replace")

        # Strip HTML tags sederhana
        if "html" in content_type.lower() or text.strip().startswith("<"):
            text = _strip_html(text)

        text = text[:max_chars]
        if len(text) == max_chars:
            text += "\n...(terpotong)"
        return f"[{url}]\n{text}"
    except urllib.error.HTTPError as e:
        return f"❌ HTTP {e.code}: {e.reason} — {url}"
    except Exception as e:
        return f"❌ Error fetch URL: {e}"


def _strip_html(html: str) -> str:
    """Strip HTML tags sederhana tanpa library tambahan."""
    import re
    # Hapus script dan style
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Hapus tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Compress whitespace
    html = re.sub(r"\s+", " ", html)
    return html.strip()


# ──────────────────────────────────────────────
# SELF-MODIFICATION
# ──────────────────────────────────────────────

#: Path direktori source agent (diisi saat startup oleh agent.py)
AGENT_DIR: str = ""


def patch_file(path: str, old_text: str, new_text: str, backup: bool = True) -> str:
    """
    Ganti teks spesifik di dalam file (find-replace tepat sasaran).
    Lebih aman dari write_file untuk self-editing karena tidak tulis ulang seluruh file.
    Otomatis backup ke <path>.bak sebelum edit.
    """
    if not old_text:
        return "❌ old_text tidak boleh kosong."
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"❌ File tidak ditemukan: {path}"
    if not p.is_file():
        return f"❌ Path bukan file: {path}"
    try:
        content = p.read_text(encoding="utf-8")
        if old_text not in content:
            # Bantu debug: cari baris yang mirip
            lines = content.splitlines()
            first_word = old_text.strip().splitlines()[0][:40] if old_text.strip() else ""
            hints = [f"  baris {i+1}: {l[:80]}" for i, l in enumerate(lines)
                     if first_word and first_word[:15] in l][:5]
            hint_str = "\n".join(hints)
            msg = f"❌ Teks tidak ditemukan di {path}."
            if hint_str:
                msg += f"\nBaris yang mungkin relevan:\n{hint_str}"
            return msg

        count = content.count(old_text)
        if count > 1:
            return (
                f"❌ Teks ditemukan {count}x di {path} — terlalu ambigu.\n"
                "Tambahkan lebih banyak konteks di old_text agar unik."
            )

        # Backup dulu
        if backup:
            bak = p.with_suffix(p.suffix + ".bak")
            bak.write_text(content, encoding="utf-8")

        new_content = content.replace(old_text, new_text, 1)

        # Validasi syntax Python jika file .py
        if p.suffix == ".py":
            import ast
            try:
                ast.parse(new_content)
            except SyntaxError as e:
                return f"❌ Syntax error setelah patch — tidak disimpan: {e}"

        p.write_text(new_content, encoding="utf-8")
        bak_note = f" (backup: {p.with_suffix(p.suffix + '.bak')})" if backup else ""
        return f"✅ Patch berhasil diterapkan ke {path}{bak_note}"
    except Exception as e:
        return f"❌ Error saat patch: {e}"


def reload_agent() -> str:
    """
    Restart proses agent ini di tempat (exec syscall).
    Panggil setelah selesai mengedit source file.
    Agent akan restart dengan kode yang sudah diupdate.
    """
    import os
    try:
        # Flush output sebelum restart
        sys.stdout.flush()
        sys.stderr.flush()
        # exec() ganti proses ini dengan proses baru (PID sama, tapi kode baru)
        os.execv(sys.executable, [sys.executable] + sys.argv)
        # Baris ini tidak akan pernah tercapai
        return "restarting..."
    except Exception as e:
        return f"❌ Gagal restart: {e}\nCoba keluar dan jalankan ulang manual."


def list_agent_files() -> str:
    """Tampilkan file-file source code agent ini sendiri."""
    base = Path(AGENT_DIR) if AGENT_DIR else Path(__file__).parent
    py_files = sorted(base.glob("*.py"))
    lines = [f"📂 Source agent di: {base}", ""]
    for f in py_files:
        size = f.stat().st_size
        size_str = f"{size}B" if size < 1024 else f"{size//1024}KB"
        lines.append(f"  🐍 {f.name} ({size_str})")
    # Tampilkan juga file config/data
    for ext in ("*.json", "*.env", "*.md", "*.txt", "*.sh"):
        for f in sorted(base.glob(ext)):
            size = f.stat().st_size
            lines.append(f"  📄 {f.name} ({size}B)")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# CODE EXECUTION
# ──────────────────────────────────────────────

def run_python(code: str, timeout: int = 30) -> str:
    """Jalankan Python code dalam subprocess yang terisolasi."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
        output_parts = []
        if result.stdout.strip():
            output_parts.append(result.stdout.strip())
        if result.stderr.strip():
            output_parts.append(f"[stderr]\n{result.stderr.strip()}")
        if result.returncode != 0:
            output_parts.append(f"[exit code: {result.returncode}]")
        return "\n".join(output_parts) if output_parts else "(kode selesai, tidak ada output)"
    except subprocess.TimeoutExpired:
        return f"❌ Timeout: kode tidak selesai dalam {timeout} detik."
    except Exception as e:
        return f"❌ Error menjalankan kode: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_bash(code: str, timeout: int = 30) -> str:
    """Jalankan bash script dalam file sementara."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, encoding="utf-8"
    ) as f:
        f.write("#!/bin/bash\n" + code)
        tmp_path = f.name
    os.chmod(tmp_path, 0o755)

    try:
        with Spinner("menjalankan bash script..."):
            result = subprocess.run(
                ["bash", tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ},
            )
        out = result.stdout.strip()
        err = result.stderr.strip()
        parts = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"[stderr]\n{err}")
        if result.returncode != 0:
            parts.append(f"[exit code: {result.returncode}]")
        return "\n".join(parts) if parts else "(script selesai, tidak ada output)"
    except subprocess.TimeoutExpired:
        return f"❌ Timeout {timeout}s."
    except Exception as e:
        return f"❌ Error: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ──────────────────────────────────────────────
# TOOL DEFINITIONS (untuk OpenAI function calling)
# ──────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": (
                "Jalankan perintah shell/terminal di sistem. "
                "Gunakan untuk: install package, jalankan program, manipulasi file via CLI, "
                "cek sistem, download file, dll. "
                "Sangat berguna untuk efisiensi: pakai grep, rg, find, sed, awk, wc -l, head, tail "
                "untuk mencari/inspeksi file tanpa harus membaca seluruh file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Perintah shell yang akan dijalankan"},
                    "working_dir": {"type": "string", "description": "Direktori kerja (opsional)"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Baca konten file dari filesystem. "
                "Untuk file besar, gunakan start_line/end_line untuk baca hanya bagian yang relevan; "
                "hindari membaca seluruh file besar sekaligus."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path file yang akan dibaca"},
                    "start_line": {"type": "integer", "description": "Baris awal (1-based, opsional)"},
                    "end_line": {"type": "integer", "description": "Baris akhir (opsional)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Tulis konten ke file. Buat file baru atau timpa yang sudah ada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path file tujuan"},
                    "content": {"type": "string", "description": "Konten yang akan ditulis"},
                    "append": {"type": "boolean", "description": "Tambah ke akhir file (default: false = timpa)"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Tampilkan daftar file dan folder dalam direktori.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path direktori (default: direktori saat ini)"},
                    "recursive": {"type": "boolean", "description": "List rekursif (default: false)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Cari informasi di internet menggunakan DuckDuckGo. "
                "Gunakan untuk: cari info terkini, dokumentasi, berita, dll."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Query pencarian"},
                    "num_results": {"type": "integer", "description": "Jumlah hasil (default: 5, max: 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Ambil konten dari URL tertentu (web page, API, dll).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL yang akan di-fetch"},
                    "max_chars": {"type": "integer", "description": "Maksimal karakter yang dikembalikan (default: 8000)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Jalankan kode Python dan kembalikan outputnya. "
                "Gunakan untuk: kalkulasi, data processing, script otomasi, dll."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Kode Python yang akan dijalankan"},
                    "timeout": {"type": "integer", "description": "Timeout dalam detik (default: 30)"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Jalankan bash script multi-baris.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Bash script yang akan dijalankan"},
                    "timeout": {"type": "integer", "description": "Timeout dalam detik (default: 30)"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": (
                "Edit file secara tepat sasaran dengan find-replace. "
                "LEBIH AMAN dari write_file untuk mengedit kode — hanya ubah bagian yang dimaksud, "
                "sisanya tidak tersentuh. Otomatis backup dan validasi syntax Python. "
                "Gunakan ini untuk memodifikasi source code agent sendiri (agent.py, tools.py, config.py)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":     {"type": "string", "description": "Path file yang akan di-patch"},
                    "old_text": {"type": "string", "description": "Teks yang akan diganti (harus unik di file)"},
                    "new_text": {"type": "string", "description": "Teks pengganti"},
                    "backup":   {"type": "boolean", "description": "Buat backup .bak sebelum edit (default: true)"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reload_agent",
            "description": (
                "Restart agent ini di tempat setelah selesai mengedit source code. "
                "Proses baru akan pakai kode yang sudah diupdate. "
                "Panggil ini setelah patch_file selesai dan kamu yakin perubahannya benar."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_agent_files",
            "description": "Tampilkan semua file source code agent ini sendiri.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def dispatch_tool(name: str, args: dict, cfg: dict) -> str:
    """Panggil tool berdasarkan nama."""
    timeout_shell = int(cfg.get("shell_timeout", 30))
    timeout_code = int(cfg.get("code_timeout", 30))
    max_results = int(cfg.get("max_search_results", 5))

    if name == "execute_shell":
        return execute_shell(
            args["command"],
            timeout=timeout_shell,
            working_dir=args.get("working_dir"),
        )
    elif name == "read_file":
        return read_file(
            args["path"],
            start_line=args.get("start_line"),
            end_line=args.get("end_line"),
        )
    elif name == "write_file":
        return write_file(args["path"], args["content"], append=args.get("append", False))
    elif name == "list_directory":
        return list_directory(args.get("path", "."), recursive=args.get("recursive", False))
    elif name == "web_search":
        return web_search(args["query"], num_results=min(args.get("num_results", max_results), 10))
    elif name == "fetch_url":
        return fetch_url(args["url"], max_chars=args.get("max_chars", 8000))
    elif name == "run_python":
        return run_python(args["code"], timeout=args.get("timeout", timeout_code))
    elif name == "run_bash":
        return run_bash(args["code"], timeout=args.get("timeout", timeout_code))
    elif name == "patch_file":
        return patch_file(
            args["path"],
            args["old_text"],
            args["new_text"],
            backup=args.get("backup", True),
        )
    elif name == "reload_agent":
        return reload_agent()
    elif name == "list_agent_files":
        return list_agent_files()
    else:
        return f"❌ Tool tidak dikenal: {name}"
