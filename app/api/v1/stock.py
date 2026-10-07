from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.stock import StockMovement
from app.schemas.stock import StockAdjustmentRequest, StockBatchAdjustmentRequest, StockMovementRead
from app.services.stock import StockService

router = APIRouter(prefix="/stock", tags=["stock"])


def read_movement(item: StockMovement) -> StockMovementRead:
    return StockMovementRead(
        id=item.id,
        product_id=item.product_id,
        product_name=getattr(item.product, "name", None),
        movement_type=item.movement_type,
        quantity=item.quantity,
        previous_stock=item.previous_stock,
        new_stock=item.new_stock,
        reason=item.reason,
        note=item.note,
        reference_type=item.reference_type,
        reference_id=item.reference_id,
        created_at=item.created_at,
        date=item.created_at,
        type=item.movement_type,
        balance=item.new_stock,
    )


@router.get("/movements", response_model=list[StockMovementRead])
def list_stock_movements(
    product_id: str | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StockMovementRead]:
    items = StockService(db).list_movements(
        product_id=product_id,
        movement_type=movement_type,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        shop_id=current_user.shop_id,
    )
    response: list[StockMovementRead] = []
    for item in items:
        response.append(read_movement(item))
    return response


@router.post("/adjustments", response_model=StockMovementRead, status_code=status.HTTP_201_CREATED)
def create_stock_adjustment(
    payload: StockAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StockMovementRead:
    try:
        item = StockService(db).adjust_stock(payload, shop_id=current_user.shop_id)
        return StockMovementRead(
            id=item.id,
            product_id=item.product_id,
            product_name=getattr(item.product, "name", None),
            movement_type=item.movement_type,
            quantity=item.quantity,
            previous_stock=item.previous_stock,
            new_stock=item.new_stock,
            reason=item.reason,
            note=item.note,
            reference_type=item.reference_type,
            reference_id=item.reference_id,
            created_at=item.created_at,
        )
    except AppException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/adjustments/batch", response_model=list[StockMovementRead], status_code=status.HTTP_201_CREATED)
def create_batch_stock_adjustments(
    payload: StockBatchAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StockMovementRead]:
    try:
        items = StockService(db).adjust_stock_batch(payload, shop_id=current_user.shop_id)
        return [
            StockMovementRead(
                id=item.id,
                product_id=item.product_id,
                product_name=getattr(item.product, "name", None),
                movement_type=item.movement_type,
                quantity=item.quantity,
                previous_stock=item.previous_stock,
                new_stock=item.new_stock,
                reason=item.reason,
                note=item.note,
                reference_type=item.reference_type,
                reference_id=item.reference_id,
                created_at=item.created_at,
            )
            for item in items
        ]
    except AppException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
