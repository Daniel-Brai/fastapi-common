from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import and_, col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from lib.logger import get_logger
from lib.notifications.exceptions import (
    PushSubscriptionAlreadyExistsError,
    PushSubscriptionError,
    PushSubscriptionNotFoundError,
)
from lib.notifications.models import PushSubscription

logger = get_logger("lib.notifications.services.push_subscription")


class PushSubscriptionService:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(
        self,
        *,
        user_id: Any,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> PushSubscription:
        """
        Register a new push subscription for a user device.

        If the endpoint already exists for this user, upsert the keys (the browser may rotate keys on re-subscription).

        Args:
            user_id (Any): The ID of the user who owns the subscription.
            endpoint (str): The unique endpoint URL provided by the push service.

        Returns:
            PushSubscription: The newly created or updated PushSubscription object.

        Raises:
            PushSubscriptionAlreadyExistsError: If the endpoint is already registered to a different user.
            PushSubscriptionError: If there was an error during registration.
        """

        existing = await self._get_by_endpoint(endpoint)

        user_id_str = str(user_id)

        if existing is not None:
            if existing.user_id != user_id_str:
                raise PushSubscriptionAlreadyExistsError("Endpoint already registered to a different user.")

            existing.p256dh = p256dh
            existing.auth = auth
            existing.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            return existing

        subscription = PushSubscription(  # type: ignore
            user_id=user_id_str,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        )
        self._session.add(subscription)

        try:
            await self._session.flush()
        except IntegrityError as e:
            await self._session.rollback()
            logger.error("Failed to register push subscription, possible duplicate endpoint", exc_info=True)
            raise PushSubscriptionAlreadyExistsError("Endpoint already registered.") from e

        return subscription

    async def unregister(
        self,
        *,
        user_id: Any,
        endpoint: str,
    ) -> None:
        """
        Remove a specific push subscription by endpoint.


        Args:
            user_id (Any): The ID of the user who owns the subscription.
            endpoint (str): The unique endpoint URL of the push subscription to remove.

        Raises:
            PushSubscriptionNotFoundError: If no subscription with the given endpoint exists for the user.
        """

        try:
            subscription = await self._get_by_endpoint(endpoint)

            user_id_str = str(user_id)

            if subscription is None or subscription.user_id != user_id_str:
                raise PushSubscriptionNotFoundError("No push subscription found for this endpoint.")

            await self._session.delete(subscription)
            await self._session.flush()
        except SQLAlchemyError as e:
            await self._session.rollback()
            logger.error("Failed to unregister push subscription", exc_info=True)
            raise PushSubscriptionError("Failed to unregister push subscription") from e

    async def unregister_all(self, *, user_id: Any) -> int:
        """
        Remove all push subscriptions for a user (e.g. on account deletion or when the user explicitly revokes push permission globally).

        Args:
            user_id (Any): The ID of the user whose subscriptions should be removed.

        Returns:
            int: The number of subscriptions that were deleted.
        """

        try:
            result = await self._session.exec(
                delete(PushSubscription).where(col(PushSubscription.user_id) == str(user_id))
            )
            await self._session.flush()
            return result.rowcount
        except SQLAlchemyError as e:
            await self._session.rollback()
            logger.error("Failed to unregister all push subscriptions", exc_info=True)
            raise PushSubscriptionError("Failed to unregister all push subscriptions") from e

    async def prune_expired(
        self,
        *,
        user_id: Any,
        endpoints: list[str],
    ) -> int:
        """
        Delete subscriptions whose endpoints returned 410 Gone from the push service.

        Args:
            user_id (Any): The ID of the user whose subscriptions should be pruned.
            endpoints (list[str]): A list of endpoint URLs that have been identified as expired.

        Returns:
            int: The number of subscriptions that were deleted.
        """

        if not endpoints:
            return 0

        try:
            result = await self._session.exec(
                delete(PushSubscription).where(
                    and_(
                        col(PushSubscription.user_id) == str(user_id),
                        col(PushSubscription.endpoint).in_(endpoints),
                    )
                )
            )
            await self._session.flush()
            await self._session.commit()
            return result.rowcount
        except SQLAlchemyError as e:
            await self._session.rollback()
            logger.error("Failed to prune expired push subscriptions", exc_info=True)
            raise PushSubscriptionError("Failed to prune expired push subscriptions") from e

    async def get_for_user(self, user_id: Any) -> list[PushSubscription]:
        """
        Load all active push subscriptions for a user.

        Args:
            user_id (Any): The ID of the user whose subscriptions should be retrieved.

        Returns:
            list[PushSubscription]: A list of PushSubscription objects representing the user's active subscriptions, ordered
        """

        try:
            result = await self._session.exec(
                select(PushSubscription)
                .where(PushSubscription.user_id == str(user_id))
                .order_by(col(PushSubscription.created_at).asc())
            )
            return list(result.all())
        except SQLAlchemyError as e:
            logger.error("Failed to retrieve push subscriptions for user", exc_info=True)
            raise PushSubscriptionError("Failed to retrieve push subscriptions for user") from e

    async def get_by_id(
        self,
        *,
        user_id: Any,
        subscription_id: str,
    ) -> PushSubscription:
        """
        Fetch a single subscription, scoped to the owning user.

        Args:
            user_id (Any): The ID of the user who owns the subscription.
            subscription_id (str): The ID of the subscription to retrieve.

        Returns:
            PushSubscription: The subscription matching the given ID and user.
        """

        result = await self._session.exec(
            select(PushSubscription).where(
                and_(
                    col(PushSubscription.id) == subscription_id,
                    col(PushSubscription.user_id) == str(user_id),
                )
            )
        )
        subscription = result.one_or_none()
        if subscription is None:
            raise PushSubscriptionNotFoundError(f"Push subscription {subscription_id} not found.")

        return subscription

    async def list_all_endpoints(self, user_id: Any) -> list[str]:
        """
        Retrieve a list of all push subscription endpoints for a user.

        Args:
            user_id (Any): The ID of the user whose subscription endpoints should be listed.

        Returns:
            list[str]: A list of endpoint URLs for the user's active push subscriptions.
        """

        result = await self._session.exec(
            select(PushSubscription.endpoint).where(col(PushSubscription.user_id) == str(user_id))
        )
        return list(result.all())

    async def _get_by_endpoint(self, endpoint: str) -> PushSubscription | None:
        result = await self._session.exec(select(PushSubscription).where(col(PushSubscription.endpoint) == endpoint))
        return result.one_or_none()
