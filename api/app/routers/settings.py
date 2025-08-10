"""
Settings router for user and system configuration management
"""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, Field, validator
import structlog

from app.core.database import get_db
from app.core.config import settings as app_settings
from app.models.user import User
from app.models.trading import SystemConfig
from app.routers.auth import get_current_active_user

logger = structlog.get_logger()

router = APIRouter(prefix="/settings", tags=["Settings"])

# ================================
# PYDANTIC MODELS
# ================================

class TradingSettings(BaseModel):
    """Trading configuration settings"""
    auto_trading_enabled: bool = Field(default=False, description="Enable automated trading")
    paper_trading_mode: bool = Field(default=True, description="Use paper trading mode")
    max_daily_trades: int = Field(default=50, ge=1, le=1000, description="Maximum trades per day")
    min_trade_amount: Decimal = Field(default=Decimal("10.0"), gt=0, description="Minimum trade amount in EUR")
    max_position_size: Decimal = Field(default=Decimal("0.2"), gt=0, le=1, description="Maximum position size as % of portfolio")
    default_stop_loss: Decimal = Field(default=Decimal("0.05"), ge=0, le=1, description="Default stop loss percentage")
    default_take_profit: Decimal = Field(default=Decimal("0.15"), ge=0, description="Default take profit percentage")
    
    # Risk Management
    risk_tolerance: Decimal = Field(default=Decimal("0.05"), ge=0, le=1, description="Risk tolerance (0-1)")
    max_portfolio_risk: Decimal = Field(default=Decimal("0.15"), ge=0, le=1, description="Maximum portfolio risk")
    enable_risk_alerts: bool = Field(default=True, description="Enable risk management alerts")
    
    # Order Management
    order_timeout_minutes: int = Field(default=60, ge=1, description="Order timeout in minutes")
    enable_partial_fills: bool = Field(default=True, description="Allow partial order fills")
    slippage_tolerance: Decimal = Field(default=Decimal("0.01"), ge=0, description="Maximum acceptable slippage")
    
    @validator('max_position_size', 'default_stop_loss', 'risk_tolerance', 'max_portfolio_risk')
    def validate_percentages(cls, v):
        if v > 1:
            raise ValueError('Percentage values must be between 0 and 1')
        return v

class NotificationSettings(BaseModel):
    """Notification preferences"""
    email_notifications: bool = Field(default=True, description="Enable email notifications")
    push_notifications: bool = Field(default=True, description="Enable push notifications")
    sms_notifications: bool = Field(default=False, description="Enable SMS notifications")
    
    # Notification Categories
    trade_executions: bool = Field(default=True, description="Notify on trade executions")
    risk_alerts: bool = Field(default=True, description="Notify on risk alerts")
    price_alerts: bool = Field(default=True, description="Notify on price alerts")
    portfolio_updates: bool = Field(default=False, description="Notify on portfolio updates")
    system_maintenance: bool = Field(default=True, description="Notify on system maintenance")
    
    # Frequency Settings
    daily_summary: bool = Field(default=True, description="Send daily portfolio summary")
    weekly_report: bool = Field(default=True, description="Send weekly performance report")
    monthly_report: bool = Field(default=True, description="Send monthly tax report")
    
    # Delivery Times
    notification_hours_start: int = Field(default=8, ge=0, le=23, description="Start of notification hours")
    notification_hours_end: int = Field(default=22, ge=0, le=23, description="End of notification hours")
    timezone: str = Field(default="Europe/Vienna", description="User timezone")

class APISettings(BaseModel):
    """API integration settings"""
    # Bitpanda Settings
    bitpanda_sandbox: bool = Field(default=True, description="Use Bitpanda sandbox environment")
    bitpanda_api_key: str | None = Field(None, description="Bitpanda API key (masked)")
    
    # AI Services
    preferred_ai_model: str = Field(default="gpt-4", description="Preferred AI model for analysis")
    ai_analysis_frequency: str = Field(default="hourly", description="AI analysis frequency")
    enable_consensus_analysis: bool = Field(default=True, description="Enable multi-AI consensus")
    
    # Data Sources
    enable_news_sentiment: bool = Field(default=True, description="Include news sentiment in analysis")
    enable_social_sentiment: bool = Field(default=True, description="Include social media sentiment")
    data_refresh_interval: int = Field(default=300, ge=60, description="Data refresh interval in seconds")

class UISettings(BaseModel):
    """User interface preferences"""
    theme: str = Field(default="dark", description="UI theme (light/dark)")
    language: str = Field(default="en", description="Interface language")
    currency_display: str = Field(default="EUR", description="Primary currency for display")
    number_format: str = Field(default="european", description="Number formatting style")
    
    # Dashboard Layout
    default_timeframe: str = Field(default="1d", description="Default chart timeframe")
    show_portfolio_allocation: bool = Field(default=True, description="Show portfolio allocation chart")
    show_performance_metrics: bool = Field(default=True, description="Show performance metrics")
    show_risk_indicators: bool = Field(default=True, description="Show risk indicators")
    
    # Chart Settings
    chart_type: str = Field(default="candlestick", description="Default chart type")
    show_volume: bool = Field(default=True, description="Show volume on charts")
    show_indicators: bool = Field(default=True, description="Show technical indicators")

class SecuritySettings(BaseModel):
    """Security and privacy settings"""
    two_factor_enabled: bool = Field(default=False, description="Enable 2FA authentication")
    session_timeout: int = Field(default=60, ge=15, le=1440, description="Session timeout in minutes")
    ip_whitelist: List[str] = Field(default=[], description="Allowed IP addresses")
    
    # Privacy Settings
    data_sharing: bool = Field(default=False, description="Allow anonymous data sharing for research")
    marketing_emails: bool = Field(default=False, description="Receive marketing emails")
    analytics_tracking: bool = Field(default=True, description="Enable analytics tracking")
    
    # Audit Settings
    log_all_actions: bool = Field(default=True, description="Log all user actions")
    export_data_retention: int = Field(default=90, ge=30, description="Data export retention days")

class TaxSettings(BaseModel):
    """Tax and regulatory settings"""
    tax_residence: str = Field(default="AT", description="Tax residence country code")
    tax_id: str | None = Field(None, description="Tax identification number")
    
    # Austrian Tax Settings
    enable_tax_reporting: bool = Field(default=True, description="Enable tax report generation")
    tax_year: int = Field(default=datetime.now().year, description="Current tax year")
    include_crypto_taxes: bool = Field(default=True, description="Include cryptocurrency in tax reports")
    
    # Reporting Preferences  
    monthly_tax_summary: bool = Field(default=True, description="Generate monthly tax summaries")
    export_format: str = Field(default="pdf", description="Tax report export format")
    automatic_categorization: bool = Field(default=True, description="Automatically categorize transactions")

class SystemSettings(BaseModel):
    """System-wide settings (admin only)"""
    maintenance_mode: bool = Field(default=False, description="Enable maintenance mode")
    max_users: int = Field(default=1000, ge=1, description="Maximum number of users")
    rate_limit_per_minute: int = Field(default=100, ge=10, description="API rate limit per minute")
    
    # Trading System
    global_trading_enabled: bool = Field(default=True, description="Enable trading system-wide")
    market_hours_only: bool = Field(default=False, description="Restrict trading to market hours")
    emergency_stop: bool = Field(default=False, description="Emergency stop all trading")
    
    # Data Retention
    log_retention_days: int = Field(default=365, ge=30, description="Log retention in days")
    market_data_retention_days: int = Field(default=1095, ge=365, description="Market data retention in days")

class UserSettingsResponse(BaseModel):
    """Complete user settings response"""
    user_id: str
    trading: TradingSettings
    notifications: NotificationSettings
    api: APISettings
    ui: UISettings
    security: SecuritySettings
    tax: TaxSettings
    last_updated: datetime

    class Config:
        from_attributes = True

# ================================
# SETTINGS ENDPOINTS
# ================================

@router.get("/", response_model=UserSettingsResponse)
async def get_user_settings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get all user settings"""
    
    # For now, return default settings combined with user profile data
    # TODO: Implement actual settings storage in database
    
    trading_settings = TradingSettings(
        auto_trading_enabled=current_user.auto_trading_enabled,
        risk_tolerance=current_user.risk_tolerance,
        max_portfolio_risk=current_user.max_portfolio_risk,
        paper_trading_mode=app_settings.PAPER_TRADING_MODE,
        max_daily_trades=app_settings.MAX_DAILY_TRADES,
        min_trade_amount=app_settings.MIN_TRADE_AMOUNT,
        max_position_size=app_settings.MAX_POSITION_SIZE,
        default_stop_loss=app_settings.DEFAULT_STOP_LOSS,
        default_take_profit=app_settings.DEFAULT_TAKE_PROFIT
    )
    
    return UserSettingsResponse(
        user_id=str(current_user.id),
        trading=trading_settings,
        notifications=NotificationSettings(),
        api=APISettings(),
        ui=UISettings(),
        security=SecuritySettings(),
        tax=TaxSettings(
            tax_residence=current_user.tax_residence,
            tax_id=current_user.tax_id
        ),
        last_updated=current_user.updated_at
    )

@router.get("/trading", response_model=TradingSettings)
async def get_trading_settings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get trading configuration settings"""
    
    return TradingSettings(
        auto_trading_enabled=current_user.auto_trading_enabled,
        risk_tolerance=current_user.risk_tolerance,
        max_portfolio_risk=current_user.max_portfolio_risk,
        paper_trading_mode=app_settings.PAPER_TRADING_MODE,
        max_daily_trades=app_settings.MAX_DAILY_TRADES,
        min_trade_amount=app_settings.MIN_TRADE_AMOUNT,
        max_position_size=app_settings.MAX_POSITION_SIZE,
        default_stop_loss=app_settings.DEFAULT_STOP_LOSS,
        default_take_profit=app_settings.DEFAULT_TAKE_PROFIT
    )

@router.put("/trading", response_model=TradingSettings)
async def update_trading_settings(
    settings: TradingSettings,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update trading configuration settings"""
    
    # Update user settings
    current_user.auto_trading_enabled = settings.auto_trading_enabled
    current_user.risk_tolerance = settings.risk_tolerance
    current_user.max_portfolio_risk = settings.max_portfolio_risk
    
    await db.commit()
    await db.refresh(current_user)
    
    logger.info("Trading settings updated", user_id=str(current_user.id))
    
    return settings

@router.get("/notifications", response_model=NotificationSettings)
async def get_notification_settings(
    current_user: Annotated[User, Depends(get_current_active_user)] = None
):
    """Get notification preferences"""
    
    # TODO: Implement actual notification settings storage
    return NotificationSettings()

@router.put("/notifications", response_model=NotificationSettings)
async def update_notification_settings(
    settings: NotificationSettings,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update notification preferences"""
    
    # TODO: Implement notification settings storage in database
    
    logger.info("Notification settings updated", user_id=str(current_user.id))
    
    return settings

@router.get("/api", response_model=APISettings)
async def get_api_settings(
    current_user: Annotated[User, Depends(get_current_active_user)] = None
):
    """Get API integration settings"""
    
    # Return settings with masked API keys
    settings = APISettings()
    settings.bitpanda_sandbox = app_settings.BITPANDA_SANDBOX
    
    # Mask API key for security
    if app_settings.BITPANDA_API_KEY:
        masked_key = app_settings.BITPANDA_API_KEY[:4] + "***" + app_settings.BITPANDA_API_KEY[-4:]
        settings.bitpanda_api_key = masked_key
    
    return settings

@router.put("/api", response_model=APISettings)
async def update_api_settings(
    settings: APISettings,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update API integration settings"""
    
    # TODO: Implement secure API key storage
    
    logger.info("API settings updated", user_id=str(current_user.id))
    
    return settings

@router.get("/ui", response_model=UISettings)
async def get_ui_settings(
    current_user: Annotated[User, Depends(get_current_active_user)] = None
):
    """Get user interface preferences"""
    
    return UISettings()

@router.put("/ui", response_model=UISettings)
async def update_ui_settings(
    settings: UISettings,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update user interface preferences"""
    
    # TODO: Implement UI settings storage in database
    
    logger.info("UI settings updated", user_id=str(current_user.id))
    
    return settings

@router.get("/security", response_model=SecuritySettings)
async def get_security_settings(
    current_user: Annotated[User, Depends(get_current_active_user)] = None
):
    """Get security and privacy settings"""
    
    return SecuritySettings()

@router.put("/security", response_model=SecuritySettings)
async def update_security_settings(
    settings: SecuritySettings,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update security and privacy settings"""
    
    # TODO: Implement security settings storage and enforcement
    
    logger.info("Security settings updated", user_id=str(current_user.id))
    
    return settings

@router.get("/tax", response_model=TaxSettings)
async def get_tax_settings(
    current_user: Annotated[User, Depends(get_current_active_user)] = None
):
    """Get tax and regulatory settings"""
    
    return TaxSettings(
        tax_residence=current_user.tax_residence,
        tax_id=current_user.tax_id
    )

@router.put("/tax", response_model=TaxSettings)
async def update_tax_settings(
    settings: TaxSettings,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Update tax and regulatory settings"""
    
    # Update user tax information
    current_user.tax_residence = settings.tax_residence
    current_user.tax_id = settings.tax_id
    
    await db.commit()
    await db.refresh(current_user)
    
    logger.info("Tax settings updated", user_id=str(current_user.id))
    
    return settings

@router.get("/system", response_model=Dict[str, Any])
async def get_system_config(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Get system configuration (public read-only values)"""
    
    # Get system config from database
    result = await db.execute(select(SystemConfig))
    configs = result.scalars().all()
    
    config_dict = {}
    for config in configs:
        # Only return non-sensitive configuration values
        if config.key in [
            'max_daily_trades',
            'min_trade_amount',
            'max_position_size',
            'stop_loss_default',
            'take_profit_default'
        ]:
            config_dict[config.key] = config.value
    
    return config_dict

@router.get("/export", response_model=Dict[str, Any])
async def export_user_data(
    format: str = Query("json", regex="^(json|csv|pdf)$"),
    include_history: bool = Query(True, description="Include transaction history"),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Export user data for backup or compliance"""
    
    # TODO: Implement comprehensive data export
    
    export_data = {
        "user_profile": {
            "id": str(current_user.id),
            "username": current_user.username,
            "email": current_user.email,
            "created_at": current_user.created_at.isoformat(),
            "tax_residence": current_user.tax_residence
        },
        "settings": {
            "risk_tolerance": float(current_user.risk_tolerance),
            "max_portfolio_risk": float(current_user.max_portfolio_risk),
            "auto_trading_enabled": current_user.auto_trading_enabled
        },
        "export_metadata": {
            "exported_at": datetime.utcnow().isoformat(),
            "format": format,
            "includes_history": include_history
        }
    }
    
    logger.info("User data exported", user_id=str(current_user.id), format=format)
    
    return export_data

@router.delete("/data")
async def delete_user_data(
    confirm_deletion: bool = Query(False, description="Confirm data deletion"),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Delete user data (GDPR compliance)"""
    
    if not confirm_deletion:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data deletion must be explicitly confirmed"
        )
    
    # TODO: Implement comprehensive data deletion (GDPR right to be forgotten)
    # This should include all user data, portfolios, orders, etc.
    
    logger.warning("User data deletion requested", user_id=str(current_user.id))
    
    return {"message": "Data deletion request received and will be processed within 30 days"}

@router.post("/reset")
async def reset_to_defaults(
    settings_category: str = Query("all", regex="^(all|trading|notifications|ui|security)$"),
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db)
):
    """Reset settings to default values"""
    
    if settings_category in ["all", "trading"]:
        # Reset trading settings to defaults
        current_user.risk_tolerance = Decimal("0.05")
        current_user.max_portfolio_risk = Decimal("0.15")
        current_user.auto_trading_enabled = False
    
    # TODO: Implement reset for other settings categories
    
    await db.commit()
    
    logger.info("Settings reset to defaults", user_id=str(current_user.id), category=settings_category)
    
    return {"message": f"Settings ({settings_category}) reset to default values"}