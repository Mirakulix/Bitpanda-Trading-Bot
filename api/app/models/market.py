"""
Market data and time-series models
"""
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class MarketData(Base):
    """Market data model for OHLCV data (TimescaleDB hypertable)"""
    
    __tablename__ = "market_data"
    
    # Composite primary key for time-series
    time = Column(TIMESTAMP(timezone=True), nullable=False, primary_key=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, primary_key=True)
    timeframe = Column(String(10), nullable=False, primary_key=True)  # 1m, 5m, 1h, 1d, etc.
    
    # OHLCV data
    open_price = Column(DECIMAL(15, 8), nullable=False)
    high_price = Column(DECIMAL(15, 8), nullable=False)
    low_price = Column(DECIMAL(15, 8), nullable=False)
    close_price = Column(DECIMAL(15, 8), nullable=False)
    volume = Column(DECIMAL(20, 8), nullable=False)
    
    # Additional metrics
    volume_quote = Column(DECIMAL(20, 8))  # volume in quote currency
    trades_count = Column(Integer)
    
    # Relationships
    asset = relationship("Asset")
    
    def __repr__(self):
        return f"<MarketData(asset={self.asset_id}, time={self.time}, timeframe={self.timeframe})>"


class PortfolioHistory(Base):
    """Portfolio value history model (TimescaleDB hypertable)"""
    
    __tablename__ = "portfolio_history"
    
    # Composite primary key for time-series
    time = Column(TIMESTAMP(timezone=True), nullable=False, primary_key=True)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, primary_key=True)
    
    # Portfolio metrics
    total_value = Column(DECIMAL(15, 2), nullable=False)
    cash_balance = Column(DECIMAL(15, 2), nullable=False)
    invested_value = Column(DECIMAL(15, 2), nullable=False)
    unrealized_pnl = Column(DECIMAL(15, 2), nullable=False)
    realized_pnl = Column(DECIMAL(15, 2), nullable=False)
    
    # Performance metrics
    daily_return = Column(DECIMAL(8, 6))
    sharpe_ratio = Column(DECIMAL(8, 4))
    max_drawdown = Column(DECIMAL(8, 4))
    
    # Relationships
    portfolio = relationship("Portfolio")
    
    def __repr__(self):
        return f"<PortfolioHistory(portfolio={self.portfolio_id}, time={self.time})>"


class PriceUpdate(Base):
    """Real-time price updates model (TimescaleDB hypertable)"""
    
    __tablename__ = "price_updates"
    
    # Composite primary key for time-series
    time = Column(TIMESTAMP(timezone=True), nullable=False, default=func.now(), primary_key=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, primary_key=True)
    
    # Price data
    price = Column(DECIMAL(15, 8), nullable=False)
    volume_24h = Column(DECIMAL(20, 8))
    change_24h = Column(DECIMAL(15, 8))
    change_percent_24h = Column(DECIMAL(8, 4))
    
    # Market data
    market_cap = Column(DECIMAL(20, 0))
    rank = Column(Integer)
    
    # Relationships
    asset = relationship("Asset")
    
    def __repr__(self):
        return f"<PriceUpdate(asset={self.asset_id}, price={self.price}, time={self.time})>"


class SentimentData(Base):
    """Social sentiment data model (TimescaleDB hypertable)"""
    
    __tablename__ = "sentiment_data"
    
    # Composite primary key for time-series
    time = Column(TIMESTAMP(timezone=True), nullable=False, default=func.now(), primary_key=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, primary_key=True)
    
    # Sentiment scores (-1 to 1)
    twitter_sentiment = Column(DECIMAL(5, 4))
    reddit_sentiment = Column(DECIMAL(5, 4))
    news_sentiment = Column(DECIMAL(5, 4))
    overall_sentiment = Column(DECIMAL(5, 4))
    
    # Volume metrics
    twitter_mentions = Column(Integer, default=0)
    reddit_mentions = Column(Integer, default=0)
    news_articles = Column(Integer, default=0)
    
    # Fear & Greed Index
    fear_greed_index = Column(Integer)  # 0-100
    
    # Relationships
    asset = relationship("Asset")
    
    def __repr__(self):
        return f"<SentimentData(asset={self.asset_id}, sentiment={self.overall_sentiment}, time={self.time})>"


class SystemMetrics(Base):
    """System metrics model (TimescaleDB hypertable)"""
    
    __tablename__ = "system_metrics"
    
    # Composite primary key for time-series
    time = Column(TIMESTAMP(timezone=True), nullable=False, default=func.now(), primary_key=True)
    metric_name = Column(String(100), nullable=False, primary_key=True)
    
    # Metric values
    value = Column(DECIMAL(15, 8))
    string_value = Column(String)
    
    # Labels (JSON for flexibility)
    labels = Column(JSONB)
    
    def __repr__(self):
        return f"<SystemMetrics(name={self.metric_name}, value={self.value}, time={self.time})>"