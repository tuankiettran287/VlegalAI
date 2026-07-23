from __future__ import annotations

import hashlib
import uuid

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import decrypt_text, encrypt_text
from app.db import SessionFactory
from app.models import ChatMessage, Conversation, ConversationSummary
from app.services.ai import QwenService
from app.services.embeddings import EmbeddingConfig, LocalEmbeddingService, get_embedding_service


SUMMARY_SYSTEM_PROMPT = """Bạn là bộ nhớ hội thoại pháp lý.
Hãy tạo một bản tóm tắt lũy tiến, chính xác và súc tích bằng tiếng Việt.
Phải giữ lại sự kiện, chủ thể, mốc thời gian, câu hỏi, kết luận pháp lý, căn cứ đã viện dẫn
và các vấn đề chưa được giải quyết. Không thêm thông tin không có trong hội thoại.
Không dùng markdown, không giải thích quy trình tóm tắt."""


def _embedding_config(settings: Settings) -> EmbeddingConfig:
    return EmbeddingConfig(
        model_path=settings.embedding_model_path,
        model_repo=settings.embedding_model_repo,
        model_revision=settings.embedding_model_revision,
        device=settings.embedding_device,
        dimensions=settings.postgres_vector_size,
        batch_size=settings.embedding_batch_size,
        max_sequence_length=settings.embedding_max_sequence_length,
    )


class ConversationMemoryService:
    """Create encrypted LLM summaries and searchable BGE-M3 vectors."""

    def __init__(
        self,
        settings: Settings,
        ai: QwenService,
        embeddings: LocalEmbeddingService | None = None,
    ) -> None:
        self.settings = settings
        self.ai = ai
        self.embeddings = embeddings or get_embedding_service(_embedding_config(settings))

    async def get_summary(self, db: AsyncSession, conversation_id: uuid.UUID) -> str:
        memory = await db.scalar(
            select(ConversationSummary).where(
                ConversationSummary.conversation_id == conversation_id
            )
        )
        if not memory:
            return ""
        return decrypt_text(memory.summary_ciphertext, self.settings)

    async def refresh(self, conversation_id: uuid.UUID) -> ConversationSummary | None:
        lock_key = f"vlegal:conversation-summary:{conversation_id}"
        async with SessionFactory() as db:
            await db.execute(
                sql_text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": lock_key},
            )
            exists = await db.scalar(
                select(Conversation.id).where(Conversation.id == conversation_id)
            )
            if not exists:
                return None

            memory = await db.scalar(
                select(ConversationSummary).where(
                    ConversationSummary.conversation_id == conversation_id
                )
            )
            message_count = int(
                await db.scalar(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.conversation_id == conversation_id
                    )
                )
                or 0
            )
            summarized_count = memory.source_message_count if memory else 0
            if message_count == 0 or summarized_count >= message_count:
                return memory

            new_messages = (
                await db.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.conversation_id == conversation_id)
                    .order_by(ChatMessage.created_at, ChatMessage.id)
                    .offset(summarized_count)
                )
            ).all()
            summary = (
                decrypt_text(memory.summary_ciphertext, self.settings)
                if memory
                else "(Chưa có tóm tắt trước đó)"
            )
            batch_size = self.settings.conversation_summary_batch_size
            for start in range(0, len(new_messages), batch_size):
                batch = new_messages[start : start + batch_size]
                transcript = "\n".join(
                    f"{'Người dùng' if message.role == 'USER' else 'Trợ lý'}: "
                    f"{decrypt_text(message.content_ciphertext, self.settings)[:4000]}"
                    for message in batch
                )
                summary = (
                    await self.ai.complete(
                        SUMMARY_SYSTEM_PROMPT,
                        f"TÓM TẮT HIỆN CÓ:\n{summary}\n\n"
                        f"CÁC LƯỢT HỘI THOẠI MỚI:\n{transcript}\n\n"
                        "Hãy trả về bản tóm tắt hợp nhất thay thế cho bản cũ.",
                        temperature=0,
                        max_tokens=self.settings.conversation_summary_max_tokens,
                    )
                ).strip()

            vectors = await run_in_threadpool(self.embeddings.embed_documents, [summary])
            embedding = vectors[0]
            if memory is None:
                memory = ConversationSummary(
                    conversation_id=conversation_id,
                    summary_ciphertext="",
                    summary_hash="",
                    source_message_count=message_count,
                    embedding_model=self.settings.embedding_model_repo,
                    embedding_revision=self.settings.embedding_model_revision,
                    embedding=embedding,
                )
                db.add(memory)
            memory.summary_ciphertext = encrypt_text(summary, self.settings)
            memory.summary_hash = hashlib.sha256(summary.encode("utf-8")).hexdigest()
            memory.source_message_count = message_count
            memory.embedding_model = self.settings.embedding_model_repo
            memory.embedding_revision = self.settings.embedding_model_revision
            memory.embedding = embedding
            await db.commit()
            await db.refresh(memory)
            return memory
