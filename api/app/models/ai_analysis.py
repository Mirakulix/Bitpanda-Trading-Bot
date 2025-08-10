"""
AI analysis models for storing AI-generated market insights
"""
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class AIAnalysis(Base):
    """AI analysis results model"""
    
    __tablename__ = "ai_analyses"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True)
    
    # Analysis details
    analysis_type = Column(String(20), nullable=False, index=True)  # fundamental, technical, sentiment, consensus
    ai_model = Column(String(50), nullable=False)  # gpt-4.1, deepseek-r1, gemini, etc.
    
    # Results
    recommendation = Column(String(10), nullable=False)  # BUY, SELL, HOLD
    confidence_score = Column(DECIMAL(5, 4), nullable=False)  # 0.0000 to 1.0000
    target_price = Column(DECIMAL(15, 8))
    reasoning = Column(Text)
    
    # Key indicators (JSON)
    indicators = Column(JSONB)
    
    # Metadata
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(TIMESTAMP(timezone=True), index=True)  # when analysis becomes stale
    
    # Relationships
    asset = relationship("Asset")
    
    def __repr__(self):
        return f"<AIAnalysis(id={self.id}, asset={self.asset_id}, recommendation={self.recommendation})>"


# Update relationships in other models
# This should be added to the User model in user.py
"""
# Add to User model:
portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")
"""

# Add indexes for performance (these would be created via Alembic migrations)
"""
CREATE INDEX idx_ai_analyses_asset_id ON ai_analyses(asset_id);
CREATE INDEX idx_ai_analyses_type ON ai_analyses(analysis_type);
CREATE INDEX idx_ai_analyses_created_at ON ai_analyses(created_at);
CREATE INDEX idx_ai_analyses_expires_at ON ai_analyses(expires_at);

CREATE INDEX idx_market_data_asset_timeframe ON market_data(asset_id, timeframe, time DESC);
CREATE INDEX idx_portfolio_history_portfolio ON portfolio_history(portfolio_id, time DESC);
CREATE INDEX idx_price_updates_asset ON price_updates(asset_id, time DESC);
CREATE INDEX idx_sentiment_data_asset ON sentiment_data(asset_id, time DESC);
"""