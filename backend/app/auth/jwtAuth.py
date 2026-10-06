import os
from datetime import datetime, timedelta, timezone
 
from jose import JWTError, jwt
from passlib.context import CryptContext


secret_key = os.environ.get("JWT_SECRET_KEY")
if secret_key is None:
    raise RuntimeError("JWT_SECRET_KEY environment variable is not set")
SECRET_KEY: str = secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60*8

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password:str) ->str:

    return pwd_context.hash(password)


def  verify_password(plain_password:str, hashed_password:str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data:dict, expires_delta:timedelta|None = None) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    to_encode.update({"exp":expire})

    return jwt.encode(to_encode,SECRET_KEY,algorithm=ALGORITHM)


#jwt verification 

def decode_access_token(token:str) ->dict |None:
    try:
        payload = jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        return payload

    except JWTError:
        return None
