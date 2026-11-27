import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    runs: Mapped[list["EvaluationRun"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_evaluation_runs_status",
        ),
        Index("ix_evaluation_runs_experiment_created", "experiment_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    precision_at_k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recall_at_k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mrr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ndcg_at_k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    citation_correctness: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    abstention_accuracy: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    avg_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    experiment: Mapped["Experiment"] = relationship(back_populates="runs")
