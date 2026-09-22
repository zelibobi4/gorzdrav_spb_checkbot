# Горздрав СПб бот

Бот для телеграм для проверки талонов к врачу через апи горздрава

## Установка и запуск

- склонировать или скопировать репозиторий

  ```sh
  git clone <repository-url>
  cd <repository-folder>
  ```

- создать `.env` файл в корне проекта

  ```sh
  BOT_TOKEN="ваш телеграм токен от @BotFather"
  DB_FILE="sqlite.db"
  CHECKER_TIMEOUT_SECS=60
  ```

- создать виртуальное окружение

  ```sh
  python -m venv venv
  ```

- активировать виртуальное окружение

  Linux

  ```sh
  source venv/bin/activate
  ```
  
  Windows

  ```cmd
  venv\Scripts\activate
  ```

- установить зависимости

  ```sh
  # Установить зависимости
  pip install -r requirements.txt
  ```

- Запуск

  ```bash
  python3 src/app.py
  ```

### Конфигурация программы

Настройки для запуска программы хранятся в текстовом файле `.env`.

Параметр | Описание
-- | --
`BOT_TOKEN` | токен телеграм бота от [@BotFather](https://t.me/botfather)
`DB_FILE` | имя файла базы данных (создается новый если файла нет)
`CHECKER_TIMEOUT_SECS` | период проверки свободных талончиков через api горздрава

## Функционал

Бот периодически проверяет доступность талончиков к врачу и отправляет уведомление в Telegram, если найден подходящий свободный талон. Можно ограничить поиск количеством дней и временем приёма, например ждать только вечерние слоты после 17:00.

## Команды бота

Команда       | Описание
-|-
`/status`     | показать статус врача и статус отслеживания
`/on`         | включить отслеживание свободных мест для записи
`/off`        | отключить отслеживание свободных мест для записи
`/help`       | помощь
`/start`      | создать профиль пользователя бота
`/delete`     | удалить профиль пользователя бота
`/set_doctor` | задать врача для отслеживания
`/evening`    | искать только вечерние талоны с 17:00 до конца дня
`/time 17:00-21:00` | задать произвольный диапазон времени
`/time_off`   | сбросить фильтр времени

## База данных

- хранит пользователей бота:
  - телеграм ид
  - включен ли мониторинг свободных мест у врача
  - ссылка на врача
  - время последнего взаимодействия с ботом
  - ограничение по количеству дней
  - диапазон времени приёма
- хранит врачей пользователя:
  - ид района
  - ид медучреждения
  - ид специальности
  - ид врача

## API

### Gorzdrav API

[https://github.com/egorantonov/gorzdrav/wiki/SPB-Gorzdrav-API-Documentation](https://github.com/egorantonov/gorzdrav/wiki/SPB-Gorzdrav-API-Documentation)

#### Примеры запросов к горздраву

- [https://gorzdrav.spb.ru/_api/api/v2/shared/districts](https://gorzdrav.spb.ru/_api/api/v2/shared/districts) - список районов
- [https://gorzdrav.spb.ru/_api/api/v2/shared/district/10/lpus](https://gorzdrav.spb.ru/_api/api/v2/shared/district/10/lpus) - список медучреждений в 10 районе
- [https://gorzdrav.spb.ru/_api/api/v2/schedule/lpu/229/specialties](https://gorzdrav.spb.ru/_api/api/v2/schedule/lpu/229/specialties) - информация по всем свободным специальностям в больнице с ид 229
- [https://gorzdrav.spb.ru/_api/api/v2/schedule/lpu/30/speciality/981/doctors](https://gorzdrav.spb.ru/_api/api/v2/schedule/lpu/30/speciality/981/doctors) - информация по доступным врачам в больнице 30 по специальности 981
- [https://gorzdrav.spb.ru/_api/api/v2/schedule/lpu/1138/doctor/36/timetable](https://gorzdrav.spb.ru/_api/api/v2/schedule/lpu/1138/doctor/36/timetable) - расписание врача 36 в больнице 1138
- [https://gorzdrav.spb.ru/_api/api/v2/schedule/lpu/30/doctor/222618/appointments](https://gorzdrav.spb.ru/_api/api/v2/schedule/lpu/30/doctor/222618/appointments) - доступные назначения к врачу

### Особенности

При получении списка докторов на сайте горздрава, можно сразу получить информацию о количестве у них свободных мест в поле `freeParticipantCount`. Далее при выборе места для записи запрашивается информация о `appointments`. __Но__ количество `appointments` может отличаться от количества свободных номерков `freeParticipantCount` в поле доктора. Т.е. в списке докторов у него может не быть свободных номерков, но быть несколько свободных `appointments`.

## Тесты

Запуск тестов

```sh
cd src
python -m pytest .
```

## Releases

- fork: добавлен фильтр времени приёма (`/evening`, `/time`, `/time_off`) и ожидание только подходящих слотов
- `v1.2.2` - фикс модели ApiAppointment
- `v1.2.0` - Автоматически отключаются проверку у пользователей, которых не было видно больше 2х месяцев
- `v1.1.0` - Добавлена возможность устанавливать количество дней в пределах которого ищется талончик от текущего дня. (в БД появилась новая колонка у пользователя)
