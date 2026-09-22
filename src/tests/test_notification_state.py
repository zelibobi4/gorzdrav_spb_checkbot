import datetime
import os
import random

from db.sqlite_db import SqliteDb
from gorzdrav.models import ApiAppointment
from models.pydantic_models import DbUser
from telegram.message_composer import TgMessageComposer


def _make_db() -> tuple[SqliteDb, str]:
    path = f"test_notification_state_{random.randint(10_000_000, 99_999_999)}.db"
    return SqliteDb(db_path=path), path


def test_seen_appointments_are_current_snapshot():
    db, path = _make_db()
    try:
        db.add_user(DbUser(id=1, ping_status=True))

        db.set_seen_appointment_keys(1, {"doctor-a:1", "doctor-a:2"})
        assert db.get_seen_appointment_keys(1) == {"doctor-a:1", "doctor-a:2"}

        # Талон 1 исчез, талон 3 появился: снимок должен отражать только
        # реально доступное сейчас состояние.
        db.set_seen_appointment_keys(1, {"doctor-a:2", "doctor-a:3"})
        assert db.get_seen_appointment_keys(1) == {"doctor-a:2", "doctor-a:3"}
    finally:
        db.connection.close()
        if os.path.exists(path):
            os.remove(path)


def test_filter_change_resets_notification_snapshot():
    db, path = _make_db()
    try:
        db.add_user(DbUser(id=1, ping_status=True))
        db.set_seen_appointment_keys(1, {"doctor-a:1"})

        db.set_time_filter(
            user_id=1,
            time_from_minutes=18 * 60,
            time_to_minutes=23 * 60,
        )

        assert db.get_seen_appointment_keys(1) == set()
    finally:
        db.connection.close()
        if os.path.exists(path):
            os.remove(path)


def test_reenabling_monitoring_resets_notification_snapshot():
    db, path = _make_db()
    try:
        db.add_user(DbUser(id=1, ping_status=False))
        db.set_seen_appointment_keys(1, {"doctor-a:1"})

        db.set_user_ping_status(user_id=1, ping_status=True)

        assert db.get_seen_appointment_keys(1) == set()
        assert db.get_user_ping_status(1) is True
    finally:
        db.connection.close()
        if os.path.exists(path):
            os.remove(path)


def test_specialty_change_resets_notification_snapshot():
    db, path = _make_db()
    try:
        db.add_user(DbUser(id=1, ping_status=True))
        db.set_seen_appointment_keys(1, {"doctor-a:1"})

        db.set_user_specialty_watch(
            user_id=1,
            district_id="10",
            lpu_id=123,
            specialty_id="dentist",
        )

        assert db.get_seen_appointment_keys(1) == set()
    finally:
        db.connection.close()
        if os.path.exists(path):
            os.remove(path)


def test_specialty_message_lists_all_current_slots_and_keeps_monitoring():
    day = datetime.date(2030, 1, 1)
    matches = []

    for number in range(1, 11):
        appointment = ApiAppointment(
            id=str(number),
            visitStart=datetime.datetime.combine(
                day,
                datetime.time(18, number),
            ),
            visitEnd=datetime.datetime.combine(
                day,
                datetime.time(18, number + 1),
            ),
            number=number,
            room=str(number),
        )
        matches.append(
            (
                f"Врач {number}",
                appointment,
                f"https://example.test/{number}",
            )
        )

    message = TgMessageComposer.get_any_doctor_ready_message_md(matches)

    assert "Сейчас найдено подходящих талонов: 10." in message
    assert "Врач 1" in message
    assert "Врач 10" in message
    assert "Отслеживание продолжается" in message
    assert "Отслеживание отключено" not in message
