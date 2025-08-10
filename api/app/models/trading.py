"""
Trading models for orders and execution
"""
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class Order(Base):
    """Order model for trading orders"""
    
    __tablename__ = "orders"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    position_id = Column(UUID(as_uuid=True), ForeignKey("positions.id"))  # NULL for opening positions
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    
    # Order details
    order_type = Column(String(20), nullable=False, index=True)  # buy, sell, stop_loss, take_profit
    quantity = Column(DECIMAL(20, 8), nullable=False)
    price = Column(DECIMAL(15, 8))
    stop_price = Column(DECIMAL(15, 8))  # for stop orders
    
    # Order execution
    status = Column(String(20), default="pending", index=True)  # pending, executed, cancelled, failed
    executed_quantity = Column(DECIMAL(20, 8), default=0)
    executed_price = Column(DECIMAL(15, 8))
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    executed_at = Column(TIMESTAMP(timezone=True))
    cancelled_at = Column(TIMESTAMP(timezone=True))
    
    # External reference
    external_order_id = Column(String(100), index=True)  # Bitpanda order ID
    
    # Fees
    fee_amount = Column(DECIMAL(15, 8), default=0)
    fee_currency = Column(String(10))
    
    # Relationships
    portfolio = relationship("Portfolio", back_populates="orders")
    position = relationship("Position", back_populates="orders")
    asset = relationship("Asset", back_populates="orders")
    
    def __repr__(self):
        return f"<Order(id={self.id}, type={self.order_type}, status={self.status})>"


class RiskAlert(Base):
    """Risk alert model for portfolio monitoring"""
    
    __tablename__ = "risk_alerts"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"))
    
    # Alert details
    alert_type = Column(String(30), nullable=False, index=True)  # drawdown, concentration, volatility
    severity = Column(String(10), nullable=False, index=True)  # low, medium, high, critical
    message = Column(String, nullable=False)
    
    # Alert data
    current_value = Column(DECIMAL(15, 8))
    threshold_value = Column(DECIMAL(15, 8))
    
    # Status
    is_active = Column(String(10), default=True)
    acknowledged_at = Column(TIMESTAMP(timezone=True))
    resolved_at = Column(TIMESTAMP(timezone=True))
    
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User")
    portfolio = relationship("Portfolio")
    
    def __repr__(self):
        return f"<RiskAlert(id={self.id}, type={self.alert_type}, severity={self.severity})>"


class SystemConfig(Base):
    """System configuration model"""
    
    __tablename__ = "system_config"
    
    # Primary key
    key = Column(String(100), primary_key=True)
    
    # Config data
    value = Column(String, nullable=False)
    description = Column(String)
    
    # Metadata
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    def __repr__(self):
        return f"<SystemConfig(key={self.key}, value={self.value})>"