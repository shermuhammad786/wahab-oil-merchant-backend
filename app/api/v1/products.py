from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services.product import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductRead])
def list_products(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[ProductRead]:
    products = ProductService(db).list_products(include_archived=False)
    return [ProductRead.model_validate(product) for product in products]


@router.get("/all", response_model=list[ProductRead])
def list_all_products(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[ProductRead]:
    products = ProductService(db).list_products(include_archived=True)
    return [ProductRead.model_validate(product) for product in products]


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ProductRead:
    try:
        product = ProductService(db).get_product(product_id)
        return ProductRead.model_validate(product)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ProductRead:
    product = ProductService(db).create_product(payload)
    return ProductRead.model_validate(product)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(product_id: str, payload: ProductUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ProductRead:
    try:
        product = ProductService(db).update_product(product_id, payload)
        return ProductRead.model_validate(product)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{product_id}/archive", response_model=ProductRead)
def archive_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ProductRead:
    try:
        product = ProductService(db).archive_product(product_id)
        return ProductRead.model_validate(product)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> None:
    ProductService(db).delete_product(product_id)
    return None
