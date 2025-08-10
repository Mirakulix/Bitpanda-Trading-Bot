"""
Database connection and utilities for data collector service
"""
import asyncio
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Global database engine
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


def get_engine() -> AsyncEngine:
    """Get or create database engine"""
    global _engine
    
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            poolclass=NullPool,  # Disable connection pooling for data collector
            pool_pre_ping=True,
        )
        logger.info("Database engine created", url=settings.DATABASE_URL.split("@")[1] if "@" in settings.DATABASE_URL else "***")
    
    return _engine


def get_session_factory() -> async_sessionmaker:
    """Get session factory"""
    global _session_factory
    
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False
        )
        logger.info("Database session factory created")
    
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception as e:
            logger.error("Database session error", error=str(e))
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_database_connection() -> AsyncEngine:
    """Initialize and test database connection"""
    engine = get_engine()
    
    try:
        # Test connection
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            test_result = result.scalar()
            
            if test_result == 1:
                logger.info("Database connection successful")
            else:
                raise Exception("Database connection test failed")
        
        return engine
        
    except Exception as e:
        logger.error("Failed to connect to database", error=str(e))
        raise


async def close_database_connection():
    """Close database connections"""
    global _engine, _session_factory
    
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connections closed")


class DatabaseManager:
    """Database connection manager for data collector"""
    
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None
    
    async def initialize(self):
        """Initialize database connections"""
        self.engine = get_engine()
        self.session_factory = get_session_factory()
        
        # Test connection
        await get_database_connection()
        logger.info("Database manager initialized")
    
    async def get_session(self) -> AsyncSession:
        """Get a database session"""
        if not self.session_factory:
            await self.initialize()
        
        return self.session_factory()
    
    async def health_check(self) -> bool:
        """Check database health"""
        try:
            if not self.engine:
                return False
                
            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
                
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False
    
    async def close(self):
        """Close all database connections"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            logger.info("Database manager closed")


# Global database manager instance
db_manager = DatabaseManager()