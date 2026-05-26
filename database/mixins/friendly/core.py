from typing import Any, ClassVar
from weakref import WeakKeyDictionary

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from .schemas import SlugConfig
from .utils import make_unique_slug, slugify, truncate_slug

_attached_sessions = WeakKeyDictionary()

# Global flag to attach event to Session class once
_SLUG_EVENT_ATTACHED_GLOBAL = False


def _slug_table_column(cls, slug_field: str):
    mapper = sa_inspect(cls)
    table = mapper.persist_selectable
    if slug_field not in table.c:
        raise AttributeError(
            f"{cls.__name__} has no column '{slug_field}'. "
            f"Declare it in your model:\n"
            f"    {slug_field}: str | None = Field(default=None, unique=True, index=True)"
        )
    return table.c[slug_field]


def _pk_table_column(cls):
    return sa_inspect(cls).primary_key[0]


def _build_candidate(instance: Any, cfg: SlugConfig) -> str:
    parts = [str(getattr(instance, f, "") or "") for f in cfg.from_fields]
    raw = cfg.separator.join(filter(None, parts))
    slug = slugify(raw, separator=cfg.separator, allow_unicode=cfg.allow_unicode)
    return truncate_slug(slug, cfg.max_length, cfg.separator)


def _resolve_unique(
    instance: Any,
    candidate: str,
    cfg: SlugConfig,
    session: Session,
    claimed: set[str],
) -> str:
    cls = type(instance)
    slug_col = _slug_table_column(cls, cfg.slug_field)
    pk_col = _pk_table_column(cls)

    def exists(slug: str) -> bool:
        if slug in claimed:
            return True
        stmt = select(cls).where(slug_col == slug)
        pk_val = getattr(instance, pk_col.key, None)
        if pk_val is not None:
            stmt = stmt.where(pk_col != pk_val)
        return session.execute(stmt).first() is not None

    result = make_unique_slug(
        candidate,
        exists=exists,
        separator=cfg.separator,
        max_length=cfg.max_length,
    )
    claimed.add(result)
    return result


def _on_before_flush(session: Session, _flush_context: Any, _instances: Any):  # noqa: ARG001
    targets: list = list(session.new)

    for obj in list(session.dirty):
        cfg = getattr(type(obj), "slug_config", None)
        if cfg and cfg.update_on_change:
            targets.append(obj)

    claimed: dict[tuple, set[str]] = {}

    for instance in targets:
        cfg = getattr(type(instance), "slug_config", None)
        if cfg is None:
            continue

        slug_field = cfg.slug_field
        current_slug = getattr(instance, slug_field, None)
        is_new = instance in session.new

        if current_slug and not (cfg.update_on_change and not is_new):
            continue

        candidate = _build_candidate(instance, cfg)
        if not candidate:
            continue

        mapper = sa_inspect(type(instance))
        key = (mapper.persist_selectable.name, slug_field)
        bucket = claimed.setdefault(key, set())

        setattr(
            instance,
            slug_field,
            _resolve_unique(instance, candidate, cfg, session, bucket),
        )


class SluggedMixin:
    """
    Mixin that adds automatic slug generation to any SQLAlchemy or SQLModel mapped class.

    Subclasses MUST:
      1. Assign `slug_config: ClassVar[SlugConfig] = SlugConfig(from_fields=[...])`.
      2. Declare the slug column explicitly (SQLModel Field or SQLAlchemy Column).

    The slug event is NOT attached automatically. You must call
    `attach_slug_events()` at application startup (or `attach_slug_event_to_session`
    per session) to enable slug generation.

    Example:

        from slug_mixin import SluggedMixin, attach_slug_events

        class Post(SluggedMixin, SQLModel, table=True):
            slug_config: ClassVar[SlugConfig] = SlugConfig(from_fields=["title"])

            id: int | None = Field(default=None, primary_key=True)
            title: str
            slug: str | None = Field(default=None, unique=True, index=True)

        # In app startup
        attach_slug_events()
    """

    slug_config: ClassVar[SlugConfig]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        cfg: SlugConfig | None = cls.__dict__.get("slug_config")
        if cfg is None:
            return

        @event.listens_for(cls, "mapper_configured")
        def _mapper_ready(mapper, class_):
            table = mapper.persist_selectable
            if cfg.slug_field not in table.c:
                raise AttributeError(
                    f"{class_.__name__}: slug field '{cfg.slug_field}' not found. "
                    f"Declare it in your model:\n"
                    f"    {cfg.slug_field}: str | None = Field(default=None, unique=True, index=True)"
                )


def attach_slug_events() -> None:
    """
    Attach the slug event handler to SQLAlchemy's Session class once globally.

    Call this at application startup (e.g., in lifespan or main).
    """
    global _SLUG_EVENT_ATTACHED_GLOBAL

    if not _SLUG_EVENT_ATTACHED_GLOBAL:
        event.listen(Session, "before_flush", _on_before_flush)
        _SLUG_EVENT_ATTACHED_GLOBAL = True


def attach_slug_event_to_session(session: AsyncSession | Session) -> None:
    """
    Attach the slug event to the underlying sync session of an AsyncSession.

    Call this right after obtaining the session (e.g., in get_db).
    """

    if isinstance(session, AsyncSession):
        sync_session = session.sync_session
    else:
        sync_session = session

    if sync_session not in _attached_sessions:
        event.listen(sync_session, "before_flush", _on_before_flush)
        _attached_sessions[sync_session] = True
