from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria

from app.core.config import get_settings
from app.db.base import Base

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


@event.listens_for(Session, "do_orm_execute")
def apply_shop_scope(execute_state) -> None:
    shop_id = execute_state.session.info.get("shop_id")
    if not shop_id or not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        return
    scoped_models = [
        mapper.class_
        for mapper in Base.registry.mappers
        if "shop_id" in mapper.attrs
    ]
    execute_state.statement = execute_state.statement.options(*(
        with_loader_criteria(
            model,
            lambda entity: entity.shop_id == shop_id,
            include_aliases=True,
        )
        for model in scoped_models
    ))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
