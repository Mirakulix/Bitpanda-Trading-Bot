"""
Risk management router for portfolio risk assessment and alerts
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func, or_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
from enum import Enum
import structlog

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.portfolio import Portfolio, Position, Asset
from app.models.trading import RiskAlert, Order
from app.routers.auth import get_current_active_user

logger = structlog.get_logger()

router = APIRouter(prefix="/risk", tags=["Risk Management"])

# ================================
# ENUMS
# ================================

class AlertTypeEnum(str, Enum):
    DRAWDOWN = "drawdown"
    CONCENTRATION = "concentration"
    VOLATILITY = "volatility"
    STOP_LOSS = "stop_loss"
    MARGIN_CALL = "margin_call"

class SeverityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

# ================================
# PYDANTIC MODELS
# ================================

class RiskMetrics(BaseModel):
    """Portfolio risk metrics model"""
    portfolio_id: str
    total_value: Decimal
    var_1d: Decimal  # Value at Risk (1 day)
    var_7d: Decimal  # Value at Risk (7 days)
    max_drawdown: Decimal
    current_drawdown: Decimal
    sharpe_ratio: Decimal | None
    beta: Decimal | None
    volatility_30d: Decimal
    concentration_risk: Decimal  # % of portfolio in largest position
    correlation_risk: Decimal  # Average correlation between positions
    leverage_ratio: Decimal
    
    # Allocation breakdown
    asset_allocation: Dict[str, Decimal]  # Asset type allocation %
    sector_allocation: Dict[str, Decimal]  # Sector allocation %
    geographic_allocation: Dict[str, Decimal]  # Geographic allocation %
    
    # Risk-adjusted returns
    sortino_ratio: Decimal | None
    calmar_ratio: Decimal | None
    information_ratio: Decimal | None
    
    last_calculated: datetime

    class Config:
        from_attributes = True

class RiskAlertResponse(BaseModel):
    """Risk alert response model"""
    id: str
    portfolio_id: str | None
    alert_type: str
    severity: str
    message: str
    current_value: Decimal | None
    threshold_value: Decimal | None
    is_active: bool
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    
    # Additional context
    portfolio_name: str | None = None
    recommendation: str | None = None
    impact_level: str | None = None

    class Config:
        from_attributes = True

class RiskLimits(BaseModel):
    """Risk limits configuration"""
    max_position_size: Decimal = Field(default=Decimal("0.20"), description="Max position size as % of portfolio")
    max_sector_concentration: Decimal = Field(default=Decimal("0.30"), description="Max sector allocation %")
    max_drawdown_limit: Decimal = Field(default=Decimal("0.15"), description="Max acceptable drawdown %")
    var_limit_1d: Decimal = Field(default=Decimal("0.05"), description="Max 1-day VaR %")
    min_diversification: int = Field(default=5, description="Minimum number of positions")
    max_correlation: Decimal = Field(default=Decimal("0.80"), description="Max correlation between positions")
    stop_loss_buffer: Decimal = Field(default=Decimal("0.02"), description="Stop loss buffer %")

class RiskAssessment(BaseModel):
    """Comprehensive risk assessment"""
    portfolio_id: str
    overall_risk_score: Decimal  # 1-10 scale
    risk_level: str  # "low", "medium", "high", "critical"
    risk_metrics: RiskMetrics
    active_alerts: List[RiskAlertResponse]
    recommendations: List[Dict[str, Any]]
    stress_test_results: Dict[str, Decimal]
    risk_budget_utilization: Decimal  # % of risk budget used
    
    # Forward-looking risks
    potential_risks: List[Dict[str, Any]]
    scenario_analysis: Dict[str, Dict[str, Decimal]]
    
    created_at: datetime

class StressTestScenario(BaseModel):
    """Stress test scenario configuration"""
    name: str
    description: str
    market_shock: Decimal  # Market decline %
    volatility_increase: Decimal  # Volatility increase factor
    correlation_increase: Decimal  # Correlation increase factor
    duration_days: int = Field(default=5, description="Scenario duration in days")

class StressTestRequest(BaseModel):
    """Stress test request model"""
    portfolio_id: str
    scenarios: List[StressTestScenario] = Field(
        default=[
            StressTestScenario(
                name="Market Crash",
                description="30% market decline with increased volatility",
                market_shock=Decimal("-0.30"),
                volatility_increase=Decimal("2.0"),
                correlation_increase=Decimal("1.5")
            ),
            StressTestScenario(
                name="Flash Crash",
                description="15% sudden drop with high correlation",
                market_shock=Decimal("-0.15"),
                volatility_increase=Decimal("3.0"),
                correlation_increase=Decimal("2.0"),
                duration_days=1
            )
        ]
    )

class StressTestResult(BaseModel):
    """Stress test results"""
    portfolio_id: str
    scenario_results: Dict[str, Dict[str, Decimal]]
    worst_case_loss: Decimal
    worst_case_scenario: str
    recovery_time_estimate: int  # Days
    recommendations: List[str]
    hedging_suggestions: List[Dict[str, Any]]
    
    # Risk metrics under stress
    stress_var: Decimal
    stress_max_drawdown: Decimal
    liquidity_risk: Decimal
    
    created_at: datetime

# ================================
# UTILITY FUNCTIONS
# ================================

async def get_user_portfolio(
    portfolio_id: str,
    user: User,
    db: AsyncSession
) -> Portfolio:
    """Get portfolio by ID for current user"""
    result = await db.execute(
        select(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
    )
    portfolio = result.scalar_one_or_none()
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found"
        )
    
    return portfolio

async def calculate_risk_metrics(portfolio: Portfolio, db: AsyncSession) -> RiskMetrics:
    """Calculate comprehensive risk metrics for a portfolio"""
    
    # Get all open positions
    result = await db.execute(
        select(Position)
        .options(selectinload(Position.asset))
        .filter(Position.portfolio_id == portfolio.id, Position.status == "open")
    )
    positions = result.scalars().all()
    
    if not positions:
        # Return default metrics for empty portfolio
        return RiskMetrics(
            portfolio_id=str(portfolio.id),
            total_value=portfolio.current_balance,
            var_1d=Decimal("0.0"),
            var_7d=Decimal("0.0"),
            max_drawdown=Decimal("0.0"),
            current_drawdown=Decimal("0.0"),
            sharpe_ratio=None,
            beta=None,
            volatility_30d=Decimal("0.0"),
            concentration_risk=Decimal("0.0"),
            correlation_risk=Decimal("0.0"),
            leverage_ratio=Decimal("1.0"),
            asset_allocation={},
            sector_allocation={},
            geographic_allocation={},
            sortino_ratio=None,
            calmar_ratio=None,
            information_ratio=None,
            last_calculated=datetime.utcnow()
        )
    
    # Calculate portfolio value
    total_value = portfolio.current_balance
    for position in positions:
        position_value = position.quantity * (position.current_price or position.avg_buy_price)
        total_value += position_value
    
    # Calculate concentration risk (largest position %)
    position_values = [
        position.quantity * (position.current_price or position.avg_buy_price)
        for position in positions
    ]
    largest_position = max(position_values) if position_values else 0
    concentration_risk = (largest_position / total_value * 100) if total_value > 0 else 0
    
    # Calculate asset allocation
    asset_allocation = {}
    for position in positions:
        asset_type = position.asset.asset_type
        position_value = position.quantity * (position.current_price or position.avg_buy_price)
        position_percent = (position_value / total_value * 100) if total_value > 0 else 0
        
        if asset_type in asset_allocation:
            asset_allocation[asset_type] += position_percent
        else:
            asset_allocation[asset_type] = position_percent
    
    # Add cash allocation
    cash_percent = (portfolio.current_balance / total_value * 100) if total_value > 0 else 100
    asset_allocation["cash"] = cash_percent
    
    # Mock calculations for advanced metrics (TODO: implement real calculations)
    var_1d = total_value * Decimal("0.02")  # 2% VaR
    var_7d = total_value * Decimal("0.05")  # 5% VaR
    max_drawdown = Decimal("0.0")
    current_drawdown = Decimal("0.0")
    volatility_30d = Decimal("0.15")  # 15% annualized volatility
    
    return RiskMetrics(
        portfolio_id=str(portfolio.id),
        total_value=total_value,
        var_1d=var_1d,
        var_7d=var_7d,
        max_drawdown=max_drawdown,
        current_drawdown=current_drawdown,
        sharpe_ratio=Decimal("1.2"),
        beta=Decimal("0.8"),
        volatility_30d=volatility_30d,
        concentration_risk=concentration_risk,
        correlation_risk=Decimal("0.6"),
        leverage_ratio=Decimal("1.0"),
        asset_allocation=asset_allocation,
        sector_allocation={"technology": 40, "finance": 30, "energy": 20, "other": 10},
        geographic_allocation={"US": 60, "EU": 25, "Asia": 15},
        sortino_ratio=Decimal("1.5"),
        calmar_ratio=Decimal("0.8"),
        information_ratio=Decimal("0.3"),
        last_calculated=datetime.utcnow()
    )

async def check_risk_limits(portfolio: Portfolio, risk_metrics: RiskMetrics, db: AsyncSession) -> List[Dict[str, Any]]:
    """Check portfolio against risk limits and generate alerts"""
    
    alerts = []
    
    # Check concentration risk
    if risk_metrics.concentration_risk > 25:  # 25% threshold
        alerts.append({
            "type": "concentration",
            "severity": "high" if risk_metrics.concentration_risk > 40 else "medium",
            "message": f"Portfolio concentration risk at {risk_metrics.concentration_risk:.1f}% (recommended max: 25%)",
            "current_value": risk_metrics.concentration_risk,
            "threshold_value": Decimal("25.0")
        })
    
    # Check drawdown
    if risk_metrics.current_drawdown > 10:  # 10% threshold
        alerts.append({
            "type": "drawdown",
            "severity": "critical" if risk_metrics.current_drawdown > 20 else "high",
            "message": f"Portfolio drawdown at {risk_metrics.current_drawdown:.1f}% (max limit: 10%)",
            "current_value": risk_metrics.current_drawdown,
            "threshold_value": Decimal("10.0")
        })
    
    # Check volatility
    if risk_metrics.volatility_30d > 30:  # 30% volatility threshold
        alerts.append({
            "type": "volatility",
            "severity": "medium",
            "message": f"High portfolio volatility at {risk_metrics.volatility_30d:.1f}% (recommended max: 30%)",
            "current_value": risk_metrics.volatility_30d,
            "threshold_value": Decimal("30.0")
        })
    
    return alerts

# ================================
# RISK MANAGEMENT ENDPOINTS
# ================================

@router.get("/metrics/{portfolio_id}", response_model=RiskMetrics)
async def get_risk_metrics(
    portfolio_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive risk metrics for a portfolio"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    risk_metrics = await calculate_risk_metrics(portfolio, db)
    
    logger.info("Risk metrics calculated", portfolio_id=portfolio_id, total_value=risk_metrics.total_value)
    
    return risk_metrics

@router.get("/assessment/{portfolio_id}", response_model=RiskAssessment)
async def get_risk_assessment(
    portfolio_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive risk assessment for a portfolio"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    risk_metrics = await calculate_risk_metrics(portfolio, db)
    
    # Get active alerts
    alerts_result = await db.execute(
        select(RiskAlert)
        .filter(
            RiskAlert.user_id == current_user.id,
            or_(RiskAlert.portfolio_id == portfolio.id, RiskAlert.portfolio_id.is_(None)),
            RiskAlert.is_active == True,
            RiskAlert.resolved_at.is_(None)
        )
        .order_by(desc(RiskAlert.created_at))
    )
    active_alerts = alerts_result.scalars().all()
    
    # Convert to response models
    alert_responses = []
    for alert in active_alerts:
        alert_response = RiskAlertResponse.from_orm(alert)
        alert_response.portfolio_name = portfolio.name if alert.portfolio_id == portfolio.id else None
        alert_responses.append(alert_response)
    
    # Calculate overall risk score (1-10 scale)
    risk_score = min(10, max(1, 
        5 + (risk_metrics.concentration_risk / 10) + 
        (risk_metrics.current_drawdown / 5) + 
        (risk_metrics.volatility_30d / 20)
    ))
    
    # Determine risk level
    if risk_score <= 3:
        risk_level = "low"
    elif risk_score <= 6:
        risk_level = "medium"
    elif risk_score <= 8:
        risk_level = "high"
    else:
        risk_level = "critical"
    
    # Generate recommendations
    recommendations = []
    if risk_metrics.concentration_risk > 20:
        recommendations.append({
            "type": "diversification",
            "priority": "high",
            "message": "Consider reducing position size in largest holdings to improve diversification"
        })
    
    if risk_metrics.current_drawdown > 5:
        recommendations.append({
            "type": "stop_loss",
            "priority": "medium",
            "message": "Review and tighten stop-loss orders to limit further downside"
        })
    
    return RiskAssessment(
        portfolio_id=portfolio_id,
        overall_risk_score=Decimal(str(risk_score)),
        risk_level=risk_level,
        risk_metrics=risk_metrics,
        active_alerts=alert_responses,
        recommendations=recommendations,
        stress_test_results={
            "market_crash_30": Decimal("-25.5"),
            "flash_crash_15": Decimal("-12.8"),
            "volatility_spike": Decimal("-8.3")
        },
        risk_budget_utilization=Decimal("68.5"),
        potential_risks=[
            {
                "risk": "concentration",
                "probability": 0.7,
                "impact": "medium",
                "description": "High concentration in technology sector"
            }
        ],
        scenario_analysis={
            "bull_market": {"return": Decimal("15.2"), "volatility": Decimal("12.5")},
            "bear_market": {"return": Decimal("-18.7"), "volatility": Decimal("28.3")},
            "sideways": {"return": Decimal("2.1"), "volatility": Decimal("8.9")}
        },
        created_at=datetime.utcnow()
    )

@router.get("/alerts", response_model=List[RiskAlertResponse])
async def get_risk_alerts(
    portfolio_id: Optional[str] = Query(None),
    severity: Optional[SeverityEnum] = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(50, le=100),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get risk alerts for user portfolios"""
    
    query = select(RiskAlert).filter(RiskAlert.user_id == current_user.id)
    
    if portfolio_id:
        query = query.filter(RiskAlert.portfolio_id == portfolio_id)
    
    if severity:
        query = query.filter(RiskAlert.severity == severity.value)
    
    if active_only:
        query = query.filter(RiskAlert.is_active == True, RiskAlert.resolved_at.is_(None))
    
    query = query.order_by(desc(RiskAlert.created_at)).limit(limit)
    
    result = await db.execute(query)
    alerts = result.scalars().all()
    
    # Enhance with portfolio names
    alert_responses = []
    for alert in alerts:
        alert_response = RiskAlertResponse.from_orm(alert)
        
        if alert.portfolio_id:
            portfolio_result = await db.execute(
                select(Portfolio.name).filter(Portfolio.id == alert.portfolio_id)
            )
            portfolio_name = portfolio_result.scalar_one_or_none()
            alert_response.portfolio_name = portfolio_name
        
        alert_responses.append(alert_response)
    
    return alert_responses

@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Acknowledge a risk alert"""
    
    # Get alert
    result = await db.execute(
        select(RiskAlert).filter(RiskAlert.id == alert_id, RiskAlert.user_id == current_user.id)
    )
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk alert not found"
        )
    
    # Acknowledge alert
    alert.acknowledged_at = datetime.utcnow()
    await db.commit()
    
    logger.info("Risk alert acknowledged", alert_id=alert_id, user_id=str(current_user.id))
    
    return {"message": "Alert acknowledged successfully"}

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Resolve a risk alert"""
    
    # Get alert
    result = await db.execute(
        select(RiskAlert).filter(RiskAlert.id == alert_id, RiskAlert.user_id == current_user.id)
    )
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk alert not found"
        )
    
    # Resolve alert
    alert.resolved_at = datetime.utcnow()
    alert.is_active = False
    await db.commit()
    
    logger.info("Risk alert resolved", alert_id=alert_id, user_id=str(current_user.id))
    
    return {"message": "Alert resolved successfully"}

@router.post("/stress-test", response_model=StressTestResult)
async def run_stress_test(
    request: StressTestRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Run stress tests on a portfolio"""
    
    portfolio = await get_user_portfolio(request.portfolio_id, current_user, db)
    risk_metrics = await calculate_risk_metrics(portfolio, db)
    
    # Simulate stress test results
    scenario_results = {}
    worst_case_loss = Decimal("0.0")
    worst_case_scenario = ""
    
    for scenario in request.scenarios:
        # Mock stress test calculation
        portfolio_loss = risk_metrics.total_value * scenario.market_shock
        var_under_stress = abs(portfolio_loss) * scenario.volatility_increase
        
        scenario_results[scenario.name] = {
            "portfolio_loss": portfolio_loss,
            "var_impact": var_under_stress,
            "recovery_days": scenario.duration_days * 3,
            "max_drawdown": abs(portfolio_loss / risk_metrics.total_value * 100)
        }
        
        if abs(portfolio_loss) > abs(worst_case_loss):
            worst_case_loss = portfolio_loss
            worst_case_scenario = scenario.name
    
    recommendations = [
        "Consider reducing portfolio concentration in volatile assets",
        "Implement dynamic hedging strategies during high volatility periods",
        "Maintain higher cash reserves during uncertain market conditions"
    ]
    
    hedging_suggestions = [
        {
            "instrument": "VIX Options",
            "strategy": "Buy protective puts during high volatility",
            "cost_estimate": "2-3% of portfolio value"
        }
    ]
    
    logger.info("Stress test completed", portfolio_id=request.portfolio_id, worst_case_loss=worst_case_loss)
    
    return StressTestResult(
        portfolio_id=request.portfolio_id,
        scenario_results=scenario_results,
        worst_case_loss=worst_case_loss,
        worst_case_scenario=worst_case_scenario,
        recovery_time_estimate=15,  # Days
        recommendations=recommendations,
        hedging_suggestions=hedging_suggestions,
        stress_var=risk_metrics.var_1d * Decimal("2.5"),
        stress_max_drawdown=Decimal("22.5"),
        liquidity_risk=Decimal("15.0"),
        created_at=datetime.utcnow()
    )

@router.post("/stop-loss/{portfolio_id}/{symbol}")
async def set_stop_loss(
    portfolio_id: str,
    symbol: str,
    stop_price: Decimal = Query(..., gt=0, description="Stop loss price"),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Set or update stop loss for a position"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    
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
    
    # Get position
    position_result = await db.execute(
        select(Position)
        .filter(
            Position.portfolio_id == portfolio.id,
            Position.asset_id == asset.id,
            Position.status == "open"
        )
    )
    position = position_result.scalar_one_or_none()
    
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No open position found for {symbol}"
        )
    
    # Update stop loss
    position.stop_loss_price = stop_price
    await db.commit()
    
    logger.info("Stop loss updated", portfolio_id=portfolio_id, symbol=symbol, stop_price=stop_price)
    
    return {"message": f"Stop loss set at {stop_price} for {symbol}"}

@router.get("/limits", response_model=RiskLimits)
async def get_risk_limits(
    current_user: Annotated[User, Depends(get_current_active_user)] = None
):
    """Get current risk limits configuration"""
    
    # For now, return default limits
    # TODO: Implement user-specific risk limits storage
    
    return RiskLimits()

@router.put("/limits", response_model=RiskLimits)
async def update_risk_limits(
    limits: RiskLimits,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update risk limits configuration"""
    
    # TODO: Implement user-specific risk limits storage in database
    
    logger.info("Risk limits updated", user_id=str(current_user.id), limits=limits.dict())
    
    return limits