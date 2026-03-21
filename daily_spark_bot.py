#!/usr/bin/env python3
"""
✨ THE DAILY SPARK ⚡ — Angel Team Slack Bot
=============================================
Sends daily team engagement prompts to #water-cooler-chats at 9:15 AM
Mountain Time, Monday through Friday.

SETUP (for engineers):
----------------------
1. Create a Slack App at https://api.slack.com/apps
   - Enable Socket Mode (under Settings > Socket Mode)
   - Add Bot Token Scopes (under OAuth & Permissions > Scopes > Bot Token Scopes):
       chat:write
       reactions:write
       channels:read
       channels:history
       groups:read
   - Subscribe to bot events (under Event Subscriptions > Subscribe to bot events):
       message.channels
       message.groups
   - Install the app to your workspace (OAuth & Permissions > Install to Workspace)

2. Copy your tokens into a .env file (see .env.example):
   - Bot Token (starts with xoxb-) → SLACK_BOT_TOKEN
   - App-Level Token (starts with xapp-, needs connections:write scope) → SLACK_APP_TOKEN

3. Install Python dependencies:
       pip install -r requirements.txt

4. Invite the bot to both channels in Slack:
       /invite @YourBotName  (in #water-cooler-chats)
       /invite @YourBotName  (in #team-principle-shoutout-wall-of-light)

5. First-time launch (sends the intro message + starts the scheduler):
       python daily_spark_bot.py --launch

6. Normal daily operation (scheduler only, no intro message):
       python daily_spark_bot.py

7. Test without waiting for 9:15 AM (posts today's message immediately):
       python daily_spark_bot.py --test

NOTES:
- The bot must stay running for scheduled posts to fire. Deploy it as a
  persistent process on your internal hosting platform.
- Friday prompts are "one-word" threads. The bot watches for replies longer
  than one word and posts a funny correction. This is intentional — it's
  part of the fun!
"""

import os
import random
import logging
from datetime import datetime, timedelta

import pytz
from typing import Optional
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG (edit these if anything changes)
# ─────────────────────────────────────────────────────────────────────────────
CHANNEL = "water-cooler-chats"                        # without the #
CHANNEL_ID = "C0101T8N9C0"                            # Slack ID for #water-cooler-chats
SHOUTOUT_CHANNEL = "team-principle-shoutout-wall-of-light"
SHOUTOUT_CHANNEL_ID = "C08QCQJ8S0Z"                  # Slack ID for #team-principle-shoutout-wall-of-light
POST_HOUR = 9
POST_MINUTE = 15
TIMEZONE = pytz.timezone("America/Denver")            # Mountain Time

# ─────────────────────────────────────────────────────────────────────────────
# SLACK APP
# ─────────────────────────────────────────────────────────────────────────────
app = App(token=os.environ["SLACK_BOT_TOKEN"])

# Tracks active "one-word" threads so we can validate Friday replies.
# Format: { thread_ts: expiry_datetime }
# Threads expire after 10 hours so the bot doesn't flag late-night conversation.
one_word_threads: dict[str, datetime] = {}

# ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
# QUESTION BANKS
# ══════════════════════════════════════════════════════════════════════════════
# ─────────────────────────────────────────────────────────────────────────────

# ── MONDAY — Gratitude & Energy ──────────────────────────────────────────────
# Team Principles: Take care of our team · Amplifying Light
MONDAY_QUESTIONS = [
    "What's one thing you're grateful for today?",
    "One small win from this week — share it.",
    "Someone who made your job easier recently — who deserves a nod?",
    "Something that went better than expected this week.",
    "One thing you're proud of this week.",
    "A small moment that made you smile recently.",
    "One thing you'd thank your past self for.",
    "One thing you appreciate about this team.",
    "A win that might go unnoticed — let's spotlight it.",
    "Something outside work you're grateful for.",
    "One challenge you're grateful for because it helped you grow.",
    "Someone you want to recognize today — tag them.",
]

# ── TUESDAY — Fun & Light ────────────────────────────────────────────────────
# Team Principle: Execute with high energy
TUESDAY_QUESTIONS = [
    "If your job had a smell, what would it be?",
    "What's your 'this meeting could've been an email' face?",
    "If your role had a mascot, what would it be?",
    "If your brain had too many tabs open right now, what are they?",
    "What's your go-to recharge when you need a mental reset?",
    "If your Slack status could be hilariously honest, what would it say?",
    "If your week were a meme, what would it be?",
    "What would your warning label say today?",
    "If your job turned into a video game, what's the hardest level?",
    "What's your most unnecessary workplace talent?",
    "If your to-do list could talk, what would it yell?",
    "If your email inbox had a personality, what would it be?",
    "If you could rename Mondays, what would you call them?",
    "If your job was a reality show, what would it be called?",
    "If your laptop could talk, what would it complain about?",
    "If you had to give a TED Talk right now, what topic could you fake?",
]

# ── WEDNESDAY — Scenarios & Thinking ────────────────────────────────────────
# Team Principles: Take ownership · Test everything
WEDNESDAY_QUESTIONS = [
    "You wake up and your biggest work problem is solved — what changed?",
    "You get to shadow your future self — what are they doing differently?",
    "You can automate one part of your job — what disappears?",
    "A new tool instantly improves your workflow — what is it?",
    "You're told to simplify your role by 50% — what stays?",
    "Your workload doubles — what do you stop doing first?",
    "You're mentoring someone new — what advice do you give first?",
    "You have to teach your role in 10 minutes — what do you focus on?",
    "You get a redo on yesterday — what do you change?",
    "You inherit someone else's role — what's your first move?",
    "You're asked to improve one team habit — what do you pick?",
    "A new hire asks what actually matters — what do you say?",
    "You challenge one assumption your team holds — what do you test first?",
    "You run an experiment on your current workflow — what do you try?",
    "You're asked to prove something you assumed was true — what do you discover?",
]

# ── THURSDAY POOL A — Perspective & Growth ───────────────────────────────────
# Team Principles: Hunger to learn · Candor · Better solutions
THURSDAY_PERSPECTIVE_QUESTIONS = [
    "What's something that feels hard now but will matter later?",
    "What's one thing you've gotten better at recently?",
    "What's something you used to overcomplicate?",
    "What's one thing you wish people understood about your role?",
    "What's something that saves you time every week?",
    "What's something you've learned from a mistake recently?",
    "What's a small improvement that made a big difference?",
    "What are you intentionally setting aside right now — and why?",
    "What helps you stay focused when things get chaotic?",
    "What gives you energy at work?",
    "What's one assumption you've challenged recently?",
    "What's one thing you'd do differently if you started fresh today?",
]

# ── THURSDAY POOL B — Role Flip Edition ─────────────────────────────────────
# Team Principles: Hunger to learn · Candor · Better solutions
THURSDAY_ROLEFLIP_QUESTIONS = [
    "What does your future self wish you'd start doing now?",
    "What does your past self thank you for?",
    "If you were your manager, what feedback would you give yourself?",
    "What would a customer say about your work this week?",
    "What does another team depend on you for most?",
    "If you were onboarding yourself, what would confuse you?",
    "What's something leadership might not see that matters?",
    "What would your replacement need to know on day one?",
    "If you swapped roles with someone here, what would surprise you?",
]

# ── THURSDAY POOL C — Future Focus ──────────────────────────────────────────
# Team Principles: Hunger to learn · Candor · Better solutions
THURSDAY_PREDICTION_QUESTIONS = [
    "Will today feel long or short — what's your gut say?",
    "Will your top task get done before noon? What would make that happen?",
    "Will something unexpected come up today — and will it lead somewhere good?",
    "Will next week be more or less intense? What does that tell you?",
    "Will your energy go up or down by end of day? What would shift it?",
    "Will you lean into 'yes' or 'no' more today — which do you actually need?",
    "Will this week feel successful? What one thing would make it so?",
    "Will something you're worried about right now matter in 30 days?",
    "What's one thing you could do differently tomorrow to get a better outcome?",
    "What's one small bet you could place on a better solution this week?",
]

# Thursday pools: (display_name, question_list)
THURSDAY_POOLS = [
    ("Perspective & Growth", THURSDAY_PERSPECTIVE_QUESTIONS),
    ("Role Flip Edition",    THURSDAY_ROLEFLIP_QUESTIONS),
    ("Future Focus",         THURSDAY_PREDICTION_QUESTIONS),
]

# ── FRIDAY — Team Reflection & Alignment ─────────────────────────────────────
# Team Principles: Share context · Align to North Star
FRIDAY_QUESTIONS = [
    "Build a sentence about this week — one word per person in the thread.",
    "One word each: describe this week.",
    "Build a headline for the week — one word per person.",
    '"This team is…" — one word each.',
    "Build a mission statement — one word per person, go.",
    "Describe our current challenge in one word each.",
    "Build a picture of a perfect day at work — one word each.",
    "One word each: what we need more of.",
]

# ─────────────────────────────────────────────────────────────────────────────
# FUNNY CORRECTIONS (fired when someone breaks the one-word rule on Fridays)
# ─────────────────────────────────────────────────────────────────────────────
VIOLATION_MESSAGES = [
    "That was more than one word. Try again — we believe in you.",
    "Bold attempt. This is a one-word zone though. Condense it down.",
    "Points for enthusiasm. Minus points for word count. *One word.*",
    "The prompt said one word. What you gave us was a masterpiece. Save it for your memoir.",
    "One-word zone. Please reduce your word count to exactly 1 and try again.",
    "You used *{count}* word{plural}. Allowed: *1.* Give it another shot.",
]


def get_violation_message(word_count: int) -> str:
    msg = random.choice(VIOLATION_MESSAGES)
    plural = "s" if word_count != 1 else ""
    return msg.replace("{count}", str(word_count)).replace("{plural}", plural)




# ─────────────────────────────────────────────────────────────────────────────
# BLOCK BUILDER HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _header(text: str) -> dict:
    return {
        "type": "header",
        "text": {"type": "plain_text", "text": text, "emoji": True},
    }


def _divider() -> dict:
    return {"type": "divider"}


def _section(text: str) -> dict:
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    }


def _context(text: str) -> dict:
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": text}],
    }


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE BUILDERS (one per day + launch)
# ─────────────────────────────────────────────────────────────────────────────
def build_monday_message() -> dict:
    q = random.choice(MONDAY_QUESTIONS)
    return {
        "blocks": [
            _header("The Daily Spark | Monday — Gratitude & Energy"),
            _divider(),
            _section(f"*Today's Spark:*\n\n{q}\n\n_Drop your answer in the thread._"),
            _divider(),
            _section(f"Give someone a shoutout in <#{SHOUTOUT_CHANNEL_ID}> — let them know they're seen."),
        ]
    }


def build_tuesday_message() -> dict:
    q = random.choice(TUESDAY_QUESTIONS)
    return {
        "blocks": [
            _header("The Daily Spark | Tuesday — Fun & Light"),
            _divider(),
            _section(f"*Today's Spark:*\n\n{q}\n\n_Drop your answer in the thread._"),
        ]
    }


def build_wednesday_message() -> dict:
    q = random.choice(WEDNESDAY_QUESTIONS)
    return {
        "blocks": [
            _header("The Daily Spark | Wednesday — Scenarios & Thinking"),
            _divider(),
            _section(f"*Today's Spark:*\n\n{q}\n\n_Drop your answer in the thread._"),
        ]
    }


def build_thursday_message() -> dict:
    pool_name, questions = random.choice(THURSDAY_POOLS)
    q = random.choice(questions)
    return {
        "blocks": [
            _header(f"The Daily Spark | Thursday — {pool_name}"),
            _divider(),
            _section(f"*Today's Spark:*\n\n{q}\n\n_Drop your answer in the thread._"),
        ]
    }


def build_friday_message() -> dict:
    q = random.choice(FRIDAY_QUESTIONS)
    return {
        "blocks": [
            _header("The Daily Spark | Friday — Team Reflection"),
            _divider(),
            _section(
                f"*Today's Spark:*\n\n{q}\n\n"
                "_One word per person in the thread. The bot is watching._ 👀"
            ),
            _divider(),
            _section(
                f"Got a win or want to shoutout someone? Head to <#{SHOUTOUT_CHANNEL_ID}>."
            ),
        ]
    }


def build_launch_message() -> dict:
    """One-time intro message. Run with --launch flag."""
    return {
        "blocks": [
            _header("Meet The Daily Spark ⚡"),
            _divider(),
            _section(
                "*Hey Angel Team!*\n\n"
                "Every weekday at *9:15 AM MT*, this channel gets a short prompt built "
                "around our team principles. Reply in the thread, react, shout each other "
                "out — it's our way of staying connected while we Amplify Light together."
            ),
            _divider(),
            _section(
                "*Weekly lineup:*\n"
                "*Monday* — Gratitude & Energy\n"
                "*Tuesday* — Fun & Light\n"
                "*Wednesday* — Scenarios & Thinking\n"
                "*Thursday* — Perspective & Growth\n"
                "*Friday* — Team Reflection"
            ),
            _divider(),
            _section("To kick things off — drop *one word* in the thread that describes how you're showing up today."),
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def get_channel_id(channel_name: str) -> Optional[str]:
    """Resolve a channel name to its Slack channel ID (handles pagination)."""
    name = channel_name.lstrip("#")
    cursor = None
    try:
        while True:
            kwargs = {
                "limit": 200,
                "types": "public_channel,private_channel",
                "exclude_archived": True,
            }
            if cursor:
                kwargs["cursor"] = cursor
            result = app.client.conversations_list(**kwargs)
            for ch in result.get("channels", []):
                if ch["name"] == name:
                    return ch["id"]
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        logger.error(f"Error fetching channel list: {e}")
    return None


# Cached channel IDs (resolved once at startup)
_channel_ids: dict[str, str] = {}


def resolve_channels():
    """Resolve and cache channel IDs at startup."""
    for name in (CHANNEL, SHOUTOUT_CHANNEL):
        cid = get_channel_id(name)
        if cid:
            _channel_ids[name] = cid
            logger.info(f"Resolved #{name} → {cid}")
        else:
            logger.warning(
                f"Could not resolve #{name}. "
                "Make sure the bot is invited to that channel."
            )


# ─────────────────────────────────────────────────────────────────────────────
# POSTING LOGIC
# ─────────────────────────────────────────────────────────────────────────────

# Maps Slack emoji reaction names to each weekday
DAY_REACTIONS = {
    0: ["pray", "heart", "raised_hands"],       # Monday
    1: ["joy", "fire", "bulb"],                 # Tuesday
    2: ["thinking_face", "bulb", "fire"],       # Wednesday
    3: ["bulb", "seedling", "fire"],            # Thursday
    4: ["raised_hands", "bricks", "dart"],      # Friday
}

DAY_BUILDERS = {
    0: build_monday_message,
    1: build_tuesday_message,
    2: build_wednesday_message,
    3: build_thursday_message,
    4: build_friday_message,
}


def post_daily_message():
    """Called by the scheduler. Posts the appropriate message for the current weekday."""
    now = datetime.now(TIMEZONE)
    weekday = now.weekday()  # 0 = Monday … 4 = Friday

    if weekday > 4:
        logger.info("Weekend — skipping post.")
        return

    channel_id = CHANNEL_ID

    message = DAY_BUILDERS[weekday]()

    try:
        result = app.client.chat_postMessage(
            channel=channel_id,
            unfurl_links=False,
            **message,
        )
        thread_ts = result["ts"]
        logger.info(f"Posted Daily Spark for weekday={weekday}, ts={thread_ts}")

        # Add emoji reactions so people can "react-vote" without typing
        for reaction in DAY_REACTIONS.get(weekday, []):
            try:
                app.client.reactions_add(
                    channel=channel_id,
                    timestamp=thread_ts,
                    name=reaction,
                )
            except Exception:
                pass  # Non-critical — bot may have already reacted

        # Track Friday threads for one-word enforcement (expires after 10 hours)
        if weekday == 4:
            expiry = now + timedelta(hours=10)
            one_word_threads[thread_ts] = expiry
            logger.info(f"Tracking Friday thread {thread_ts} for word-count checks (expires {expiry})")

    except Exception as e:
        logger.error(f"Failed to post Daily Spark: {e}")


def send_launch_message():
    """Posts the one-time intro message. Called with --launch flag."""
    channel_id = CHANNEL_ID
    try:
        app.client.chat_postMessage(
            channel=channel_id,
            unfurl_links=False,
            **build_launch_message(),
        )
        logger.info("Launch message sent!")
    except Exception as e:
        logger.error(f"Failed to send launch message: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# EVENT HANDLERS
# ─────────────────────────────────────────────────────────────────────────────
@app.event("message")
def handle_message(event, client):
    """
    Watches thread replies on Friday one-word prompts.
    If someone replies with more than one word, the bot posts a funny correction.
    """
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return  # Not a thread reply

    if thread_ts not in one_word_threads:
        return  # Not a tracked Friday thread

    # Check expiry — clean up stale entries while we're here
    now = datetime.now(TIMEZONE)
    if now > one_word_threads[thread_ts]:
        del one_word_threads[thread_ts]
        return

    # Ignore bot messages and system messages
    if event.get("bot_id") or event.get("subtype"):
        return

    text = (event.get("text") or "").strip()
    if not text:
        return

    # Count "real" words — exclude Slack emoji codes like :fire: or :white_check_mark:
    words = [
        w for w in text.split()
        if not (w.startswith(":") and w.endswith(":"))
    ]
    word_count = len(words)

    if word_count > 1:
        violation_msg = get_violation_message(word_count)
        try:
            client.chat_postMessage(
                channel=event["channel"],
                thread_ts=thread_ts,
                text=violation_msg,
            )
            logger.info(
                f"Word-count violation in thread {thread_ts}: "
                f"{word_count} words from user {event.get('user')}"
            )
        except Exception as e:
            logger.error(f"Failed to post violation message: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────────────────────────────────────
def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        post_daily_message,
        CronTrigger(
            hour=POST_HOUR,
            minute=POST_MINUTE,
            day_of_week="mon-fri",
            timezone=TIMEZONE,
        ),
        id="daily_spark",
        name="The Daily Spark",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"Scheduler running — posting at {POST_HOUR}:{POST_MINUTE:02d} MT, Mon–Fri"
    )
    return scheduler


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    logger.info("The Daily Spark ⚡ — starting up...")
    logger.info(f"Posting to #{CHANNEL} ({CHANNEL_ID}) | Shoutouts → #{SHOUTOUT_CHANNEL} ({SHOUTOUT_CHANNEL_ID})")

    # --launch: send the one-time intro message, then continue running
    if "--launch" in sys.argv:
        logger.info("Sending launch message...")
        send_launch_message()

    # --test: post today's message immediately (useful for verification)
    if "--test" in sys.argv:
        logger.info("Sending test message for today's weekday...")
        post_daily_message()

    scheduler = start_scheduler()

    logger.info("Connecting to Slack via Socket Mode...")
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()  # Blocks here — the scheduler fires in the background
