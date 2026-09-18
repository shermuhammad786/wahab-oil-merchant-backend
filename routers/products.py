from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas.schemas import UserCreate, UserResponse,UserUpdate
from queries import (
    create_user,
    get_all_users,
    get_user_by_id,
    get_user_by_email,
    delete_user_by_id,
    update_user_by_id
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


    user_id = create_user(
        db=db,
        name=user.name,
        phone=user.phone,
        address=user.address,
        type=user.type
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


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):

    deleted = delete_user_by_id(
        db,
        user_id
    )

    if deleted == 0:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return {
        "message": "User deleted successfully",
        "user_id": user_id
    }



@router.put("/{user_id}")
def update_user( user_id:int, user: UserUpdate,db: Session = Depends(get_db)):

    find_user = get_user_by_id(
            db,
            user_id
        )

    print(f"user ==>> {find_user}")
    if not find_user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
     
    update_user_by_id(
        db,
        user_id=user_id,
        name=user.name,
        phone=user.phone,
        address=user.address,
        type=user.type
    )
    return {
        "message": "User updated successfully",
        "user_id": user_id
    }