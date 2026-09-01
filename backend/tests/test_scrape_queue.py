"""
The scrape queue.

The interesting test is the claim: two workers polling the same table both see
the same queued row, and if the claim is a read followed by a write they will
both run it -- two scrapes hitting one store's servers at once, from a system
whose entire scraping stance is to be polite.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.scrape_job import JobStatus, ScrapeJob
from app.models.user import User, UserRole
from app.services import jobs

PASSWORD = "TestPass123"



def make_admin(client, db_session, email="admin@example.com"):
    response = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201
    user = db_session.query(User).filter(User.email == email).first()
    user.role = UserRole.admin
    db_session.commit()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --- Enqueue ----------------------------------------------------------------


class TestEnqueue:
    def test_triggering_a_scrape_creates_a_row_not_a_thread(
        self, client, db_session
    ):
        """
        The whole point. BackgroundTasks left nothing behind, so a run killed
        by a deploy vanished without trace.
        """
        admin = make_admin(client, db_session)
        response = client.post("/admin/scrape", headers=admin)
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "queued"

        job = db_session.query(ScrapeJob).one()
        assert job.status == JobStatus.queued.value
        assert job.requested_by is not None

    def test_the_response_does_not_wait_for_the_scrape(self, client, db_session):
        """A full run is minutes of deliberately spaced requests."""
        admin = make_admin(client, db_session)
        client.post("/admin/scrape", headers=admin)
        job = db_session.query(ScrapeJob).one()
        # Still queued: nothing ran inside the request.
        assert job.status == JobStatus.queued.value
        assert job.started_at is None

    def test_a_single_store_can_be_targeted(self, client, db_session):
        admin = make_admin(client, db_session)
        client.post("/admin/scrape?store=smartbuy", headers=admin)
        assert db_session.query(ScrapeJob).one().store_codes == "smartbuy"

    def test_an_unknown_store_is_rejected_without_queueing(self, client, db_session):
        admin = make_admin(client, db_session)
        assert (
            client.post("/admin/scrape?store=nonsense", headers=admin).status_code
            == 404
        )
        assert db_session.query(ScrapeJob).count() == 0

    @pytest.mark.parametrize("who", ["buyer", "merchant"])
    def test_only_an_admin_can_queue_a_scrape(self, client, db_session, who):
        response = client.post(
            "/auth/register",
            json={
                "email": f"{who}@example.com",
                "password": PASSWORD,
                "account_type": who,
            },
        )
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        assert client.post("/admin/scrape", headers=headers).status_code == 403
        assert db_session.query(ScrapeJob).count() == 0


# --- Claiming ---------------------------------------------------------------


class TestClaiming:
    def test_a_queued_job_is_claimed_once(self, db_session):
        jobs.enqueue(db_session, ["smartbuy"])
        first = jobs.claim_next(db_session)
        second = jobs.claim_next(db_session)

        assert first is not None
        assert second is None, "the same job was handed out twice"
        assert first.status == JobStatus.running.value
        assert first.started_at is not None

    def test_two_workers_cannot_claim_the_same_job(self, db_session):
        """
        The lost-update race. A read-then-write claim lets both workers see
        `queued` and both proceed; the conditional UPDATE lets the database
        decide, and exactly one wins.
        """
        job = jobs.enqueue(db_session, ["smartbuy"])

        # Simulate the loser: another worker already moved the row on.
        db_session.query(ScrapeJob).filter(ScrapeJob.id == job.id).update(
            {ScrapeJob.status: JobStatus.running.value}
        )
        db_session.commit()

        assert jobs.claim_next(db_session) is None

    def test_jobs_are_claimed_oldest_first(self, db_session):
        first = jobs.enqueue(db_session, ["smartbuy"])
        second = jobs.enqueue(db_session, ["igeek"])
        assert jobs.claim_next(db_session).id == first.id
        assert jobs.claim_next(db_session).id == second.id

    def test_an_empty_queue_returns_nothing(self, db_session):
        assert jobs.claim_next(db_session) is None

    def test_a_finished_job_is_never_reclaimed(self, db_session):
        job = jobs.enqueue(db_session)
        claimed = jobs.claim_next(db_session)
        jobs.finish(db_session, claimed, "done")
        assert jobs.claim_next(db_session) is None
        assert job.status == JobStatus.succeeded.value


# --- Surviving a dead process -----------------------------------------------


class TestStaleJobs:
    def test_a_job_abandoned_by_a_killed_process_is_requeued(self, db_session):
        """
        Deploys kill processes routinely, so this is the normal case. Without
        it the row sits in `running` forever and every later worker walks past.
        """
        jobs.enqueue(db_session, ["smartbuy"])
        claimed = jobs.claim_next(db_session)
        claimed.started_at = datetime.now(timezone.utc) - timedelta(
            minutes=jobs.STALE_AFTER_MINUTES + 5
        )
        db_session.commit()

        assert jobs.reclaim_stale(db_session) == 1
        assert jobs.claim_next(db_session) is not None

    def test_a_job_still_running_is_left_alone(self, db_session):
        """A full run is minutes long; requeueing it mid-flight would double it."""
        jobs.enqueue(db_session, ["smartbuy"])
        jobs.claim_next(db_session)
        assert jobs.reclaim_stale(db_session) == 0
        assert jobs.claim_next(db_session) is None


# --- Outcomes are recorded --------------------------------------------------


class TestOutcomes:
    def test_a_failure_is_written_to_the_row(self, db_session):
        """
        A job that died silently is exactly what this queue exists to prevent.
        The admin screen must be able to say why without anyone reading logs.
        """
        jobs.enqueue(db_session)
        job = jobs.claim_next(db_session)
        jobs.fail(db_session, job, "ConnectTimeout: the store did not answer")

        assert job.status == JobStatus.failed.value
        assert "ConnectTimeout" in job.error
        assert job.finished_at is not None

    def test_a_failing_job_does_not_block_the_one_behind_it(self, db_session):
        jobs.enqueue(db_session, ["smartbuy"])
        jobs.enqueue(db_session, ["igeek"])

        first = jobs.claim_next(db_session)
        jobs.fail(db_session, first, "boom")
        second = jobs.claim_next(db_session)

        assert second is not None
        assert second.store_codes == "igeek"

    def test_the_admin_can_read_the_history(self, client, db_session):
        admin = make_admin(client, db_session)
        job = jobs.enqueue(db_session, ["smartbuy"])
        jobs.fail(db_session, jobs.claim_next(db_session), "ConnectTimeout")

        rows = client.get("/admin/scrape-jobs", headers=admin).json()
        assert len(rows) == 1
        assert rows[0]["id"] == job.id
        assert rows[0]["status"] == "failed"
        assert "ConnectTimeout" in rows[0]["error"]

    @pytest.mark.parametrize("who", ["buyer", "merchant"])
    def test_the_history_is_admin_only(self, client, db_session, who):
        response = client.post(
            "/auth/register",
            json={
                "email": f"{who}@example.com",
                "password": PASSWORD,
                "account_type": who,
            },
        )
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        assert client.get("/admin/scrape-jobs", headers=headers).status_code == 403
