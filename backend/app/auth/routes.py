from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.auth.jwtAuth import create_access_token, hash_password, verify_password
from app.auth.models import Token, UserCreate, UserOut
from app.db.models import User, UserRole
from app.db.session import get_db

router = APIRouter(prefix = "/auth", tags=["auth"])



@router.post("/register", response_model=UserOut,status_code=status.HTTP_201_CREATED)


def register(payload:UserCreate, db:Session = Depends(get_db)) -> UserOut:
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=payload.email,
        hashed_password = hash_password(payload.password),
        role = UserRole.EMPLOYEE
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post("/login",response_model = Token) 

def login(form_data:OAuth2PasswordRequestForm = Depends(), db:Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None or not verify_password(form_data.password,user.hashed_password):
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Incorrect email or password",
            headers = {"WWW-Authenticate":"Bearer"},
        )

    access_token = create_access_token(data={"sub":str(user.id),"role":user.role.value})
    return Token(access_token=access_token)

@router.get("/me",response_model=UserOut)
def get_me(current_user:User = Depends(get_current_user)) -> UserOut:
    return current_user
