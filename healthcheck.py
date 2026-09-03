import logging
import os
import threading
import time
from contextlib import contextmanager

import requests

from config import MAX_PING_RETRIES

logger = logging.getLogger('snuphya')

HEARTBEAT_INTERVAL_SECONDS = 180
HEARTBEAT_MAX_SECONDS = 1800
HEARTBEAT_PING_TIMEOUT = (5, 10)
HEARTBEAT_JOIN_TIMEOUT = 30

# Shared by every heartbeat in this process so retried logins cannot each claim
# a fresh HEARTBEAT_MAX_SECONDS allowance.
_budget_lock = threading.Lock()
_budget_remaining = HEARTBEAT_MAX_SECONDS


def _url(suffix=''):
    base = os.getenv('HEALTHCHECK_SNUPHYA')
    if not base:
        return None
    return base + suffix


def ping(url, message, retries=MAX_PING_RETRIES, timeout=10):
    if not url:
        logger.info('HEALTHCHECK_SNUPHYA is not set, skipping ping')
        return False
    for attempt in range(1, retries + 1):
        try:
            requests.get(url, data=message.encode('utf-8'), timeout=timeout)
            return True
        except requests.RequestException as e:
            logger.info(f"Ping failed (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(attempt)
    logger.info("All retry attempts exhausted")
    return False


def ping_start(message):
    return ping(_url('/start'), message)


def ping_success(message):
    return ping(_url(), message)


def ping_fail(message):
    return ping(_url('/fail'), message)


@contextmanager
def heartbeat(message):
    """Keep the healthcheck up while a slow operation runs.

    Pings the success endpoint immediately and then every
    HEARTBEAT_INTERVAL_SECONDS. The total time any number of heartbeats may
    cover in one process is capped at HEARTBEAT_MAX_SECONDS, so a wedged
    operation still surfaces as down.

    A success ping closes the run that main.py opened with /start, so
    healthchecks.io records the login as several short runs instead of one long
    one. The elapsed minutes ride along in the ping body to keep that visible.
    """
    global _budget_remaining

    url = _url()
    with _budget_lock:
        allowance = _budget_remaining
    if url is None:
        yield
        return
    if allowance <= 0:
        logger.info('healthcheck heartbeat budget for this run is used up, not pinging')
        yield
        return

    stop = threading.Event()
    started = time.monotonic()

    def loop():
        deadline = started + allowance
        while not stop.is_set() and time.monotonic() < deadline:
            elapsed = int(time.monotonic() - started) // 60
            try:
                ping(url, f'{message} ({elapsed} min elapsed)', retries=1,
                     timeout=HEARTBEAT_PING_TIMEOUT)
            except Exception as e:
                logger.warning(f'healthcheck heartbeat ping raised: {e}')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if stop.wait(min(HEARTBEAT_INTERVAL_SECONDS, remaining)):
                return
        if not stop.is_set():
            logger.info('healthcheck heartbeat used up its allowance, stopping')

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=HEARTBEAT_JOIN_TIMEOUT)
        if thread.is_alive():
            logger.warning('healthcheck heartbeat thread did not stop in time')
        with _budget_lock:
            _budget_remaining = max(0.0, _budget_remaining - (time.monotonic() - started))
