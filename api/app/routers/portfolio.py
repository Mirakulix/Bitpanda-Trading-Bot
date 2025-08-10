"""
Portfolio management router for portfolio operations and position tracking
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
import structlog

from app.core.database import get_db
from app.models.user import User
from app.models.portfolio import Portfolio, Position, Asset
from app.models.trading import Order
from app.models.market import PortfolioHistory
from app.routers.auth import get_current_active_user

logger = structlog.get_logger()

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

# ================================
# PYDANTIC MODELS
# ================================

class AssetResponse(BaseModel):
    """Asset response model"""
    id: str
    symbol: str
    name: str
    asset_type: str
    exchange: str | None
    is_active: bool
    sector: str | None
    market_cap: Decimal | None

    class Config:
        from_attributes = True

class PositionResponse(BaseModel):
    """Position response model"""
    id: str
    asset: AssetResponse
    quantity: Decimal
    avg_buy_price: Decimal
    current_price: Decimal | None
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    status: str
    opened_at: datetime
    closed_at: datetime | None
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    
    # Calculated fields
    current_value: Decimal | None = None
    pnl_percentage: Decimal | None = None

    class Config:
        from_attributes = True

class PortfolioResponse(BaseModel):
    """Portfolio response model"""
    id: str
    name: str
    initial_balance: Decimal
    current_balance: Decimal
    total_invested: Decimal
    total_profit_loss: Decimal
    created_at: datetime
    updated_at: datetime
    
    # Summary fields
    total_value: Decimal = Field(description="Total portfolio value (cash + positions)")
    unrealized_pnl: Decimal = Field(description="Total unrealized P&L")
    realized_pnl: Decimal = Field(description="Total realized P&L")
    positions_count: int = Field(description="Number of open positions")
    performance_1d: Decimal | None = Field(None, description="1-day performance %")
    performance_7d: Decimal | None = Field(None, description="7-day performance %")
    performance_30d: Decimal | None = Field(None, description="30-day performance %")

    class Config:
        from_attributes = True

class PortfolioCreate(BaseModel):
    """Portfolio creation model"""
    name: str = Field(..., min_length=1, max_length=100)
    initial_balance: Decimal = Field(..., gt=0, description="Initial balance in EUR")

class PortfolioUpdate(BaseModel):
    """Portfolio update model"""
    name: str | None = Field(None, min_length=1, max_length=100)

class PortfolioSummary(BaseModel):
    """Portfolio summary model"""
    total_value: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    total_pnl_percentage: Decimal
    positions_count: int
    active_orders_count: int
    largest_position: str | None
    largest_position_value: Decimal | None
    risk_metrics: dict

class PerformanceMetrics(BaseModel):
    """Performance metrics model"""
    total_return: Decimal
    annualized_return: Decimal
    sharpe_ratio: Decimal
    max_drawdown: Decimal
    volatility: Decimal
    win_rate: Decimal
    profit_factor: Decimal

class HistoryEntry(BaseModel):
    """Portfolio history entry"""
    timestamp: datetime
    total_value: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal

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

async def calculate_portfolio_summary(portfolio: Portfolio, db: AsyncSession) -> dict:
    """Calculate portfolio summary with metrics"""
    
    # Get all open positions
    result = await db.execute(
        select(Position)
        .options(selectinload(Position.asset))
        .filter(Position.portfolio_id == portfolio.id, Position.status == "open")
    )
    positions = result.scalars().all()
    
    # Calculate metrics
    total_invested = sum(pos.quantity * pos.avg_buy_price for pos in positions)
    current_value = portfolio.current_balance + sum(
        pos.quantity * (pos.current_price or pos.avg_buy_price) for pos in positions
    )
    unrealized_pnl = sum(pos.unrealized_pnl or 0 for pos in positions)
    realized_pnl = sum(pos.realized_pnl or 0 for pos in positions)
    total_pnl = unrealized_pnl + realized_pnl
    total_pnl_percentage = (total_pnl / portfolio.initial_balance * 100) if portfolio.initial_balance > 0 else 0
    
    # Get active orders count
    orders_result = await db.execute(
        select(func.count(Order.id))
        .filter(Order.portfolio_id == portfolio.id, Order.status == "pending")
    )
    active_orders_count = orders_result.scalar() or 0
    
    # Find largest position
    largest_position = None
    largest_position_value = None
    if positions:
        largest_pos = max(positions, key=lambda p: p.quantity * (p.current_price or p.avg_buy_price))
        largest_position = largest_pos.asset.symbol
        largest_position_value = largest_pos.quantity * (largest_pos.current_price or largest_pos.avg_buy_price)
    
    # Basic risk metrics
    portfolio_value = current_value or 1  # Avoid division by zero
    risk_metrics = {
        "concentration_risk": (largest_position_value / portfolio_value * 100) if largest_position_value else 0,
        "cash_allocation": (portfolio.current_balance / portfolio_value * 100),
        "equity_allocation": ((portfolio_value - portfolio.current_balance) / portfolio_value * 100),
        "position_count": len(positions)
    }
    
    return {
        "total_value": current_value,
        "cash_balance": portfolio.current_balance,
        "invested_value": total_invested,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "total_pnl": total_pnl,
        "total_pnl_percentage": total_pnl_percentage,
        "positions_count": len(positions),
        "active_orders_count": active_orders_count,
        "largest_position": largest_position,
        "largest_position_value": largest_position_value,
        "risk_metrics": risk_metrics
    }

# ================================
# PORTFOLIO ENDPOINTS
# ================================

@router.get("/", response_model=List[PortfolioResponse])
async def get_user_portfolios(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get all portfolios for the current user"""
    
    logger.info("Fetching user portfolios", user_id=str(current_user.id))
    
    result = await db.execute(
        select(Portfolio)
        .filter(Portfolio.user_id == current_user.id)
        .order_by(desc(Portfolio.created_at))
    )
    portfolios = result.scalars().all()
    
    # Enhance portfolios with summary data
    enhanced_portfolios = []
    for portfolio in portfolios:
        summary = await calculate_portfolio_summary(portfolio, db)
        
        portfolio_response = PortfolioResponse(
            id=str(portfolio.id),
            name=portfolio.name,
            initial_balance=portfolio.initial_balance,
            current_balance=portfolio.current_balance,
            total_invested=portfolio.total_invested,
            total_profit_loss=portfolio.total_profit_loss,
            created_at=portfolio.created_at,
            updated_at=portfolio.updated_at,
            total_value=summary["total_value"],
            unrealized_pnl=summary["unrealized_pnl"],
            realized_pnl=summary["realized_pnl"],
            positions_count=summary["positions_count"]
        )
        enhanced_portfolios.append(portfolio_response)
    
    return enhanced_portfolios

@router.post("/", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    portfolio_data: PortfolioCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Create a new portfolio"""
    
    logger.info("Creating new portfolio", user_id=str(current_user.id), portfolio_name=portfolio_data.name)
    
    # Check if portfolio name already exists for user
    result = await db.execute(
        select(Portfolio)
        .filter(Portfolio.user_id == current_user.id, Portfolio.name == portfolio_data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portfolio name already exists"
        )
    
    # Create new portfolio
    db_portfolio = Portfolio(
        user_id=current_user.id,
        name=portfolio_data.name,
        initial_balance=portfolio_data.initial_balance,
        current_balance=portfolio_data.initial_balance,
        total_invested=0,
        total_profit_loss=0
    )
    
    db.add(db_portfolio)
    await db.commit()
    await db.refresh(db_portfolio)
    
    logger.info("Portfolio created", portfolio_id=str(db_portfolio.id))
    
    return PortfolioResponse(
        id=str(db_portfolio.id),
        name=db_portfolio.name,
        initial_balance=db_portfolio.initial_balance,
        current_balance=db_portfolio.current_balance,
        total_invested=db_portfolio.total_invested,
        total_profit_loss=db_portfolio.total_profit_loss,
        created_at=db_portfolio.created_at,
        updated_at=db_portfolio.updated_at,
        total_value=db_portfolio.current_balance,
        unrealized_pnl=0,
        realized_pnl=0,
        positions_count=0
    )

@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get specific portfolio by ID"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    summary = await calculate_portfolio_summary(portfolio, db)
    
    return PortfolioResponse(
        id=str(portfolio.id),
        name=portfolio.name,
        initial_balance=portfolio.initial_balance,
        current_balance=portfolio.current_balance,
        total_invested=portfolio.total_invested,
        total_profit_loss=portfolio.total_profit_loss,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        total_value=summary["total_value"],
        unrealized_pnl=summary["unrealized_pnl"],
        realized_pnl=summary["realized_pnl"],
        positions_count=summary["positions_count"]
    )

@router.put("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: str,
    portfolio_update: PortfolioUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update portfolio settings"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    
    if portfolio_update.name is not None:
        # Check if new name already exists
        result = await db.execute(
            select(Portfolio)
            .filter(
                Portfolio.user_id == current_user.id,
                Portfolio.name == portfolio_update.name,
                Portfolio.id != portfolio.id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Portfolio name already exists"
            )
        portfolio.name = portfolio_update.name
    
    await db.commit()
    await db.refresh(portfolio)
    
    logger.info("Portfolio updated", portfolio_id=str(portfolio.id))
    
    summary = await calculate_portfolio_summary(portfolio, db)
    
    return PortfolioResponse(
        id=str(portfolio.id),
        name=portfolio.name,
        initial_balance=portfolio.initial_balance,
        current_balance=portfolio.current_balance,
        total_invested=portfolio.total_invested,
        total_profit_loss=portfolio.total_profit_loss,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        total_value=summary["total_value"],
        unrealized_pnl=summary["unrealized_pnl"],
        realized_pnl=summary["realized_pnl"],
        positions_count=summary["positions_count"]
    )

@router.delete("/{portfolio_id}")
async def delete_portfolio(
    portfolio_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Delete a portfolio (only if no active positions)"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    
    # Check for active positions
    result = await db.execute(
        select(func.count(Position.id))
        .filter(Position.portfolio_id == portfolio.id, Position.status == "open")
    )
    active_positions = result.scalar() or 0
    
    if active_positions > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete portfolio with active positions"
        )
    
    # Check for pending orders
    result = await db.execute(
        select(func.count(Order.id))
        .filter(Order.portfolio_id == portfolio.id, Order.status == "pending")
    )
    pending_orders = result.scalar() or 0
    
    if pending_orders > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete portfolio with pending orders"
        )
    
    await db.delete(portfolio)
    await db.commit()
    
    logger.info("Portfolio deleted", portfolio_id=str(portfolio.id))
    
    return {"message": "Portfolio deleted successfully"}

# ================================
# PORTFOLIO SUMMARY ENDPOINTS
# ================================

@router.get("/{portfolio_id}/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    portfolio_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive portfolio summary"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    summary = await calculate_portfolio_summary(portfolio, db)
    
    return PortfolioSummary(**summary)

@router.get("/{portfolio_id}/positions", response_model=List[PositionResponse])
async def get_portfolio_positions(
    portfolio_id: str,
    status_filter: Optional[str] = Query(None, description="Filter by position status"),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get all positions in a portfolio"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    
    # Build query
    query = (
        select(Position)
        .options(selectinload(Position.asset))
        .filter(Position.portfolio_id == portfolio.id)
    )
    
    if status_filter:
        query = query.filter(Position.status == status_filter)
    
    query = query.order_by(desc(Position.opened_at))
    
    result = await db.execute(query)
    positions = result.scalars().all()
    
    # Enhance positions with calculated fields
    enhanced_positions = []
    for position in positions:
        current_value = None
        pnl_percentage = None
        
        if position.current_price and position.quantity:
            current_value = position.quantity * position.current_price
            if position.avg_buy_price > 0:
                pnl_percentage = ((position.current_price - position.avg_buy_price) / position.avg_buy_price * 100)
        
        pos_response = PositionResponse.from_orm(position)
        pos_response.current_value = current_value
        pos_response.pnl_percentage = pnl_percentage
        
        enhanced_positions.append(pos_response)
    
    return enhanced_positions

@router.get("/{portfolio_id}/history", response_model=List[HistoryEntry])
async def get_portfolio_history(
    portfolio_id: str,
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get portfolio value history for charting"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    result = await db.execute(
        select(PortfolioHistory)
        .filter(
            PortfolioHistory.portfolio_id == portfolio.id,
            PortfolioHistory.time >= start_date
        )
        .order_by(PortfolioHistory.time)
    )
    history = result.scalars().all()
    
    return [
        HistoryEntry(
            timestamp=entry.time,
            total_value=entry.total_value,
            cash_balance=entry.cash_balance,
            invested_value=entry.invested_value,
            unrealized_pnl=entry.unrealized_pnl,
            realized_pnl=entry.realized_pnl
        )
        for entry in history
    ]

@router.get("/{portfolio_id}/performance", response_model=PerformanceMetrics)
async def get_portfolio_performance(
    portfolio_id: str,
    days: int = Query(30, ge=1, le=365, description="Performance calculation period"),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get portfolio performance metrics"""
    
    portfolio = await get_user_portfolio(portfolio_id, current_user, db)
    
    # For now, return basic metrics
    # TODO: Implement comprehensive performance calculation
    return PerformanceMetrics(
        total_return=Decimal("0.0"),
        annualized_return=Decimal("0.0"),
        sharpe_ratio=Decimal("0.0"),
        max_drawdown=Decimal("0.0"),
        volatility=Decimal("0.0"),
        win_rate=Decimal("0.0"),
        profit_factor=Decimal("0.0")
    )