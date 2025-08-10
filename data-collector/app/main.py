"""
Main data collection service application
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import List
import structlog

# Add the parent directory to the path to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.collectors.market_data_collector import MarketDataCollector
from app.collectors.news_collector import NewsCollector  
from app.collectors.sentiment_collector import SentimentCollector
from app.core.config import settings
from app.core.database import get_database_connection

# Setup structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Configuration is already imported and instantiated in config.py

class DataCollectionOrchestrator:
    """Main orchestrator for all data collection tasks"""
    
    def __init__(self):
        self.market_collector = MarketDataCollector()
        self.news_collector = NewsCollector()
        self.sentiment_collector = SentimentCollector()
        self.is_running = False
        
    async def initialize(self):
        """Initialize all collectors"""
        logger.info("Initializing data collection service")
        
        # Initialize database connection
        await get_database_connection()
        
        # Initialize collectors
        await self.market_collector.initialize()
        await self.news_collector.initialize()
        await self.sentiment_collector.initialize()
        
        logger.info("Data collection service initialized successfully")
    
    async def start_collection(self):
        """Start all data collection tasks"""
        self.is_running = True
        logger.info("Starting data collection tasks")
        
        # Define collection tasks
        tasks = [
            self.run_market_data_collection(),
            self.run_news_collection(),
            self.run_sentiment_collection(),
            self.run_health_check()
        ]
        
        # Run all tasks concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def run_market_data_collection(self):
        """Run market data collection loop"""
        logger.info("Starting market data collection")
        
        while self.is_running:
            try:
                # Collect market data for all configured assets
                await self.market_collector.collect_all_assets()
                
                # Wait for next collection interval
                await asyncio.sleep(settings.MARKET_DATA_INTERVAL)
                
            except Exception as e:
                logger.error("Error in market data collection", error=str(e))
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    async def run_news_collection(self):
        """Run news collection loop"""
        logger.info("Starting news collection")
        
        while self.is_running:
            try:
                # Collect news for all configured assets
                await self.news_collector.collect_all_news()
                
                # Wait for next collection interval
                await asyncio.sleep(settings.NEWS_COLLECTION_INTERVAL)
                
            except Exception as e:
                logger.error("Error in news collection", error=str(e))
                await asyncio.sleep(300)  # Wait 5 minutes before retry
    
    async def run_sentiment_collection(self):
        """Run sentiment analysis collection loop"""
        logger.info("Starting sentiment collection")
        
        while self.is_running:
            try:
                # Collect sentiment data for all configured assets
                await self.sentiment_collector.collect_all_sentiment()
                
                # Wait for next collection interval
                await asyncio.sleep(settings.SENTIMENT_COLLECTION_INTERVAL)
                
            except Exception as e:
                logger.error("Error in sentiment collection", error=str(e))
                await asyncio.sleep(600)  # Wait 10 minutes before retry
    
    async def run_health_check(self):
        """Run periodic health checks"""
        logger.info("Starting health check monitoring")
        
        while self.is_running:
            try:
                # Check collector health
                market_health = await self.market_collector.health_check()
                news_health = await self.news_collector.health_check()
                sentiment_health = await self.sentiment_collector.health_check()
                
                # Log health status
                logger.info(
                    "Health check completed",
                    market_data=market_health,
                    news=news_health,
                    sentiment=sentiment_health
                )
                
                # Wait for next health check
                await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL)
                
            except Exception as e:
                logger.error("Error in health check", error=str(e))
                await asyncio.sleep(300)  # Wait 5 minutes before retry
    
    async def stop_collection(self):
        """Stop all collection tasks"""
        logger.info("Stopping data collection service")
        self.is_running = False
        
        # Close collectors
        await self.market_collector.close()
        await self.news_collector.close()
        await self.sentiment_collector.close()
        
        logger.info("Data collection service stopped")

async def main():
    """Main application entry point"""
    orchestrator = DataCollectionOrchestrator()
    
    try:
        # Initialize the service
        await orchestrator.initialize()
        
        # Start collection (this will run indefinitely)
        await orchestrator.start_collection()
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error("Fatal error in data collection service", error=str(e))
    finally:
        # Clean shutdown
        await orchestrator.stop_collection()

if __name__ == "__main__":
    # Run the main application
    asyncio.run(main())