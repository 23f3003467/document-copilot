"""Create initial application schema.

Revision ID: 20261108_0001
Revises:
Create Date: 2026-11-08
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "20261108_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "source_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("primary_document", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("markdown_content", sa.Text(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("accession_number", name="uq_source_documents_accession_number"),
    )
    op.create_index("ix_source_documents_ticker_fiscal_year", "source_documents", ["ticker", "fiscal_year"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page", sa.String(length=64), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("chunk_metadata", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_chunk"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_search_vector_gin "
        "ON document_chunks USING gin (search_vector)"
    )

    op.create_table(
        "document_tables",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("table_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("units", sa.String(length=255), nullable=True),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("table_data", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("source_html_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "table_index", name="uq_document_tables_document_table"),
    )
    op.create_index("ix_document_tables_document_id", "document_tables", ["document_id"])

    op.create_table(
        "chat_threads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), server_default="New chat", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_threads_user_id", "chat_threads", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("parts", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "sequence", name="uq_chat_messages_thread_sequence"),
    )
    op.create_index("ix_chat_messages_thread_id", "chat_messages", ["thread_id"])

    op.create_table(
        "message_citations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("page", sa.String(length=64), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "citation_index", name="uq_message_citations_message_citation_index"),
    )
    op.create_index("ix_message_citations_message_id", "message_citations", ["message_id"])

    op.execute("ALTER TABLE chat_threads ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE message_citations ENABLE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY chat_threads_user_policy ON chat_threads
        FOR ALL TO authenticated
        USING (user_id = auth.uid())
        WITH CHECK (user_id = auth.uid())
        """
    )
    op.execute(
        """
        CREATE POLICY chat_messages_user_policy ON chat_messages
        FOR ALL TO authenticated
        USING (
            EXISTS (
                SELECT 1 FROM chat_threads
                WHERE chat_threads.id = chat_messages.thread_id
                  AND chat_threads.user_id = auth.uid()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM chat_threads
                WHERE chat_threads.id = chat_messages.thread_id
                  AND chat_threads.user_id = auth.uid()
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY message_citations_user_policy ON message_citations
        FOR ALL TO authenticated
        USING (
            EXISTS (
                SELECT 1
                FROM chat_messages
                JOIN chat_threads ON chat_threads.id = chat_messages.thread_id
                WHERE chat_messages.id = message_citations.message_id
                  AND chat_threads.user_id = auth.uid()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM chat_messages
                JOIN chat_threads ON chat_threads.id = chat_messages.thread_id
                WHERE chat_messages.id = message_citations.message_id
                  AND chat_threads.user_id = auth.uid()
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS message_citations_user_policy ON message_citations")
    op.execute("DROP POLICY IF EXISTS chat_messages_user_policy ON chat_messages")
    op.execute("DROP POLICY IF EXISTS chat_threads_user_policy ON chat_threads")
    op.drop_table("message_citations")
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
    op.drop_table("document_tables")
    op.drop_table("document_chunks")
    op.drop_table("source_documents")
    op.drop_table("users")
