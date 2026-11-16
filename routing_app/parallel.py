"""Bounded local CPU workers. Road requests and fleet ownership stay coordinated."""
from concurrent.futures import ProcessPoolExecutor, TimeoutError
from contextlib import contextmanager
from itertools import islice
import multiprocessing
import os

from .optimizer import load_plan, solve_section


def worker_count(requested):
    return max(1, min(int(requested), 4, max(1, (os.cpu_count() or 1) - 1)))


@contextmanager
def workers(requested):
    count = worker_count(requested)
    pool = (ProcessPoolExecutor(max_workers=count,
            mp_context=multiprocessing.get_context('spawn')) if count > 1 else None)
    if pool:
        pool.routing_queue_limit = 2 * count
    try:
        yield pool
    finally:
        if pool:
            pool.shutdown(wait=True, cancel_futures=True)


def bounded_map(pool, function, tasks, checkpoint=lambda: None):
    """Keep at most two tasks per worker queued; preserve deterministic order.

    Check cancellation while workers run. No HTTP session, SQLite connection,
    browser, geographic cut or partial fleet is handed to a worker.
    """
    if pool is None:
        for task in tasks:
            checkpoint()
            yield function(task)
        return
    iterator = iter(tasks)
    pending = []
    try:
        while True:
            pending = [pool.submit(function, task) for task in
                       islice(iterator, pool.routing_queue_limit)]
            if not pending:
                break
            for future in pending:
                while True:
                    checkpoint()
                    try:
                        yield future.result(timeout=.5)
                        break
                    except TimeoutError:
                        if future.done():
                            raise
                        continue
    finally:
        for future in pending:
            future.cancel()


def section_job(task):
    matrix, incoming, outgoing, seconds = task
    return solve_section(matrix, incoming, outgoing, seconds)


def load_job(task):
    """Pure complete-route load evaluation; no independent truck assignment."""
    sequence, internal, joins, dispatch, to_rf, from_rf, return_time, cfg, stream = task
    return load_plan(sequence, internal, joins, dispatch, to_rf, from_rf,
                     return_time, cfg, stream)


def territory_job(task):
    token, alternatives = task
    candidates = []
    for metadata, arguments in alternatives:
        plan = load_job(arguments)
        if plan:
            candidates.append({**metadata, 'plan': plan})
    return token, candidates
