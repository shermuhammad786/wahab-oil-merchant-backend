from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import UserCreate, UserResponse
from queries import (
    create_user,
    get_all_users,
    get_user_by_id,
    get_user_by_email
)
from services.users import get_user_by_id_by_email


router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.post("/", status_code=201)
def add_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):

    # Check duplicate email
    existing_user = get_user_by_id_by_email(
        db,
        user.email
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

    user_id = create_user(
        db=db,
        name=user.name,
        email=user.email,
        password=user.password,
        age=user.age,
        phone=user.phone
    )

    return {
        "message": "User created successfully",
        "user_id": user_id
    }


@router.get("/")
def get_users(
    db: Session = Depends(get_db)
):

    users = get_all_users(db)

    return {
        "count": len(users),
        "users": users
    }


@router.get("/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = get_user_by_id(
        db,
        user_id
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user

@router.get("/email/{email}")
def get_user(
    email: str,
    db: Session = Depends(get_db)
):

    user = get_user_by_email(
        db,
        email
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user
