#!/usr/bin/env bash
# Auto-deploy script for Daily Spark bot.
# Pulls latest code from GitHub and restarts the bot if there are changes.

set -euo pipefail

BOT_DIR="/Users/otherliz/Daily-Spark"
BOT_SCRIPT="daily_spark_bot.py"
LOG_FILE="$BOT_DIR/deploy.log"
PID_FILE="$BOT_DIR/bot.pid"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') — $1" >> "$LOG_FILE"
}

cd "$BOT_DIR"

# Fetch latest from origin
git fetch origin main --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0
fi

log "New commits detected ($LOCAL -> $REMOTE). Updating..."

git pull origin main --quiet

# Kill the running bot process using PID file, with pgrep as fallback
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID"
        sleep 2
        # Force-kill if it's still running
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill -9 "$OLD_PID"
            sleep 1
        fi
        log "Stopped old process (PID $OLD_PID)"
    fi
    rm -f "$PID_FILE"
fi

# Fallback: kill any remaining bot processes not tracked by PID file
STALE_PIDS=$(pgrep -f "$BOT_SCRIPT" || true)
if [ -n "$STALE_PIDS" ]; then
    kill $STALE_PIDS 2>/dev/null || true
    sleep 2
    log "Cleaned up stale processes: $STALE_PIDS"
fi

# Start the bot in the background
nohup python3 "$BOT_DIR/$BOT_SCRIPT" >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
log "Started new process (PID $NEW_PID)"
