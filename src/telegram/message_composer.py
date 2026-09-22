from gorzdrav.models import ApiAppointment


class TgMessageComposer:
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
