import logging
import time
import traceback

from config import Config, LoggerConfig
from core.checker_app import CheckerApp
from depends import sqlite_db as DB
from gorzdrav.api import Gorzdrav
from gorzdrav.exceptions import GorzdravExceptionBase
from gorzdrav.models import ApiAppointment, Doctor
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
        time.sleep(timeout_secs)


def raw_sql_checker():
    """Проверяет нужных докторов и отправляет всем желающим пользователям сообщение о наличи талончика"""
    active_docs_with_users = DB.get_active_doctors_joined_users()
    logger.info("got %s pinging doctors", len(active_docs_with_users))
    logger.debug("active_docs_with_users: %s", active_docs_with_users)
    for doc_with_users in active_docs_with_users.values():
        # запрашиваем информацию о враче у горздрава
        try:
            api_doctor: Doctor | None = Gorzdrav.get_doctor(
                lpuId=doc_with_users.lpuId,
                specialtyId=doc_with_users.specialtyId,
                doctorId=doc_with_users.doctorId,
            )
            logger.debug(
                "api_doctor: %s",
                api_doctor.model_dump_json(indent=2) if api_doctor else None,
            )
        except Exception as e:
            # когда медучреждение не отвечает
            logger.info("Gorzdrav exception: %s", str(e))
            logger.debug("Exception traceback: %s", traceback.format_exc())
            continue
        if api_doctor is None:
            continue

        doctor_users = doc_with_users.pinging_users

        # Для фильтров нельзя полагаться только на freeParticipantCount:
        # API Горздрава иногда отдаёт appointments при нулевом счётчике врача.
        need_appointments = any(
            (user.limit_days is not None and user.limit_days > 0)
            or user.time_from_minutes is not None
            or user.time_to_minutes is not None
            for user in doctor_users
        )
        if not api_doctor.have_free_places and not need_appointments:
            continue

        link: str = Gorzdrav.generate_link(
            districtId=doc_with_users.districtId,
            lpuId=doc_with_users.lpuId,
            specialtyId=doc_with_users.specialtyId,
            scheduleId=doc_with_users.doctorId,
        )

        # Реальные appointments нужны, если хотя бы один пользователь фильтрует
        # результат по дате или времени.
        appointments: list[ApiAppointment] = []
        if need_appointments:
            appointments = Gorzdrav.get_appointments(
                lpuId=doc_with_users.lpuId,
                doctorId=doc_with_users.doctorId,
            )
            logger.debug("doctor appointments: %s", appointments)

        for user in doc_with_users.pinging_users:
            logger.debug("user: %s", user.model_dump_json(indent=2))

            user_has_filters = (
                (user.limit_days is not None and user.limit_days > 0)
                or user.time_from_minutes is not None
                or user.time_to_minutes is not None
            )
            user_appointments = appointments
            if user_has_filters:
                user_appointments = CheckerApp.filter_appointments_for_user(
                    appointments=appointments,
                    user=user,
                )
                if not user_appointments:
                    logger.debug(
                        "no appointments matching filters for user %s",
                        user.id,
                    )
                    continue

            message: str = TgMessageComposer.get_doc_ready_message_md(
                doctor_name=api_doctor.name,
                free_participant_count=api_doctor.freeParticipantCount,
                free_ticket_count=api_doctor.freeTicketCount,
                doctor_link=link,
                appointments=user_appointments,
            )

            time.sleep(0.2)
            logger.info("send message about doc to user: %s", user.id)
            CheckerApp.send_tg_message(
                message=message,
                api_token=Config.BOT_TOKEN,
                chat_id=user.id,
                parse_mode=TGParseMode.MARKDOWN,
            )
            DB.set_user_ping_status(user_id=user.id, ping_status=False)


if __name__ == "__main__":
    old_scheduler(timeout_secs=Config.CHECKER_TIMEOUT_SECS)
