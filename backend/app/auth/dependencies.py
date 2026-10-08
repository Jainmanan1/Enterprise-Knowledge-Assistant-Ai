from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
 
from app.auth.jwtAuth import decode_access_token
from app.db.models import User, UserRole
from app.db.session import get_db


Oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token:str = Depends(Oauth2_scheme), db:Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code =status.HTTP_401_UNAUTHORIZED,
        detail = "Could not validate credentials",
        headers = {"WWW-Authenticate":"Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.id ==user_id).first()
    if user is None:
        raise credentials_exception
 
    return user


def require_role(*allowed_roles: UserRole):
 
 
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return user
 
    return role_checker

    

