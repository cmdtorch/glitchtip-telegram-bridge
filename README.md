# GlitchTip → Telegram Bridge

A lightweight FastAPI service that receives GlitchTip webhook events and forwards them as formatted HTML messages to a Telegram chat.

## How it works

```
GlitchTip  →  POST /webhook/{bot_token}/{chat_id}  →  Telegram Bot API
```

Each incoming webhook is validated, formatted with severity emojis, and sent to the specified Telegram chat. The bot token and chat ID live in the URL, so a single running instance can serve multiple projects and bots simultaneously.

## Example notification

```
🔴 New ERROR in my-api

📝 Message: ValueError: invalid literal for int()
📍 Culprit: views.py in post_data
🕒 Time: 2026-02-18 13:00:00 UTC

🔗 View Issue on GlitchTip
```

## Prerequisites

- [uv](https://github.com/astral-sh/uv)
- A Telegram bot token — create one via [@BotFather](https://t.me/BotFather)
- The chat ID of the target channel/group — use [@userinfobot](https://t.me/userinfobot)

## Running locally

```bash
uv sync
uvicorn main:app --host 0.0.0.0 --port 8000
```

The API docs are available at `http://localhost:8000/docs`.

## Running with Docker

```bash
docker build -t glitchtip-telegram-bridge .
docker run -p 8000:8000 glitchtip-telegram-bridge
```

## GlitchTip configuration

In your GlitchTip project go to **Settings → Integrations → Webhook** and set the URL to:

```
http://your-host:8000/webhook/<BOT_TOKEN>/<CHAT_ID>
```

### Expected payload fields

| Field          | Type     | Required | Description                        |
|----------------|----------|----------|------------------------------------|
| `project_name` | `string` | No       | Display name of the project        |
| `message`      | `string` | No       | Error message or exception string  |
| `culprit`      | `string` | No       | File/function where the error occurred |
| `issue_url`    | `string` | No       | Link to the issue in GlitchTip     |
| `level`        | `string` | No       | `critical` / `error` / `warning` / `info` / `debug` |
| `timestamp`    | `string` | No       | ISO-8601 datetime; defaults to now |

## Severity emoji mapping

| Level      | Emoji |
|------------|-------|
| `critical` | 🚨    |
| `error`    | 🔴    |
| `warning`  | ⚠️    |
| `info`     | ℹ️    |
| `debug`    | 🐛    |

## Security note

The bot token is embedded in the URL. If this service is exposed to the public internet, restrict access at the network level (reverse proxy, firewall) or add a shared secret segment to the path to prevent unauthorized use.
