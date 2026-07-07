# 🤖 Termux AI Agent

AI agent serba bisa yang berjalan di terminal (Termux / Linux). Bisa chat, jalankan shell, baca/tulis file, search internet, dan generate + jalankan kode.

## Fitur

| Fitur | Deskripsi |
|-------|-----------|
| 💬 Chat | Tanya-jawab dengan AI (GPT-4o, Claude, Llama, dll) |
| 🖥️ Shell | Jalankan perintah terminal langsung |
| 📁 File | Baca, tulis, dan list file/folder |
| 🌐 Web | Search DuckDuckGo + fetch URL |
| 🐍 Kode | Generate dan jalankan Python/Bash |

## Instalasi di Termux

### 1. Copy file ke Termux

**Opsi A — Download lewat git (butuh internet):**
```bash
pkg install git -y
git clone <url-repo> ~/termux-agent
cd ~/termux-agent
```

**Opsi B — Copy manual:**
Pindahkan folder `termux-agent/` ke direktori Termux kamu (misalnya `~/termux-agent/`).

### 2. Jalankan setup

```bash
cd ~/termux-agent
bash setup.sh
```

Script ini akan:
- Install Python (kalau belum ada)
- Install semua dependency
- Buat shortcut `ai` agar bisa dijalankan dari mana saja

### 3. Jalankan agent

```bash
ai
# atau
python3 agent.py
```

Pertama kali jalan, kamu akan diminta memilih provider dan memasukkan API key.

---

## Konfigurasi

### Provider yang didukung

| Provider | Base URL | Catatan |
|----------|----------|---------|
| OpenAI | `https://api.openai.com/v1` | Perlu API key |
| Groq | `https://api.groq.com/openai/v1` | Gratis, cepat |
| Together AI | `https://api.together.xyz/v1` | Perlu API key |
| OpenRouter | `https://openrouter.ai/api/v1` | Banyak model |
| Ollama | `http://localhost:11434/v1` | Lokal, gratis |
| Custom | URL lainnya | Provider apapun yg OpenAI-compatible |

### Cara ganti provider saat agent jalan

```
/config
```

### Edit manual

Buka `config.json`:
```json
{
  "base_url": "https://api.groq.com/openai/v1",
  "model": "llama-3.1-70b-versatile",
  "max_tokens": 4096,
  "temperature": 0.7
}
```

API key disimpan terpisah di `.env`:
```
OPENAI_API_KEY=gsk_xxxxxxxxxxxx
```

### Environment variables

Semua config bisa di-set via env var:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4o"
export AGENT_TEMPERATURE="0.7"
export AGENT_MAX_TOKENS="4096"
export AGENT_SHELL_TIMEOUT="30"
export AGENT_CODE_TIMEOUT="30"
```

---

## Penggunaan

### Perintah khusus

```
/help      — tampilkan bantuan
/clear     — hapus riwayat chat
/config    — ganti provider/model/API key
/status    — lihat konfigurasi saat ini
/tools     — daftar semua tool
/history   — lihat riwayat chat
/exit      — keluar
Ctrl+C     — keluar
```

### Contoh percakapan

```
› buat file halo.py berisi script hello world lalu jalankan

› list semua file di folder Downloads

› search cara install ffmpeg di termux

› fetch url https://api.github.com/users/torvalds

› hitung semua bilangan prima di bawah 1000 pakai Python

› backup folder ~/documents ke ~/backup dengan timestamp

› install cowsay dan tampilkan "Halo dari AI agent"
```

---

## Struktur File

```
termux-agent/
├── agent.py          # Main agent + loop utama
├── tools.py          # Implementasi semua tools
├── config.py         # Manajemen konfigurasi
├── requirements.txt  # Dependency Python
├── setup.sh          # Script setup Termux
├── config.json       # Konfigurasi (dibuat otomatis)
└── .env              # API key (dibuat otomatis)
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'openai'`**
```bash
pip install openai
```

**`ModuleNotFoundError: No module named 'duckduckgo_search'`**
```bash
pip install duckduckgo-search
# Web search akan tetap berfungsi dengan fallback jika tidak ada
```

**API key tidak valid**
```
Ketik /config lalu masukkan ulang API key yang benar
```

**Tidak bisa konek ke API (offline)**
Cek koneksi internet:
```bash
curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Ollama tidak bisa diakses**
```bash
# Pastikan Ollama jalan di PC/laptop kamu
# Kemudian akses via IP lokal, bukan localhost
# (Termux tidak share localhost dengan host)
export OPENAI_BASE_URL="http://192.168.x.x:11434/v1"
```

---

## Lisensi

MIT — bebas digunakan dan dimodifikasi.
