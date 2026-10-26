# Security policy

## Reporting a vulnerability

Do not publish tokens, browser cookies, or private user information in issues. Revoke any exposed token immediately. For a suspected vulnerability in this prototype, contact the repository owner privately through GitHub.

## Secret handling

All credentials belong in GitHub Actions repository secrets. Never commit `TELEGRAM_BOT_TOKEN`, `OPENBAND_GITHUB_TOKEN`, or `TIKTOK_MS_TOKEN`. Use a fine-grained GitHub token scoped only to `iltempe/openband` with the minimum issue permissions required.
