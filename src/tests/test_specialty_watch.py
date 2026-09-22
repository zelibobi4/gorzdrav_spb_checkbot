import os
import random

import pytest

from db.sqlite_db import SqliteDb
from models.pydantic_models import DbDoctorToCreate, DbUser


@pytest.fixture(scope="function")
def test_db():
    db_path = f"test_specialty_{random.randint(10_000_000, 99_999_999)}.db"
    db = SqliteDb(db_path=db_path)
    yield db
    db.connection.close()
    if os.path.exists(db_path):
        os.remove(db_path)


def test_specialty_watch_is_persisted_and_grouped(test_db: SqliteDb):
    test_db.add_user(DbUser(id=1, ping_status=True))

    test_db.set_user_specialty_watch(
        user_id=1,
        district_id="10",
        lpu_id=123,
        specialty_id="dentist",
    )

    user = test_db.get_user(1)
    assert user is not None
    assert user.watch_mode == "specialty"
    assert user.doctor_id is None
    assert user.target_district_id == "10"
    assert user.target_lpu_id == 123
    assert user.target_specialty_id == "dentist"

    grouped = test_db.get_active_specialties_joined_users()
    assert len(grouped) == 1

    target = next(iter(grouped.values()))
    assert target.districtId == "10"
    assert target.lpuId == 123
    assert target.specialtyId == "dentist"
    assert [item.id for item in target.pinging_users] == [1]


def test_selecting_specific_doctor_resets_specialty_watch(test_db: SqliteDb):
    test_db.add_user(DbUser(id=1, ping_status=True))
    test_db.set_user_specialty_watch(
        user_id=1,
        district_id="10",
        lpu_id=123,
        specialty_id="dentist",
    )

    doctor_id = test_db.add_doctor(
        DbDoctorToCreate(
            districtId="10",
            lpuId=123,
            specialtyId="dentist",
            doctorId="doctor-1",
        )
    )
    test_db.add_user_doctor(user_id=1, doctor_id=doctor_id)

    user = test_db.get_user(1)
    assert user is not None
    assert user.watch_mode == "doctor"
    assert user.doctor_id == doctor_id
    assert user.target_district_id is None
    assert user.target_lpu_id is None
    assert user.target_specialty_id is None
