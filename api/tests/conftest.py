"""
Pytest configuration and shared fixtures for testing
"""
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
import structlog

from app.main import app
from app.core.database import get_db
from app.core.config import settings
from app.models.base import Base
from app.models.user import User
from app.models.portfolio import Portfolio, Asset
from app.routers.auth import get_current_active_user
from app.services.ai_service import ai_service_manager


# Configure test logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# ================================
# DATABASE FIXTURES
# ================================

@pytest_asyncio.fixture
async def test_db_engine():
    """Create test database engine with in-memory SQLite"""
    # Use in-memory SQLite for fast testing
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    session_factory = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_client(test_db):
    """Create test client with mocked database"""
    
    async def override_get_db():
        yield test_db
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as client:
        yield client
    
    # Cleanup
    app.dependency_overrides.clear()


# ================================
# USER AND AUTH FIXTURES
# ================================

@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession) -> User:
    """Create a test user"""
    from app.routers.auth import get_password_hash
    
    user = User(
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        hashed_password=get_password_hash("testpassword123"),
        is_active=True,
        is_verified=True
    )
    
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    
    return user


@pytest_asyncio.fixture
async def admin_user(test_db: AsyncSession) -> User:
    """Create a test admin user"""
    from app.routers.auth import get_password_hash
    
    user = User(
        email="admin@example.com",
        username="admin",
        full_name="Admin User",
        hashed_password=get_password_hash("adminpassword123"),
        is_active=True,
        is_verified=True,
        is_superuser=True
    )
    
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    
    return user


@pytest.fixture
def mock_current_user(test_user):
    """Mock current user for authenticated endpoints"""
    async def _get_current_user():
        return test_user
    
    app.dependency_overrides[get_current_active_user] = _get_current_user
    
    yield test_user
    
    # Cleanup
    if get_current_active_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_active_user]


@pytest.fixture
def auth_headers(test_user) -> dict:
    """Generate authentication headers for test requests"""
    from app.routers.auth import create_access_token
    
    token = create_access_token(data={"sub": test_user.email})
    return {"Authorization": f"Bearer {token}"}


# ================================
# PORTFOLIO AND TRADING FIXTURES
# ================================

@pytest_asyncio.fixture
async def test_portfolio(test_db: AsyncSession, test_user: User) -> Portfolio:
    """Create a test portfolio"""
    portfolio = Portfolio(
        user_id=test_user.id,
        name="Test Portfolio",
        description="Portfolio for testing",
        total_value=10000.0,
        cash_balance=5000.0,
        paper_trading=True
    )
    
    test_db.add(portfolio)
    await test_db.commit()
    await test_db.refresh(portfolio)
    
    return portfolio


@pytest_asyncio.fixture
async def test_assets(test_db: AsyncSession) -> list[Asset]:
    """Create test assets"""
    assets = [
        Asset(
            symbol="BTC",
            name="Bitcoin",
            asset_type="cryptocurrency",
            is_tradeable=True,
            current_price=45000.0
        ),
        Asset(
            symbol="ETH", 
            name="Ethereum",
            asset_type="cryptocurrency",
            is_tradeable=True,
            current_price=3000.0
        ),
        Asset(
            symbol="AAPL",
            name="Apple Inc.",
            asset_type="stock",
            is_tradeable=True,
            current_price=150.0
        )
    ]
    
    for asset in assets:
        test_db.add(asset)
    
    await test_db.commit()
    
    for asset in assets:
        await test_db.refresh(asset)
    
    return assets


# ================================
# AI SERVICE FIXTURES
# ================================

@pytest.fixture
def mock_ai_service():
    """Mock AI service for testing"""
    mock_service = AsyncMock()
    
    # Mock AI analysis response
    mock_service.analyze_market.return_value = {
        "recommendation": "BUY",
        "confidence_score": 0.85,
        "target_price": 50000.0,
        "reasoning": "Technical indicators show bullish momentum",
        "indicators": {"RSI": 65, "MACD": 0.002},
        "expires_at": "2024-01-01T12:00:00Z"
    }
    
    mock_service.health_check.return_value = True
    
    return mock_service


@pytest.fixture
def mock_ai_service_manager(mock_ai_service):
    """Mock AI service manager"""
    with pytest.mock.patch.object(ai_service_manager, 'services') as mock_services:
        mock_services.__getitem__.return_value = mock_ai_service
        mock_services.keys.return_value = ['azure_openai', 'deepseek', 'ollama']
        
        with pytest.mock.patch.object(ai_service_manager, 'analyze_with_consensus') as mock_consensus:
            mock_consensus.return_value = {
                "recommendation": "BUY",
                "confidence_score": 0.78,
                "target_price": 48000.0,
                "reasoning": "Consensus of 3 AI models shows bullish sentiment",
                "indicators": {"consensus_score": 0.78, "models_agreement": 0.85},
                "expires_at": "2024-01-01T12:00:00Z"
            }
            
            with pytest.mock.patch.object(ai_service_manager, 'health_check_all') as mock_health:
                mock_health.return_value = {
                    "azure_openai": True,
                    "deepseek": True, 
                    "ollama": False
                }
                
                yield ai_service_manager


# ================================
# EXTERNAL API FIXTURES
# ================================

@pytest.fixture
def mock_external_apis():
    """Mock external API calls"""
    mocks = {}
    
    # Mock CCXT exchange
    mocks['exchange'] = MagicMock()
    mocks['exchange'].fetch_ticker.return_value = {
        'symbol': 'BTC/USDT',
        'last': 45000.0,
        'high': 46000.0,
        'low': 44000.0,
        'volume': 1000000.0,
        'percentage': 2.5
    }
    
    # Mock news API
    mocks['news_api'] = MagicMock()
    mocks['news_api'].get_everything.return_value = {
        'status': 'ok',
        'articles': [
            {
                'title': 'Bitcoin Reaches New High',
                'description': 'Bitcoin price surges to new all-time high',
                'url': 'https://example.com/bitcoin-news',
                'publishedAt': '2024-01-01T10:00:00Z'
            }
        ]
    }
    
    return mocks


# ================================
# PERFORMANCE AND LOAD TEST FIXTURES
# ================================

@pytest.fixture
def performance_test_config():
    """Configuration for performance tests"""
    return {
        "max_response_time": 1.0,  # seconds
        "concurrent_requests": 10,
        "test_duration": 30,  # seconds
        "error_threshold": 0.05  # 5% error rate
    }


# ================================
# UTILITY FIXTURES
# ================================

@pytest.fixture
def sample_market_data():
    """Sample market data for testing"""
    return {
        "price": 45000.0,
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


@pytest.fixture
def sample_news_articles():
    """Sample news articles for testing"""
    return [
        {
            "title": "Bitcoin Adoption Increases in El Salvador",
            "description": "El Salvador reports increased Bitcoin usage among citizens",
            "url": "https://example.com/bitcoin-adoption",
            "source": "CryptoNews",
            "published_at": "2024-01-01T09:00:00Z",
            "relevance_score": 0.85
        },
        {
            "title": "Ethereum 2.0 Staking Reaches New Milestone", 
            "description": "Total ETH staked surpasses 30 million tokens",
            "url": "https://example.com/eth-staking",
            "source": "EthereumNews",
            "published_at": "2024-01-01T08:00:00Z",
            "relevance_score": 0.78
        }
    ]


# ================================
# EVENT LOOP CONFIGURATION
# ================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ================================
# CLEANUP FIXTURES
# ================================

@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Automatic cleanup after each test"""
    yield
    
    # Clear any dependency overrides
    app.dependency_overrides.clear()
    
    # Reset any global state if needed
    # This ensures tests don't interfere with each other


# ================================
# PARAMETRIZED FIXTURES
# ================================

@pytest.fixture(params=["BTC", "ETH", "ADA"])
def crypto_symbol(request):
    """Parametrized fixture for testing multiple crypto symbols"""
    return request.param


@pytest.fixture(params=["1h", "4h", "1d"])
def timeframe(request):
    """Parametrized fixture for testing multiple timeframes"""
    return request.param


@pytest.fixture(params=["technical", "fundamental", "sentiment", "consensus"])
def analysis_type(request):
    """Parametrized fixture for testing multiple analysis types"""
    return request.param