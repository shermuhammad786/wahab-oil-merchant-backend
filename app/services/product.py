from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.product import Product
from app.repositories.product import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProductRepository(db)

    def list_products(self, include_archived: bool = False) -> list[Product]:
        return self.repo.list(include_archived=include_archived)

    def get_product(self, product_id: str) -> Product:
        product = self.repo.get_by_id(product_id)
        if product is None:
            raise ValueError("Product not found")
        return product

    def create_product(self, payload: ProductCreate) -> Product:
        payload_data = payload.model_dump(exclude_none=True)
        payload_data.setdefault("status", "active")
        return self.repo.create(**payload_data)

    def update_product(self, product_id: str, payload: ProductUpdate) -> Product:
        return self.repo.update(product_id, payload.model_dump(exclude_unset=True, exclude_none=True))

    def archive_product(self, product_id: str) -> Product:
        product = self.get_product(product_id)
        if product.status == "archived":
            return product
        return self.repo.archive(product_id)

    def delete_product(self, product_id: str) -> None:
        product = self.get_product(product_id)
        if product.status == "archived":
            self.repo.delete(product_id)
            return
        if self.repo.has_transaction_history(product_id):
            self.repo.archive(product_id)
            return
        self.repo.delete(product_id)
