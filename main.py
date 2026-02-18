import html
import logging

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GlitchTip → Telegram Bridge")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# GlitchTip uses Rocket.Chat/Slack-style color codes for severity.
COLOR_EMOJI = {
    "#e52b50": "🔴",  # error
    "#f4a836": "⚠️",  # warning
    "#1e88e5": "ℹ️",  # info
    "#757575": "🐛",  # debug
}

FIELD_EMOJI = {
    "project":     "📦",
    "environment": "🌍",
    "server name": "🖥",
    "release":     "🏷",
}


class AttachmentField(BaseModel):
    title: str
    value: str
    short: bool = False


class Attachment(BaseModel):
    title: str = ""
    title_link: str | None = None
    text: str | None = None
    color: str | None = None
    fields: list[AttachmentField] = []


class GlitchTipPayload(BaseModel):
    alias: str = "GlitchTip"
    text: str = "GlitchTip Alert"
    attachments: list[Attachment] = []


def build_message(payload: GlitchTipPayload) -> str:
    attachment = payload.attachments[0] if payload.attachments else Attachment()

    emoji = COLOR_EMOJI.get((attachment.color or "").lower(), "🔴")
    title = html.escape(attachment.title or payload.text)

    lines = [f"{emoji} <b>{title}</b>"]

    for field in attachment.fields:
        field_emoji = FIELD_EMOJI.get(field.title.lower(), "•")
        lines.append(f"{field_emoji} <b>{html.escape(field.title)}:</b> {html.escape(field.value)}")

    if attachment.title_link:
        lines += ["", f'🔗 <a href="{html.escape(attachment.title_link)}">View Issue on GlitchTip</a>']

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

    project = next(
        (f.value for f in (payload.attachments[0].fields if payload.attachments else []) if f.title == "Project"),
        "unknown",
    )
    logger.info("Forwarded alert for project '%s'", project)
    return JSONResponse({"status": "ok", "telegram_message_id": response.json().get("result", {}).get("message_id")})
