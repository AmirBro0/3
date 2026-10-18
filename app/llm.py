"""Модель команды (LLM/VLM): запрос, ответ и заглушка.

КАК ПОДКЛЮЧИТЬ — три строки в файле .env (больше нигде ничего менять не нужно):
    OKO_LLM_URL=http://localhost:8001/v1      # vLLM, Ollama, LM Studio, llama.cpp — любой OpenAI-совместимый сервер
    OKO_LLM_KEY=ключ-если-нужен
    OKO_LLM_MODEL=имя-модели-на-сервере
Пока OKO_LLM_URL пустой, работает заглушка: отвечает в том же формате с пометкой [MOCK]
и с низкой уверенностью, поэтому её ответы видны только в интерфейсе («на проверку»)
и никогда не уходят жюри.

Модель должна работать локально (ТЗ: облачные AI-сервисы запрещены).

Что получает модель: кадры одного куска видео (JPEG) с временем и список типов нарушений.
Что должна вернуть (JSON):
    {"violations": [{"rule_id": "V03", "timecode_sec": 12.5, "confidence": 0.8,
                     "observed": "Кассир ушёл из кабины, клиент стоит у окна"}]}
Пункт норм модель не пишет: его берём из каталога по rule_id (без выдуманных ссылок).
"""
from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request

import cv2
import numpy as np

from .config import Settings
from .rules.catalog import RULES

log = logging.getLogger("oko.llm")

SYSTEM_PROMPT = (
    "Ты проверяешь видео с камеры над банковской кассой. Кадры идут по порядку, у каждого указано время.\n"
    "Описывай только то, что видно. Людей не узнавай, называй по роли: кассир, клиент, инкассатор.\n"
    "Найди нарушения из списка. Верни только JSON без пояснений:\n"
    '{"violations": [{"rule_id": "V03", "timecode_sec": 12.5, "confidence": 0.8, "observed": "что видно, одной фразой"}]}\n'
    'Если нарушений нет: {"violations": []}. Похоже на нарушение, но его нет в списке — rule_id "X00".\n'
    "Список:\n" + "\n".join(f"{r.id} — {r.title}: {r.hint}" for r in RULES.values())
)


def is_mock(settings: Settings) -> bool:
    return not settings.llm_url


def ask(frames: list[tuple[float, np.ndarray]], settings: Settings, timeout: float) -> list[dict]:
    """Кадры одного куска видео → проверенный список нарушений. Ошибки не роняют анализ."""
    if not frames:
        return []
    if is_mock(settings):
        return _mock(frames)
    try:
        text = _chat(frames, settings, timeout)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
        log.warning("Модель не ответила (%s): %s", settings.llm_url, exc)
        return []
    return validate(parse(text), frames[0][0], frames[-1][0])


def _chat(frames: list[tuple[float, np.ndarray]], settings: Settings, timeout: float) -> str:
    content: list[dict] = [{"type": "text", "text": "Кадры: " + ", ".join(f"{t:.1f} с" for t, _ in frames)}]
    for t, frame in frames:
        content.append({"type": "text", "text": f"Время {t:.1f} с:"})
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _jpeg_b64(frame)}})
    body = {
        "model": settings.llm_model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 600,
    }
    url = settings.llm_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.llm_key:
        headers["Authorization"] = f"Bearer {settings.llm_key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — адрес задаёт команда
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"] or ""


def _jpeg_b64(frame: np.ndarray, width: int = 512) -> str:
    h, w = frame.shape[:2]
    if w > width:
        frame = cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf.tobytes()).decode("ascii") if ok else ""


def parse(text: str) -> list[dict]:
    """Достаёт {"violations": [...]} из ответа, даже если модель обернула его в текст или ```json."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    items = data.get("violations", []) if isinstance(data, dict) else []
    return [x for x in items if isinstance(x, dict)]


def validate(items: list[dict], t_min: float, t_max: float) -> list[dict]:
    """Оставляет только понятные ответы: известный тип, время внутри куска, уверенность 0–1."""
    out = []
    for x in items:
        rule_id = str(x.get("rule_id", "")).strip().upper().replace("Х", "X")
        if rule_id not in RULES:
            continue
        try:
            t = float(x.get("timecode_sec", t_min))
            conf = float(x.get("confidence", 0.5))
        except (TypeError, ValueError):
            continue
        out.append({
            "rule_id": rule_id,
            "timecode_sec": min(max(t, t_min), t_max),
            "confidence": min(max(conf, 0.0), 1.0),
            "observed": str(x.get("observed") or RULES[rule_id].hint).strip(),
        })
    return out


def _mock(frames: list[tuple[float, np.ndarray]]) -> list[dict]:
    """Заглушка: «находит» момент с самым сильным движением в куске. Уверенность 0.4 — только «на проверку»."""
    best_t, best = frames[0][0], 0.0
    prev = None
    for t, frame in frames:
        small = cv2.cvtColor(cv2.resize(frame, (96, 54)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None:
            motion = float(np.mean(np.abs(small - prev)))
            if motion > best:
                best_t, best = t, motion
        prev = small
    if best < 2.0:  # почти статичный кусок — заглушка молчит
        return []
    return [{
        "rule_id": "V05",
        "timecode_sec": best_t,
        "confidence": 0.4,
        "observed": "[MOCK] Пример ответа модели: заметное движение в рабочей зоне",
        "score": best,
    }]
