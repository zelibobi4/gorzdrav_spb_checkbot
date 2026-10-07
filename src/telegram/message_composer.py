from gorzdrav.models import ApiAppointment


class TgMessageComposer:
    @staticmethod
    def _format_minutes(value: int | None, fallback: str) -> str:
        if value is None:
            return fallback
        return f"{value // 60:02d}:{value % 60:02d}"

    @staticmethod
    def get_manual_check_message_md(
        matches: list[tuple[str, ApiAppointment, str]],
        checked_doctors: int,
        failed_doctors: int,
        excluded_doctors: int,
        limit_days: int | None,
        time_from_minutes: int | None,
        time_to_minutes: int | None,
        exclude_duty_doctor: bool | None,
        ping_status: bool,
    ) -> str:
        """Формирует результат ручной /check без изменения состояния мониторинга."""
        sorted_matches = sorted(matches, key=lambda item: item[1].visitStart)
        shown_matches = sorted_matches[:10]

        if sorted_matches:
            lines = []
            for doctor_name, appointment, doctor_link in shown_matches:
                room_text = f", каб. {appointment.room}" if appointment.room else ""
                lines.append(
                    f"• {appointment.visitStart:%d.%m.%Y %H:%M}{room_text}"
                    + f" — {doctor_name} — [записаться]({doctor_link})"
                )

            hidden_count = len(sorted_matches) - len(shown_matches)
            hidden_text = (
                f"\n…и ещё {hidden_count}."
                if hidden_count > 0
                else ""
            )
            result_text = (
                f"🔎 *Сейчас найдено подходящих талонов: {len(sorted_matches)}*\n"
                + "\n".join(lines)
                + hidden_text
            )
        else:
            if failed_doctors:
                result_text = (
                    "🔎 Проверка завершена.\n"
                    "Среди успешно проверенных врачей подходящих талонов сейчас нет."
                )
            else:
                result_text = (
                    "🔎 Проверка завершена.\n"
                    "Подходящих талонов сейчас нет."
                )

        if limit_days is not None and limit_days > 0:
            days_text = f"{limit_days} дн."
        else:
            days_text = "без ограничения"

        time_from = TgMessageComposer._format_minutes(
            time_from_minutes,
            "00:00",
        )
        time_to = TgMessageComposer._format_minutes(
            time_to_minutes,
            "23:59",
        )
        if time_from_minutes is None and time_to_minutes is None:
            time_text = "любое"
        else:
            time_text = f"{time_from}–{time_to}"

        monitoring_text = "включено" if ping_status else "выключено"

        stats = (
            f"\n\nПроверено врачей: {checked_doctors}."
            + (
                f" Ошибок API: {failed_doctors}."
                if failed_doctors
                else ""
            )
            + (
                f" Исключено дежурных: {excluded_doctors}."
                if excluded_doctors
                else ""
            )
            + f"\nФильтр: {days_text}, время {time_text}."
            + (
                f"\nДежурный врач: {'исключён' if exclude_duty_doctor else 'учитывается'}."
                if exclude_duty_doctor is not None
                else ""
            )
            + f"\nОтслеживание: {monitoring_text}."
            + "\n\nРучная проверка не меняет отслеживание и антиспам."
        )
        return result_text + stats

    @staticmethod
    def get_doc_ready_message_md(
        doctor_name: str,
        free_participant_count: int,
        free_ticket_count: int,
        doctor_link: str,
        appointments: list[ApiAppointment],
    ) -> str:
        appointments_text = ""
        if appointments:
            sorted_appointments = sorted(
                appointments,
                key=lambda x: x.visitStart,
            )
            shown_appointments = sorted_appointments[:20]
            appointments_text = (
                f"Сейчас подходит талонов: {len(sorted_appointments)}.\n"
                + "".join(
                    f"• {appointment.visitStart:%d.%m.%Y %H:%M}"
                    + (f", каб. {appointment.room}" if appointment.room else "")
                    + "\n"
                    for appointment in shown_appointments
                )
            )
            if len(sorted_appointments) > len(shown_appointments):
                appointments_text += (
                    f"…и ещё {len(sorted_appointments) - len(shown_appointments)}.\n"
                )

        message = (
            f"Врач {doctor_name} доступен для записи.\n"
            + appointments_text
            + f"Мест для записи: {free_participant_count}.\n"
            + f"Талонов для записи: {free_ticket_count}.\n"
            + "\n"
            + f"Запишитесь на приём по [ссылке]({doctor_link})\n\n"
            + "Отслеживание продолжается. Следующее сообщение придёт, когда появится новый подходящий талон."
        )
        return message

    @staticmethod
    def get_any_doctor_ready_message_md(
        matches: list[tuple[str, ApiAppointment, str]],
    ) -> str:
        """Сообщение о подходящих талонах у любого врача специальности."""
        sorted_matches = sorted(
            matches,
            key=lambda item: item[1].visitStart,
        )
        shown_matches = sorted_matches[:10]

        lines = []
        for doctor_name, appointment, doctor_link in shown_matches:
            room_text = f", каб. {appointment.room}" if appointment.room else ""
            lines.append(
                f"• {appointment.visitStart:%d.%m.%Y %H:%M}{room_text}"
                + f" — {doctor_name} — [записаться]({doctor_link})"
            )

        hidden_count = len(sorted_matches) - len(shown_matches)
        hidden_text = f"\n…и ещё {hidden_count}." if hidden_count > 0 else ""

        return (
            f"Сейчас найдено подходящих талонов: {len(sorted_matches)}.\n"
            + "\n".join(lines)
            + hidden_text
            + "\n\nОтслеживание продолжается. "
            + "Следующее сообщение придёт, когда появится новый подходящий талон."
        )

    @staticmethod
    def get_doc_selected_message_md(
        doctor_name: str,
        free_participant_count: int,
        free_ticket_count: int,
        doctor_link: str,
        ping_status: bool,
    ) -> str:
        ping_text = f"Отслеживание {'включено' if ping_status else 'отключено'}."
        text = (
            f"Выбран врач {doctor_name}\n"
            + f"Свободных мест {free_participant_count}.\n"
            + f"Свободных талонов {free_ticket_count}.\n"
            + "\n"
            + f"{ping_text}\n\n"
        )
        text += f"Ссылка на запись: [ссылка]({doctor_link})"
        return text
