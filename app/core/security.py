from fastapi import Header, HTTPException
from jose import jwt, JWTError
from app.core.config import settings

ALGORITHM = "HS256"


def verify_token(authorization: str = Header(None)):
    if authorization is None:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])

        username = payload.get("sub")

        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        return username

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")