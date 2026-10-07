"""Bounded background enrichment for the single-process Gunicorn deployment.

Only derived information runs here. The listing and basic score are committed
before enqueueing. Restarted jobs may be retried with the refresh action.
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from db_helper import query_one
from services.scoring import score_listing
from scrapers.machimusubi import get_station_review

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rental-enrichment")
_lock = threading.Lock()
_jobs = {}
_rerun = set()
MAX_PENDING = 32


def _run(listing_id):
    while True:
        state = "complete"
        try:
            score_listing(listing_id)
            row = query_one("SELECT nearest_station FROM rental_listings WHERE id=? AND is_active=1", (listing_id,))
            if row and row["nearest_station"]:
                get_station_review(row["nearest_station"], retries=0)
        except Exception:
            logging.getLogger(__name__).exception("Enrichment failed for listing %s", listing_id)
            state = "failed"
        with _lock:
            if listing_id in _rerun:
                _rerun.remove(listing_id)
                continue
            _jobs[listing_id] = state
            return


def enqueue(listing_id):
    with _lock:
        if _jobs.get(listing_id) == "pending":
            # A refresh or preference change happened during the previous pass.
            # Coalesce repeated requests, but always process the latest inputs.
            _rerun.add(listing_id)
            return "pending"
        if sum(s == "pending" for s in _jobs.values()) >= MAX_PENDING:
            return "deferred"
        for key in list(_jobs):
            if len(_jobs) < 128:
                break
            if _jobs[key] != "pending":
                del _jobs[key]
        _jobs[listing_id] = "pending"
        _executor.submit(_run, listing_id)
    return "pending"


def status(listing_id):
    with _lock:
        return _jobs.get(listing_id, "idle")
