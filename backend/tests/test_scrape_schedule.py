"""
Prices that refresh themselves.

WHY THIS EXISTS. Production had no scheduled scrape. Prices moved only when an
admin pressed "scrape" -- which nobody had done since the site went live, so
the newest price on the site was nineteen days old. The GitHub Actions cron
meant to do it could never reach production Postgres and was deleted. The
worker now queues a full run itself (jobs.enqueue_if_due), and a run no longer
ends at the prices: alerts are sent and cached pages are retired.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import fakeredis
import pytest

from app.models.scrape_job import JobStatus, ScrapeJob
from app.models.user import User, UserRole
from app.services import cache, jobs, worker

PASSWORD = "TestPass123"

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def full_run(db_session, *, hours_ago, status=JobStatus.succeeded.value, codes=""):
    job = ScrapeJob(
        status=status,
        store_codes=codes,
        created_at=NOW - timedelta(hours=hours_ago),
    )
    db_session.add(job)
    db_session.commit()
    return job


def make_admin(client, db_session, email="admin@example.com"):
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    user = db_session.query(User).filter(User.email == email).first()
    user.role = UserRole.admin
    db_session.commit()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def queued(db_session):
    return (
        db_session.query(ScrapeJob)
        .filter(ScrapeJob.status == JobStatus.queued.value)
        .all()
    )


# --- When a run is due ------------------------------------------------------


class TestWhenARunIsDue:
    def test_a_site_that_has_never_scraped_scrapes_now(self, db_session):
        job = jobs.enqueue_if_due(db_session, 6, now=NOW)
        assert job is not None
        assert job.store_codes == ""
        assert job.requested_by is None, "a scheduled run is nobody's request"

    def test_not_again_within_the_interval(self, db_session):
        full_run(db_session, hours_ago=5)
        assert jobs.enqueue_if_due(db_session, 6, now=NOW) is None
        assert queued(db_session) == []

    def test_again_once_the_interval_has_passed(self, db_session):
        full_run(db_session, hours_ago=7)
        assert jobs.enqueue_if_due(db_session, 6, now=NOW) is not None

    def test_a_failed_run_waits_the_interval_too(self, db_session):
        """Otherwise a store that is down would be asked again every poll."""
        full_run(db_session, hours_ago=1, status=JobStatus.failed.value)
        assert jobs.enqueue_if_due(db_session, 6, now=NOW) is None

    def test_an_admins_scrape_all_resets_the_clock(self, client, db_session):
        """
        Through the real endpoint. It used to store "every store" as the list
        of codes, which the schedule read as a partial run -- so the worker
        scraped everything again the moment the admin's run finished. A test
        that built the row by hand with empty codes could not see it.
        """
        full_run(db_session, hours_ago=30)
        admin = make_admin(client, db_session)
        assert client.post("/admin/scrape", headers=admin).status_code == 202

        job = jobs.claim_next(db_session)
        assert job.store_codes == "", "an admin's full run must look like one"
        jobs.finish(db_session, job, "done")
        job.created_at = NOW - timedelta(minutes=5)
        db_session.commit()

        assert jobs.enqueue_if_due(db_session, 6, now=NOW) is None

    def test_an_admin_cannot_stack_a_second_full_run(self, client, db_session):
        admin = make_admin(client, db_session)
        assert client.post("/admin/scrape", headers=admin).status_code == 202

        second = client.post("/admin/scrape", headers=admin)
        assert second.status_code == 409
        assert "already queued" in second.json()["detail"]
        assert len(queued(db_session)) == 1

    def test_one_store_runs_can_still_queue_side_by_side(self, client, db_session):
        admin = make_admin(client, db_session)
        assert client.post("/admin/scrape?store=smartbuy", headers=admin).status_code == 202
        assert client.post("/admin/scrape?store=igeek", headers=admin).status_code == 202
        assert client.post("/admin/scrape", headers=admin).status_code == 202

    def test_a_one_store_run_does_not_reset_the_clock(self, db_session):
        """The other stores are still stale."""
        full_run(db_session, hours_ago=7)
        full_run(db_session, hours_ago=1, codes="smartbuy")
        assert jobs.enqueue_if_due(db_session, 6, now=NOW) is not None

    @pytest.mark.parametrize("status", [JobStatus.queued.value, JobStatus.running.value])
    def test_nothing_is_stacked_behind_a_pending_job(self, db_session, status):
        full_run(db_session, hours_ago=30, status=status, codes="igeek")
        assert jobs.enqueue_if_due(db_session, 6, now=NOW) is None

    @pytest.mark.parametrize("interval", [0, -1])
    def test_an_interval_of_zero_turns_it_off(self, db_session, interval):
        assert jobs.enqueue_if_due(db_session, interval, now=NOW) is None
        assert db_session.query(ScrapeJob).count() == 0

    def test_the_schedule_is_off_unless_configured(self):
        """A developer's local worker must not start scraping real stores."""
        from app.config import Settings

        assert Settings.model_fields["scrape_interval_hours"].default == 0


class TestTwoWorkersScheduling:
    """
    Both workers can pass the checks before either inserts. The database
    allows one full run queued or running, so the second insert is refused.
    """

    def _rival_inserts_between_check_and_insert(self, monkeypatch, rival_status):
        real_enqueue = jobs.enqueue

        def enqueue_after_rival(db, *args, **kwargs):
            db.add(ScrapeJob(status=rival_status, store_codes=""))
            db.commit()
            return real_enqueue(db, *args, **kwargs)

        monkeypatch.setattr(jobs, "enqueue", enqueue_after_rival)

    @pytest.mark.parametrize("rival", [JobStatus.queued.value, JobStatus.running.value])
    def test_the_second_insert_is_refused(self, db_session, monkeypatch, rival):
        self._rival_inserts_between_check_and_insert(monkeypatch, rival)

        assert jobs.enqueue_if_due(db_session, 6, now=NOW) is None
        pending = (
            db_session.query(ScrapeJob)
            .filter(ScrapeJob.status.in_([JobStatus.queued.value, JobStatus.running.value]))
            .count()
        )
        assert pending == 1, "two full runs pending at once"

    def test_the_session_is_usable_after_losing(self, db_session, monkeypatch):
        self._rival_inserts_between_check_and_insert(monkeypatch, JobStatus.queued.value)
        jobs.enqueue_if_due(db_session, 6, now=NOW)
        # A refused INSERT leaves the transaction aborted unless rolled back.
        assert db_session.query(ScrapeJob).count() == 1

    def test_finished_full_runs_do_not_count(self, db_session):
        for hours in (40, 30, 20):
            full_run(db_session, hours_ago=hours)
        full_run(db_session, hours_ago=10, status=JobStatus.failed.value)
        assert jobs.enqueue_if_due(db_session, 6, now=NOW) is not None


# --- What a run does --------------------------------------------------------


@dataclass
class FakeStore:
    code: str
    name: str


STORES = (FakeStore("up", "Up Store"), FakeStore("down", "Down Store"))


@pytest.fixture
def run(db_session, monkeypatch):
    """A job runner with the network, the mail and Redis replaced."""
    calls = {"stores": [], "alerts": 0, "bumps": 0}
    broken, empty = set(), set()

    def run_store(self, config):
        calls["stores"].append(config.code)
        if config.code in broken:
            raise ConnectionError(f"{config.name} did not answer")
        return {"store": config.name, "seen": 0 if config.code in empty else 3}

    def process_alerts(db):
        calls["alerts"] += 1
        return {"checked": 1, "notified": 1}

    def bump():
        calls["bumps"] += 1

    monkeypatch.setattr("app.services.scrapers.STORES", STORES)
    monkeypatch.setattr("app.services.ingest.IngestService.run_store", run_store)
    monkeypatch.setattr("app.services.notifications.process_alerts", process_alerts)
    monkeypatch.setattr("app.services.cache.bump_catalogue_version_sync", bump)

    def go(*down, silent=()):
        broken.update(down)
        empty.update(silent)
        jobs.enqueue(db_session)
        job = jobs.claim_next(db_session)
        jobs.run_job(db_session, job)
        db_session.refresh(job)
        return job

    go.calls = calls
    return go


class TestWhatARunDoes:
    def test_one_store_down_does_not_fail_the_others(self, run):
        job = run("down")

        assert run.calls["stores"] == ["up", "down"]
        assert job.status == JobStatus.succeeded.value
        assert "Up Store" in job.result
        assert "FAILED Down Store: ConnectionError" in job.result

    def test_a_store_that_fails_first_does_not_stop_the_ones_after_it(
        self, run, monkeypatch
    ):
        monkeypatch.setattr("app.services.scrapers.STORES", tuple(reversed(STORES)))
        job = run("down")

        assert run.calls["stores"] == ["down", "up"]
        assert job.status == JobStatus.succeeded.value

    def test_a_store_that_returns_nothing_is_a_failure(self, run):
        """
        The scraper stops quietly on a 403, a 429 or a robots refusal. Counted
        as a success, a store blocking the bot would read "succeeded" forever.
        """
        job = run(silent=("down",))
        assert "FAILED Down Store: returned no listings" in job.result

    def test_every_store_silent_is_a_failed_job(self, run):
        job = run(silent=("up", "down"))
        assert job.status == JobStatus.failed.value

    def test_every_store_down_is_a_failed_job(self, run):
        job = run("up", "down")

        assert job.status == JobStatus.failed.value
        assert "Up Store" in job.error and "Down Store" in job.error
        assert run.calls["alerts"] == 0

    def test_cached_pages_are_retired_even_when_every_store_failed(self, run):
        """Listings commit one at a time: a store failing on page 2 changed page 1."""
        run("up", "down")
        assert run.calls["bumps"] == 1

    def test_price_alerts_are_sent_after_a_clean_run(self, run):
        job = run()
        assert run.calls["alerts"] == 1
        assert "alerts:" in job.result

    @pytest.mark.parametrize("how", ["raised", "silent"])
    def test_no_alerts_while_any_store_failed(self, run, how):
        """
        A failed store keeps its old prices in the comparison. An email saying
        the price dropped must not rest on a figure nobody re-checked.
        """
        job = run("down") if how == "raised" else run(silent=("down",))
        assert run.calls["alerts"] == 0
        assert "alerts skipped" in job.result

    def test_cached_pages_are_retired_after_the_prices(self, run):
        run()
        assert run.calls["bumps"] == 1

    def test_an_alert_failure_keeps_the_prices_and_says_so(self, run, monkeypatch):
        def broken_alerts(db):
            raise RuntimeError("smtp down")

        monkeypatch.setattr("app.services.notifications.process_alerts", broken_alerts)
        job = run()

        assert job.status == JobStatus.succeeded.value
        assert "FAILED alerts: RuntimeError" in job.result
        assert run.calls["bumps"] == 1


class TestStoppedMidRun:
    """Docker stops the worker with SIGTERM on every deploy."""

    def _borrowed(self, db_session):
        class Borrowed:
            def __getattr__(self, name):
                return getattr(db_session, name)

            def close(self):
                pass

        return Borrowed

    def test_the_job_goes_back_in_the_queue(self, db_session, monkeypatch):
        monkeypatch.setattr(worker, "SessionLocal", self._borrowed(db_session))

        def stopped(db, job):
            raise SystemExit(0)

        monkeypatch.setattr(jobs, "run_job", stopped)
        job = jobs.enqueue(db_session)

        with pytest.raises(SystemExit):
            worker.drain()

        db_session.refresh(job)
        assert job.status == JobStatus.queued.value
        assert job.started_at is None

    def test_a_finished_job_is_never_requeued(self, db_session):
        job = jobs.enqueue(db_session)
        jobs.finish(db_session, jobs.claim_next(db_session), "done")
        assert jobs.requeue(db_session, job.id) is False
        db_session.refresh(job)
        assert job.status == JobStatus.succeeded.value

    def test_sigterm_becomes_a_clean_exit(self):
        with pytest.raises(SystemExit):
            worker._stop(15, None)


# --- The worker loop --------------------------------------------------------


class TestWorkerLoop:
    def test_a_tick_schedules_before_it_drains(self, monkeypatch):
        """So a due run starts in this pass, not one poll later."""
        order = []
        monkeypatch.setattr(worker, "schedule", lambda hours: order.append(("schedule", hours)))
        monkeypatch.setattr(worker, "drain", lambda: order.append(("drain",)) or 0)

        worker.tick(6)
        assert order == [("schedule", 6), ("drain",)]

    def test_schedule_off_never_opens_the_database(self, monkeypatch):
        def no_session():
            raise AssertionError("opened a session with the schedule off")

        monkeypatch.setattr(worker, "SessionLocal", no_session)
        assert worker.schedule(0) is False

    def test_schedule_queues_through_the_real_check(self, db_session, monkeypatch):
        class Borrowed:
            """The test's session, without closing it on the test."""

            def __getattr__(self, name):
                return getattr(db_session, name)

            def close(self):
                pass

        monkeypatch.setattr(worker, "SessionLocal", Borrowed)
        assert worker.schedule(6) is True
        assert worker.schedule(6) is False, "queued twice in one interval"


# --- Retiring cached pages without an event loop ----------------------------


class TestSyncBump:
    def test_it_increments_the_catalogue_version(self, monkeypatch):
        server = fakeredis.FakeServer()
        monkeypatch.setattr(
            "redis.Redis.from_url",
            lambda *a, **k: fakeredis.FakeRedis(server=server),
        )

        cache.bump_catalogue_version_sync()
        cache.bump_catalogue_version_sync()

        assert fakeredis.FakeRedis(server=server).get(cache.VERSION_KEY) == b"2"

    def test_an_unreachable_redis_is_not_a_failed_scrape(self, monkeypatch):
        def unreachable(*a, **k):
            raise ConnectionError("no redis")

        monkeypatch.setattr("redis.Redis.from_url", unreachable)
        cache.bump_catalogue_version_sync()  # must not raise
