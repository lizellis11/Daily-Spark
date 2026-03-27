#!/usr/bin/env bash
# Auto-deploy script for Daily Spark bot.
# Pulls latest code from GitHub and restarts the bot if there are changes.

set -euo pipefail

BOT_DIR="/Users/otherliz/Daily-Spark"
BOT_SCRIPT="daily_spark_bot.py"
LOG_FILE="$BOT_DIR/deploy.log"

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

# Find and kill the running bot process (if any)
BOT_PID=$(pgrep -f "$BOT_SCRIPT" || true)
if [ -n "$BOT_PID" ]; then
    kill $BOT_PID
    sleep 2
    log "Stopped old process (PID $BOT_PID)"
fi

# Start the bot in the background
nohup python3 "$BOT_DIR/$BOT_SCRIPT" >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
log "Started new process (PID $NEW_PID)"
