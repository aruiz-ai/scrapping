"""Registro persistente de uso del scraper (data/usage_state.json).

Lleva la cuenta diaria de visitas a perfil hechas por el scraper y la hora
de fin de la última ejecución, para aplicar el tope diario, el cooldown
entre ejecuciones y la ventana horaria de arranque.

El archivo vive en data/ (volumen Docker): sobrevive reinicios y
recreaciones del contenedor. El uso MANUAL de LinkedIn no es rastreable
desde aquí: para contabilizarlo, edita a mano la entrada del día en
"profile_lookups".
"""

import json
import os
import threading
from datetime import datetime, timedelta

import config

_LOCK = threading.Lock()
_PRUNE_DAYS = 7  # días de historial que se conservan en el JSON


def _today():
    """Fecha local del servidor: clave del contador diario."""
    return _now_local().strftime("%Y-%m-%d")


def _load():
    try:
        with open(config.USAGE_STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("profile_lookups"), dict):
        data["profile_lookups"] = {}
    return data


def _save(data):
    tmp_path = config.USAGE_STATE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, config.USAGE_STATE_PATH)


def daily_profile_count():
    with _LOCK:
        return int(_load()["profile_lookups"].get(_today(), 0))


def remaining_daily_lookups():
    return max(0, config.DAILY_PROFILE_LOOKUP_LIMIT - daily_profile_count())


def add_profile_lookups(count=1):
    """Suma visitas de perfil al día actual (llamada incremental por job)."""
    if count <= 0:
        return
    with _LOCK:
        data = _load()
        lookups = data["profile_lookups"]
        today = _today()
        lookups[today] = int(lookups.get(today, 0)) + count
        cutoff = (datetime.now() - timedelta(days=_PRUNE_DAYS)).strftime("%Y-%m-%d")
        for day in [day for day in lookups if str(day) < cutoff]:
            del lookups[day]
        _save(data)


def _now_local():
    """Ahora mismo con zona horaria explícita (hora del servidor)."""
    return datetime.now().astimezone()


def _parse_dt(value):
    """ISO -> datetime aware; los naive se interpretan en hora local."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def seconds_since_last_run():
    with _LOCK:
        last = _parse_dt(_load().get("last_run_end"))
    if last is None:
        return None
    return max(0.0, (_now_local() - last).total_seconds())


def record_run_start():
    with _LOCK:
        data = _load()
        data["last_run_start"] = _now_local().isoformat(timespec="seconds")
        _save(data)


def record_run_end():
    with _LOCK:
        data = _load()
        data["last_run_end"] = _now_local().isoformat(timespec="seconds")
        _save(data)


def clear_run_end():
    """Borra last_run_end (reinicia el cooldown, usado al solicitar login)."""
    with _LOCK:
        data = _load()
        data.pop("last_run_end", None)
        _save(data)


def can_start_search(now=None):
    """Devuelve (permitido, motivo) según ventana horaria y cooldown.

    Se evalúa al INICIAR una búsqueda; los jobs ya arrancados nunca se
    interrumpen por estos límites. Todo en hora del servidor (TZ).
    """
    now = now if now is not None else _now_local()
    if now.tzinfo is None:
        now = now.astimezone()
    start_hour = config.ALLOWED_START_HOUR
    end_hour = config.ALLOWED_END_HOUR
    hour = now.hour + now.minute / 60 + now.second / 3600
    if not (start_hour <= hour < end_hour):
        return False, (
            f"Fuera del horario permitido para iniciar búsquedas "
            f"({start_hour:02d}:00–{end_hour:02d}:00, hora del servidor)."
        )
    with _LOCK:
        last_end = _parse_dt(_load().get("last_run_end"))
    if last_end is not None:
        ready_at = last_end + timedelta(hours=config.COOLDOWN_HOURS)
        if now < ready_at:
            ready_local = ready_at.astimezone(now.tzinfo)
            return False, (
                "Cooldown entre ejecuciones activo: próxima búsqueda disponible "
                f"a las {ready_local.strftime('%H:%M')} (hora del servidor)."
            )
    return True, ""
