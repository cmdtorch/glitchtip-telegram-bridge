import html
import logging
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GlitchTip → Telegram Bridge")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

LEVEL_EMOJI = {
    "critical": "🚨",
    "error": "🔴",
    "warning": "⚠️",
    "info": "ℹ️",
    "debug": "🐛",
}


class GlitchTipPayload(BaseModel):
    project_name: str = "Unknown Project"
    message: str = "No message provided"
    culprit: str | None = None
    issue_url: HttpUrl | None = None
    level: str = "error"
    timestamp: datetime | None = None


def build_message(payload: GlitchTipPayload) -> str:
    emoji = LEVEL_EMOJI.get(payload.level.lower(), "🔴")
    level_label = payload.level.upper()
    project = html.escape(payload.project_name)
    message = html.escape(payload.message)

    ts = payload.timestamp or datetime.now(tz=timezone.utc)
    time_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"{emoji} <b>New {level_label} in {project}</b>",
        "",
        f"📝 <b>Message:</b> <code>{message}</code>",
    ]

    if payload.culprit:
        culprit = html.escape(payload.culprit)
        lines.append(f"📍 <b>Culprit:</b> <code>{culprit}</code>")

    lines.append(f"🕒 <b>Time:</b> {time_str}")

    if payload.issue_url:
        lines += ["", f'🔗 <a href="{payload.issue_url}">View Issue on GlitchTip</a>']

    return "\n".join(lines)


@app.get("/webhook/{bot_token}/{chat_id}")
async def verify_webhook(bot_token: str, chat_id: str) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/webhook/{bot_token}/{chat_id}")
async def receive_webhook(
    bot_token: str,
    chat_id: str,
    request: Request,
) -> JSONResponse:
    # Parse body — return 422 on bad JSON or validation errors automatically via Pydantic.
    body = await request.json()
    payload = GlitchTipPayload.model_validate(body)

    message = build_message(payload)
    url = TELEGRAM_API.format(token=bot_token)

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )

            # Telegram returns 400 when a group was upgraded to a supergroup.
            # The response body contains the new chat ID — retry once with it.
            if response.status_code == 400:
                tg_body = response.json()
                migrated_id = tg_body.get("parameters", {}).get("migrate_to_chat_id")
                if migrated_id:
                    logger.warning(
                        "Chat %s migrated to supergroup %s, retrying with new ID.",
                        chat_id,
                        migrated_id,
                    )
                    response = await client.post(
                        url,
                        json={
                            "chat_id": migrated_id,
                            "text": message,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True,
                        },
                    )

            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Telegram API error: status=%s body=%s",
                exc.response.status_code,
                exc.response.text,
            )
            raise HTTPException(
                status_code=502,
                detail=f"Telegram API error {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Network error contacting Telegram: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Network error contacting Telegram: {exc}",
            ) from exc

    logger.info("Forwarded %s event for project '%s'", payload.level, payload.project_name)
    return JSONResponse({"status": "ok", "telegram_message_id": response.json().get("result", {}).get("message_id")})
