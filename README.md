# OpenBand TikTok Feedback Agent

Free-first prototype for reviewing suggestions from comments on your own public TikTok videos and creating GitHub issues in `iltempe/openband` only after your approval in Telegram.

## Status: experimental

The collector uses the unofficial `TikTok-Api` Python package. TikTok may block it or change its website. Test collection manually before relying on it. This project does not bypass CAPTCHAs, access controls, or rate limits. Use it only where consistent with TikTok's terms and applicable privacy rules.

### What it does

- Runs from GitHub Actions; no always-on server.
- Discovers recent public videos automatically from the configured TikTok username and scans their comments.
- Uses a small, free keyword heuristic to identify possible feature requests.
- Checks existing OpenBand issues for duplicates.
- Sends proposals to a private Telegram chat. An issue is created only after an authorized Telegram approval.
- Checks GitHub issues for a source-comment marker before proposing or creating an issue, reducing duplicates.

### Repository setup

1. Create a Telegram bot with `@BotFather`, open a private chat with it, and send `/start`.
2. Create a fine-grained GitHub personal access token restricted to `iltempe/openband`, with **Issues: Read and write** and **Metadata: Read-only**. Store it as `OPENBAND_GITHUB_TOKEN` in this repository's **Settings → Secrets and variables → Actions**.
3. Add Actions secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. The workflow currently scans the public profile `@iltempe`; change `TIKTOK_USERNAME` in `.github/workflows/daily.yml` if your username differs. No per-video IDs are needed.
4. `TIKTOK_MS_TOKEN` is optional. It is a sensitive session cookie; do not paste it into chat or commit it. Start without it. If you choose to use it, add it only as a secret and revoke it if exposed.
5. Create the `community-feedback` label in `iltempe/openband`.
6. Open **Actions → OpenBand TikTok feedback agent → Run workflow** and choose `collect` for the first diagnostic run.
7. Inspect the logs. If the collector is blocked or returns an error, stop and diagnose rather than using proxies or attempting to evade the block.

### Workflow schedule

GitHub Actions scheduled jobs use UTC. The workflow runs a lightweight timezone check at 07:00 and 08:00 UTC and collects only when the local time in `Europe/Rome` is 09:00. This covers both daylight-saving and standard time. GitHub can delay scheduled starts, so this is not a guaranteed exact-time scheduler.

A separate lightweight poll runs every 15 minutes to handle Telegram button callbacks without a permanently running server. This is a prototype trade-off: scheduled runs can be delayed, and repository/workflow limits apply. If this proves noisy, we can replace it with an approval command processed during a manual workflow run.

### Manual operation

Use **Run workflow** with:
- `collect`: retrieve comments and send suggestions to Telegram.
- `poll`: process Telegram approval/rejection callbacks.
- `both`: do both for diagnosis.

### Security

- Never commit tokens, `.env` files, or session cookies.
- Keep the Telegram bot in a private chat. The code checks the configured numeric Telegram user/chat ID before accepting a decision.
- The target GitHub token should have access only to `iltempe/openband` and only the permissions needed to create issues.
- Comment text is untrusted user input; the agent treats it as data, not instructions.
- Public repositories expose code. Never store secrets or session cookies in repository files.

### Limits of the first version

- Automatic discovery depends on TikTokApi being able to read the public profile feed; TikTok may change or block this unofficial interface.
- Classification is heuristic, not an LLM; expect false positives and missed suggestions.
- TikTok scraping reliability is not guaranteed.
- No live end-to-end run has been verified yet.
