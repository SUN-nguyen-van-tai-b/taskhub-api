from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Lấy dữ liệu được gửi lên bằng model_dump(exclude_unset=True)
    update_data = data.model_dump(exclude_unset=True)
    # 2. Cập nhật các field được gửi vào current_user
    for key, value in update_data.items():
        setattr(current_user, key, value)
    # 3. Commit thay đổi vào database
    await db.commit()
    # 4. Refresh current_user
    await db.refresh(current_user)
    # 5. Return current_user
    return current_user


@router.post(
    "/me/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Kiểm tra old_password có đúng không
    is_valid = verify_password(data.old_password, current_user.hashed_password)
    # 2. Nếu sai → HTTP 400
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Wrongs password"
        )
    # 3. Kiểm tra new_password khác old_password
    if data.old_password == data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from old password",
        )
    # 4. Hash new_password
    hashed_password = hash_password(data.new_password)
    # 5. Gán vào current_user.hashed_password
    current_user.hashed_password = hashed_password
    # 6. Commit database
    await db.commit()
    # 7. Không trả response body
