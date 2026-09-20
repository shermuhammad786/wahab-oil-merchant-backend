from fastapi import APIRouter

from app.api.v1 import (
    auth_router,
    categories_router,
    customers_router,
    health_router,
    products_router,
    stock_router,
    suppliers_router,
    operations_router,
)

router = APIRouter()
router.include_router(auth_router, prefix="/api/v1")
router.include_router(health_router, prefix="/api/v1")
router.include_router(customers_router, prefix="/api/v1")
router.include_router(suppliers_router, prefix="/api/v1")
router.include_router(categories_router, prefix="/api/v1")
router.include_router(products_router, prefix="/api/v1")
router.include_router(stock_router, prefix="/api/v1")
router.include_router(operations_router, prefix="/api/v1")
