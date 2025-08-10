"""
Authentication router for user login, registration, and profile management
"""
from datetime import datetime, timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr, Field
import structlog
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

logger = structlog.get_logger()

# Security setup
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ================================
# PYDANTIC MODELS
# ================================

class UserCreate(BaseModel):
    """User creation model"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    risk_tolerance: float = Field(default=0.05, ge=0.0, le=1.0)
    max_portfolio_risk: float = Field(default=0.15, ge=0.0, le=1.0)

class UserLogin(BaseModel):
    """User login model"""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)

class UserResponse(BaseModel):
    """User response model (without password)"""
    id: str
    username: str
    email: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: datetime | None
    risk_tolerance: float
    max_portfolio_risk: float
    auto_trading_enabled: bool
    tax_residence: str
    tax_id: str | None

    class Config:
        from_attributes = True

class Token(BaseModel):
    """Token response model"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

class PasswordChange(BaseModel):
    """Password change model"""
    current_password: str
    new_password: str = Field(..., min_length=8)

class UserUpdate(BaseModel):
    """User profile update model"""
    email: EmailStr | None = None
    risk_tolerance: float | None = Field(None, ge=0.0, le=1.0)
    max_portfolio_risk: float | None = Field(None, ge=0.0, le=1.0)
    auto_trading_enabled: bool | None = None
    tax_residence: str | None = Field(None, max_length=2)
    tax_id: str | None = None

# ================================
# UTILITY FUNCTIONS
# ================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            credentials.credentials, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """Get current active user (additional check)"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

# ================================
# AUTHENTICATION ENDPOINTS
# ================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user"""
    
    logger.info("User registration attempt", username=user_data.username, email=user_data.email)
    
    # Check if username already exists
    result = await db.execute(select(User).filter(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    result = await db.execute(select(User).filter(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password,
        risk_tolerance=user_data.risk_tolerance,
        max_portfolio_risk=user_data.max_portfolio_risk,
        is_verified=False  # Email verification required
    )
    
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    
    logger.info("User registered successfully", user_id=str(db_user.id), username=db_user.username)
    
    return UserResponse.from_orm(db_user)

@router.post("/login", response_model=Token)
async def login_user(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return access token"""
    
    logger.info("User login attempt", username=user_data.username)
    
    # Get user from database
    result = await db.execute(select(User).filter(User.username == user_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(user_data.password, user.password_hash):
        logger.warning("Failed login attempt", username=user_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    logger.info("User logged in successfully", user_id=str(user.id), username=user.username)
    
    return Token(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.from_orm(user)
    )

@router.post("/logout")
async def logout_user(current_user: Annotated[User, Depends(get_current_active_user)]):
    """User logout (client-side token removal)"""
    logger.info("User logged out", user_id=str(current_user.id), username=current_user.username)
    return {"message": "Successfully logged out"}

# ================================
# USER PROFILE ENDPOINTS
# ================================

@router.get("/profile", response_model=UserResponse)
async def get_user_profile(current_user: Annotated[User, Depends(get_current_active_user)]):
    """Get current user profile"""
    return UserResponse.from_orm(current_user)

@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_update: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update user profile"""
    
    logger.info("Profile update request", user_id=str(current_user.id))
    
    # Update fields if provided
    if user_update.email is not None:
        # Check if email already exists (for other users)
        result = await db.execute(
            select(User).filter(User.email == user_update.email, User.id != current_user.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered to another user"
            )
        current_user.email = user_update.email
        current_user.is_verified = False  # Re-verify email
    
    if user_update.risk_tolerance is not None:
        current_user.risk_tolerance = user_update.risk_tolerance
    
    if user_update.max_portfolio_risk is not None:
        current_user.max_portfolio_risk = user_update.max_portfolio_risk
    
    if user_update.auto_trading_enabled is not None:
        current_user.auto_trading_enabled = user_update.auto_trading_enabled
    
    if user_update.tax_residence is not None:
        current_user.tax_residence = user_update.tax_residence
    
    if user_update.tax_id is not None:
        current_user.tax_id = user_update.tax_id
    
    await db.commit()
    await db.refresh(current_user)
    
    logger.info("Profile updated successfully", user_id=str(current_user.id))
    
    return UserResponse.from_orm(current_user)

@router.post("/change-password")
async def change_password(
    password_change: PasswordChange,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Change user password"""
    
    logger.info("Password change request", user_id=str(current_user.id))
    
    # Verify current password
    if not verify_password(password_change.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    # Update password
    current_user.password_hash = get_password_hash(password_change.new_password)
    await db.commit()
    
    logger.info("Password changed successfully", user_id=str(current_user.id))
    
    return {"message": "Password changed successfully"}

@router.delete("/account")
async def delete_account(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    confirmation: str = Form(...)
):
    """Delete user account (requires confirmation)"""
    
    if confirmation != "DELETE_MY_ACCOUNT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account deletion requires confirmation string 'DELETE_MY_ACCOUNT'"
        )
    
    logger.warning("Account deletion request", user_id=str(current_user.id), username=current_user.username)
    
    # Soft delete - deactivate account instead of hard delete
    current_user.is_active = False
    current_user.username = f"deleted_{current_user.username}_{datetime.utcnow().timestamp()}"
    current_user.email = f"deleted_{current_user.email}"
    
    await db.commit()
    
    logger.warning("Account deleted", user_id=str(current_user.id))
    
    return {"message": "Account deactivated successfully"}

# ================================
# ADMIN ENDPOINTS (Future)
# ================================

# Note: Admin endpoints would be implemented here for user management
# These would require additional role-based access control