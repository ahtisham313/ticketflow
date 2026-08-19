"""Idempotently create the configured support agent."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import async_session_factory, engine
from app.models.user import User, UserRole
from app.services.auth_service import normalize_email

logger = logging.getLogger(__name__)


async def seed_agent() -> None:
    """Create the configured agent unless an account with its email already exists."""

    settings = get_settings()
    email = normalize_email(str(settings.seeded_agent_email))

    async with async_session_factory() as session:
        existing_user_id = await session.scalar(select(User.id).where(User.email == email))
        if existing_user_id is not None:
            logger.info("Seed agent already exists; skipping creation: %s", email)
            return

        agent = User(
            email=email,
            password_hash=hash_password(settings.seeded_agent_password.get_secret_value()),
            role=UserRole.AGENT,
        )
        session.add(agent)

        try:
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            logger.exception("Failed to create seed agent")
            raise

        logger.info("Created seed agent: %s", email)


async def main() -> None:
    """Run the seed operation and release the process database pool."""

    try:
        await seed_agent()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(main())
