"""Сборка HTML-страницы интерфейса из исходников в app/static/ui/.

  page.html  — разметка (фрагмент без <html>/<head>, чтобы ту же страницу можно было
               опубликовать как статическое демо);
  style.css, i18n.js, demo.js, app.js — стили и код;
  icons.json — пиксельные SVG, подставляются вместо {{icon:NAME}};
  fonts/     — Monocraft (OFL), встраивается в страницу: интерфейс работает без интернета.

Сервер подставляет данные загрузки (каталог, лимиты, признак «есть сервер»). Сборка
кэшируется и пересобирается, если какой-то исходник изменился, — сборщик не нужен.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

UI = Path(__file__).parent / "static" / "ui"
SOURCES = ("page.html", "style.css", "i18n.js", "demo.js", "app.js", "icons.json")
FONTS = (("monocraft-regular.woff2", 400), ("monocraft-bold.woff2", 700))
PLACEHOLDER = "/*OKO_BOOT*/null"

FAVICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 9 7' shape-rendering='crispEdges'%3E"
    "%3Cpath fill='%23181c27' d='M2 0h5v1H2zM1 1h1v1H1zM7 1h1v1H7zM0 2h1v3H0zM8 2h1v3H8zM1 5h1v1H1zM7 5h1v1H7zM2 6h5v1H2z'/%3E"
    "%3Cpath fill='%239b6ae6' d='M3 2h3v3H3z'/%3E%3Cpath fill='%23181c27' d='M4 3h1v1H4z'/%3E%3C/svg%3E"
)

_cache: dict = {"key": None, "html": ""}


def _stamp() -> tuple:
    return tuple((UI / name).stat().st_mtime_ns for name in SOURCES)


def _assemble() -> str:
    html = (UI / "page.html").read_text(encoding="utf-8")
    icons = json.loads((UI / "icons.json").read_text(encoding="utf-8"))
    html = re.sub(r"\{\{icon:([A-Z_]+)\}\}", lambda m: icons[m.group(1)], html)
    fonts = "".join(
        f'@font-face{{font-family:"Monocraft";font-style:normal;font-weight:{weight};font-display:swap;'
        f'src:url(data:font/woff2;base64,{base64.b64encode((UI / "fonts" / name).read_bytes()).decode()}) format("woff2")}}'
        for name, weight in FONTS
    )
    script = "\n".join((UI / name).read_text(encoding="utf-8") for name in ("i18n.js", "demo.js", "app.js"))
    if "</script" in script.lower():
        raise ValueError("В коде интерфейса не должно быть строки </script>")
    html = html.replace("/*@STYLE@*/", (UI / "style.css").read_text(encoding="utf-8"), 1)
    html = html.replace("/*@FONTS@*/", fonts, 1)
    return html.replace("/*@SCRIPT@*/", script, 1)


def template() -> str:
    key = _stamp()
    if _cache["key"] != key:
        _cache.update(key=key, html=_assemble())
    return _cache["html"]


def fragment(boot: dict) -> str:
    boot_json = json.dumps(boot, ensure_ascii=False).replace("</", "<\\/")
    return template().replace(PLACEHOLDER, boot_json, 1)


def render_page(boot: dict) -> str:
    return (
        "<!doctype html>\n<html lang=\"ru\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        "<meta name=\"theme-color\" content=\"#0f0a1c\">\n"
        f"<link rel=\"icon\" href=\"{FAVICON}\">\n"
        "<style>:root{color-scheme:dark;padding-top:env(safe-area-inset-top,0px);"
        "padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n"
        f"{fragment(boot)}\n</html>\n"
    )
