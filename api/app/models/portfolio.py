"""
Portfolio and position models for trading management
"""
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class Portfolio(Base):
    """Portfolio model"""
    
    __tablename__ = "portfolios"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Portfolio details
    name = Column(String(100), nullable=False, default="Main Portfolio")
    initial_balance = Column(DECIMAL(15, 2), nullable=False)
    current_balance = Column(DECIMAL(15, 2), nullable=False)
    total_invested = Column(DECIMAL(15, 2), default=0)
    total_profit_loss = Column(DECIMAL(15, 2), default=0)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="unique_user_portfolio"),
    )
    
    # Relationships
    user = relationship("User", back_populates="portfolios")
    positions = relationship("Position", back_populates="portfolio", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="portfolio", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Portfolio(id={self.id}, name={self.name})>"


class Asset(Base):
    """Asset model for stocks, crypto, etc."""
    
    __tablename__ = "assets"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Asset details
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    asset_type = Column(String(20), nullable=False, index=True)  # crypto, stock, etf, commodity
    exchange = Column(String(50))  # binance, nasdaq, etc.
    is_active = Column(String(10), default=True, index=True)
    
    # Asset metadata
    sector = Column(String(50))
    market_cap = Column(DECIMAL(20, 0))
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    positions = relationship("Position", back_populates="asset")
    orders = relationship("Order", back_populates="asset")
    
    def __repr__(self):
        return f"<Asset(symbol={self.symbol}, type={self.asset_type})>"


class Position(Base):
    """Position model for portfolio holdings"""
    
    __tablename__ = "positions"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    
    # Position details
    quantity = Column(DECIMAL(20, 8), nullable=False)
    avg_buy_price = Column(DECIMAL(15, 8), nullable=False)
    current_price = Column(DECIMAL(15, 8))
    
    # P&L calculation
    unrealized_pnl = Column(DECIMAL(15, 2), default=0)
    realized_pnl = Column(DECIMAL(15, 2), default=0)
    
    # Position management
    status = Column(String(20), default="open", index=True)  # open, closed
    opened_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    closed_at = Column(TIMESTAMP(timezone=True))
    
    # Risk management
    stop_loss_price = Column(DECIMAL(15, 8))
    take_profit_price = Column(DECIMAL(15, 8))
    
    # Relationships
    portfolio = relationship("Portfolio", back_populates="positions")
    asset = relationship("Asset", back_populates="positions")
    orders = relationship("Order", back_populates="position")
    
    def __repr__(self):
        return f"<Position(id={self.id}, asset={self.asset.symbol if self.asset else 'N/A'}, quantity={self.quantity})>"