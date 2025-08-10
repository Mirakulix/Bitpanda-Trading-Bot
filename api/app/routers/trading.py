"""
Trading router for order management and trade execution
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, or_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
from enum import Enum
import structlog

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.models.portfolio import Portfolio, Position, Asset
from app.models.trading import Order
from app.routers.auth import get_current_active_user

logger = structlog.get_logger()

router = APIRouter(prefix="/trading", tags=["Trading"])

# ================================
# ENUMS
# ================================

class OrderTypeEnum(str, Enum):
    BUY = "buy"
    SELL = "sell"
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"

class OrderStatusEnum(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    PARTIAL = "partial"

class TimeInForceEnum(str, Enum):
    GTC = "good_till_cancelled"
    IOC = "immediate_or_cancel"
    FOK = "fill_or_kill"
    DAY = "day"

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
    current_price: Decimal | None = None

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    """Order creation model"""
    portfolio_id: str
    asset_symbol: str
    order_type: OrderTypeEnum
    quantity: Decimal = Field(..., gt=0, description="Quantity to buy/sell")
    price: Decimal | None = Field(None, gt=0, description="Limit price (required for limit orders)")
    stop_price: Decimal | None = Field(None, gt=0, description="Stop price for stop orders")
    time_in_force: TimeInForceEnum = TimeInForceEnum.GTC
    
    class Config:
        json_schema_extra = {
            "example": {
                "portfolio_id": "123e4567-e89b-12d3-a456-426614174000",
                "asset_symbol": "BTC",
                "order_type": "buy",
                "quantity": "0.01",
                "price": "45000.00",
                "time_in_force": "good_till_cancelled"
            }
        }

class OrderResponse(BaseModel):
    """Order response model"""
    id: str
    portfolio_id: str
    position_id: str | None
    asset: AssetResponse
    order_type: str
    quantity: Decimal
    price: Decimal | None
    stop_price: Decimal | None
    status: str
    executed_quantity: Decimal
    executed_price: Decimal | None
    created_at: datetime
    executed_at: datetime | None
    cancelled_at: datetime | None
    external_order_id: str | None
    fee_amount: Decimal
    fee_currency: str | None
    
    # Calculated fields
    remaining_quantity: Decimal = Field(description="Remaining quantity to execute")
    total_value: Decimal | None = Field(None, description="Total order value")
    fill_percentage: Decimal = Field(description="Percentage filled")

    class Config:
        from_attributes = True

class QuickTradeRequest(BaseModel):
    """Quick trade request (market order)"""
    portfolio_id: str
    asset_symbol: str
    side: str = Field(..., regex="^(buy|sell)$")
    amount_eur: Decimal | None = Field(None, gt=0, description="Amount in EUR to trade")
    quantity: Decimal | None = Field(None, gt=0, description="Specific quantity to trade")
    
    class Config:
        json_schema_extra = {
            "example": {
                "portfolio_id": "123e4567-e89b-12d3-a456-426614174000",
                "asset_symbol": "BTC",
                "side": "buy",
                "amount_eur": "1000.00"
            }
        }

class TradeExecutionResponse(BaseModel):
    """Trade execution response"""
    order_id: str
    status: str
    executed_quantity: Decimal
    executed_price: Decimal | None
    total_value: Decimal
    fee_amount: Decimal
    net_amount: Decimal
    message: str

class OrderUpdate(BaseModel):
    """Order update model"""
    price: Decimal | None = Field(None, gt=0)
    stop_price: Decimal | None = Field(None, gt=0)
    quantity: Decimal | None = Field(None, gt=0)

class TradingStats(BaseModel):
    """Trading statistics model"""
    total_orders: int
    executed_orders: int
    cancelled_orders: int
    failed_orders: int
    total_volume_eur: Decimal
    total_fees_eur: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    largest_win: Decimal
    largest_loss: Decimal
    average_win: Decimal
    average_loss: Decimal

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

async def get_asset_by_symbol(symbol: str, db: AsyncSession) -> Asset:
    """Get asset by symbol"""
    result = await db.execute(
        select(Asset).filter(Asset.symbol == symbol.upper(), Asset.is_active == True)
    )
    asset = result.scalar_one_or_none()
    
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {symbol} not found or not tradeable"
        )
    
    return asset

async def validate_order_limits(
    user: User,
    portfolio: Portfolio,
    order_value: Decimal,
    db: AsyncSession
) -> None:
    """Validate order against user and system limits"""
    
    # Check minimum trade amount
    if order_value < settings.MIN_TRADE_AMOUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order value must be at least {settings.MIN_TRADE_AMOUNT} EUR"
        )
    
    # Check daily trade limit
    today = datetime.utcnow().date()
    result = await db.execute(
        select(func.count(Order.id))
        .filter(
            Order.portfolio_id == portfolio.id,
            func.date(Order.created_at) == today
        )
    )
    daily_trades = result.scalar() or 0
    
    if daily_trades >= settings.MAX_DAILY_TRADES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily trading limit of {settings.MAX_DAILY_TRADES} orders reached"
        )
    
    # Check portfolio balance for buy orders
    if order_value > portfolio.current_balance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient portfolio balance"
        )

async def simulate_order_execution(order: Order) -> dict:
    """Simulate order execution for paper trading"""
    
    # In paper trading mode, simulate immediate execution at current price
    # TODO: Replace with actual Bitpanda API integration
    
    if settings.PAPER_TRADING_MODE:
        # Simulate execution
        execution_price = order.price or Decimal("45000.00")  # Mock price
        fee_rate = Decimal("0.0015")  # 0.15% fee
        fee_amount = order.quantity * execution_price * fee_rate
        
        return {
            "status": "executed",
            "executed_quantity": order.quantity,
            "executed_price": execution_price,
            "fee_amount": fee_amount,
            "fee_currency": "EUR",
            "external_order_id": f"PAPER_{order.id}",
            "executed_at": datetime.utcnow()
        }
    else:
        # TODO: Implement real Bitpanda API integration
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Live trading not yet implemented"
        )

async def update_position_from_order(order: Order, execution_result: dict, db: AsyncSession) -> None:
    """Update or create position based on order execution"""
    
    if order.order_type == "buy":
        # Find existing position or create new one
        result = await db.execute(
            select(Position)
            .filter(
                Position.portfolio_id == order.portfolio_id,
                Position.asset_id == order.asset_id,
                Position.status == "open"
            )
        )
        position = result.scalar_one_or_none()
        
        if position:
            # Update existing position
            total_cost = (position.quantity * position.avg_buy_price) + (execution_result["executed_quantity"] * execution_result["executed_price"])
            total_quantity = position.quantity + execution_result["executed_quantity"]
            position.avg_buy_price = total_cost / total_quantity
            position.quantity = total_quantity
        else:
            # Create new position
            position = Position(
                portfolio_id=order.portfolio_id,
                asset_id=order.asset_id,
                quantity=execution_result["executed_quantity"],
                avg_buy_price=execution_result["executed_price"],
                current_price=execution_result["executed_price"],
                status="open"
            )
            db.add(position)
        
        # Update portfolio balance
        portfolio_result = await db.execute(select(Portfolio).filter(Portfolio.id == order.portfolio_id))
        portfolio = portfolio_result.scalar_one()
        total_cost = execution_result["executed_quantity"] * execution_result["executed_price"] + execution_result["fee_amount"]
        portfolio.current_balance -= total_cost
        
    elif order.order_type == "sell":
        # Update existing position
        result = await db.execute(
            select(Position)
            .filter(
                Position.portfolio_id == order.portfolio_id,
                Position.asset_id == order.asset_id,
                Position.status == "open"
            )
        )
        position = result.scalar_one_or_none()
        
        if not position or position.quantity < execution_result["executed_quantity"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient position quantity for sell order"
            )
        
        # Calculate P&L
        sell_proceeds = execution_result["executed_quantity"] * execution_result["executed_price"]
        cost_basis = execution_result["executed_quantity"] * position.avg_buy_price
        realized_pnl = sell_proceeds - cost_basis - execution_result["fee_amount"]
        
        # Update position
        position.quantity -= execution_result["executed_quantity"]
        position.realized_pnl += realized_pnl
        
        if position.quantity == 0:
            position.status = "closed"
            position.closed_at = datetime.utcnow()
        
        # Update portfolio balance
        portfolio_result = await db.execute(select(Portfolio).filter(Portfolio.id == order.portfolio_id))
        portfolio = portfolio_result.scalar_one()
        portfolio.current_balance += sell_proceeds - execution_result["fee_amount"]
        portfolio.total_profit_loss += realized_pnl

# ================================
# TRADING ENDPOINTS
# ================================

@router.get("/assets", response_model=List[AssetResponse])
async def get_tradeable_assets(
    asset_type: Optional[str] = Query(None, description="Filter by asset type"),
    search: Optional[str] = Query(None, description="Search by symbol or name"),
    limit: int = Query(50, le=100, description="Maximum number of assets to return"),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get list of tradeable assets"""
    
    query = select(Asset).filter(Asset.is_active == True)
    
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    
    if search:
        search_term = f"%{search.upper()}%"
        query = query.filter(
            or_(
                Asset.symbol.ilike(search_term),
                Asset.name.ilike(search_term)
            )
        )
    
    query = query.limit(limit).order_by(Asset.symbol)
    
    result = await db.execute(query)
    assets = result.scalars().all()
    
    return [AssetResponse.from_orm(asset) for asset in assets]

@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Create a new trading order"""
    
    logger.info("Creating order", user_id=str(current_user.id), order_data=order_data.dict())
    
    # Validate portfolio
    portfolio = await get_user_portfolio(order_data.portfolio_id, current_user, db)
    
    # Validate asset
    asset = await get_asset_by_symbol(order_data.asset_symbol, db)
    
    # Validate order parameters
    if order_data.order_type in ["limit", "stop_loss", "take_profit"] and not order_data.price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Price is required for limit and stop orders"
        )
    
    # Calculate order value
    estimated_price = order_data.price or Decimal("45000.00")  # Mock current price
    order_value = order_data.quantity * estimated_price
    
    # Validate limits
    await validate_order_limits(current_user, portfolio, order_value, db)
    
    # Create order
    db_order = Order(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        order_type=order_data.order_type.value,
        quantity=order_data.quantity,
        price=order_data.price,
        stop_price=order_data.stop_price,
        status="pending"
    )
    
    db.add(db_order)
    await db.commit()
    await db.refresh(db_order)
    
    # Execute order in background for market orders
    if order_data.order_type in ["market", "buy", "sell"]:
        background_tasks.add_task(execute_order_async, db_order.id)
    
    logger.info("Order created", order_id=str(db_order.id))
    
    # Prepare response
    order_response = OrderResponse.from_orm(db_order)
    order_response.asset = AssetResponse.from_orm(asset)
    order_response.remaining_quantity = db_order.quantity - db_order.executed_quantity
    order_response.fill_percentage = (db_order.executed_quantity / db_order.quantity * 100) if db_order.quantity > 0 else 0
    order_response.total_value = (db_order.price or estimated_price) * db_order.quantity
    
    return order_response

@router.post("/quick-trade", response_model=TradeExecutionResponse)
async def quick_trade(
    trade_data: QuickTradeRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Execute a quick market trade"""
    
    logger.info("Quick trade request", user_id=str(current_user.id), trade_data=trade_data.dict())
    
    # Validate portfolio
    portfolio = await get_user_portfolio(trade_data.portfolio_id, current_user, db)
    
    # Validate asset
    asset = await get_asset_by_symbol(trade_data.asset_symbol, db)
    
    # Calculate quantity if amount_eur is provided
    current_price = Decimal("45000.00")  # Mock current price
    if trade_data.amount_eur and not trade_data.quantity:
        trade_data.quantity = trade_data.amount_eur / current_price
    elif not trade_data.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either amount_eur or quantity must be provided"
        )
    
    # Create and execute market order
    order_create = OrderCreate(
        portfolio_id=trade_data.portfolio_id,
        asset_symbol=trade_data.asset_symbol,
        order_type=OrderTypeEnum.MARKET,
        quantity=trade_data.quantity
    )
    
    # Create order
    db_order = Order(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        order_type=trade_data.side,
        quantity=trade_data.quantity,
        status="pending"
    )
    
    db.add(db_order)
    await db.commit()
    await db.refresh(db_order)
    
    # Execute immediately
    execution_result = await simulate_order_execution(db_order)
    
    # Update order with execution results
    db_order.status = execution_result["status"]
    db_order.executed_quantity = execution_result["executed_quantity"]
    db_order.executed_price = execution_result["executed_price"]
    db_order.fee_amount = execution_result["fee_amount"]
    db_order.fee_currency = execution_result["fee_currency"]
    db_order.external_order_id = execution_result["external_order_id"]
    db_order.executed_at = execution_result["executed_at"]
    
    # Update position
    await update_position_from_order(db_order, execution_result, db)
    
    await db.commit()
    
    logger.info("Quick trade executed", order_id=str(db_order.id))
    
    total_value = execution_result["executed_quantity"] * execution_result["executed_price"]
    net_amount = total_value - execution_result["fee_amount"]
    
    return TradeExecutionResponse(
        order_id=str(db_order.id),
        status=execution_result["status"],
        executed_quantity=execution_result["executed_quantity"],
        executed_price=execution_result["executed_price"],
        total_value=total_value,
        fee_amount=execution_result["fee_amount"],
        net_amount=net_amount,
        message="Trade executed successfully"
    )

@router.get("/orders", response_model=List[OrderResponse])
async def get_orders(
    portfolio_id: Optional[str] = Query(None),
    status: Optional[OrderStatusEnum] = Query(None),
    asset_symbol: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get orders with filtering options"""
    
    # Base query
    query = (
        select(Order)
        .options(selectinload(Order.asset))
        .join(Portfolio)
        .filter(Portfolio.user_id == current_user.id)
    )
    
    # Apply filters
    if portfolio_id:
        query = query.filter(Order.portfolio_id == portfolio_id)
    
    if status:
        query = query.filter(Order.status == status.value)
    
    if asset_symbol:
        query = query.join(Asset).filter(Asset.symbol == asset_symbol.upper())
    
    # Order and paginate
    query = query.order_by(desc(Order.created_at)).offset(offset).limit(limit)
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    # Enhance with calculated fields
    enhanced_orders = []
    for order in orders:
        order_response = OrderResponse.from_orm(order)
        order_response.asset = AssetResponse.from_orm(order.asset)
        order_response.remaining_quantity = order.quantity - order.executed_quantity
        order_response.fill_percentage = (order.executed_quantity / order.quantity * 100) if order.quantity > 0 else 0
        
        if order.price:
            order_response.total_value = order.price * order.quantity
        
        enhanced_orders.append(order_response)
    
    return enhanced_orders

@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get specific order by ID"""
    
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.asset))
        .join(Portfolio)
        .filter(Order.id == order_id, Portfolio.user_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    order_response = OrderResponse.from_orm(order)
    order_response.asset = AssetResponse.from_orm(order.asset)
    order_response.remaining_quantity = order.quantity - order.executed_quantity
    order_response.fill_percentage = (order.executed_quantity / order.quantity * 100) if order.quantity > 0 else 0
    
    if order.price:
        order_response.total_value = order.price * order.quantity
    
    return order_response

@router.put("/orders/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: str,
    order_update: OrderUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update a pending order"""
    
    # Get order
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.asset))
        .join(Portfolio)
        .filter(Order.id == order_id, Portfolio.user_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only update pending orders"
        )
    
    # Update fields
    if order_update.price is not None:
        order.price = order_update.price
    
    if order_update.stop_price is not None:
        order.stop_price = order_update.stop_price
    
    if order_update.quantity is not None:
        order.quantity = order_update.quantity
    
    await db.commit()
    await db.refresh(order)
    
    logger.info("Order updated", order_id=order_id)
    
    order_response = OrderResponse.from_orm(order)
    order_response.asset = AssetResponse.from_orm(order.asset)
    order_response.remaining_quantity = order.quantity - order.executed_quantity
    order_response.fill_percentage = (order.executed_quantity / order.quantity * 100) if order.quantity > 0 else 0
    
    return order_response

@router.delete("/orders/{order_id}")
async def cancel_order(
    order_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Cancel a pending order"""
    
    # Get order
    result = await db.execute(
        select(Order)
        .join(Portfolio)
        .filter(Order.id == order_id, Portfolio.user_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only cancel pending orders"
        )
    
    # Cancel order
    order.status = "cancelled"
    order.cancelled_at = datetime.utcnow()
    
    await db.commit()
    
    logger.info("Order cancelled", order_id=order_id)
    
    return {"message": "Order cancelled successfully"}

@router.get("/stats", response_model=TradingStats)
async def get_trading_stats(
    portfolio_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get trading statistics"""
    
    # Base query for user's orders
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = (
        select(Order)
        .join(Portfolio)
        .filter(
            Portfolio.user_id == current_user.id,
            Order.created_at >= start_date
        )
    )
    
    if portfolio_id:
        query = query.filter(Order.portfolio_id == portfolio_id)
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    # Calculate statistics
    total_orders = len(orders)
    executed_orders = len([o for o in orders if o.status == "executed"])
    cancelled_orders = len([o for o in orders if o.status == "cancelled"])
    failed_orders = len([o for o in orders if o.status == "failed"])
    
    # Calculate volume and fees
    executed_order_list = [o for o in orders if o.status == "executed"]
    total_volume_eur = sum(
        (o.executed_quantity or 0) * (o.executed_price or 0) for o in executed_order_list
    )
    total_fees_eur = sum(o.fee_amount or 0 for o in executed_order_list)
    
    # TODO: Calculate win/loss statistics from positions
    win_rate = Decimal("0.0")
    profit_factor = Decimal("0.0")
    largest_win = Decimal("0.0")
    largest_loss = Decimal("0.0")
    average_win = Decimal("0.0")
    average_loss = Decimal("0.0")
    
    return TradingStats(
        total_orders=total_orders,
        executed_orders=executed_orders,
        cancelled_orders=cancelled_orders,
        failed_orders=failed_orders,
        total_volume_eur=total_volume_eur,
        total_fees_eur=total_fees_eur,
        win_rate=win_rate,
        profit_factor=profit_factor,
        largest_win=largest_win,
        largest_loss=largest_loss,
        average_win=average_win,
        average_loss=average_loss
    )

# ================================
# BACKGROUND TASKS
# ================================

async def execute_order_async(order_id: str):
    """Execute order asynchronously"""
    # This would be called as a background task
    # Implementation would depend on the specific trading engine
    pass