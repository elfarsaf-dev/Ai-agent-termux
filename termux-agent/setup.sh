#!/data/data/com.termux/files/usr/bin/bash
# ══════════════════════════════════════════════
#  Setup Termux AI Agent
#  Jalankan sekali setelah copy file ke Termux
# ══════════════════════════════════════════════

set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  🤖  Setup Termux AI Agent               ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Update package list ──
echo "📦 Update packages..."
pkg update -y -q 2>/dev/null || true

# ── 2. Install Python jika belum ada ──
if ! command -v python3 &>/dev/null; then
    echo "🐍 Install Python 3..."
    pkg install -y python
fi

echo "✅ Python: $(python3 --version)"

# ── 3. Install Rust (dibutuhkan untuk build beberapa package) ──
if ! command -v rustc &>/dev/null; then
    echo "🦀 Install Rust (diperlukan untuk openai)..."
    pkg install -y rust
fi

# ── 4. Upgrade pip ──
echo "📦 Upgrade pip..."
python3 -m pip install --upgrade pip -q

# ── 5. Install dependencies ──
echo "📦 Install dependencies..."
pip install -r requirements.txt -q

echo ""
echo "✅ Semua dependency terinstall!"

# ── 5. Buat shortcut ──
AGENT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$PREFIX/bin"

cat > "$BIN_DIR/ai" << EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$AGENT_DIR"
exec python3 agent.py "\$@"
EOF

chmod +x "$BIN_DIR/ai"
echo "✅ Shortcut dibuat: ketik 'ai' dari mana saja untuk jalankan agent"

echo ""
echo "══════════════════════════════════════════════"
echo "  Setup selesai! 🎉"
echo ""
echo "  Cara pakai:"
echo "    ai             — jalankan agent"
echo "    python3 agent.py  — alternatif"
echo ""
echo "  Pertama kali jalan, kamu akan diminta"
echo "  memasukkan API key."
echo "══════════════════════════════════════════════"
echo ""
