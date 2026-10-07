import datetime
import os
import random

from core.checker_app import CheckerApp
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


def test_manual_check_message_shows_current_results_and_settings():
    day = datetime.date(2030, 1, 1)
    matches = []
    for number in range(1, 4):
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

    message = TgMessageComposer.get_manual_check_message_md(
        matches=matches,
        checked_doctors=29,
        failed_doctors=0,
        excluded_doctors=1,
        limit_days=15,
        time_from_minutes=18 * 60,
        time_to_minutes=23 * 60,
        exclude_duty_doctor=True,
        ping_status=True,
    )

    assert "Сейчас найдено подходящих талонов: 3" in message
    assert "Проверено врачей: 29." in message
    assert "Исключено дежурных: 1." in message
    assert "Фильтр: 15 дн., время 18:00–23:00." in message
    assert "Дежурный врач: исключён." in message
    assert "Отслеживание: включено." in message
    assert "не меняет отслеживание и антиспам" in message


def test_manual_check_message_marks_partial_api_failure():
    message = TgMessageComposer.get_manual_check_message_md(
        matches=[],
        checked_doctors=27,
        failed_doctors=2,
        excluded_doctors=1,
        limit_days=None,
        time_from_minutes=None,
        time_to_minutes=None,
        exclude_duty_doctor=True,
        ping_status=False,
    )

    assert "Среди успешно проверенных врачей" in message
    assert "Проверено врачей: 27." in message
    assert "Ошибок API: 2." in message
    assert "Фильтр: без ограничения, время любое." in message
    assert "Отслеживание: выключено." in message


def test_manual_check_specific_doctor_omits_duty_filter_line():
    message = TgMessageComposer.get_manual_check_message_md(
        matches=[],
        checked_doctors=1,
        failed_doctors=0,
        excluded_doctors=0,
        limit_days=7,
        time_from_minutes=None,
        time_to_minutes=None,
        exclude_duty_doctor=None,
        ping_status=True,
    )

    assert "Проверено врачей: 1." in message
    assert "Дежурный врач:" not in message


def test_check_cache_roundtrip_and_expiry():
    db, path = _make_db()
    try:
        db.add_user(DbUser(id=1, ping_status=True))
        db.set_check_cache(
            user_id=1,
            signature="settings-a",
            payload='{"matches":[]}',
        )

        cached = db.get_fresh_check_cache(
            user_id=1,
            signature="settings-a",
            max_age_seconds=60,
        )
        assert cached is not None
        payload, age_seconds = cached
        assert payload == '{"matches":[]}'
        assert 0 <= age_seconds <= 2

        db.cursor.execute(
            """
            UPDATE user_check_cache
            SET checked_at = ?
            WHERE user_id = ?;
            """,
            (
                (
                    datetime.datetime.now(datetime.UTC)
                    - datetime.timedelta(seconds=120)
                ).isoformat(),
                1,
            ),
        )
        db.connection.commit()

        assert (
            db.get_fresh_check_cache(
                user_id=1,
                signature="settings-a",
                max_age_seconds=60,
            )
            is None
        )
    finally:
        db.connection.close()
        if os.path.exists(path):
            os.remove(path)


def test_check_cache_rejected_when_search_settings_changed():
    db, path = _make_db()
    try:
        user = DbUser(
            id=1,
            ping_status=True,
            watch_mode="specialty",
            target_district_id="10",
            target_lpu_id=123,
            target_specialty_id="dentist",
            limit_days=15,
            time_from_minutes=18 * 60,
            time_to_minutes=23 * 60,
            exclude_duty_doctor=True,
        )
        db.add_user(user)

        signature = CheckerApp.get_check_cache_signature(user)
        db.set_check_cache(
            user_id=1,
            signature=signature,
            payload='{"matches":[]}',
        )

        changed_user = user.model_copy(update={"time_from_minutes": 17 * 60})
        changed_signature = CheckerApp.get_check_cache_signature(changed_user)

        assert changed_signature != signature
        assert (
            db.get_fresh_check_cache(
                user_id=1,
                signature=changed_signature,
                max_age_seconds=60,
            )
            is None
        )
    finally:
        db.connection.close()
        if os.path.exists(path):
            os.remove(path)


def test_check_snapshot_serialization_roundtrip():
    appointment = ApiAppointment(
        id="slot-1",
        visitStart=datetime.datetime(2030, 1, 1, 18, 30),
        visitEnd=datetime.datetime(2030, 1, 1, 18, 45),
        number=1,
        room="12",
    )
    matches = [
        (
            "Иванов Иван Иванович",
            appointment,
            "https://example.test/doctor-1",
        )
    ]

    payload = CheckerApp.serialize_check_snapshot(
        matches=matches,
        checked_doctors=29,
        failed_doctors=1,
        excluded_doctors=1,
    )
    restored, checked, failed, excluded = (
        CheckerApp.deserialize_check_snapshot(payload)
    )

    assert checked == 29
    assert failed == 1
    assert excluded == 1
    assert len(restored) == 1
    assert restored[0][0] == "Иванов Иван Иванович"
    assert restored[0][1].id == "slot-1"
    assert restored[0][1].visitStart == appointment.visitStart
    assert restored[0][2] == "https://example.test/doctor-1"


def test_manual_check_message_marks_cached_result():
    message = TgMessageComposer.get_manual_check_message_md(
        matches=[],
        checked_doctors=29,
        failed_doctors=0,
        excluded_doctors=1,
        limit_days=15,
        time_from_minutes=18 * 60,
        time_to_minutes=23 * 60,
        exclude_duty_doctor=True,
        ping_status=True,
        cache_age_seconds=17,
    )

    assert "17 сек. назад" in message
    assert "без новых запросов к API" in message


def test_check_cache_signature_ignores_monitoring_status():
    user_on = DbUser(
        id=1,
        ping_status=True,
        watch_mode="specialty",
        target_district_id="10",
        target_lpu_id=123,
        target_specialty_id="dentist",
        limit_days=15,
        time_from_minutes=18 * 60,
        time_to_minutes=23 * 60,
        exclude_duty_doctor=True,
    )
    user_off = user_on.model_copy(update={"ping_status": False})

    assert (
        CheckerApp.get_check_cache_signature(user_on)
        == CheckerApp.get_check_cache_signature(user_off)
    )
