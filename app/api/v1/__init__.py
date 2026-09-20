from app.api.v1.auth import router as auth_router
from app.api.v1.categories import router as categories_router
from app.api.v1.customers import router as customers_router
from app.api.v1.health import router as health_router
from app.api.v1.products import router as products_router
from app.api.v1.stock import router as stock_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.operations import router as operations_router

__all__ = [
    "auth_router",
    "categories_router",
    "customers_router",
    "health_router",
    "products_router",
    "stock_router",
    "suppliers_router",
    "operations_router",
]
