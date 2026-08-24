import os
import re
import threading

from flask import Flask, jsonify, render_template, request, send_file

import config
import usage
from excel_writer import export_to_excel
from jobs import JobManager
from scraper.linkedin import (
    AuthWallError,
    CaptchaError,
    LoginRequiredError,
    RestrictionError,
    ScraperError,
    LinkedInScraper,
)

app = Flask(__name__)
jobs = JobManager()
scraper = LinkedInScraper()

_lock = threading.Lock()
LOGIN_STATE = {"running": False, "last_result": None}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/auth/status")
def auth_status():
    return jsonify(
        {
            "logged_in": os.path.exists(config.STORAGE_STATE_PATH),
            "login_running": LOGIN_STATE["running"],
            "last_result": LOGIN_STATE["last_result"],
        }
    )


@app.post("/api/login")
def api_login():
    with _lock:
        if LOGIN_STATE["running"]:
            return jsonify({"ok": True, "running": True})
        LOGIN_STATE["running"] = True
        LOGIN_STATE["last_result"] = None
    threading.Thread(target=_run_login, daemon=True).start()
    return jsonify({"ok": True, "running": True})


def _run_login():
    try:
        result = scraper.login()
        LOGIN_STATE["last_result"] = {"ok": True, "result": result}
    except Exception as error:
        LOGIN_STATE["last_result"] = {"ok": False, "error": str(error)}
    finally:
        LOGIN_STATE["running"] = False


def _normalize_list(value):
    """Acepta una lista JSON o texto separado por coma/;/| (con soporte de
    comillas para valores que contienen coma) y devuelve una lista limpia."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in value]
    else:
        parts, current, quoted = [], [], False
        for char in str(value):
            if char == '"':
                quoted = not quoted
                continue
            if not quoted and char in ",;|\n":
                parts.append("".join(current))
                current = []
            else:
                current.append(char)
        parts.append("".join(current))
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


@app.post("/api/search")
def api_search():
    data = request.get_json(silent=True) or {}
    company = (data.get("company") or "").strip()
    if not company:
        return jsonify({"error": "El nombre de la empresa es obligatorio."}), 400

    # Límites anti-detección: ventana horaria y cooldown entre ejecuciones.
    # Solo aplican al INICIAR; un job en marcha no se interrumpe por ellos.
    allowed, reason = usage.can_start_search()
    if not allowed:
        return jsonify({"error": reason}), 429

    all_pages = bool(data.get("all_pages"))
    if all_pages:
        max_pages = 0
    else:
        try:
            max_pages = int(data.get("max_pages") or config.DEFAULT_MAX_PAGES)
        except (TypeError, ValueError):
            max_pages = config.DEFAULT_MAX_PAGES
        max_pages = max(1, min(max_pages, config.MAX_PAGES_LIMIT))

    # Filtros del nuevo panel: ubicación(es), sector(es) y SIEMPRE la empresa
    # buscada como "Empresa actual" (automática, no la pide el usuario).
    raw_filters = data.get("filters") or {}
    locations = _normalize_list(raw_filters.get("locations"))
    industries = _normalize_list(raw_filters.get("industries"))
    filters = None
    if locations or industries:
        filters = {
            "locations": locations,
            "industries": industries,
            "current_company": company,
        }

    if not os.path.exists(config.STORAGE_STATE_PATH):
        return jsonify({"error": "Necesitas iniciar sesión en LinkedIn primero."}), 401

    daily_budget = usage.remaining_daily_lookups()
    usage.record_run_start()
    job = jobs.create(company, max_pages, all_pages=all_pages, filters=filters)
    threading.Thread(
        target=_run_job,
        kwargs={
            "company": company,
            "max_pages": max_pages,
            "all_pages": all_pages,
            "filters": filters,
            "job_id": job["id"],
            "daily_budget": daily_budget,
        },
        daemon=True,
    ).start()
    return jsonify({"job_id": job["id"]})


def _run_job(company, max_pages, all_pages, filters, job_id, daily_budget=None):
    jobs.update(job_id, status="running", message="Iniciando búsqueda en LinkedIn...")

    def progress(page_no, found, results):
        message = (
            f"Página {page_no} procesada"
            if all_pages
            else f"Página {page_no} de {max_pages} procesada"
        )
        jobs.update(
            job_id,
            current_page=page_no,
            message=message,
        )
        jobs.append_results(job_id, results)

    def on_usage(count):
        # Persiste cada visita a perfil al instante: si el proceso muere,
        # el tope diario ya contabiliza lo visitado.
        try:
            usage.add_profile_lookups(count)
        except Exception:
            pass

    stats = {}
    try:
        rows = scraper.scrape(
            company=company,
            progress=progress,
            max_pages=max_pages,
            filters=filters,
            daily_lookup_budget=daily_budget,
            on_usage=on_usage,
            stats=stats,
        )
        jobs.append_results(job_id, rows)
        notes = []
        if stats.get("cut_by_session"):
            notes.append(
                f"sesión cortada por límite de "
                f"{config.SESSION_MAX_ACTIVE_SECONDS // 60} min de actividad"
            )
        if stats.get("skipped_daily"):
            notes.append(
                f"{stats['skipped_daily']} perfiles sin verificar por tope diario"
            )
        suffix = f" ({'; '.join(notes)})" if notes else ""
        if not rows:
            jobs.update(
                job_id, status="done", message="No se encontraron empleados." + suffix
            )
            return
        filepath, filename = export_to_excel(rows, company=company)
        jobs.update(
            job_id,
            status="done",
            message=(
                f"Scraping completado. {len(rows)} empleados encontrados." + suffix
            ),
            filepath=filepath,
            filename=filename,
        )
    except RestrictionError as error:
        jobs.update(
            job_id,
            status="error",
            error=f"LinkedIn señalizó una restricción de uso: {error}",
        )
    except LoginRequiredError:
        jobs.update(
            job_id,
            status="needs_login",
            error="La sesión de LinkedIn caducó. Inicia sesión de nuevo.",
        )
    except (AuthWallError, CaptchaError) as error:
        jobs.update(
            job_id,
            status="error",
            error=f"LinkedIn bloqueó la automatización: {error}",
        )
    except ScraperError as error:
        jobs.update(job_id, status="error", error=str(error))
    except Exception as error:
        jobs.update(
            job_id, status="error", error=f"Error inesperado: {error}"
        )
    finally:
        usage.record_run_end()


@app.get("/api/jobs/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job no encontrado."}), 404
    return jsonify(job)


@app.get("/api/jobs/<job_id>/download")
def job_download(job_id):
    job = jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job no encontrado."}), 404
    if job.get("status") != "done" or not job.get("filepath"):
        return jsonify({"error": "No hay archivo disponible para descargar."}), 400
    return send_file(
        job["filepath"], as_attachment=True, download_name=job["filename"]
    )


if __name__ == "__main__":
    print("LinkedIn Employee Scraper -> http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)