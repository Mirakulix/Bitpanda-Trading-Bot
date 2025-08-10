"""
Data collector service configuration
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class DataCollectorSettings(BaseSettings):
    """Data collector configuration settings"""
    
    # ================================
    # DATABASE CONFIG
    # ================================
    
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/bitpanda_trading",
        description="Database connection URL"
    )
    
    # ================================
    # REDIS CONFIG
    # ================================
    
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching"
    )
    
    # ================================
    # COLLECTION INTERVALS
    # ================================
    
    MARKET_DATA_INTERVAL: int = Field(
        default=60,
        description="Market data collection interval in seconds"
    )
    
    NEWS_COLLECTION_INTERVAL: int = Field(
        default=900,  # 15 minutes
        description="News collection interval in seconds"
    )
    
    SENTIMENT_COLLECTION_INTERVAL: int = Field(
        default=1800,  # 30 minutes
        description="Sentiment analysis interval in seconds"
    )
    
    HEALTH_CHECK_INTERVAL: int = Field(
        default=300,  # 5 minutes
        description="Health check interval in seconds"
    )
    
    # ================================
    # TRADING DATA CONFIG
    # ================================
    
    TRACKED_SYMBOLS: List[str] = Field(
        default=["BTC/USDT", "ETH/USDT", "ADA/USDT", "DOT/USDT", "MATIC/USDT"],
        description="List of trading symbols to track"
    )
    
    EXCHANGES: List[str] = Field(
        default=["bitpanda", "binance", "coinbase"],
        description="List of exchanges to collect data from"
    )
    
    # ================================
    # MARKET DATA APIS
    # ================================
    
    BITPANDA_API_KEY: Optional[str] = Field(
        default=None,
        description="Bitpanda Pro API key"
    )
    
    COINMARKETCAP_API_KEY: Optional[str] = Field(
        default=None,
        description="CoinMarketCap API key"
    )
    
    COINGECKO_API_KEY: Optional[str] = Field(
        default=None,
        description="CoinGecko API key"
    )
    
    ALPHA_VANTAGE_API_KEY: Optional[str] = Field(
        default=None,
        description="Alpha Vantage API key for traditional stocks"
    )
    
    # ================================
    # NEWS APIS
    # ================================
    
    NEWS_API_KEY: Optional[str] = Field(
        default=None,
        description="NewsAPI.org API key"
    )
    
    CRYPTO_NEWS_SOURCES: List[str] = Field(
        default=[
            "coindesk.com",
            "cointelegraph.com",
            "decrypt.co",
            "bitcoinmagazine.com",
            "cryptonews.com"
        ],
        description="Crypto news sources to monitor"
    )
    
    # ================================
    # SOCIAL MEDIA APIS
    # ================================
    
    TWITTER_BEARER_TOKEN: Optional[str] = Field(
        default=None,
        description="Twitter API v2 Bearer Token"
    )
    
    REDDIT_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Reddit API Client ID"
    )
    
    REDDIT_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Reddit API Client Secret"
    )
    
    REDDIT_USER_AGENT: str = Field(
        default="BitpandaBot:v1.0 (by u/tradingbot)",
        description="Reddit API User Agent"
    )
    
    # ================================
    # DATA RETENTION
    # ================================
    
    RAW_DATA_RETENTION_DAYS: int = Field(
        default=30,
        description="Days to keep raw collected data"
    )
    
    PROCESSED_DATA_RETENTION_DAYS: int = Field(
        default=365,
        description="Days to keep processed/aggregated data"
    )
    
    # ================================
    # RATE LIMITING
    # ================================
    
    MAX_REQUESTS_PER_MINUTE: int = Field(
        default=100,
        description="Maximum API requests per minute"
    )
    
    REQUEST_DELAY_SECONDS: float = Field(
        default=1.0,
        description="Delay between API requests in seconds"
    )
    
    # ================================
    # SENTIMENT ANALYSIS
    # ================================
    
    SENTIMENT_KEYWORDS: List[str] = Field(
        default=["bitcoin", "ethereum", "crypto", "cryptocurrency", "DeFi", "NFT"],
        description="Keywords to monitor for sentiment analysis"
    )
    
    SENTIMENT_SUBREDDITS: List[str] = Field(
        default=["cryptocurrency", "bitcoin", "ethereum", "CryptoMarkets", "altcoin"],
        description="Reddit subreddits to monitor for sentiment"
    )
    
    # ================================
    # TECHNICAL INDICATORS
    # ================================
    
    TECHNICAL_INDICATORS: List[str] = Field(
        default=["RSI", "MACD", "SMA", "EMA", "Bollinger_Bands", "Volume"],
        description="Technical indicators to calculate"
    )
    
    TIMEFRAMES: List[str] = Field(
        default=["1m", "5m", "15m", "1h", "4h", "1d"],
        description="Timeframes for technical analysis"
    )
    
    # ================================
    # LOGGING & MONITORING
    # ================================
    
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level"
    )
    
    ENABLE_METRICS: bool = Field(
        default=True,
        description="Enable Prometheus metrics"
    )
    
    METRICS_PORT: int = Field(
        default=8001,
        description="Port for metrics endpoint"
    )
    
    # ================================
    # ERROR HANDLING
    # ================================
    
    MAX_RETRY_ATTEMPTS: int = Field(
        default=3,
        description="Maximum retry attempts for failed requests"
    )
    
    BACKOFF_FACTOR: float = Field(
        default=2.0,
        description="Exponential backoff factor for retries"
    )
    
    ERROR_ALERT_THRESHOLD: int = Field(
        default=5,
        description="Number of consecutive errors before alerting"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = DataCollectorSettings()