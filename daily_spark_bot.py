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
    # Take care of our team — reflection
    "Our principle is *Take care of our team.* Who on this team made your week better — and what did they do?",
    "We believe in *taking care of our team.* What's one thing a teammate did recently that you want to recognize?",
    "*Take care of our team* — what's one small way you looked out for someone at work this week?",
    "Our principle says *take care of our team.* What's something a colleague does that makes your job easier? Tell them!",
    "*Take care of our team* — who's been quietly showing up and deserves a spotlight today?",
    "We practice *taking care of our team.* What's one thing you appreciate about how this team supports each other?",
    # Take care of our team — action
    "*Take care of our team* challenge: send a quick message to someone today just to say thanks. Come back and tell us who!",
    "Our principle is *take care of our team.* Your mission today: do one small thing to make a teammate's day easier. Report back!",
    # Amplifying Light — reflection
    "We're here to *Amplify Light.* What's one moment this week where you saw someone on this team shine?",
    "*Amplifying Light* — what's something you're grateful for that reminds you why this work matters?",
    "Our principle is *Amplifying Light.* What's one way your work this week created something positive for someone else?",
    "*Amplifying Light* starts with gratitude. What's one thing — big or small — that you're thankful for today?",
    # Amplifying Light — action
    "*Amplify Light* challenge: tag someone in the thread and tell them one specific thing they do that makes this team better.",
    "We believe in *Amplifying Light.* Share one win from this week — yours or someone else's — and let's celebrate it together.",
]

# ── TUESDAY — Fun & Light ────────────────────────────────────────────────────
# Team Principle: Execute with high energy
TUESDAY_QUESTIONS = [
    # Execute with high energy — fun reflection
    "Our principle is *Execute with high energy.* If your energy today were a song, what would be playing?",
    "*Execute with high energy* — what's the thing that gets you most fired up at work? (Bonus points if it's weird.)",
    "We believe in *executing with high energy.* What does your 'high energy mode' actually look like? Describe it.",
    "*Execute with high energy* — what's your secret weapon for bringing the energy when you're running on fumes?",
    "Our principle says *execute with high energy.* If your energy level right now were a weather forecast, what is it?",
    "*Execute with high energy* — what's one thing that always hypes you up before a big task?",
    "We *execute with high energy.* What's the most energetic thing you've done at work this week? (Low bar counts.)",
    "*Execute with high energy* — if your work energy were a mascot, what animal would it be today?",
    # Execute with high energy — fun action
    "*Execute with high energy* challenge: pick your most boring task today and do it with ridiculous enthusiasm. Report back.",
    "Our principle is *execute with high energy.* Your mission: hype up the next person who posts in this thread.",
    "*Execute with high energy* — drop your go-to pump-up song in the thread. Let's build a team playlist!",
    "We *execute with high energy.* Share one thing you do to recharge so you can keep bringing it every day.",
    "*Execute with high energy* — what's something you crushed this week because you brought the energy?",
    "Our principle is *execute with high energy.* Rate your energy right now 1-10 and tell us what would bump it up one notch.",
]

# ── WEDNESDAY — Scenarios & Thinking ────────────────────────────────────────
# Team Principles: Take ownership · Test everything
WEDNESDAY_QUESTIONS = [
    # Take ownership — reflection
    "Our principle is *Take ownership.* What's something in your work right now that you've fully claimed as yours — no one had to ask you?",
    "*Take ownership* — think about yesterday. Was there a moment you could've stepped up but held back? What would you do differently?",
    "We believe in *taking ownership.* What's one thing on your plate that would fall through the cracks if you didn't own it?",
    "*Take ownership* — what's a problem you noticed and fixed before anyone else even flagged it?",
    "Our principle says *take ownership.* If a new person shadowed you, what would they learn about what 'owning it' looks like?",
    "*Take ownership* — what's something outside your official role that you've chosen to care about anyway?",
    # Take ownership — action
    "*Take ownership* challenge: what's one thing that's been sitting unfinished that you'll commit to closing out today?",
    "We practice *taking ownership.* Name one thing you're going to own this week that you've been waiting on someone else for.",
    # Test everything — reflection
    "Our principle is *Test everything.* What's one assumption in your workflow that you've never actually validated?",
    "*Test everything* — what's something your team does 'because we always have' that might be worth questioning?",
    "We believe in *testing everything.* What's the last thing you tried a different way — and what did you learn?",
    "*Test everything* — if you could run one experiment on how your team works, what would you test?",
    "Our principle says *test everything.* What's a 'best practice' you followed that turned out to be wrong?",
    # Test everything — action
    "*Test everything* challenge: pick one thing you do on autopilot and try it a completely different way today. Tell us what happens.",
    "We *test everything.* What's one small experiment you could run this week to make your work better?",
]

# ── THURSDAY POOL A — Hunger to Learn ────────────────────────────────────────
# Team Principle: Hunger to learn
THURSDAY_LEARN_QUESTIONS = [
    # Hunger to learn — reflection
    "Our principle is *Hunger to learn.* What's something you learned this week — from work, a conversation, a mistake, anything?",
    "*Hunger to learn* — what's a skill or topic you've been curious about but haven't made time for yet?",
    "We believe in a *hunger to learn.* What's the last thing that changed your mind about how you do your job?",
    "*Hunger to learn* — who on this team (or outside it) has taught you something recently? What was it?",
    "Our principle says *hunger to learn.* What's something that feels hard right now because you're still learning it?",
    "*Hunger to learn* — what's one thing you know now that you wish you'd learned sooner?",
    # Hunger to learn — action
    "*Hunger to learn* challenge: ask someone on the team to teach you one thing about their role today. Report back!",
    "We have a *hunger to learn.* Share one resource — article, tool, podcast, anything — that helped you get better at your work.",
    "*Hunger to learn* — what's one thing you're going to intentionally learn or get better at this month?",
]

# ── THURSDAY POOL B — Candor ────────────────────────────────────────────────
# Team Principle: Candor
THURSDAY_CANDOR_QUESTIONS = [
    # Candor — reflection
    "Our principle is *Candor.* What's something you wish more people would just say out loud at work?",
    "*Candor* means being honest even when it's uncomfortable. When's the last time someone's directness actually helped you?",
    "We practice *candor.* What's one thing you've been thinking about your work that you haven't said yet?",
    "*Candor* — what does honest feedback look like when it's done well? Share an example you've seen.",
    "Our principle says *candor.* What makes it easier for you to be honest with your team?",
    "*Candor* — what's one question you wish someone would ask you about your work?",
    # Candor — action
    "*Candor* challenge: give someone in this thread a genuine, specific compliment about their work. Be real, not generic.",
    "We believe in *candor.* Share one honest take on something your team could do better — no sugarcoating needed.",
    "*Candor* challenge: what's one thing you want to be more upfront about going forward?",
]

# ── THURSDAY POOL C — Better Solutions ───────────────────────────────────────
# Team Principle: Better solutions
THURSDAY_SOLUTIONS_QUESTIONS = [
    # Better solutions — reflection
    "Our principle is *Better solutions.* What's a problem you solved recently by trying a different approach?",
    "*Better solutions* — what's something your team does that works fine but could probably work *better*?",
    "We pursue *better solutions.* What's the most creative workaround you've come up with at work?",
    "*Better solutions* — when you're stuck, what's your go-to method for finding a new angle?",
    "Our principle says *better solutions.* What's one process you've improved that you're proud of?",
    "*Better solutions* — what's a tool, trick, or shortcut you use that other people might not know about? Share it!",
    # Better solutions — action
    "*Better solutions* challenge: pick one thing you did this week and brainstorm a way to do it 10% better next time.",
    "We chase *better solutions.* What's one small improvement you could suggest for how the team works?",
    "*Better solutions* — what's one problem you'd love fresh eyes on? Drop it in the thread and let's think together.",
]

# Thursday pools: (display_name, question_list)
THURSDAY_POOLS = [
    ("Hunger to Learn",   THURSDAY_LEARN_QUESTIONS),
    ("Candor",            THURSDAY_CANDOR_QUESTIONS),
    ("Better Solutions",  THURSDAY_SOLUTIONS_QUESTIONS),
]

# ── FRIDAY — Team Reflection & Alignment ─────────────────────────────────────
# Team Principles: Share context · Align to North Star
FRIDAY_QUESTIONS = [
    # Share context
    "Our principle is *Share context.* In one word each, what was the theme of your week? Build the sentence together!",
    "*Share context* — one word per person: what's the most important thing your team should know going into next week?",
    "We believe in *sharing context.* One word each: what did you learn this week?",
    "*Share context* — one word per person: what was the vibe on your team this week?",
    # Align to North Star
    "Our principle is *Align to North Star.* One word each: what are we building toward?",
    "*Align to North Star* — one word per person: what keeps you focused on what matters?",
    "We *align to our North Star.* One word each: what does success look like for this team?",
    "*Align to North Star* — one word per person: what should we carry into next week?",
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
            _context("*Principles:*  Take care of our team  ·  Amplifying Light"),
            _section(f"\n{q}\n\n_Drop your answer in the thread!_"),
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
            _context("*Principle:*  Execute with high energy"),
            _section(f"\n{q}\n\n_Drop your answer in the thread!_"),
        ]
    }


def build_wednesday_message() -> dict:
    q = random.choice(WEDNESDAY_QUESTIONS)
    return {
        "blocks": [
            _header("The Daily Spark | Wednesday — Scenarios & Thinking"),
            _divider(),
            _context("*Principles:*  Take ownership  ·  Test everything"),
            _section(f"\n{q}\n\n_Drop your answer in the thread!_"),
        ]
    }


def build_thursday_message() -> dict:
    pool_name, questions = random.choice(THURSDAY_POOLS)
    q = random.choice(questions)
    return {
        "blocks": [
            _header(f"The Daily Spark | Thursday — {pool_name}"),
            _divider(),
            _context(f"*Principle:*  {pool_name}"),
            _section(f"\n{q}\n\n_Drop your answer in the thread!_"),
        ]
    }


def build_friday_message() -> dict:
    q = random.choice(FRIDAY_QUESTIONS)
    return {
        "blocks": [
            _header("The Daily Spark | Friday — Team Reflection"),
            _divider(),
            _context("*Principles:*  Share context  ·  Align to North Star"),
            _section(
                f"\n{q}\n\n"
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

DAY_BUILDERS = {
    0: build_monday_message,
    1: build_tuesday_message,
    2: build_wednesday_message,
    3: build_thursday_message,
    4: build_friday_message,
}


def already_posted_today() -> bool:
    """Check if the bot already posted a Daily Spark message in the channel today."""
    now = datetime.now(TIMEZONE)
    # Start of today in UTC epoch (what Slack expects for oldest/latest)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    oldest_ts = str(start_of_day.timestamp())

    try:
        result = app.client.conversations_history(
            channel=CHANNEL_ID,
            oldest=oldest_ts,
            limit=20,
        )
        for msg in result.get("messages", []):
            # Look for bot messages with our header pattern
            for block in msg.get("blocks", []):
                if block.get("type") == "header":
                    header_text = block.get("text", {}).get("text", "")
                    if header_text.startswith("The Daily Spark |"):
                        logger.info(
                            f"Already posted today (ts={msg['ts']}). Skipping duplicate."
                        )
                        return True
    except Exception as e:
        logger.warning(f"Could not check for duplicate post: {e}")
        # If we can't check, allow the post rather than silently skipping
        return False

    return False


def post_daily_message():
    """Called by the scheduler. Posts the appropriate message for the current weekday."""
    now = datetime.now(TIMEZONE)
    weekday = now.weekday()  # 0 = Monday … 4 = Friday

    if weekday > 4:
        logger.info("Weekend — skipping post.")
        return

    if already_posted_today():
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
