#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

run_setup_wizard() {
    echo "[setup] .env bulunamadı — ilk-çalıştırma wizard'ı"
    echo

    local token=""
    while [[ -z "$token" ]]; do
        read -r -p "Discord bot token: " token
        [[ -z "$token" ]] && echo "  Boş olamaz, tekrar gir."
    done

    echo
    echo "Yerel LLM sunucu adresi:"
    echo "  [1] http://localhost:3131/v1   (llama-server)"
    echo "  [2] http://localhost:1234/v1   (LM Studio)"
    echo "  [3] http://localhost:8000/v1   (vLLM / Ollama)"
    echo "  [4] custom"
    local choice=""
    read -r -p "Seçim [1]: " choice
    local base_url
    case "${choice:-1}" in
        1) base_url="http://localhost:3131/v1" ;;
        2) base_url="http://localhost:1234/v1" ;;
        3) base_url="http://localhost:8000/v1" ;;
        4) read -r -p "  Custom URL: " base_url ;;
        *) base_url="http://localhost:3131/v1" ;;
    esac

    echo
    local model=""
    read -r -p "Model identifier (tek-modelli sunucularda boş bırakılabilir): " model

    echo
    echo "Slash sync modu:"
    echo "  [1] Dev — guild ID set, slash anında görünür (önerilen)"
    echo "  [2] Prod — global, propagation ~1 saat"
    local sync_choice=""
    read -r -p "Seçim [1]: " sync_choice
    local guild_id=""
    if [[ "${sync_choice:-1}" == "1" ]]; then
        echo
        echo "  ID için: Discord → Ayarlar → Gelişmiş → Geliştirici Modu;"
        echo "  sunucu adına sağ tık → Sunucu Kimliğini Kopyala"
        read -r -p "  Discord sunucu ID (boş geçilebilir): " guild_id
    fi

    echo
    local tr_answer=""
    read -r -p "Türkiye'de misin? (Discord SNI engelli, SpoofDPI gerekli) [E/h]: " tr_answer
    local proxy=""
    if [[ "${tr_answer:-e}" =~ ^[EeYy]$ ]]; then
        proxy="http://127.0.0.1:8080"
    fi

    cat > .env <<ENV
DISCORD_TOKEN=$token
OPENAI_BASE_URL=$base_url
OPENAI_API_KEY=not-needed
OPENAI_MODEL=$model
SESSION_TTL_SECONDS=7200
HISTORY_MAX_MESSAGES=100
GUILD_ID=$guild_id
DISCORD_PROXY=$proxy

# Persistent memory (default'lar yeterli)
MEMPALACE_PATH=
MEMORY_AUTO_EXTRACT=true
MEMORY_EXTRACT_EVERY_N_MESSAGES=8
MEMORY_RETRIEVAL_K=3
MEMORY_MIN_FACT_LEN=6
ENV

    echo
    echo "[setup] .env yazıldı."
    echo
}

if [[ ! -f .env ]]; then
    run_setup_wizard
fi

SPOOFDPI_BIN="${SPOOFDPI_BIN:-/Users/hamuz/Desktop/spoofdpi}"
SPOOFDPI_PORT="${SPOOFDPI_PORT:-8080}"

PIDS=()
cleanup() {
    echo
    echo "[stop] cleaning up..."
    if [[ ${#PIDS[@]} -gt 0 ]]; then
        for pid in "${PIDS[@]}"; do
            kill -TERM "$pid" 2>/dev/null || true
        done
    fi
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

port_in_use() { lsof -ti ":$1" >/dev/null 2>&1; }

if port_in_use "$SPOOFDPI_PORT"; then
    echo "[start] SpoofDPI :$SPOOFDPI_PORT already running, reusing"
else
    if [[ ! -x "$SPOOFDPI_BIN" ]]; then
        echo "[start] SpoofDPI not executable at $SPOOFDPI_BIN" >&2
        echo "[start] override with: SPOOFDPI_BIN=/path/to/spoofdpi ./start.sh" >&2
        exit 1
    fi
    echo "[start] launching SpoofDPI -window-size 1 on :$SPOOFDPI_PORT (TLS Client Hello fragmentation for Discord DPI bypass)"
    "$SPOOFDPI_BIN" -window-size 1 -port "$SPOOFDPI_PORT" > /tmp/spoofdpi.log 2>&1 &
    PIDS+=($!)
    for _ in 1 2 3 4 5; do
        sleep 1
        port_in_use "$SPOOFDPI_PORT" && break
    done
    if ! port_in_use "$SPOOFDPI_PORT"; then
        echo "[start] SpoofDPI didn't bind :$SPOOFDPI_PORT, see /tmp/spoofdpi.log" >&2
        exit 1
    fi
fi

echo "[start] launching bot (preflight checks LLM + Discord reachability)"
python -u bot.py
