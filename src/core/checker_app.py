import datetime
import logging

import requests

from gorzdrav.models import ApiAppointment, Doctor
from models.pydantic_models import DbUser
from telegram.types import TGParseMode

logger = logging.getLogger(__name__)


class CheckerApp:
    @staticmethod
    def is_doc_nearestDate_in_user_limit_days(user: DbUser, doctor: Doctor) -> bool:
        """Проверяет, попадает ли ближайшая дата записи врача в лимит дней пользователя от текущей даты"""
        user_limit_days: int | None = user.limit_days
        # если лимит дней не задан или 0, то врач попадает в лимит дней
        if not user_limit_days:
            return True
        # если лимит отрицательный, то считаем что его нет
        if user_limit_days < 0:
            return True
        # не ищем дальше 99 дней
        if user_limit_days > 99:
            user_limit_days = 99

        # ТУТ НАДО ПОЛУЧАТЬ APPOINTMENTS ВРАЧА И ИСКАТЬ БЛИЖАЙШУЮ ДАТУ
        # https://gorzdrav.spb.ru/_api/api/v2/schedule/lpu/{lpu_id}/doctor/{doc_id}/appointments

        # nearest_date - то ближайшее время кода врач на работе (наверное),
        # а не время ближайшего свободного его приёма
        nearest_date: datetime.datetime | None = doctor.nearestDate
        logger.debug("nearest_date: %s", nearest_date)
        if nearest_date is None:
            return False
        # берем тз СПб +3 часа к UTC
        current_date = datetime.datetime.now(
            datetime.timezone(offset=datetime.timedelta(hours=3))
        ).date()

        # 1 день - это сегодня
        # 2 дня - это сегодня и завтра
        delta_days: int = (nearest_date.date() - current_date).days + 1
        logger.debug("delta_days: %s", delta_days)
        return delta_days <= user_limit_days

    # send message to telegram with requests.post
    @staticmethod
    def send_tg_message(
        message: str,
        api_token: str,
        chat_id: int | str,
        parse_mode: TGParseMode | None = None,
    ) -> None:
        """
        Отправка сообщений в телеграм пользователю через requests.post
        :param message: str - сообщение
        :param api_token: str - токен бота
        :param chat_id: - id чата
        :return: None
        """
        url: str = f"https://api.telegram.org/bot{api_token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        response = requests.post(
            url=url,
            data=data,
            params={"parse_mode": parse_mode},
        )
        if not response.ok:
            logger.warning(
                "Failed to send message to %s %s",
                chat_id,
                response.text,
            )

    @staticmethod
    def filter_appointments_for_user(
        appointments: list[ApiAppointment],
        user: DbUser,
    ) -> list[ApiAppointment]:
        """Возвращает свободные талоны, подходящие пользователю по дате и времени."""
        if not appointments:
            return []

        current_date = datetime.datetime.now(
            datetime.timezone(offset=datetime.timedelta(hours=3))
        ).date()
        result: list[ApiAppointment] = []

        for appointment in appointments:
            visit_start = appointment.visitStart

            if user.limit_days is not None and user.limit_days > 0:
                delta_days = (visit_start.date() - current_date).days + 1
                if delta_days < 1 or delta_days > user.limit_days:
                    continue

            visit_minutes = visit_start.hour * 60 + visit_start.minute
            if (
                user.time_from_minutes is not None
                and visit_minutes < user.time_from_minutes
            ):
                continue
            if (
                user.time_to_minutes is not None
                and visit_minutes > user.time_to_minutes
            ):
                continue

            result.append(appointment)

        return sorted(result, key=lambda appointment: appointment.visitStart)

    @staticmethod
    def check_appointments_in_user_limit_days(
        appointments: list[ApiAppointment],
        user: DbUser,
    ) -> bool:
        """Проверяет есть ли назначения врача в пределах лимита дней пользователя"""
        if not user.limit_days:
            return bool(appointments)
        return bool(
            CheckerApp.filter_appointments_for_user(
                appointments=appointments,
                user=user,
            )
        )
