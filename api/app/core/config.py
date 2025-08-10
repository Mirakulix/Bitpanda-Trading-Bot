"""
Configuration settings for the AI Trading Bot
"""
from typing import List, Optional
from pydantic import BaseSettings, validator
import secrets


class Settings(BaseSettings):
    """Application settings"""
    
    # Basic app settings
    PROJECT_NAME: str = "AI Trading Bot"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    ALLOWED_HOSTS: List[str] = ["*"]
    ALLOWED_ORIGINS: List[str] = []
    
    # Database
    DATABASE_URL: str = "postgresql://trading_user:password@localhost:5432/trading_bot"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Message Broker
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    
    # Bitpanda API
    BITPANDA_API_KEY: Optional[str] = None
    BITPANDA_API_SECRET: Optional[str] = None
    BITPANDA_BASE_URL: str = "https://api.exchange.bitpanda.com"
    BITPANDA_SANDBOX: bool = True
    
    # AI Services
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_API_VERSION: str = "2023-12-01-preview"
    AZURE_OPENAI_DEPLOYMENT_NAME: str = "gpt-4"
    
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    
    OLLAMA_ENDPOINT: str = "http://localhost:11434"
    
    # External APIs
    ALPHA_VANTAGE_API_KEY: Optional[str] = None
    COINGECKO_API_KEY: Optional[str] = None
    NEWS_API_KEY: Optional[str] = None
    TWITTER_BEARER_TOKEN: Optional[str] = None
    
    # Trading Configuration
    PAPER_TRADING_MODE: bool = True
    MAX_DAILY_TRADES: int = 50
    MIN_TRADE_AMOUNT: float = 10.0
    MAX_POSITION_SIZE: float = 0.2  # 20% of portfolio
    DEFAULT_STOP_LOSS: float = 0.05  # 5%
    DEFAULT_TAKE_PROFIT: float = 0.15  # 15%
    
    # Risk Management
    MAX_PORTFOLIO_RISK: float = 0.15  # 15% max drawdown
    VAR_CONFIDENCE_LEVEL: float = 0.95  # 95% VaR
    
    # Monitoring
    LOG_LEVEL: str = "INFO"
    PROMETHEUS_ENABLED: bool = True
    JAEGER_ENABLED: bool = False
    JAEGER_AGENT_HOST: str = "localhost"
    JAEGER_AGENT_PORT: int = 6831
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100
    
    @validator("ALLOWED_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    @validator("DATABASE_URL")
    def validate_database_url(cls, v):
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()