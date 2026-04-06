import io
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import AiChat, AiMessage, AiReport, Group, User
from app.services.ai_context_builder import (
    build_context_for_case,
    build_context_for_daily,
    build_context_for_general,
    build_context_for_group,
    build_context_for_person,
    get_context_summary,
)
from app.services.ai_service import (
    SYSTEM_PROMPT_CASE,
    SYSTEM_PROMPT_DAILY,
    SYSTEM_PROMPT_GENERAL,
    SYSTEM_PROMPT_GROUP,
    SYSTEM_PROMPT_PERSON,
    ollama_service,
)


router = APIRouter()


class ChatCreateBody(BaseModel):
    context_type: str = "general"
    context_id: Optional[str] = None
    first_message: str


class ChatMessageBody(BaseModel):
    content: str


class QuickCaseBody(BaseModel):
    case_id: str
    days: int = 7


class QuickPersonBody(BaseModel):
    person_id: str


class SaveReportBody(BaseModel):
    title: str
    report_type: str
    context_id: Optional[str] = None
    content: str


class ChatOut(BaseModel):
    id: str
    title: str
    context_type: str
    context_id: Optional[str] = None
    updated_at: Optional[str] = None


class AiMessageOut(BaseModel):
    id: str
    role: str
    content: str
    tokens_used: Optional[int] = None
    created_at: Optional[str] = None


class AiReportOut(BaseModel):
    id: str
    title: str
    report_type: str
    context_id: Optional[str] = None
    created_at: Optional[str] = None


def _serialize_chat(chat: AiChat) -> ChatOut:
    return ChatOut(
        id=str(chat.id),
        title=chat.title,
        context_type=chat.context_type,
        context_id=chat.context_id,
        updated_at=chat.updated_at.isoformat() if chat.updated_at else None,
    )


def _serialize_ai_message(message: AiMessage) -> AiMessageOut:
    return AiMessageOut(
        id=str(message.id),
        role=message.role,
        content=message.content,
        tokens_used=message.tokens_used,
        created_at=message.created_at.isoformat() if message.created_at else None,
    )


def _serialize_report(report: AiReport) -> AiReportOut:
    return AiReportOut(
        id=str(report.id),
        title=report.title,
        report_type=report.report_type,
        context_id=report.context_id,
        created_at=report.created_at.isoformat() if report.created_at else None,
    )


def _normalize_context_type(context_type: str) -> str:
    allowed = {"general", "group", "daily", "case", "person"}
    value = (context_type or "general").strip().lower()
    if value not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported context_type")
    return value


async def _get_chat_for_user(db: AsyncSession, chat_id: str, user: User) -> AiChat:
    result = await db.execute(
        select(AiChat).where(AiChat.id == uuid.UUID(chat_id), AiChat.user_id == user.id)
    )
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


async def _build_context(context_type: str, context_id: Optional[str]) -> str:
    if context_type == "general":
        return await build_context_for_general()
    if context_type == "daily":
        return await build_context_for_daily()
    if context_type == "group":
        if not context_id:
            raise HTTPException(status_code=400, detail="group context requires context_id")
        return await build_context_for_group(context_id)
    if context_type == "case":
        if not context_id:
            raise HTTPException(status_code=400, detail="case context requires context_id")
        return await build_context_for_case(context_id)
    if context_type == "person":
        if not context_id:
            raise HTTPException(status_code=400, detail="person context requires context_id")
        return await build_context_for_person(context_id)
    raise HTTPException(status_code=400, detail="Unsupported context type")


def _system_prompt(context_type: str) -> str:
    return {
        "general": SYSTEM_PROMPT_GENERAL,
        "daily": SYSTEM_PROMPT_DAILY,
        "group": SYSTEM_PROMPT_GROUP,
        "case": SYSTEM_PROMPT_CASE,
        "person": SYSTEM_PROMPT_PERSON,
    }.get(context_type, SYSTEM_PROMPT_GENERAL)


def _make_pdf(title: str, content: str) -> bytes:
    buffer = io.BytesIO()
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))

    def add_header_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVuSans", 9)
        canvas.drawString(40, 20, "ДСК")
        canvas.drawRightString(A4[0] - 40, 20, f"FaceWatch · {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        canvas.restoreState()

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="FWBody", fontName="DejaVuSans", fontSize=10, leading=14))
    styles.add(ParagraphStyle(name="FWTitle", fontName="DejaVuSans", fontSize=14, leading=18, spaceAfter=12))

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=50, bottomMargin=35)
    story = [Paragraph(title, styles["FWTitle"]), Spacer(1, 8)]
    for block in content.split("\n\n"):
        safe_block = block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        story.append(Paragraph(safe_block, styles["FWBody"]))
        story.append(Spacer(1, 10))
    doc.build(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
    return buffer.getvalue()


@router.get("/status")
async def ai_status(_: User = Depends(get_current_user)):
    return await ollama_service.get_status()


@router.get("/chats", response_model=list[ChatOut])
async def list_chats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AiChat)
        .where(AiChat.user_id == current_user.id)
        .order_by(AiChat.updated_at.desc(), AiChat.created_at.desc())
    )
    return [_serialize_chat(chat) for chat in result.scalars().all()]


@router.post("/chats")
async def create_chat(
    body: ChatCreateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context_type = _normalize_context_type(body.context_type)
    title = body.first_message.strip()[:50] or "Новий чат"
    chat = AiChat(
        id=uuid.uuid4(),
        user_id=current_user.id,
        title=title,
        context_type=context_type,
        context_id=body.context_id,
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return {"id": str(chat.id)}


@router.get("/chats/{chat_id}/messages", response_model=list[AiMessageOut])
async def list_chat_messages(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = await _get_chat_for_user(db, chat_id, current_user)
    result = await db.execute(
        select(AiMessage)
        .where(AiMessage.chat_id == chat.id)
        .order_by(AiMessage.created_at.asc())
    )
    return [_serialize_ai_message(message) for message in result.scalars().all()]


@router.get("/chats/{chat_id}/summary")
async def chat_summary(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = await _get_chat_for_user(db, chat_id, current_user)
    summary = await get_context_summary(chat.context_type, chat.context_id)
    return {"chat": _serialize_chat(chat), "summary": summary}


@router.post("/chats/{chat_id}/message")
async def send_chat_message(
    chat_id: str,
    body: ChatMessageBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = await _get_chat_for_user(db, chat_id, current_user)

    if chat.context_type in {"case", "person"}:
        raise HTTPException(
            status_code=501,
            detail=f"{chat.context_type} context is unavailable: current FaceWatch schema has no {chat.context_type}_id support.",
        )

    user_message = AiMessage(
        id=uuid.uuid4(),
        chat_id=chat.id,
        role="user",
        content=body.content.strip(),
    )
    db.add(user_message)
    chat.updated_at = datetime.utcnow()
    await db.commit()

    history_result = await db.execute(
        select(AiMessage)
        .where(AiMessage.chat_id == chat.id)
        .order_by(AiMessage.created_at.asc())
    )
    history = history_result.scalars().all()
    context = await _build_context(chat.context_type, chat.context_id)
    messages = [{"role": "user", "content": f"КОНТЕКСТ FACEWATCH:\n\n{context}"}]
    for item in history:
        messages.append({"role": item.role, "content": item.content})

    async def event_stream():
        collected: list[str] = []
        try:
            async for chunk in ollama_service.chat(messages, _system_prompt(chat.context_type)):
                collected.append(chunk)
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            assistant_content = "".join(collected).strip()
            if assistant_content:
                db.add(
                    AiMessage(
                        id=uuid.uuid4(),
                        chat_id=chat.id,
                        role="assistant",
                        content=assistant_content,
                    )
                )
                chat.updated_at = datetime.utcnow()
                await db.commit()
            yield "data: [DONE]\n\n"
        except Exception as exc:
            await db.rollback()
            yield f"data: {json.dumps(f'[ERROR] {str(exc)}', ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = await _get_chat_for_user(db, chat_id, current_user)
    await db.execute(delete(AiMessage).where(AiMessage.chat_id == chat.id))
    await db.delete(chat)
    await db.commit()
    return {"ok": True}


@router.post("/quick/daily-brief")
async def quick_daily_brief(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = await build_context_for_daily()
    prompt = (
        "Підготуй денний оперативний брифінг за наданим контекстом. "
        "Структура: ключові події, активні групи, ризики, пріоритетні дії.\n\n"
        + context
    )
    content = await ollama_service.generate(prompt)
    report = AiReport(
        id=uuid.uuid4(),
        user_id=current_user.id,
        title=f"Денний брифінг {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        report_type="daily",
        content=content,
    )
    db.add(report)
    await db.commit()
    return {"content": content, "report_id": str(report.id)}


@router.post("/quick/case-summary")
async def quick_case_summary(body: QuickCaseBody):
    raise HTTPException(status_code=501, detail="Case summary is unavailable: current schema has no case_id.")


@router.post("/quick/person-analysis")
async def quick_person_analysis(body: QuickPersonBody):
    raise HTTPException(status_code=501, detail="Person analysis is unavailable: current schema has no person_id.")


@router.get("/reports", response_model=list[AiReportOut])
async def list_reports(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AiReport)
        .where(AiReport.user_id == current_user.id)
        .order_by(AiReport.created_at.desc())
    )
    return [_serialize_report(report) for report in result.scalars().all()]


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AiReport).where(AiReport.id == uuid.UUID(report_id), AiReport.user_id == current_user.id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    payload = _serialize_report(report).model_dump()
    payload["content"] = report.content
    return payload


@router.post("/reports")
async def create_report(
    body: SaveReportBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = AiReport(
        id=uuid.uuid4(),
        user_id=current_user.id,
        title=body.title.strip()[:200] or "Звіт ШІ",
        report_type=body.report_type.strip()[:30] or "custom",
        context_id=body.context_id,
        content=body.content.strip(),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return _serialize_report(report)


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AiReport).where(AiReport.id == uuid.UUID(report_id), AiReport.user_id == current_user.id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await db.delete(report)
    await db.commit()
    return {"ok": True}


@router.get("/reports/{report_id}/pdf")
async def download_report_pdf(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AiReport).where(AiReport.id == uuid.UUID(report_id), AiReport.user_id == current_user.id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    pdf_bytes = _make_pdf(report.title, report.content)
    headers = {
        "Content-Disposition": f'attachment; filename="report-{report.id}.pdf"'
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
