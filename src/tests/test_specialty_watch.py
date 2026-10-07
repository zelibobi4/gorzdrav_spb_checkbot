import os
import random

import pytest

from core.checker_app import CheckerApp
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


def test_duty_doctor_setting_is_persisted_and_grouped(test_db: SqliteDb):
    test_db.add_user(DbUser(id=1, ping_status=True))
    test_db.set_user_specialty_watch(
        user_id=1,
        district_id="10",
        lpu_id=123,
        specialty_id="dentist",
    )

    user = test_db.get_user(1)
    assert user is not None
    assert user.exclude_duty_doctor is False

    test_db.set_exclude_duty_doctor(user_id=1, exclude=True)

    user = test_db.get_user(1)
    assert user is not None
    assert user.exclude_duty_doctor is True

    grouped = test_db.get_active_specialties_joined_users()
    target = next(iter(grouped.values()))
    assert target.pinging_users[0].exclude_duty_doctor is True


def test_duty_doctor_setting_resets_notification_snapshot(test_db: SqliteDb):
    test_db.add_user(DbUser(id=1, ping_status=True))
    test_db.set_seen_appointment_keys(1, {"doctor-a:2030-01-01T18:00:00"})

    test_db.set_exclude_duty_doctor(user_id=1, exclude=True)

    assert test_db.get_seen_appointment_keys(1) == set()


@pytest.mark.parametrize(
    "name, expected",
    [
        (
            "Дежурный врач (Осмотр и оказание неотложной помощи, "
            "явка в регистратуру за 20 мин.)",
            True,
        ),
        ("  дежурный ВРАЧ  ", True),
        ("Дежурный стоматолог", False),
        ("Иванов Иван Иванович", False),
    ],
)
def test_duty_doctor_name_matching(name: str, expected: bool):
    assert CheckerApp.is_duty_doctor_name(name) is expected
