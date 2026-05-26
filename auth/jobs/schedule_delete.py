from datetime import datetime, timedelta, timezone

from lib.jobs import BaseJob, interval


class ScheduleAccountDeletionJob(BaseJob):
    """
    Schedule Account Deletion Job.

    This job is to schedule account deletion for users marked as deleted.

    The behavior of this job depends on the `deletion_style` option in `AuthOptions`:
    - If `deletion_style` is "soft", the job will look for users that have been soft-deleted and check if their deletion date has passed the grace period before permanently deleting them.

    It only applies to users that have been marked as deleted, and it will not affect active users. This allows for a grace period during which users can recover their accounts if they were deleted by mistake.
    """

    queue = "default"
    schedule = interval(hours=24)
    max_retries = 3

    def perform(self):
        """
        Perform the job to schedule account deletion.
        """

        async def job_coro() -> None:
            try:
                from sqlmodel import select

                from lib.auth.backends import JWTBackend, SessionBackend
                from lib.auth.config import get_backend, get_options, get_user_model
                from lib.auth.helpers import db_session
                from lib.auth.models import RefreshToken, Session

                options = get_options()
                if options.deletion_style != "soft":
                    return

                user_model = get_user_model()
                now = datetime.now(tz=timezone.utc)
                grace_period = timedelta(days=options.deletion_grace_period_days)

                backend = get_backend()

                async with db_session() as s:
                    stmt = select(user_model).where(user_model.is_active == False)
                    users_to_delete = []

                    for user in s.exec(stmt).all():
                        if user.updated_at:
                            updated_at_aware = user.updated_at
                            if updated_at_aware.tzinfo is None:
                                updated_at_aware = updated_at_aware.replace(tzinfo=timezone.utc)

                            if updated_at_aware + grace_period <= now:
                                users_to_delete.append(user)

                    for user in users_to_delete:
                        self.logger.info(f"ScheduleAccountDeletionJob: Hard deleting user {user.id} after grace period")

                        if isinstance(backend, JWTBackend):
                            s.exec(select(RefreshToken).where(RefreshToken.user_id == user.id))
                            for t in s.exec(select(RefreshToken).where(RefreshToken.user_id == user.id)).all():
                                s.delete(t)

                        elif isinstance(backend, SessionBackend):
                            for sess in s.exec(select(Session).where(Session.user_id == user.id)).all():
                                s.delete(sess)

                        s.delete(user)

                    s.commit()
            except Exception as e:
                self.logger.error(f"ScheduleAccountDeletionJob: failed due to error {str(e)}")
                raise e

        self.run_async(job_coro())
