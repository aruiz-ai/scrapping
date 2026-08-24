import threading
import time
import uuid


class JobManager:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def create(self, company, max_pages, all_pages=False, filters=None):
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "company": company,
            "max_pages": max_pages,
            "all_pages": all_pages,
            "filters": dict(filters or {}),
            "status": "pending",
            "message": "",
            "current_page": 0,
            "found": 0,
            "results": [],
            "filename": None,
            "filepath": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {
                key: (list(value) if key == "results" else value)
                for key, value in job.items()
            }

    def update(self, job_id, **kwargs):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.update(kwargs)
                job["updated_at"] = time.time()

    def append_results(self, job_id, new_results):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            seen = {row.get("url") or (row.get("name") + "|" + row.get("role")) for row in job["results"]}
            for row in new_results:
                key = row.get("url") or (row.get("name") + "|" + row.get("role"))
                if key and key not in seen:
                    job["results"].append(row)
                    seen.add(key)
            job["found"] = len(job["results"])
            job["updated_at"] = time.time()