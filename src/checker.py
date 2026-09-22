import logging
import time
import traceback

from config import Config, LoggerConfig
from core.checker_app import CheckerApp
from depends import sqlite_db as DB
from gorzdrav.api import Gorzdrav
from gorzdrav.exceptions import GorzdravExceptionBase
from gorzdrav.models import ApiAppointment, ApiDoctor, Doctor
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
    """Стабильный ключ талона для антиспам-снимка."""
    return f"{doctor_id}:{appointment.id}"


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
            continue

        if api_doctor is None:
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
            continue

        if not doctors:
            continue

        appointments_by_doctor: list[tuple[ApiDoctor, list[ApiAppointment]]] = []
        failed_doctor_ids: set[str] = set()

        for doctor in doctors:
            try:
                appointments = Gorzdrav.get_appointments(
                    lpuId=specialty_with_users.lpuId,
                    doctorId=doctor.id,
                )
            except Exception as e:
                # Не считаем талоны врача исчезнувшими при 5xx/timeout:
                # просто сохраняем его часть предыдущего снимка.
                failed_doctor_ids.add(doctor.id)
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

            for doctor, appointments in appointments_by_doctor:
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

            previous_keys = DB.get_seen_appointment_keys(user.id)

            # Для врачей, чей endpoint в этом цикле упал, не делаем вывод,
            # что их старые талоны исчезли. Их ключи временно сохраняются.
            failed_prefixes = tuple(f"{doctor_id}:" for doctor_id in failed_doctor_ids)
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
                    len(failed_doctor_ids),
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
