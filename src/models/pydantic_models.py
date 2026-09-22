from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class DbDoctorToCreate(BaseModel):
    districtId: str
    lpuId: int
    specialtyId: str
    doctorId: str


class DbDoctor(DbDoctorToCreate):
    id: str


class DbUser(BaseModel):
    id: int
    ping_status: bool | None = False
    doctor_id: Optional[str] = None
    last_seen: Optional[datetime] = None
    limit_days: Optional[int] = None
    time_from_minutes: Optional[int] = None
    time_to_minutes: Optional[int] = None
    watch_mode: str = "doctor"
    target_district_id: Optional[str] = None
    target_lpu_id: Optional[int] = None
    target_specialty_id: Optional[str] = None


class DbDoctorWithUsers(DbDoctor):
    pinging_users: list[DbUser]
