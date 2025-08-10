"""
Market data router for price feeds and market information
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from pydantic import BaseModel, Field
import structlog

from app.core.database import get_db
from app.models.user import User
from app.models.portfolio import Asset
from app.models.market import MarketData, PriceUpdate, SentimentData
from app.routers.auth import get_current_active_user

logger = structlog.get_logger()

router = APIRouter(prefix="/market", tags=["Market Data"])

# ================================
# PYDANTIC MODELS
# ================================

class MarketDataResponse(BaseModel):
    """Market data response model (OHLCV)"""
    timestamp: datetime
    asset_symbol: str
    timeframe: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    volume_quote: Decimal | None
    trades_count: int | None

    class Config:
        from_attributes = True

class PriceResponse(BaseModel):
    """Current price response model"""
    asset_symbol: str
    price: Decimal
    volume_24h: Decimal | None
    change_24h: Decimal | None
    change_percent_24h: Decimal | None
    market_cap: Decimal | None
    rank: int | None
    last_updated: datetime

    class Config:
        from_attributes = True

class SentimentResponse(BaseModel):
    """Sentiment data response model"""
    asset_symbol: str
    timestamp: datetime
    twitter_sentiment: Decimal | None
    reddit_sentiment: Decimal | None
    news_sentiment: Decimal | None
    overall_sentiment: Decimal | None
    twitter_mentions: int
    reddit_mentions: int
    news_articles: int
    fear_greed_index: int | None

    class Config:
        from_attributes = True

class MarketSummary(BaseModel):
    """Market summary model"""
    total_assets: int
    active_assets: int
    total_market_cap: Decimal | None
    market_dominance: dict
    top_gainers: List[dict]
    top_losers: List[dict]
    trending_assets: List[dict]

class AssetDetails(BaseModel):
    """Detailed asset information"""
    id: str
    symbol: str
    name: str
    asset_type: str
    exchange: str | None
    sector: str | None
    market_cap: Decimal | None
    current_price: Decimal | None
    volume_24h: Decimal | None
    change_24h: Decimal | None
    change_percent_24h: Decimal | None
    high_24h: Decimal | None
    low_24h: Decimal | None
    price_history_7d: List[Decimal] | None
    sentiment_score: Decimal | None
    is_active: bool

    class Config:
        from_attributes = True

# ================================
# MARKET DATA ENDPOINTS
# ================================

@router.get("/assets", response_model=List[AssetDetails])
async def get_market_assets(
    asset_type: Optional[str] = Query(None, description="Filter by asset type"),
    active_only: bool = Query(True, description="Show only active assets"),
    limit: int = Query(50, le=100, description="Maximum number of assets"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get list of market assets with current prices"""
    
    query = select(Asset)
    
    if active_only:
        query = query.filter(Asset.is_active == True)
    
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    
    query = query.order_by(Asset.symbol).limit(limit)
    
    result = await db.execute(query)
    assets = result.scalars().all()
    
    enhanced_assets = []
    for asset in assets:
        # Get latest price update
        price_result = await db.execute(
            select(PriceUpdate)
            .filter(PriceUpdate.asset_id == asset.id)
            .order_by(desc(PriceUpdate.time))
            .limit(1)
        )
        latest_price = price_result.scalar_one_or_none()
        
        asset_detail = AssetDetails(
            id=str(asset.id),
            symbol=asset.symbol,
            name=asset.name,
            asset_type=asset.asset_type,
            exchange=asset.exchange,
            sector=asset.sector,
            market_cap=asset.market_cap,
            current_price=latest_price.price if latest_price else None,
            volume_24h=latest_price.volume_24h if latest_price else None,
            change_24h=latest_price.change_24h if latest_price else None,
            change_percent_24h=latest_price.change_percent_24h if latest_price else None,
            is_active=asset.is_active
        )
        enhanced_assets.append(asset_detail)
    
    return enhanced_assets

@router.get("/prices", response_model=List[PriceResponse])
async def get_current_prices(
    symbols: str = Query(..., description="Comma-separated list of asset symbols"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get current prices for specified assets"""
    
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    
    # Get assets
    assets_result = await db.execute(
        select(Asset).filter(Asset.symbol.in_(symbol_list))
    )
    assets = {asset.symbol: asset for asset in assets_result.scalars().all()}
    
    prices = []
    for symbol in symbol_list:
        if symbol not in assets:
            continue
        
        asset = assets[symbol]
        
        # Get latest price
        price_result = await db.execute(
            select(PriceUpdate)
            .filter(PriceUpdate.asset_id == asset.id)
            .order_by(desc(PriceUpdate.time))
            .limit(1)
        )
        latest_price = price_result.scalar_one_or_none()
        
        if latest_price:
            prices.append(PriceResponse(
                asset_symbol=symbol,
                price=latest_price.price,
                volume_24h=latest_price.volume_24h,
                change_24h=latest_price.change_24h,
                change_percent_24h=latest_price.change_percent_24h,
                market_cap=latest_price.market_cap,
                rank=latest_price.rank,
                last_updated=latest_price.time
            ))
    
    return prices

@router.get("/prices/{symbol}", response_model=PriceResponse)
async def get_asset_price(
    symbol: str,
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get current price for a specific asset"""
    
    # Get asset
    asset_result = await db.execute(
        select(Asset).filter(Asset.symbol == symbol.upper())
    )
    asset = asset_result.scalar_one_or_none()
    
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {symbol} not found"
        )
    
    # Get latest price
    price_result = await db.execute(
        select(PriceUpdate)
        .filter(PriceUpdate.asset_id == asset.id)
        .order_by(desc(PriceUpdate.time))
        .limit(1)
    )
    latest_price = price_result.scalar_one_or_none()
    
    if not latest_price:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price data available for {symbol}"
        )
    
    return PriceResponse(
        asset_symbol=symbol.upper(),
        price=latest_price.price,
        volume_24h=latest_price.volume_24h,
        change_24h=latest_price.change_24h,
        change_percent_24h=latest_price.change_percent_24h,
        market_cap=latest_price.market_cap,
        rank=latest_price.rank,
        last_updated=latest_price.time
    )

@router.get("/chart/{symbol}", response_model=List[MarketDataResponse])
async def get_chart_data(
    symbol: str,
    timeframe: str = Query("1h", description="Chart timeframe (1m, 5m, 15m, 1h, 4h, 1d)"),
    limit: int = Query(100, le=1000, description="Number of data points"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get OHLCV chart data for an asset"""
    
    # Get asset
    asset_result = await db.execute(
        select(Asset).filter(Asset.symbol == symbol.upper())
    )
    asset = asset_result.scalar_one_or_none()
    
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {symbol} not found"
        )
    
    # Get market data
    result = await db.execute(
        select(MarketData)
        .filter(
            MarketData.asset_id == asset.id,
            MarketData.timeframe == timeframe
        )
        .order_by(desc(MarketData.time))
        .limit(limit)
    )
    market_data = result.scalars().all()
    
    # Reverse to get chronological order
    market_data = list(reversed(market_data))
    
    return [
        MarketDataResponse(
            timestamp=data.time,
            asset_symbol=symbol.upper(),
            timeframe=data.timeframe,
            open_price=data.open_price,
            high_price=data.high_price,
            low_price=data.low_price,
            close_price=data.close_price,
            volume=data.volume,
            volume_quote=data.volume_quote,
            trades_count=data.trades_count
        )
        for data in market_data
    ]

@router.get("/sentiment/{symbol}", response_model=SentimentResponse)
async def get_asset_sentiment(
    symbol: str,
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get latest sentiment data for an asset"""
    
    # Get asset
    asset_result = await db.execute(
        select(Asset).filter(Asset.symbol == symbol.upper())
    )
    asset = asset_result.scalar_one_or_none()
    
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {symbol} not found"
        )
    
    # Get latest sentiment data
    sentiment_result = await db.execute(
        select(SentimentData)
        .filter(SentimentData.asset_id == asset.id)
        .order_by(desc(SentimentData.time))
        .limit(1)
    )
    sentiment = sentiment_result.scalar_one_or_none()
    
    if not sentiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sentiment data available for {symbol}"
        )
    
    return SentimentResponse(
        asset_symbol=symbol.upper(),
        timestamp=sentiment.time,
        twitter_sentiment=sentiment.twitter_sentiment,
        reddit_sentiment=sentiment.reddit_sentiment,
        news_sentiment=sentiment.news_sentiment,
        overall_sentiment=sentiment.overall_sentiment,
        twitter_mentions=sentiment.twitter_mentions,
        reddit_mentions=sentiment.reddit_mentions,
        news_articles=sentiment.news_articles,
        fear_greed_index=sentiment.fear_greed_index
    )

@router.get("/trending", response_model=List[dict])
async def get_trending_assets(
    limit: int = Query(10, le=50, description="Number of trending assets"),
    timeframe: str = Query("24h", description="Trending timeframe (1h, 24h, 7d)"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get trending assets based on price movement and volume"""
    
    # For now, return mock data
    # TODO: Implement real trending calculation based on volume and price changes
    
    trending_data = [
        {
            "symbol": "BTC",
            "name": "Bitcoin",
            "price_change_percent": Decimal("5.24"),
            "volume_change_percent": Decimal("15.32"),
            "trending_score": Decimal("8.5")
        },
        {
            "symbol": "ETH",
            "name": "Ethereum",
            "price_change_percent": Decimal("3.18"),
            "volume_change_percent": Decimal("12.45"),
            "trending_score": Decimal("7.8")
        }
    ]
    
    return trending_data[:limit]

@router.get("/summary", response_model=MarketSummary)
async def get_market_summary(
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get overall market summary"""
    
    # Count assets
    total_result = await db.execute(select(Asset))
    total_assets = len(total_result.scalars().all())
    
    active_result = await db.execute(select(Asset).filter(Asset.is_active == True))
    active_assets = len(active_result.scalars().all())
    
    # For now, return basic summary with mock data
    # TODO: Implement real market calculations
    
    return MarketSummary(
        total_assets=total_assets,
        active_assets=active_assets,
        total_market_cap=None,
        market_dominance={
            "BTC": 45.2,
            "ETH": 18.7,
            "Others": 36.1
        },
        top_gainers=[
            {"symbol": "BTC", "change_percent": 5.24},
            {"symbol": "ETH", "change_percent": 3.18}
        ],
        top_losers=[
            {"symbol": "DOGE", "change_percent": -2.45}
        ],
        trending_assets=[
            {"symbol": "BTC", "trending_score": 8.5},
            {"symbol": "ETH", "trending_score": 7.8}
        ]
    )

@router.get("/watchlist", response_model=List[AssetDetails])
async def get_user_watchlist(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get user's watchlist (placeholder for future implementation)"""
    
    # TODO: Implement user watchlist functionality
    # For now, return popular assets
    
    popular_symbols = ["BTC", "ETH", "AAPL", "GOOGL"]
    
    result = await db.execute(
        select(Asset).filter(Asset.symbol.in_(popular_symbols))
    )
    assets = result.scalars().all()
    
    enhanced_assets = []
    for asset in assets:
        # Get latest price
        price_result = await db.execute(
            select(PriceUpdate)
            .filter(PriceUpdate.asset_id == asset.id)
            .order_by(desc(PriceUpdate.time))
            .limit(1)
        )
        latest_price = price_result.scalar_one_or_none()
        
        asset_detail = AssetDetails(
            id=str(asset.id),
            symbol=asset.symbol,
            name=asset.name,
            asset_type=asset.asset_type,
            exchange=asset.exchange,
            sector=asset.sector,
            market_cap=asset.market_cap,
            current_price=latest_price.price if latest_price else None,
            volume_24h=latest_price.volume_24h if latest_price else None,
            change_24h=latest_price.change_24h if latest_price else None,
            change_percent_24h=latest_price.change_percent_24h if latest_price else None,
            is_active=asset.is_active
        )
        enhanced_assets.append(asset_detail)
    
    return enhanced_assets