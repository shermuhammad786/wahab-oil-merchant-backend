from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateEntryError, ValidationError
from app.core.security import get_current_user
from app.db.session import get_db
from app.repositories.category import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryRead
from app.services.category import CategoryService

router = APIRouter(prefix="/product-categories", tags=["product-categories"])


@router.get("", response_model=list[CategoryRead])
def list_categories(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CategoryRead]:
    items = CategoryRepository(db).list(search=search or "", shop_id=current_user.shop_id)
    return [CategoryRead.model_validate(item) for item in items]


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> CategoryRead:
    try:
        return CategoryRead.model_validate(CategoryService(db).create_category(payload, shop_id=current_user.shop_id))
    except DuplicateEntryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
