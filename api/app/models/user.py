"""
User model for authentication and profile management
"""
from sqlalchemy import Column, String, Boolean, DECIMAL, TIMESTAMP, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class User(Base):
    """User model"""
    
    __tablename__ = "users"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Authentication
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    
    # Account status
    is_active = Column(Boolean, default=True, index=True)
    is_verified = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(TIMESTAMP(timezone=True))
    
    # Trading Configuration
    risk_tolerance = Column(DECIMAL(3, 2), default=0.05)  # 5% max risk per trade
    max_portfolio_risk = Column(DECIMAL(3, 2), default=0.15)  # 15% max drawdown
    auto_trading_enabled = Column(Boolean, default=False)
    
    # Austrian Tax Settings
    tax_residence = Column(String(2), default="AT")
    tax_id = Column(String(50))
    
    # Relationships
    portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"