from fastapi import APIRouter, HTTPException, status
import uuid
import hashlib
from app.schemas.schemas import UserCreate, UserResponse
from app.core.database import db
from app.core.logger import logger

router = APIRouter()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user: UserCreate):
    logger.info("Received request to register user", extra={"username": user.username})
    async with db.lock:
        if user.username in db.username_to_id:
            logger.warning("Username already exists", extra={"username": user.username})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists.")
        
        user_id = str(uuid.uuid4())
        new_user = {
            "user_id": user_id,
            "username": user.username,
            "password_hash": hash_password(user.password)
        }
        db.users[user_id] = new_user
        db.username_to_id[user.username] = user_id
        await db.save_to_disk()
        
    logger.info("User registered successfully", extra={"user_id": user_id})
    return {"user_id": user_id, "username": user.username, "message": "User registered successfully."}
