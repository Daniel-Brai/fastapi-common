from typing import Any

from lib.jobs import BaseJob


class DeliverNotificationJob(BaseJob):
    """
    Deliver Notification Job.

    This job is responsible for delivering notifications to a single recipient via all its transports.
    """

    queue = "notifications"
    max_attempts = 3

    def perform(
        self,
        notification_class: str,
        recipient_type: str,
        recipient_id: str,
        params: dict[str, Any],
    ) -> None:
        """
        Perform the job to deliver the notification.
        """

        async def job_coro() -> None:
            try:
                self.logger.info(
                    f"DeliverNotificationJob: delivering {notification_class} to {recipient_type}#{recipient_id}"
                )

                import importlib

                from sqlalchemy.ext.asyncio import AsyncEngine
                from sqlalchemy.orm import Session

                from lib.notifications.config import get_registry

                module_path, class_name = notification_class.rsplit(".", 1)
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name, None)
                if cls is None:
                    self.logger.error(
                        "DeliverNotificationJob: notification class %r not found. "
                        "Make sure it's imported and registered.",
                        notification_class,
                    )
                    return

                notification = cls.from_params(params)

                notification_registry = get_registry()

                engine = notification_registry.engine
                if engine is None:
                    self.logger.error(
                        "DeliverNotificationJob: no engine — cannot load recipient. "
                        "Pass engine= to configure_notifications()."
                    )
                    return

                recipient_cls = notification_registry.recipient_models.get(recipient_type)
                if recipient_cls is None:
                    self.logger.error(
                        "DeliverNotificationJob: recipient model %r not registered. "
                        "Pass recipient_models= to configure_notifications().",
                        recipient_type,
                    )
                    return

                try:
                    pk = int(recipient_id)
                except ValueError:
                    pk = recipient_id

                sync_engine = engine.sync_engine if isinstance(engine, AsyncEngine) else engine

                with Session(sync_engine) as session:
                    recipient = session.get(recipient_cls, pk)

                if recipient is None:
                    self.logger.warning(f"DeliverNotificationJob: {recipient_type}#{recipient_id} not found — skipping")
                    return

                await notification.deliver(recipient)

                self.logger.info(f"DeliverNotificationJob: delivered {class_name} to {recipient_type}#{recipient_id}")
            except Exception as e:
                self.logger.exception(
                    f"DeliverNotificationJob: failed to deliver {notification_class} to {recipient_type}#{recipient_id} with exception: {e}"
                )
                raise e

        self.run_async(job_coro())
