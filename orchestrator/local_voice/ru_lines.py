"""Russian lines the orchestrator says itself. The model's own words follow the persona.

English stays the default until the person says something in Russian, so an English
session is unchanged.
"""
from __future__ import annotations


def line(lang: str, en: str, ru: str) -> str:
    return ru if lang == "ru" else en


ACKS = {
    "kb": "Сейчас посмотрю.",
    "read": "Сейчас проверю.",
    "grep": "Сейчас проверю.",
    "find": "Сейчас поищу.",
    "ls": "Сейчас посмотрю.",
    "bash": "Секунду.",
    "default": "Секунду.",
}
LABELS = {
    "kb": "ищу в базе знаний",
    "read": "читаю файл",
    "grep": "ищу в файлах",
    "find": "ищу файлы",
    "ls": "смотрю папку",
    "bash": "выполняю команду",
    "write": "записываю файл",
    "edit": "правлю файл",
}
PROGRESS = "Ещё ищу."
LOADING = "Секунду, модель просыпается."
NO_ANSWER = "Быстро не нашёл. Скажите, если искать дальше."
OFFER = "Продолжить?"
ACT = "Режим действий. Могу менять файлы и запускать команды и спрошу перед опасным."
TALK = "Снова просто разговариваем."
GO_AHEAD = "Говорите."
NOTES_ONLY = "Заметки только в журнале. Скажите: перейди в журнал."
NOTES_ON = "Записываю. Буду сохранять всё, что скажете, пока не скажете хватит записывать."
NOTES_OFF = "Больше не записываю."
SORRY = "Не получилось запустить агента."
CANT_OPEN = "Сейчас не могу открыть {desc}."
BACK = "Снова {desc}."
SWITCH = "Перехожу: {desc}."
WHICH = "Вы про {opts}?"
ASK_AGAIN = "Сделать? Да или нет."
DENIED = "Хорошо, не стал."
TIMED_OUT = "Я не услышал ответ, поэтому не стал."
SESSION = "Хорошо. До конца этой сессии не буду спрашивать ещё раз."
CARD = {
    "allow_once": "Сделать",
    "allow_session": "Разрешить до конца сессии",
    "deny": "Не надо",
}
