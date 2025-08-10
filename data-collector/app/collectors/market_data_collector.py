"""
Market data collector for cryptocurrency and traditional asset prices
"""
import asyncio
import ccxt.async_support as ccxt
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
import yfinance as yf
import aiohttp
import structlog

from app.core.config import settings
from app.core.database import db_manager


logger = structlog.get_logger()


class MarketDataCollector:
    """Collects real-time market data from multiple exchanges and sources"""
    
    def __init__(self):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.last_collection_time = None
        self.collection_errors = 0
        self.max_consecutive_errors = 5
        
    async def initialize(self):
        """Initialize exchange connections"""
        logger.info("Initializing market data collector")
        
        # Initialize cryptocurrency exchanges
        exchange_configs = {
            'binance': {
                'apiKey': None,
                'secret': None,
                'sandbox': False,
                'rateLimit': 1200,
                'enableRateLimit': True,
            },
            'coinbase': {
                'apiKey': None,
                'secret': None,
                'sandbox': False,
                'rateLimit': 1000,
                'enableRateLimit': True,
            }
        }
        
        # Add Bitpanda if API key is available
        if settings.BITPANDA_API_KEY:
            exchange_configs['bitpanda'] = {
                'apiKey': settings.BITPANDA_API_KEY,
                'secret': None,
                'sandbox': False,
                'rateLimit': 1000,
                'enableRateLimit': True,
            }
        
        for exchange_name, config in exchange_configs.items():
            try:
                if exchange_name == 'binance':
                    exchange = ccxt.binance(config)
                elif exchange_name == 'coinbase':
                    exchange = ccxt.coinbase(config)
                elif exchange_name == 'bitpanda':
                    # Note: CCXT may not support Bitpanda Pro directly
                    # This would need custom implementation
                    continue
                else:
                    continue
                
                await exchange.load_markets()
                self.exchanges[exchange_name] = exchange
                logger.info("Exchange initialized", exchange=exchange_name)
                
            except Exception as e:
                logger.warning("Failed to initialize exchange", exchange=exchange_name, error=str(e))
        
        logger.info("Market data collector initialized", exchanges=list(self.exchanges.keys()))
    
    async def collect_all_assets(self):
        """Collect market data for all tracked assets"""
        try:
            # Collect cryptocurrency data
            await self._collect_crypto_data()
            
            # Collect traditional stock data (if any)
            await self._collect_stock_data()
            
            # Reset error counter on successful collection
            self.collection_errors = 0
            self.last_collection_time = datetime.utcnow()
            
        except Exception as e:
            self.collection_errors += 1
            logger.error("Market data collection failed", error=str(e), consecutive_errors=self.collection_errors)
            
            if self.collection_errors >= self.max_consecutive_errors:
                logger.critical("Too many consecutive collection errors", errors=self.collection_errors)
                # Could implement alerting here
    
    async def _collect_crypto_data(self):
        """Collect cryptocurrency market data"""
        for symbol in settings.TRACKED_SYMBOLS:
            try:
                # Collect from multiple exchanges for comparison
                exchange_data = {}
                
                for exchange_name, exchange in self.exchanges.items():
                    try:
                        if symbol in exchange.markets:
                            ticker = await exchange.fetch_ticker(symbol)
                            ohlcv = await exchange.fetch_ohlcv(symbol, '1m', limit=100)
                            
                            exchange_data[exchange_name] = {
                                'ticker': ticker,
                                'ohlcv': ohlcv,
                                'timestamp': datetime.utcnow()
                            }
                        
                    except Exception as e:
                        logger.warning("Failed to collect from exchange", 
                                     exchange=exchange_name, symbol=symbol, error=str(e))
                
                # Store collected data
                if exchange_data:
                    await self._store_market_data(symbol, exchange_data)
                
            except Exception as e:
                logger.error("Failed to collect crypto data", symbol=symbol, error=str(e))
    
    async def _collect_stock_data(self):
        """Collect traditional stock market data using yfinance"""
        # Example stock symbols that might be relevant to crypto trading
        stock_symbols = ['TSLA', 'NVDA', 'MSTR', 'COIN']  # Tesla, Nvidia, MicroStrategy, Coinbase
        
        for symbol in stock_symbols:
            try:
                # Fetch stock data
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="1d", interval="1m")
                
                if not hist.empty:
                    stock_data = {
                        'symbol': symbol,
                        'current_price': float(hist['Close'].iloc[-1]),
                        'volume': float(hist['Volume'].iloc[-1]),
                        'open': float(hist['Open'].iloc[-1]),
                        'high': float(hist['High'].iloc[-1]),
                        'low': float(hist['Low'].iloc[-1]),
                        'change': float((hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0] * 100),
                        'timestamp': datetime.utcnow()
                    }
                    
                    await self._store_stock_data(symbol, stock_data)
                
            except Exception as e:
                logger.warning("Failed to collect stock data", symbol=symbol, error=str(e))
    
    async def _store_market_data(self, symbol: str, exchange_data: Dict[str, Dict]):
        """Store collected market data in database"""
        try:
            async with db_manager.get_session() as session:
                # Calculate aggregated data from all exchanges
                aggregated_data = self._aggregate_exchange_data(symbol, exchange_data)
                
                # Store raw exchange data for detailed analysis
                for exchange_name, data in exchange_data.items():
                    ticker = data['ticker']
                    
                    # Store in market_data table (this would need to be implemented in the models)
                    market_data_record = {
                        'asset_symbol': symbol.replace('/', ''),  # BTC/USDT -> BTC
                        'exchange': exchange_name,
                        'price': Decimal(str(ticker['last'])) if ticker['last'] else None,
                        'volume_24h': Decimal(str(ticker['baseVolume'])) if ticker['baseVolume'] else None,
                        'high_24h': Decimal(str(ticker['high'])) if ticker['high'] else None,
                        'low_24h': Decimal(str(ticker['low'])) if ticker['low'] else None,
                        'change_24h': Decimal(str(ticker['percentage'])) if ticker['percentage'] else None,
                        'timestamp': data['timestamp'],
                        'raw_data': ticker  # Store complete ticker data as JSON
                    }
                    
                    # This would insert into the actual database table
                    logger.debug("Market data stored", symbol=symbol, exchange=exchange_name)
                
                # Store OHLCV data for technical analysis
                await self._store_ohlcv_data(symbol, exchange_data)
                
                await session.commit()
                
        except Exception as e:
            logger.error("Failed to store market data", symbol=symbol, error=str(e))
    
    async def _store_stock_data(self, symbol: str, stock_data: Dict[str, Any]):
        """Store stock market data"""
        try:
            async with db_manager.get_session() as session:
                # Store stock data (would need stock-specific table)
                logger.debug("Stock data stored", symbol=symbol, price=stock_data['current_price'])
                await session.commit()
                
        except Exception as e:
            logger.error("Failed to store stock data", symbol=symbol, error=str(e))
    
    async def _store_ohlcv_data(self, symbol: str, exchange_data: Dict[str, Dict]):
        """Store OHLCV candlestick data for technical analysis"""
        try:
            for exchange_name, data in exchange_data.items():
                if 'ohlcv' in data:
                    for candle in data['ohlcv']:
                        # candle format: [timestamp, open, high, low, close, volume]
                        ohlcv_record = {
                            'asset_symbol': symbol.replace('/', ''),
                            'exchange': exchange_name,
                            'timeframe': '1m',
                            'timestamp': datetime.fromtimestamp(candle[0] / 1000),
                            'open': Decimal(str(candle[1])),
                            'high': Decimal(str(candle[2])),
                            'low': Decimal(str(candle[3])),
                            'close': Decimal(str(candle[4])),
                            'volume': Decimal(str(candle[5])) if candle[5] else None
                        }
                        
                        # This would insert into OHLCV table
                        logger.debug("OHLCV data point stored", symbol=symbol, exchange=exchange_name)
        
        except Exception as e:
            logger.error("Failed to store OHLCV data", symbol=symbol, error=str(e))
    
    def _aggregate_exchange_data(self, symbol: str, exchange_data: Dict[str, Dict]) -> Dict[str, Any]:
        """Aggregate data from multiple exchanges to get best prices and average metrics"""
        prices = []
        volumes = []
        
        for exchange_name, data in exchange_data.items():
            ticker = data['ticker']
            if ticker['last']:
                prices.append(float(ticker['last']))
            if ticker['baseVolume']:
                volumes.append(float(ticker['baseVolume']))
        
        if prices:
            return {
                'avg_price': sum(prices) / len(prices),
                'min_price': min(prices),
                'max_price': max(prices),
                'total_volume': sum(volumes) if volumes else 0,
                'exchange_count': len(prices),
                'price_spread': (max(prices) - min(prices)) / min(prices) * 100 if len(prices) > 1 else 0
            }
        
        return {}
    
    async def collect_specific_asset(self, symbol: str, exchange: str = None) -> Optional[Dict[str, Any]]:
        """Collect data for a specific asset"""
        try:
            if exchange and exchange in self.exchanges:
                exchange_obj = self.exchanges[exchange]
                if symbol in exchange_obj.markets:
                    ticker = await exchange_obj.fetch_ticker(symbol)
                    return {
                        'symbol': symbol,
                        'exchange': exchange,
                        'price': ticker['last'],
                        'volume': ticker['baseVolume'],
                        'change_24h': ticker['percentage'],
                        'timestamp': datetime.utcnow()
                    }
            else:
                # Collect from all available exchanges
                results = {}
                for exchange_name, exchange_obj in self.exchanges.items():
                    try:
                        if symbol in exchange_obj.markets:
                            ticker = await exchange_obj.fetch_ticker(symbol)
                            results[exchange_name] = ticker
                    except Exception as e:
                        logger.warning("Failed to fetch from exchange", 
                                     exchange=exchange_name, symbol=symbol, error=str(e))
                
                return results if results else None
                
        except Exception as e:
            logger.error("Failed to collect specific asset data", symbol=symbol, error=str(e))
            return None
    
    async def get_market_status(self) -> Dict[str, Any]:
        """Get overall market status and health metrics"""
        status = {
            'active_exchanges': len(self.exchanges),
            'last_collection': self.last_collection_time.isoformat() if self.last_collection_time else None,
            'consecutive_errors': self.collection_errors,
            'exchange_status': {}
        }
        
        for exchange_name, exchange in self.exchanges.items():
            try:
                # Test exchange connectivity
                markets = await exchange.fetch_markets()
                status['exchange_status'][exchange_name] = {
                    'status': 'connected',
                    'markets_count': len(markets),
                    'rate_limit': exchange.rateLimit
                }
            except Exception as e:
                status['exchange_status'][exchange_name] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        return status
    
    async def health_check(self) -> bool:
        """Check collector health"""
        try:
            # Check if we have active exchanges
            if not self.exchanges:
                return False
            
            # Check if recent collection was successful
            if self.collection_errors >= self.max_consecutive_errors:
                return False
            
            # Test at least one exchange
            for exchange_name, exchange in self.exchanges.items():
                try:
                    await exchange.fetch_markets()
                    return True  # If any exchange works, we're healthy
                except:
                    continue
            
            return False
            
        except Exception:
            return False
    
    async def close(self):
        """Close all exchange connections"""
        for exchange_name, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info("Exchange connection closed", exchange=exchange_name)
            except Exception as e:
                logger.warning("Error closing exchange", exchange=exchange_name, error=str(e))
        
        self.exchanges.clear()
        logger.info("Market data collector closed")