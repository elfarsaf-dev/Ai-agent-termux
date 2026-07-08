"""
Konfigurasi agent — bisa di-set via environment variable, file .env, atau config.json
"""

import os
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config.json"
ENV_FILE = Path(__file__).parent / ".env"

DEFAULTS = {
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "api_key": "",
    "model": "gemini-2.0-flash",
    "max_tokens": 4096,
    "temperature": 0.7,
    "system_prompt": (
        "Kamu adalah AI agent serba bisa yang berjalan di terminal (Termux/Linux). "
        "Kamu bisa: chat biasa, jalankan shell commands, baca/tulis file, search internet, "
        "dan generate + jalankan kode Python. "
        "Selalu gunakan tools yang tersedia jika user meminta sesuatu yang butuh aksi nyata. "
        "Jawab dalam bahasa yang sama dengan user (Indonesia atau Inggris). "
        "Jika kamu menjalankan shell command, tampilkan output-nya. "
        "Jika ada error, coba diagnosa dan perbaiki sendiri. "
        "EFISIENSI: untuk tugas file/kode, jangan langsung baca seluruh file besar. "
        "Pertama pakai execute_shell dengan grep/rg/find/sed/wc -l/head/tail untuk mencari bagian relevan. "
        "Baru baca snippet dengan read_file(start_line, end_line). Gunakan patch_file untuk edit tepat sasaran, "
        "hindari write_file menimpa seluruh file. Jawaban langsung dan to the point, tanpa basa-basi. "
        "Jika user meminta aksi (jalankan command, baca/edit file, search, dll), kamu WAJIB langsung memanggil tool yang tersedia. "
        "Jangan pernah menyuruh user mengetik atau menjalankan command manual — AI yang jalankan semuanya via tool."
    ),
    "shell_timeout": 30,
    "code_timeout": 30,
    "max_search_results": 5,
    "max_history": 50,
}


def _load_env_file():
    """Load .env file jika ada."""
    if not ENV_FILE.exists():
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


def load_config() -> dict:
    """Load config dari berbagai sumber, priority: env > config.json > defaults."""
    _load_env_file()

    cfg = dict(DEFAULTS)

    # Load dari config.json jika ada
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                file_cfg = json.load(f)
            cfg.update(file_cfg)
        except (json.JSONDecodeError, OSError):
            pass

    # Override dari environment variables
    env_map = {
        "OPENAI_BASE_URL": "base_url",
        "OPENAI_API_KEY": "api_key",
        "OPENAI_MODEL": "model",
        "AGENT_MODEL": "model",
        "AGENT_BASE_URL": "base_url",
        "AGENT_API_KEY": "api_key",
        "AGENT_MAX_TOKENS": "max_tokens",
        "AGENT_TEMPERATURE": "temperature",
        "AGENT_SYSTEM_PROMPT": "system_prompt",
        "AGENT_SHELL_TIMEOUT": "shell_timeout",
        "AGENT_CODE_TIMEOUT": "code_timeout",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            cfg[cfg_key] = val

    return cfg


def save_config(cfg: dict):
    """Simpan config ke config.json.
    api_key utama tidak disimpan ke file (pakai .env).
    api_key fallback_providers disimpan di file (device lokal, aman).
    """
    save_data = {k: v for k, v in cfg.items() if k != "api_key"}
    with open(CONFIG_FILE, "w") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    print(f"✅ Config disimpan ke {CONFIG_FILE}")


PROVIDER_PRESETS: dict[str, tuple[str, str, str]] = {
    "1": ("Google Gemini",       "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.0-flash"),
    "2": ("OpenAI",              "https://api.openai.com/v1",                               "gpt-4o"),
    "3": ("Groq",                "https://api.groq.com/openai/v1",                          "llama-3.3-70b-versatile"),
    "4": ("Together AI",         "https://api.together.xyz/v1",                             "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"),
    "5": ("OpenRouter",          "https://openrouter.ai/api/v1",                            ""),
    "6": ("Nexray",              "",                                                          ""),
    "7": ("Ollama (lokal)",      "http://localhost:11434/v1",                                 "llama3"),
    "8": ("Custom / Lainnya",    "",                                                          ""),
}


def setup_wizard():
    """Interactive setup jika config belum lengkap."""
    print("\n" + "═" * 50)
    print("  ⚙️  SETUP AI AGENT")
    print("═" * 50)
    print("Konfigurasi provider AI kamu.\n")

    providers = PROVIDER_PRESETS

    print("Pilih provider:")
    for k, (name, url, model) in providers.items():
        note = ""
        if "Groq" in name:
            note = " ← limit cepet, cocok buat fallback"
        elif "OpenRouter" in name:
            note = " ← ketik model ID manual (contoh: openai/gpt-4o)"
        elif "Nexray" in name:
            note = " ← 3 URL custom API (saling bantu)"
        print(f"  {k}. {name}{note}")
    print()

    choice = input("Pilihan (1-8): ").strip() or "1"
    name, base_url, model = providers.get(choice, ("Custom", "", ""))

    kind = "openai"
    nexray_urls = None

    if choice == "6":  # Nexray
        kind = "nexray"
        print("\nMasukkan 3 endpoint Nexray (GET <url>?text=<prompt>).")
        print("Kosongkan kalau tidak punya, tapi minimal isi 1 URL agar bisa jalan.")
        urls = []
        for i in range(1, 4):
            u = input(f"Nexray URL {i}: ").strip()
            if u:
                urls.append(u)
        if not urls:
            print("[!] Minimal 1 URL Nexray diperlukan. Setup dibatalkan.")
            return load_config()
        base_url = urls[0]
        model = "nexray"
        nexray_urls = urls

    elif choice == "8" or not base_url:
        base_url = input(f"Base URL (contoh: https://api.openai.com/v1): ").strip()
        model = input(f"Nama model: ").strip()
    else:
        custom_model = input(f"Model [{model}]: ").strip()
        if custom_model:
            model = custom_model

    # Pastikan model tidak kosong (wajib untuk OpenRouter dsb)
    while not model:
        model = input(f"Model ID untuk {name} (wajib, contoh: openai/gpt-4o): ").strip()
        if not model:
            print("[!] Model tidak boleh kosong. Coba lagi.")

    # Tanya jenis endpoint hanya untuk custom / lainnya
    if choice == "8":
        print(f"\nJenis endpoint:")
        print(f"  1. OpenAI-compatible (default) — pakai /chat/completions")
        print(f"  2. Custom API GET — pakai <url>?text=<prompt> (contoh Nexray)")
        kind_choice = input("Pilihan (1/2): ").strip()
        kind = "custom" if kind_choice == "2" else "openai"

    api_key = ""
    if kind not in ("custom", "nexray") and "localhost" not in base_url and "127.0.0.1" not in base_url:
        api_key = input("API Key: ").strip()
    if kind == "custom":
        print("  Custom API: masukkan URL lengkap endpoint, contoh https://api.nexray.eu.cc/ai/gpt-3.5-turbo")

    cfg = load_config()
    update = {"base_url": base_url, "api_key": api_key, "model": model, "kind": kind}
    if nexray_urls:
        update["nexray_urls"] = nexray_urls
    cfg.update(update)
    save_config(cfg)

    # Simpan api_key ke .env agar tidak masuk config.json
    if api_key:
        with open(ENV_FILE, "w") as f:
            f.write(f"OPENAI_API_KEY={api_key}\n")
        print(f"🔑 API key disimpan ke {ENV_FILE}")

    print("\n✅ Setup selesai! Jalankan ulang agent.\n")
    return cfg
