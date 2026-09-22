import datetime
import os
import random
import sqlite3

import pytest

from core.checker_app import CheckerApp
from db.sqlite_db import SqliteDb
from gorzdrav.models import ApiAppointment
from models.pydantic_models import DbUser


TEST_DB = f"test_time_filter_{random.randint(10_000_000, 99_999_999)}.db"


@pytest.fixture(scope="function")
def test_db():
    db = SqliteDb(db_path=TEST_DB)
    yield db
    db.connection.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_time_filter_defaults_to_any_time(test_db: SqliteDb):
    test_db.add_user(DbUser(id=1))
    user = test_db.get_user(1)

    assert user is not None
    assert user.time_from_minutes is None
    assert user.time_to_minutes is None


def test_set_and_reset_time_filter(test_db: SqliteDb):
    test_db.add_user(DbUser(id=1))

    test_db.set_time_filter(
        user_id=1,
        time_from_minutes=17 * 60,
        time_to_minutes=21 * 60,
    )
    user = test_db.get_user(1)

    assert user is not None
    assert user.time_from_minutes == 1020
    assert user.time_to_minutes == 1260

    test_db.reset_time_filter(user_id=1)
    user = test_db.get_user(1)

    assert user is not None
    assert user.time_from_minutes is None
    assert user.time_to_minutes is None


@pytest.mark.parametrize(
    "time_from,time_to",
    [
        (-1, 100),
        (0, 1440),
        (1200, 1000),
    ],
)
def test_invalid_time_filter_is_rejected(
    test_db: SqliteDb,
    time_from: int,
    time_to: int,
):
    test_db.add_user(DbUser(id=1))

    with pytest.raises(ValueError):
        test_db.set_time_filter(
            user_id=1,
            time_from_minutes=time_from,
            time_to_minutes=time_to,
        )


def test_existing_database_is_migrated_without_losing_user():
    legacy_db = f"legacy_{random.randint(10_000_000, 99_999_999)}.db"
    connection = sqlite3.connect(legacy_db)
    connection.execute(
        """CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            ping_status INTEGER DEFAULT 0 NOT NULL,
            doctor_id VARCHAR(40),
            last_seen DATETIME,
            limit_days INTEGER
        );"""
    )
    connection.execute(
        "INSERT INTO users (id, ping_status, last_seen) VALUES (?, ?, ?)",
        (123, 1, datetime.datetime.now(datetime.UTC)),
    )
    connection.commit()
    connection.close()

    try:
        db = SqliteDb(db_path=legacy_db)
        columns = {
            row[1]
            for row in db.cursor.execute("PRAGMA table_info(users);").fetchall()
        }
        user = db.get_user(123)

        assert "time_from_minutes" in columns
        assert "time_to_minutes" in columns
        assert "watch_mode" in columns
        assert "target_district_id" in columns
        assert "target_lpu_id" in columns
        assert "target_specialty_id" in columns
        assert user is not None
        assert user.watch_mode == "doctor"
        assert user.id == 123
        assert user.ping_status is True
        db.connection.close()
    finally:
        if os.path.exists(legacy_db):
            os.remove(legacy_db)


def test_appointments_are_filtered_by_time():
    day = datetime.date(2030, 1, 1)
    appointments = [
        ApiAppointment(
            id="1",
            visitStart=datetime.datetime.combine(day, datetime.time(16, 30)),
            visitEnd=datetime.datetime.combine(day, datetime.time(16, 45)),
            number=1,
            room="1",
        ),
        ApiAppointment(
            id="2",
            visitStart=datetime.datetime.combine(day, datetime.time(17, 0)),
            visitEnd=datetime.datetime.combine(day, datetime.time(17, 15)),
            number=2,
            room="2",
        ),
        ApiAppointment(
            id="3",
            visitStart=datetime.datetime.combine(day, datetime.time(20, 30)),
            visitEnd=datetime.datetime.combine(day, datetime.time(20, 45)),
            number=3,
            room="3",
        ),
        ApiAppointment(
            id="4",
            visitStart=datetime.datetime.combine(day, datetime.time(21, 30)),
            visitEnd=datetime.datetime.combine(day, datetime.time(21, 45)),
            number=4,
            room="4",
        ),
    ]
    user = DbUser(
        id=1,
        time_from_minutes=17 * 60,
        time_to_minutes=21 * 60,
    )

    filtered = CheckerApp.filter_appointments_for_user(
        appointments=appointments,
        user=user,
    )

    assert [appointment.id for appointment in filtered] == ["2", "3"]
