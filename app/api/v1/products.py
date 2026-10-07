from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services.product import ProductService

router = APIRouter(prefix="/products", tags=["products"])


def read_product(product) -> ProductRead:
    return ProductRead(
        id=product.id,
        name=product.name,
        category_id=product.category_id,
        purchase_price=product.purchase_price,
        current_stock=product.current_stock,
        minimum_stock=product.minimum_stock,
        status=product.status,
        category=product.category.name if product.category else None,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get("", response_model=list[ProductRead])
def list_products(search: str = Query(default=""), status_filter: str = Query(default="", alias="status"), page: int = 1, page_size: int = 500, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[ProductRead]:
    products = ProductService(db).list_products(include_archived=False, search=search, status=status_filter, page=page, page_size=page_size, shop_id=current_user.shop_id)
    return [read_product(product) for product in products]


@router.get("/all", response_model=list[ProductRead])
def list_all_products(search: str = Query(default=""), page: int = 1, page_size: int = 500, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[ProductRead]:
    products = ProductService(db).list_products(include_archived=True, search=search, page=page, page_size=page_size, shop_id=current_user.shop_id)
    return [read_product(product) for product in products]


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ProductRead:
    try:
        product = ProductService(db).get_product(product_id, shop_id=current_user.shop_id)
        return read_product(product)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ProductRead:
    product = ProductService(db).create_product(payload, shop_id=current_user.shop_id)
    return read_product(product)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(product_id: str, payload: ProductUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ProductRead:
    try:
        product = ProductService(db).update_product(product_id, payload, shop_id=current_user.shop_id)
        return read_product(product)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{product_id}/archive", response_model=ProductRead)
def archive_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> ProductRead:
    try:
        product = ProductService(db).archive_product(product_id, shop_id=current_user.shop_id)
        return read_product(product)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> None:
    ProductService(db).delete_product(product_id, shop_id=current_user.shop_id)
    return None
