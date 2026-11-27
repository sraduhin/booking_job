from typing import Annotated

from fastapi import Header, HTTPException, status


async def get_current_user_id(
    x_user_id: Annotated[int | None, Header(alias="X-User-Id")] = None,
) -> int:
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-User-Id header is required",
        )
    if x_user_id < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-User-Id must be a positive integer",
        )
    return x_user_id


async def get_dedup_id(
    dedup_id: Annotated[int | None, Header(alias="Dedup-Id")] = None,
) -> int:
    if dedup_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dedup-Id header is required",
        )
    return dedup_id
