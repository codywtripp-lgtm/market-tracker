"""Thin client for the USDA MARS API and the LMR datamart."""

import datetime as dt
import logging
import os
import time

import requests

from . import config

log = logging.getLogger(__name__)


class USDAError(Exception):
    pass


class Client:
    def __init__(self, api_key=None, session=None):
        self.api_key = api_key if api_key is not None else os.environ.get("MARS_API_KEY", "").strip()
        self.session = session or requests.Session()

    def _get(self, url, params, auth, tries=4):
        last = None
        for attempt in range(tries):
            try:
                r = self.session.get(url, params=params, auth=auth, timeout=300)
            except requests.RequestException as e:
                last = repr(e)
            else:
                if r.status_code == 200:
                    return r.json()
                last = f"HTTP {r.status_code}: {r.text[:200]}"
                if r.status_code in (400, 401, 403, 404):
                    break  # not retryable
            time.sleep(min(60, 5 * 2 ** attempt))
        raise USDAError(f"{url} {params}: {last}")

    @staticmethod
    def _rows(payload):
        if isinstance(payload, dict):
            return payload.get("results", []) or []
        return payload or []

    def _ranged(self, base, section, start, end, auth, date_field, chunk_days):
        rows = []
        s = start
        while s <= end:
            e = min(s + dt.timedelta(days=chunk_days - 1), end)
            q = f"{date_field}={s:%m/%d/%Y}:{e:%m/%d/%Y}"
            rows += self._rows(self._get(f"{base}/{section}", {"q": q}, auth))
            s = e + dt.timedelta(days=1)
        return rows

    def mars(self, slug, section, start, end, chunk_days=31):
        if not self.api_key:
            raise USDAError("MARS_API_KEY is not set")
        return self._ranged(f"{config.MARS}/reports/{slug}", section, start, end,
                            (self.api_key, ""), "report_begin_date", chunk_days)

    def datamart(self, slug, section, start, end, chunk_days=92):
        return self._ranged(f"{config.DATAMART}/reports/{slug}", section, start, end,
                            None, "report_date", chunk_days)
