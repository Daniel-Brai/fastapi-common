from lib.jobs import BaseJob, cron


class SweepAuditJob(BaseJob):
    """
    Sweep Audit Job.

    This job is responsible for nightly sweep of audit records older than rentention days.
    """

    queue = "maintenance"
    max_attempts = 2
    schedule = cron("0 2 * * *")  # 02:00 UTC daily

    def perform(self) -> None:
        """
        Perform the audit sweep
        """

        async def job_coro() -> None:
            try:
                self.logger.info("SweepAuditJob: starting audit sweep")

                from datetime import datetime, timedelta

                from sqlmodel import Session, select

                from lib.audit.config import get_registry, get_rentention_days
                from lib.audit.models import Audit

                registry = get_registry()

                if not registry.is_configured:
                    self.logger.warning("SweepAuditJob: audit registry not configured, skipping")
                    return

                engine = registry.get_sync_engine()
                if engine is None:
                    self.logger.warning("SweepAuditJob: no engine configured, skipping")
                    return

                retain_days = get_rentention_days()

                cutoff = datetime.now() - timedelta(days=retain_days)

                with Session(engine) as s:
                    old = s.exec(select(Audit).where(Audit.created_at < cutoff)).all()
                    count = len(old)
                    for rec in old:
                        s.delete(rec)

                    s.commit()

                self.logger.info(f"SweepAuditJob: deleted {count} audit record(s) older than {retain_days} days")
            except Exception as e:
                self.logger.exception(f"SweepAuditJob: failed with exception: {e}")
                raise e

        self.run_async(job_coro())
