from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.product import Product
from app.repositories.product import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProductRepository(db)

    def list_products(self, include_archived: bool = False, search: str = "", status: str = "", page: int = 1, page_size: int = 500, shop_id: str | None = None) -> list[Product]:
        return self.repo.list(include_archived=include_archived, search=search, status=status, page=page, page_size=page_size, shop_id=shop_id)

    def get_product(self, product_id: str, shop_id: str | None = None) -> Product:
        product = self.repo.get_by_id(product_id, shop_id=shop_id)
        if product is None:
            raise ValueError("Product not found")
        return product

    def create_product(self, payload: ProductCreate, shop_id: str | None = None) -> Product:
        payload_data = payload.model_dump(exclude_none=True)
        payload_data.setdefault("status", "active")
        payload_data["shop_id"] = shop_id
        opening_stock = payload_data.pop("current_stock", 0)
        product = self.repo.create(**payload_data, current_stock=opening_stock)
        if opening_stock:
            from app.models.stock import StockMovement
            from app.services.operations import uid, qty
            product.current_stock = qty(opening_stock)
            self.db.add(StockMovement(id=uid("STM"), product_id=product.id, shop_id=shop_id, movement_type="manual_in", quantity=qty(opening_stock), previous_stock=0, new_stock=qty(opening_stock), reason="Opening stock", reference_type="product", reference_id=product.id))
            self.db.commit()
            self.db.refresh(product)
        return product

    def update_product(self, product_id: str, payload: ProductUpdate, shop_id: str | None = None) -> Product:
        return self.repo.update(product_id, payload.model_dump(exclude_unset=True, exclude_none=True), shop_id=shop_id)

    def archive_product(self, product_id: str, shop_id: str | None = None) -> Product:
        product = self.get_product(product_id, shop_id=shop_id)
        if product.status == "archived":
            return product
        return self.repo.archive(product_id, shop_id=shop_id)

    def delete_product(self, product_id: str, shop_id: str | None = None) -> None:
        product = self.get_product(product_id, shop_id=shop_id)
        if product.status == "archived":
            self.repo.delete(product_id, shop_id=shop_id)
            return
        if self.repo.has_transaction_history(product_id, shop_id=shop_id):
            self.repo.archive(product_id, shop_id=shop_id)
            return
        self.repo.delete(product_id, shop_id=shop_id)
