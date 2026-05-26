from lib.jobs import BaseJob, cron


class SweepAuthJob(BaseJob):
    """
    Nightly sweep of all auth-related expired records:
        • auth_sessions            (SessionBackend)
        • auth_refresh_tokens      (JWTBackend)
        • auth_one_time_tokens     (password reset, email verify, magic link)

    Logs a summary of how many rows were pruned per table.

    Configuration:
        queue: "maintenance"
        max_attempts: 2
        schedule: "0 3 * * *" (03:00 UTC daily)
        discard_on_success: False (keep job history even on success, for auditing)
    """

    queue = "maintenance"
    max_attempts = 2
    schedule = cron("0 3 * * *")  # 03:00 UTC daily
    discard_on_success = False

    def perform(self) -> None:
        try:
            self.logger.info("SweepAuthJob: starting auth sweep")

            from lib.auth.backends import JWTBackend, SessionBackend
            from lib.auth.config import get_backend
            from lib.auth.helpers import sweep_tokens

            backend = get_backend()

            ott_deleted = self.run_async(sweep_tokens())
            self.logger.info(f"SweepAuthJob: pruned {ott_deleted} one-time token(s)")

            if isinstance(backend, SessionBackend):
                sess_deleted = self.run_async(backend.sweep())
                self.logger.info(f"SweepAuthJob: pruned {sess_deleted} session(s)")

            elif isinstance(backend, JWTBackend):
                tok_deleted = self.run_async(backend.sweep())
                self.logger.info(f"SweepAuthJob: pruned {tok_deleted} refresh token(s)")

            self.logger.info("SweepAuthJob: completed successfully")
        except Exception as e:
            self.logger.exception(f"SweepAuthJob: failed with exception: {e}")
            raise e
