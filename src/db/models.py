import datetime
import sqlalchemy as sa
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from db.database import Base

metadata_obj = sa.MetaData()

users_table = sa.Table(
    "users",
    metadata_obj,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("ping_status", sa.Boolean, default=False),
    sa.Column(
        "last_seen",
        sa.DateTime,
        default=sa.func.now,
        onupdate=sa.func.now,
    ),
    sa.Column("time_from_minutes", sa.Integer),
    sa.Column("time_to_minutes", sa.Integer),
    sa.Column("watch_mode", sa.String, default="doctor"),
    sa.Column("target_district_id", sa.String),
    sa.Column("target_lpu_id", sa.Integer),
    sa.Column("target_specialty_id", sa.String),
)


class UserOrm(Base):
    """
    Table "users"
    id: int - telegram id of user
    ping_status: bool - ping or not gorzdrav for user'd doctor
    last_seen: datetime - last time user was in system
    doctor_id: int - id of doctor for user
    doctor: DoctorOrm - doctor for user
    limit_date: date - дата окончания поиска свободного места
    """

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    ping_status: Mapped[bool] = mapped_column(default=False)
    last_seen: Mapped[datetime.datetime] = mapped_column(
        default=datetime.datetime.now(datetime.UTC),
        onupdate=datetime.datetime.now(datetime.UTC),
    )
    doctor_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey(column="doctors.id", ondelete="SET NULL"),
        default=None,
    )
    doctor: Mapped["DoctorOrm"] = relationship(back_populates="users")
    limit_days: Mapped[int | None] = mapped_column(default=None)
    time_from_minutes: Mapped[int | None] = mapped_column(default=None)
    time_to_minutes: Mapped[int | None] = mapped_column(default=None)
    watch_mode: Mapped[str] = mapped_column(default="doctor")
    target_district_id: Mapped[str | None] = mapped_column(default=None)
    target_lpu_id: Mapped[int | None] = mapped_column(default=None)
    target_specialty_id: Mapped[str | None] = mapped_column(default=None)

    @property
    def ping_status_str(self) -> str:
        return (
            "Статус проверки: " + f"{'Включена' if self.ping_status else 'Отключена'}"
        )

    def __repr__(self) -> str:
        return f"""UserOrm ({self.id})"""


class DoctorOrm(Base):
    """
    Таблица "doctors"
    id: int - ид строки
    districtId: str - id района в системе горздрава
    lpuId: int - id медучреждения в системе горздрава
    specialtyId: str - id специальности врача в системе горздрава
    doctorId: str - id врача в системе горздрава
    """

    __tablename__ = "doctors"
    id: Mapped[str] = mapped_column(
        primary_key=True,
    )
    districtId: Mapped[str]
    lpuId: Mapped[int]
    specialtyId: Mapped[str]
    doctorId: Mapped[str]
    users: Mapped[list["UserOrm"]] = relationship(back_populates="doctor")

    def __str__(self) -> str:
        return f"""Врач ({self.lpuId}; {self.specialtyId}; {self.doctorId})"""
