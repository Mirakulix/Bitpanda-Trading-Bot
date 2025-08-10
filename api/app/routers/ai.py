"""
AI analysis router for market analysis and trading recommendations
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func
from pydantic import BaseModel, Field
from enum import Enum
import structlog

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.portfolio import Asset
from app.models.ai_analysis import AIAnalysis
from app.routers.auth import get_current_active_user
from app.services.ai_service import ai_service_manager

logger = structlog.get_logger()

router = APIRouter(prefix="/ai", tags=["AI Analysis"])

# ================================
# ENUMS
# ================================

class AnalysisTypeEnum(str, Enum):
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    SENTIMENT = "sentiment"
    CONSENSUS = "consensus"

class RecommendationEnum(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class AIModelEnum(str, Enum):
    GPT4 = "gpt-4"
    DEEPSEEK_R1 = "deepseek-r1"
    GEMINI = "gemini"
    MISTRAL = "mistral"

# ================================
# PYDANTIC MODELS
# ================================

class AnalysisRequest(BaseModel):
    """AI analysis request model"""
    symbols: List[str] = Field(..., description="List of asset symbols to analyze")
    analysis_types: List[AnalysisTypeEnum] = Field(
        default=[AnalysisTypeEnum.CONSENSUS],
        description="Types of analysis to perform"
    )
    timeframe: str = Field(default="1h", description="Analysis timeframe")
    ai_models: List[AIModelEnum] = Field(
        default=[AIModelEnum.GPT4, AIModelEnum.DEEPSEEK_R1],
        description="AI models to use for analysis"
    )
    force_refresh: bool = Field(default=False, description="Force new analysis even if recent data exists")
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbols": ["BTC", "ETH", "AAPL"],
                "analysis_types": ["consensus"],
                "timeframe": "1h",
                "ai_models": ["gpt-4", "deepseek-r1"],
                "force_refresh": False
            }
        }

class AIAnalysisResponse(BaseModel):
    """AI analysis response model"""
    id: str
    asset_symbol: str
    analysis_type: str
    ai_model: str
    recommendation: str
    confidence_score: Decimal
    target_price: Decimal | None
    reasoning: str | None
    key_indicators: Dict[str, Any] | None
    created_at: datetime
    expires_at: datetime | None
    
    # Additional computed fields
    time_to_expiry: int | None = Field(None, description="Minutes until expiry")
    reliability_score: Decimal | None = Field(None, description="Historical accuracy of this AI model")

    class Config:
        from_attributes = True

class ConsensusAnalysis(BaseModel):
    """Multi-AI consensus analysis"""
    asset_symbol: str
    consensus_recommendation: str
    consensus_confidence: Decimal
    target_price_avg: Decimal | None
    target_price_range: Dict[str, Decimal] | None
    analysis_count: int
    model_agreement: Decimal  # Percentage of models that agree
    individual_analyses: List[AIAnalysisResponse]
    risk_assessment: Dict[str, Any]
    created_at: datetime

class MarketSentiment(BaseModel):
    """Overall market sentiment analysis"""
    overall_sentiment: str  # "bullish", "bearish", "neutral"
    confidence_score: Decimal
    sentiment_distribution: Dict[str, int]
    top_bullish_assets: List[Dict[str, Any]]
    top_bearish_assets: List[Dict[str, Any]]
    market_fear_greed: int | None  # Fear & Greed Index
    key_market_drivers: List[str]
    last_updated: datetime

class BacktestRequest(BaseModel):
    """Backtesting request model"""
    strategy_name: str
    symbols: List[str]
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal = Field(default=Decimal("10000"))
    strategy_params: Dict[str, Any] = Field(default_factory=dict)

class BacktestResult(BaseModel):
    """Backtesting result model"""
    strategy_name: str
    total_return: Decimal
    annualized_return: Decimal
    max_drawdown: Decimal
    sharpe_ratio: Decimal
    win_rate: Decimal
    total_trades: int
    profit_factor: Decimal
    avg_trade_duration: timedelta | None
    performance_chart: List[Dict[str, Any]]
    trade_log: List[Dict[str, Any]]

# ================================
# UTILITY FUNCTIONS
# ================================

async def get_asset_by_symbol(symbol: str, db: AsyncSession) -> Asset:
    """Get asset by symbol"""
    result = await db.execute(
        select(Asset).filter(Asset.symbol == symbol.upper())
    )
    asset = result.scalar_one_or_none()
    
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {symbol} not found"
        )
    
    return asset

async def check_existing_analysis(
    asset_id: str,
    analysis_type: str,
    ai_model: str,
    db: AsyncSession,
    max_age_minutes: int = 60
) -> AIAnalysis | None:
    """Check if recent analysis exists"""
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=max_age_minutes)
    
    result = await db.execute(
        select(AIAnalysis)
        .filter(
            AIAnalysis.asset_id == asset_id,
            AIAnalysis.analysis_type == analysis_type,
            AIAnalysis.ai_model == ai_model,
            AIAnalysis.created_at >= cutoff_time
        )
        .order_by(desc(AIAnalysis.created_at))
        .limit(1)
    )
    
    return result.scalar_one_or_none()

async def get_market_data_for_analysis(asset: Asset, timeframe: str) -> Dict[str, Any]:
    """Get market data for AI analysis"""
    
    # Mock market data - in production this would fetch real data
    return {
        "price": 45000.00,
        "volume_24h": 2500000000,
        "change_24h": 2.5,
        "market_cap": 850000000000,
        "ohlcv": [
            {"open": 44800, "high": 45200, "low": 44600, "close": 45000, "volume": 125000},
            {"open": 45000, "high": 45300, "low": 44900, "close": 45100, "volume": 135000}
        ],
        "indicators": {
            "rsi": 65.3,
            "macd": 0.0023,
            "sma_20": 44850.0,
            "sma_50": 43200.0
        }
    }

# ================================
# AI ANALYSIS ENDPOINTS
# ================================

@router.post("/analyze", response_model=List[AIAnalysisResponse])
async def analyze_assets(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Trigger AI analysis for specified assets"""
    
    logger.info("AI analysis request", user_id=str(current_user.id), request=request.dict())
    
    analyses = []
    
    for symbol in request.symbols:
        # Get asset
        asset = await get_asset_by_symbol(symbol, db)
        
        for analysis_type in request.analysis_types:
            for ai_model in request.ai_models:
                # Check for existing recent analysis
                if not request.force_refresh:
                    existing = await check_existing_analysis(
                        str(asset.id), analysis_type.value, ai_model.value, db
                    )
                    if existing:
                        analysis_response = AIAnalysisResponse.from_orm(existing)
                        analysis_response.asset_symbol = asset.symbol
                        if existing.expires_at:
                            analysis_response.time_to_expiry = int(
                                (existing.expires_at - datetime.utcnow()).total_seconds() / 60
                            )
                        analyses.append(analysis_response)
                        continue
                
                # Get market data for analysis
                market_data = await get_market_data_for_analysis(asset, request.timeframe)
                
                # Generate new analysis using real AI services
                if analysis_type.value == "consensus":
                    # Use consensus analysis for consensus type
                    ai_result = await ai_service_manager.analyze_with_consensus(
                        asset.symbol,
                        request.timeframe,
                        analysis_type.value,
                        market_data,
                        [ai_model.value.replace("-", "_")]  # Convert model name format
                    )
                else:
                    # Use specific AI service
                    service_name = ai_model.value.replace("-", "_")
                    if service_name == "gpt_4":
                        service_name = "azure_openai"
                    elif service_name == "deepseek_r1":
                        service_name = "deepseek"
                    elif service_name in ["gemini", "mistral"]:
                        service_name = "ollama"
                    
                    if service_name in ai_service_manager.services:
                        ai_result = await ai_service_manager.services[service_name].analyze_market(
                            asset.symbol,
                            request.timeframe,
                            analysis_type.value,
                            market_data
                        )
                    else:
                        # Fallback to consensus if service not found
                        ai_result = await ai_service_manager.analyze_with_consensus(
                            asset.symbol,
                            request.timeframe,
                            analysis_type.value,
                            market_data,
                            ["azure_openai", "deepseek", "ollama"]
                        )
                
                # Create analysis record
                db_analysis = AIAnalysis(
                    asset_id=asset.id,
                    analysis_type=analysis_type.value,
                    ai_model=ai_model.value,
                    recommendation=ai_result["recommendation"],
                    confidence_score=ai_result["confidence_score"],
                    target_price=ai_result["target_price"],
                    reasoning=ai_result["reasoning"],
                    indicators=ai_result["indicators"],
                    expires_at=ai_result["expires_at"]
                )
                
                db.add(db_analysis)
                await db.commit()
                await db.refresh(db_analysis)
                
                analysis_response = AIAnalysisResponse.from_orm(db_analysis)
                analysis_response.asset_symbol = asset.symbol
                analysis_response.time_to_expiry = int(
                    (db_analysis.expires_at - datetime.utcnow()).total_seconds() / 60
                ) if db_analysis.expires_at else None
                
                analyses.append(analysis_response)
    
    logger.info("AI analysis completed", analyses_count=len(analyses))
    return analyses

@router.get("/analysis/{symbol}", response_model=List[AIAnalysisResponse])
async def get_asset_analysis(
    symbol: str,
    analysis_type: Optional[AnalysisTypeEnum] = Query(None),
    ai_model: Optional[AIModelEnum] = Query(None),
    limit: int = Query(10, le=50),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get AI analysis history for an asset"""
    
    # Get asset
    asset = await get_asset_by_symbol(symbol, db)
    
    # Build query
    query = select(AIAnalysis).filter(AIAnalysis.asset_id == asset.id)
    
    if analysis_type:
        query = query.filter(AIAnalysis.analysis_type == analysis_type.value)
    
    if ai_model:
        query = query.filter(AIAnalysis.ai_model == ai_model.value)
    
    query = query.order_by(desc(AIAnalysis.created_at)).limit(limit)
    
    result = await db.execute(query)
    analyses = result.scalars().all()
    
    # Enhance with computed fields
    enhanced_analyses = []
    for analysis in analyses:
        analysis_response = AIAnalysisResponse.from_orm(analysis)
        analysis_response.asset_symbol = asset.symbol
        
        if analysis.expires_at:
            analysis_response.time_to_expiry = max(0, int(
                (analysis.expires_at - datetime.utcnow()).total_seconds() / 60
            ))
        
        enhanced_analyses.append(analysis_response)
    
    return enhanced_analyses

@router.get("/consensus/{symbol}", response_model=ConsensusAnalysis)
async def get_ai_consensus(
    symbol: str,
    max_age_hours: int = Query(4, ge=1, le=24, description="Maximum age of analysis in hours"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get multi-AI consensus analysis for an asset"""
    
    # Get asset
    asset = await get_asset_by_symbol(symbol, db)
    
    # Get recent analyses
    cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
    
    result = await db.execute(
        select(AIAnalysis)
        .filter(
            AIAnalysis.asset_id == asset.id,
            AIAnalysis.created_at >= cutoff_time
        )
        .order_by(desc(AIAnalysis.created_at))
    )
    analyses = result.scalars().all()
    
    if not analyses:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No recent AI analysis found for {symbol}"
        )
    
    # Calculate consensus
    recommendations = [a.recommendation for a in analyses]
    buy_votes = recommendations.count("BUY")
    sell_votes = recommendations.count("SELL")
    hold_votes = recommendations.count("HOLD")
    total_votes = len(recommendations)
    
    # Determine consensus
    if buy_votes > sell_votes and buy_votes > hold_votes:
        consensus_recommendation = "BUY"
        consensus_confidence = Decimal(str(buy_votes / total_votes))
    elif sell_votes > buy_votes and sell_votes > hold_votes:
        consensus_recommendation = "SELL"
        consensus_confidence = Decimal(str(sell_votes / total_votes))
    else:
        consensus_recommendation = "HOLD"
        consensus_confidence = Decimal(str(hold_votes / total_votes))
    
    # Calculate target price statistics
    target_prices = [a.target_price for a in analyses if a.target_price]
    target_price_avg = None
    target_price_range = None
    
    if target_prices:
        target_price_avg = sum(target_prices) / len(target_prices)
        target_price_range = {
            "min": min(target_prices),
            "max": max(target_prices),
            "median": sorted(target_prices)[len(target_prices) // 2]
        }
    
    # Calculate model agreement
    most_common_rec = max(set(recommendations), key=recommendations.count)
    model_agreement = Decimal(str(recommendations.count(most_common_rec) / total_votes))
    
    # Prepare individual analyses
    individual_analyses = []
    for analysis in analyses:
        analysis_response = AIAnalysisResponse.from_orm(analysis)
        analysis_response.asset_symbol = asset.symbol
        individual_analyses.append(analysis_response)
    
    return ConsensusAnalysis(
        asset_symbol=symbol.upper(),
        consensus_recommendation=consensus_recommendation,
        consensus_confidence=consensus_confidence,
        target_price_avg=target_price_avg,
        target_price_range=target_price_range,
        analysis_count=total_votes,
        model_agreement=model_agreement,
        individual_analyses=individual_analyses,
        risk_assessment={
            "volatility": "medium",
            "confidence_spread": float(max([a.confidence_score for a in analyses]) - min([a.confidence_score for a in analyses])),
            "model_disagreement": 1.0 - float(model_agreement)
        },
        created_at=datetime.utcnow()
    )

@router.get("/sentiment", response_model=MarketSentiment)
async def get_market_sentiment(
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get overall market sentiment analysis"""
    
    # For now, return mock market sentiment
    # TODO: Implement real market sentiment calculation
    
    return MarketSentiment(
        overall_sentiment="neutral",
        confidence_score=Decimal("0.72"),
        sentiment_distribution={
            "bullish": 35,
            "bearish": 28,
            "neutral": 37
        },
        top_bullish_assets=[
            {"symbol": "BTC", "sentiment_score": 0.85},
            {"symbol": "ETH", "sentiment_score": 0.78}
        ],
        top_bearish_assets=[
            {"symbol": "DOGE", "sentiment_score": -0.65}
        ],
        market_fear_greed=52,
        key_market_drivers=[
            "Federal Reserve policy expectations",
            "Cryptocurrency adoption news",
            "Economic inflation data"
        ],
        last_updated=datetime.utcnow()
    )

@router.post("/backtest", response_model=BacktestResult)
async def run_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Run strategy backtesting"""
    
    logger.info("Backtest request", user_id=str(current_user.id), strategy=request.strategy_name)
    
    # TODO: Implement real backtesting engine
    # For now, return mock results
    
    return BacktestResult(
        strategy_name=request.strategy_name,
        total_return=Decimal("15.24"),
        annualized_return=Decimal("18.45"),
        max_drawdown=Decimal("-8.32"),
        sharpe_ratio=Decimal("1.45"),
        win_rate=Decimal("0.68"),
        total_trades=142,
        profit_factor=Decimal("1.82"),
        avg_trade_duration=timedelta(days=3, hours=12),
        performance_chart=[
            {"date": "2024-01-01", "portfolio_value": 10000},
            {"date": "2024-12-31", "portfolio_value": 11524}
        ],
        trade_log=[
            {
                "date": "2024-01-15",
                "symbol": "BTC",
                "action": "buy",
                "quantity": 0.1,
                "price": 42000,
                "pnl": 0
            }
        ]
    )

@router.get("/models", response_model=List[dict])
async def get_ai_models(
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get available AI models and their health status"""
    
    # Check health of all AI services
    health_status = await ai_service_manager.health_check_all()
    
    return [
        {
            "model": "gpt-4",
            "provider": "Azure OpenAI",
            "status": "active" if health_status.get("azure_openai", False) else "unavailable",
            "accuracy_score": 0.78,
            "avg_confidence": 0.82,
            "total_analyses": 1250,
            "specialties": ["fundamental", "consensus"],
            "endpoint_configured": bool(settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT)
        },
        {
            "model": "deepseek-r1",
            "provider": "DeepSeek",
            "status": "active" if health_status.get("deepseek", False) else "unavailable",
            "accuracy_score": 0.75,
            "avg_confidence": 0.79,
            "total_analyses": 980,
            "specialties": ["technical", "sentiment"],
            "endpoint_configured": bool(settings.DEEPSEEK_API_KEY)
        },
        {
            "model": "gemini",
            "provider": "Ollama",
            "status": "active" if health_status.get("ollama", False) else "unavailable",
            "accuracy_score": 0.71,
            "avg_confidence": 0.76,
            "total_analyses": 650,
            "specialties": ["sentiment", "fundamental"],
            "endpoint_configured": True  # Ollama endpoint is always configured
        }
    ]

@router.get("/health", response_model=Dict[str, Any])
async def get_ai_services_health(
    current_user: Annotated[User, Depends(get_current_active_user)] = None
):
    """Get health status of all AI services"""
    
    health_status = await ai_service_manager.health_check_all()
    
    return {
        "overall_status": "healthy" if any(health_status.values()) else "unhealthy",
        "services": health_status,
        "available_services": [k for k, v in health_status.items() if v],
        "unavailable_services": [k for k, v in health_status.items() if not v],
        "total_services": len(health_status),
        "healthy_services": sum(health_status.values()),
        "checked_at": datetime.utcnow().isoformat()
    }