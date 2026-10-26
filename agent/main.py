from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any
from urllib.parse import quote

import requests
from TikTokApi import TikTokApi

GITHUB_REPO = os.getenv("OPENBAND_REPO", "iltempe/openband")
GITHUB_TOKEN = os.getenv("OPENBAND_GITHUB_TOKEN", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TIKTOK_USERNAME = os.getenv("TIKTOK_USERNAME", "iltempe").strip().lstrip("@")
TIKTOK_MS_TOKEN = os.getenv("TIKTOK_MS_TOKEN", "").strip() or None

SUGGESTION_PATTERNS = [
    r"\b(feature request|suggestion|suggest|please add|could you add|would be nice|would love|it would be great)\b",
    r"\b(improve|improvement|add support|support for|missing feature|bug|issue|fix|export|import|midi|plugin|shortcut|workflow)\b",
    r"\b(potresti|sarebbe bello|sarebbe utile|aggiungere|aggiungi|migliorare|miglioria|manca|mancano|problema|errore|esportare|importare)\b",
]


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}", flush=True)


def github_headers() -> dict[str, str]:
    if not GITHUB_TOKEN:
        raise RuntimeError("Missing OPENBAND_GITHUB_TOKEN secret")
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_issue_exists(comment_id: str) -> bool:
    marker = f"tiktok-comment:{comment_id}"
    query = quote(f'repo:{GITHUB_REPO} "{marker}"')
    response = requests.get(
        f"https://api.github.com/search/issues?q={query}&per_page=10",
        headers=github_headers(), timeout=20,
    )
    response.raise_for_status()
    return response.json().get("total_count", 0) > 0


def create_github_issue(title: str, body: str, comment_id: str) -> str:
    if github_issue_exists(comment_id):
        return "DUPLICATE"
    response = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers=github_headers(),
        json={"title": title[:250], "body": body, "labels": ["community-feedback"]},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["html_url"]


def telegram_api(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN secret")
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
        json=payload or {}, timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error in {method}: {data}")
    return data


def normalize_line(value: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def is_suggestion(text: str) -> bool:
    lowered = text.casefold()
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in SUGGESTION_PATTERNS)


def unix_comment_time(raw: dict[str, Any]) -> float | None:
    value = raw.get("create_time") or raw.get("createTime")
    try:
        number = float(value)
        return number / 1000 if number > 10_000_000_000 else number
    except (TypeError, ValueError):
        return None


def send_proposal(video_id: str, comment_id: str, author: str, text: str, created: float) -> None:
    if not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID secret")
    title = normalize_line(text, 95)
    if len(title) > 90:
        title = title[:87] + "..."
    author = normalize_line(author or "utente TikTok", 80)
    text = normalize_line(text, 1200)
    video_url = f"https://www.tiktok.com/video/{video_id}"
    timestamp = datetime.fromtimestamp(created, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message = (
        "NUOVO SUGGERIMENTO OPENBAND\n"
        f"Titolo: Feedback TikTok — {title}\n"
        f"Autore: @{author.lstrip('@')}\n"
        f"Data commento: {timestamp}\n"
        f"Video: {video_url}\n"
        f"Commento: {text}\n"
        f"ID commento: {comment_id}"
    )
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Approva e crea issue", "callback_data": f"approve|{video_id}|{comment_id}"},
        {"text": "❌ Rifiuta", "callback_data": f"reject|{video_id}|{comment_id}"},
    ]]}
    telegram_api("sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message[:3900],
        "reply_markup": keyboard,
        "disable_web_page_preview": True,
    })


async def collect_comments() -> int:
    if not TIKTOK_USERNAME:
        raise RuntimeError("Set TIKTOK_USERNAME to the public TikTok username")
    if not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID secret")

    now = time.time()
    local_now = datetime.now(ZoneInfo("Europe/Rome"))
    yesterday_start = (local_now.date() - timedelta(days=1))
    day_start = datetime.combine(yesterday_start, datetime.min.time(), tzinfo=ZoneInfo("Europe/Rome")).timestamp()
    day_end = datetime.combine(local_now.date(), datetime.min.time(), tzinfo=ZoneInfo("Europe/Rome")).timestamp()
    count_sent = 0
    videos_scanned = 0
    ms_tokens = [TIKTOK_MS_TOKEN] if TIKTOK_MS_TOKEN else [None]

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=ms_tokens,
            num_sessions=1,
            sleep_after=3,
            browser=os.getenv("TIKTOK_BROWSER", "chromium"),
        )
        user = api.user(username=TIKTOK_USERNAME)
        async for video in user.videos(count=30):
            raw_video = getattr(video, "as_dict", {}) or {}
            video_id = str(getattr(video, "id", "") or raw_video.get("id", ""))
            created_raw = raw_video.get("createTime") or raw_video.get("create_time")
            try:
                video_created = float(created_raw)
                if video_created > 10_000_000_000:
                    video_created /= 1000
            except (TypeError, ValueError):
                video_created = None

            # Profile feeds are normally newest-first. Select videos published on the
            # previous calendar day in Europe/Rome, not simply the last rolling 24 hours.
            if video_created is None:
                log(f"Skipping video with unknown publish time: {video_id or 'unknown ID'}")
                continue
            if video_created >= day_end:
                continue
            if video_created < day_start:
                # Stop once the feed reaches videos older than yesterday; newest-first ordering is expected.
                log("Reached videos older than yesterday (Europe/Rome); stopping discovery")
                break
            if not video_id:
                log("Skipping video without an ID")
                continue

            videos_scanned += 1
            log(f"Scanning yesterday/recent public video {video_id}")
            try:
                async for comment in video.comments(count=100):
                    raw = getattr(comment, "as_dict", {}) or {}
                    comment_id = str(getattr(comment, "id", "") or raw.get("cid", ""))
                    text = normalize_line(getattr(comment, "text", "") or raw.get("text", ""), 1200)
                    created = unix_comment_time(raw)
                    if not comment_id or not text or created is None:
                        continue
                    if not is_suggestion(text):
                        continue
                    if github_issue_exists(comment_id):
                        log(f"Already represented by a GitHub issue: {comment_id}")
                        continue
                    author_obj = getattr(comment, "author", None)
                    author = getattr(author_obj, "username", "") if author_obj else ""
                    send_proposal(video_id, comment_id, author, text, created)
                    count_sent += 1
                    await asyncio.sleep(1)
            except Exception as exc:
                log(f"Could not read comments for video {video_id}: {type(exc).__name__}: {exc}")
                raise
    log(f"Discovered and scanned {videos_scanned} video(s) published yesterday in Europe/Rome; sent {count_sent} suggestion(s) to Telegram")
    return count_sent


def parse_message(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        for key in ("Titolo", "Autore", "Data commento", "Video", "Commento", "ID commento"):
            prefix = f"{key}: "
            if line.startswith(prefix):
                fields[key] = line[len(prefix):].strip()
                break
    return fields


def handle_callback(callback: dict[str, Any]) -> None:
    callback_id = callback.get("id", "")
    data = callback.get("data", "")
    message = callback.get("message", {})
    sender = callback.get("from", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    if chat_id != str(TELEGRAM_CHAT_ID) or str(sender.get("id", "")) != str(TELEGRAM_CHAT_ID):
        telegram_api("answerCallbackQuery", {
            "callback_query_id": callback_id, "text": "Non autorizzato", "show_alert": True,
        })
        return

    parts = data.split("|", 2)
    if len(parts) != 3 or parts[0] not in {"approve", "reject"}:
        telegram_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Azione non riconosciuta"})
        return
    action, video_id, comment_id = parts
    if action == "reject":
        telegram_api("editMessageReplyMarkup", {
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": message.get("message_id"),
            "reply_markup": {"inline_keyboard": []},
        })
        telegram_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Suggerimento rifiutato"})
        return

    fields = parse_message(message.get("text", ""))
    title = fields.get("Titolo", f"Feedback TikTok — {comment_id}")
    original = fields.get("Commento", "Commento non disponibile")
    author = fields.get("Autore", "utente TikTok")
    video_url = fields.get("Video", f"https://www.tiktok.com/video/{video_id}")
    body = (
        "## Suggerimento dalla community TikTok\n\n"
        f"**Commento originale:** {original}\n\n"
        f"**Autore:** {author}\n\n"
        f"**Video:** {video_url}\n\n"
        f"**Data commento:** {fields.get('Data commento', 'non disponibile')}\n\n"
        "### Criteri di accettazione\n"
        "- [ ] Valutare la richiesta rispetto alla roadmap di OpenBand.\n"
        "- [ ] Definire il comportamento atteso e i casi limite.\n"
        "- [ ] Aggiornare la documentazione o i test, se pertinenti.\n\n"
        f"<!-- tiktok-comment:{comment_id} -->\n"
        f"Source: TikTok comment {comment_id}"
    )
    url = create_github_issue(title, body, comment_id)
    if url == "DUPLICATE":
        result_text = "Issue non creata: questo commento risulta già presente su GitHub."
        answer = "Duplicato già presente"
    else:
        result_text = f"Issue creata: {url}"
        answer = "Issue GitHub creata"
    telegram_api("editMessageText", {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": message.get("message_id"),
        "text": message.get("text", "") + "\n\n" + result_text,
        "disable_web_page_preview": True,
    })
    telegram_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": answer})
    log(f"Handled {action} for TikTok comment {comment_id}: {url}")


def poll_telegram() -> int:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets")
    data = telegram_api("getUpdates", {"timeout": 0, "allowed_updates": ["callback_query"]})
    updates = data.get("result", [])
    if not updates:
        log("No Telegram approvals waiting")
        return 0
    max_update_id = max(int(item["update_id"]) for item in updates)
    processed = 0
    for update in updates:
        callback = update.get("callback_query")
        if callback:
            handle_callback(callback)
            processed += 1
    telegram_api("getUpdates", {
        "offset": max_update_id + 1, "timeout": 0, "allowed_updates": ["callback_query"],
    })
    log(f"Processed {processed} Telegram callback(s)")
    return processed


def main() -> int:
    mode = os.getenv("AGENT_MODE", "poll").lower()
    try:
        if mode == "collect":
            asyncio.run(collect_comments())
        elif mode == "poll":
            poll_telegram()
        elif mode == "both":
            poll_telegram()
            asyncio.run(collect_comments())
        else:
            raise ValueError("AGENT_MODE must be collect, poll, both, or skip")
        return 0
    except KeyError as exc:
        if exc.args == ("id",):
            log(
                "ERROR: TikTok did not return a usable public-profile response (missing 'id'). "
                "This is a TikTokApi/profile-access failure, not a Telegram or GitHub token error. "
                "The unofficial profile discovery cannot continue; do not retry repeatedly. "
                "Use a supported TikTok API integration if available, or choose another source for video discovery."
            )
        else:
            log(f"ERROR: KeyError: {exc}")
        return 1
    except Exception as exc:
        log(f"ERROR: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
