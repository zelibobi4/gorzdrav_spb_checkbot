import logging
import time
import traceback

from config import Config, LoggerConfig
from core.checker_app import CheckerApp
from depends import sqlite_db as DB
from gorzdrav.api import Gorzdrav
from gorzdrav.exceptions import GorzdravExceptionBase
from gorzdrav.models import ApiAppointment, ApiDoctor, Doctor
from models.pydantic_models import DbUser
from queries.orm import SyncOrm
from telegram.message_composer import TgMessageComposer
from telegram.types import TGParseMode

logging.basicConfig(
    level=LoggerConfig.LEVEL,
    format=LoggerConfig.FORMAT,
)

logger = logging.getLogger(__name__)

SyncOrm.create_tables()


def old_scheduler(timeout_secs: int):
    # бесконечный цикл периодической проверки
    time.sleep(2)
    logger.info("old scheduler started")
    while True:
        DB.inactivate_ping_for_old_users(inactive_months=2)
        raw_sql_checker()
        raw_sql_specialty_checker()
        time.sleep(timeout_secs)


def _appointment_key(doctor_id: str, appointment: ApiAppointment) -> str:
    """Стабильный ключ слота: врач + фактическое время приёма."""
    return f"{doctor_id}:{appointment.visitStart.isoformat()}"


def _save_check_snapshot(
    user: DbUser,
    matches: list[tuple[str, ApiAppointment, str]],
    checked_doctors: int,
    failed_doctors: int,
    excluded_doctors: int,
) -> None:
    """Сохраняет свежий результат фоновой проверки для быстрого /check."""
    DB.set_check_cache(
        user_id=user.id,
        signature=CheckerApp.get_check_cache_signature(user),
        payload=CheckerApp.serialize_check_snapshot(
            matches=matches,
            checked_doctors=checked_doctors,
            failed_doctors=failed_doctors,
            excluded_doctors=excluded_doctors,
        ),
    )


def raw_sql_checker():
    """Проверяет конкретных врачей и уведомляет только о новых подходящих талонах."""
    active_docs_with_users = DB.get_active_doctors_joined_users()
    logger.info("got %s pinging doctors", len(active_docs_with_users))
    logger.debug("active_docs_with_users: %s", active_docs_with_users)

    for doc_with_users in active_docs_with_users.values():
        try:
            api_doctor: Doctor | None = Gorzdrav.get_doctor(
                lpuId=doc_with_users.lpuId,
                specialtyId=doc_with_users.specialtyId,
                doctorId=doc_with_users.doctorId,
            )
        except Exception as e:
            logger.info("Gorzdrav exception: %s", str(e))
            logger.debug("Exception traceback: %s", traceback.format_exc())
            for user in doc_with_users.pinging_users:
                _save_check_snapshot(
                    user=user,
                    matches=[],
                    checked_doctors=0,
                    failed_doctors=1,
                    excluded_doctors=0,
                )
            continue

        if api_doctor is None:
            for user in doc_with_users.pinging_users:
                _save_check_snapshot(
                    user=user,
                    matches=[],
                    checked_doctors=0,
                    failed_doctors=1,
                    excluded_doctors=0,
                )
            continue

        try:
            appointments = Gorzdrav.get_appointments(
                lpuId=doc_with_users.lpuId,
                doctorId=doc_with_users.doctorId,
            )
        except Exception as e:
            # Ошибка API — это неизвестное состояние, а не подтверждение,
            # что талоны исчезли. Старый снимок оставляем как есть.
            logger.info(
                "Gorzdrav appointments exception for doctor %s: %s",
                doc_with_users.doctorId,
                str(e),
            )
            logger.debug("Exception traceback: %s", traceback.format_exc())
            for user in doc_with_users.pinging_users:
                _save_check_snapshot(
                    user=user,
                    matches=[],
                    checked_doctors=0,
                    failed_doctors=1,
                    excluded_doctors=0,
                )
            continue

        doctor_link: str = Gorzdrav.generate_link(
            districtId=doc_with_users.districtId,
            lpuId=doc_with_users.lpuId,
            specialtyId=doc_with_users.specialtyId,
            scheduleId=doc_with_users.doctorId,
        )

        for user in doc_with_users.pinging_users:
            user_appointments = CheckerApp.filter_appointments_for_user(
                appointments=appointments,
                user=user,
            )
            current_matches = [
                (api_doctor.name, appointment, doctor_link)
                for appointment in user_appointments
            ]
            _save_check_snapshot(
                user=user,
                matches=current_matches,
                checked_doctors=1,
                failed_doctors=0,
                excluded_doctors=0,
            )

            current_keys = {
                _appointment_key(doc_with_users.doctorId, appointment)
                for appointment in user_appointments
            }
            previous_keys = DB.get_seen_appointment_keys(user.id)
            new_keys = current_keys - previous_keys

            if not new_keys:
                # Исчезнувшие талоны удаляются из снимка.
                DB.set_seen_appointment_keys(user.id, current_keys)
                logger.debug(
                    "no new appointments for user %s; current=%s",
                    user.id,
                    len(current_keys),
                )
                continue

            message: str = TgMessageComposer.get_doc_ready_message_md(
                doctor_name=api_doctor.name,
                free_participant_count=api_doctor.freeParticipantCount,
                free_ticket_count=api_doctor.freeTicketCount,
                doctor_link=doctor_link,
                appointments=user_appointments,
            )

            time.sleep(0.2)
            logger.info(
                "send %s current appointments (%s new) to user %s",
                len(current_keys),
                len(new_keys),
                user.id,
            )
            delivered = CheckerApp.send_tg_message(
                message=message,
                api_token=Config.BOT_TOKEN,
                chat_id=user.id,
                parse_mode=TGParseMode.MARKDOWN,
            )
            if delivered:
                DB.set_seen_appointment_keys(user.id, current_keys)


def raw_sql_specialty_checker():
    """Ищет новые подходящие талоны у любого врача выбранной специальности."""
    active_specialties = DB.get_active_specialties_joined_users()
    logger.info("got %s specialty-wide watches", len(active_specialties))

    for specialty_with_users in active_specialties.values():
        try:
            doctors = Gorzdrav.get_doctors(
                lpuId=specialty_with_users.lpuId,
                specialtyId=specialty_with_users.specialtyId,
            )
        except Exception as e:
            logger.info("Gorzdrav specialty exception: %s", str(e))
            logger.debug("Exception traceback: %s", traceback.format_exc())
            for user in specialty_with_users.pinging_users:
                _save_check_snapshot(
                    user=user,
                    matches=[],
                    checked_doctors=0,
                    failed_doctors=1,
                    excluded_doctors=0,
                )
            continue

        if not doctors:
            for user in specialty_with_users.pinging_users:
                _save_check_snapshot(
                    user=user,
                    matches=[],
                    checked_doctors=0,
                    failed_doctors=0,
                    excluded_doctors=0,
                )
            continue

        appointments_by_doctor: list[tuple[ApiDoctor, list[ApiAppointment]]] = []
        failed_doctors_by_id: dict[str, str] = {}

        for doctor in doctors:
            try:
                appointments = Gorzdrav.get_appointments(
                    lpuId=specialty_with_users.lpuId,
                    doctorId=doctor.id,
                )
            except Exception as e:
                # Не считаем талоны врача исчезнувшими при 5xx/timeout:
                # просто сохраняем его часть предыдущего снимка.
                failed_doctors_by_id[doctor.id] = doctor.name
                logger.info(
                    "Gorzdrav appointments exception for doctor %s: %s",
                    doctor.id,
                    str(e),
                )
                logger.debug("Exception traceback: %s", traceback.format_exc())
                continue

            appointments_by_doctor.append((doctor, appointments))

        for user in specialty_with_users.pinging_users:
            matches: list[tuple[str, ApiAppointment, str]] = []
            successful_current_keys: set[str] = set()
            checked_doctors = 0
            excluded_doctors = 0

            for doctor, appointments in appointments_by_doctor:
                if (
                    user.exclude_duty_doctor
                    and CheckerApp.is_duty_doctor_name(doctor.name)
                ):
                    excluded_doctors += 1
                    logger.debug(
                        "duty doctor excluded for user %s: %s",
                        user.id,
                        doctor.name,
                    )
                    continue

                checked_doctors += 1

                user_appointments = CheckerApp.filter_appointments_for_user(
                    appointments=appointments,
                    user=user,
                )

                doctor_link = Gorzdrav.generate_link(
                    districtId=specialty_with_users.districtId,
                    lpuId=specialty_with_users.lpuId,
                    specialtyId=specialty_with_users.specialtyId,
                    scheduleId=doctor.id,
                )

                for appointment in user_appointments:
                    successful_current_keys.add(
                        _appointment_key(doctor.id, appointment)
                    )
                    matches.append(
                        (doctor.name, appointment, doctor_link)
                    )

            relevant_failed_ids: set[str] = set()
            for doctor_id, doctor_name in failed_doctors_by_id.items():
                if (
                    user.exclude_duty_doctor
                    and CheckerApp.is_duty_doctor_name(doctor_name)
                ):
                    excluded_doctors += 1
                else:
                    relevant_failed_ids.add(doctor_id)

            _save_check_snapshot(
                user=user,
                matches=matches,
                checked_doctors=checked_doctors,
                failed_doctors=len(relevant_failed_ids),
                excluded_doctors=excluded_doctors,
            )

            previous_keys = DB.get_seen_appointment_keys(user.id)

            # Для врачей, чей endpoint в этом цикле упал, не делаем вывод,
            # что их старые талоны исчезли. Их ключи временно сохраняются.
            failed_prefixes = tuple(f"{doctor_id}:" for doctor_id in relevant_failed_ids)
            preserved_failed_keys = (
                {
                    key
                    for key in previous_keys
                    if failed_prefixes and key.startswith(failed_prefixes)
                }
                if failed_prefixes
                else set()
            )
            effective_current_keys = successful_current_keys | preserved_failed_keys
            new_keys = successful_current_keys - previous_keys

            if not new_keys:
                # Если успешно опрошенный талон исчез, его больше нет в снимке.
                DB.set_seen_appointment_keys(user.id, effective_current_keys)
                logger.debug(
                    "no new specialty appointments for user %s; current=%s; failed_doctors=%s",
                    user.id,
                    len(successful_current_keys),
                    len(relevant_failed_ids),
                )
                continue

            # Уведомление содержит только подтверждённо доступные сейчас талоны.
            message = TgMessageComposer.get_any_doctor_ready_message_md(matches)
            time.sleep(0.2)
            logger.info(
                "send %s current specialty appointments (%s new) to user %s",
                len(successful_current_keys),
                len(new_keys),
                user.id,
            )
            delivered = CheckerApp.send_tg_message(
                message=message,
                api_token=Config.BOT_TOKEN,
                chat_id=user.id,
                parse_mode=TGParseMode.MARKDOWN,
            )
            if delivered:
                DB.set_seen_appointment_keys(user.id, effective_current_keys)


if __name__ == "__main__":
    old_scheduler(timeout_secs=Config.CHECKER_TIMEOUT_SECS)
