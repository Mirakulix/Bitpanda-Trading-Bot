"""
News collector for cryptocurrency and financial market news
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import structlog
import hashlib
from urllib.parse import urlparse

from app.core.config import settings
from app.core.database import db_manager


logger = structlog.get_logger()


class NewsCollector:
    """Collects news from various financial and cryptocurrency news sources"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.collected_urls: set = set()  # Track collected URLs to avoid duplicates
        self.last_collection_time = None
        self.collection_errors = 0
        self.max_consecutive_errors = 5
        
        # News API endpoints
        self.news_sources = {
            'newsapi': {
                'url': 'https://newsapi.org/v2/everything',
                'api_key': settings.NEWS_API_KEY,
                'enabled': bool(settings.NEWS_API_KEY)
            },
            'coindesk_rss': {
                'url': 'https://www.coindesk.com/arc/outboundfeeds/rss/',
                'enabled': True
            },
            'cointelegraph_rss': {
                'url': 'https://cointelegraph.com/rss',
                'enabled': True
            }
        }
    
    async def initialize(self):
        """Initialize the news collector"""
        logger.info("Initializing news collector")
        
        # Create HTTP session with proper headers
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                'User-Agent': 'Bitpanda-Trading-Bot/1.0 (+https://github.com/your-repo)'
            }
        )
        
        # Test connectivity to available sources
        available_sources = []
        for source_name, config in self.news_sources.items():
            if config.get('enabled', True):
                try:
                    if await self._test_source_connectivity(source_name, config):
                        available_sources.append(source_name)
                    else:
                        logger.warning("News source not available", source=source_name)
                except Exception as e:
                    logger.warning("Failed to test news source", source=source_name, error=str(e))
        
        logger.info("News collector initialized", available_sources=available_sources)
    
    async def _test_source_connectivity(self, source_name: str, config: Dict[str, Any]) -> bool:
        """Test if a news source is accessible"""
        try:
            if source_name == 'newsapi':
                if not config.get('api_key'):
                    return False
                
                # Test NewsAPI with a simple request
                params = {
                    'q': 'bitcoin',
                    'apiKey': config['api_key'],
                    'pageSize': 1
                }
                
                async with self.session.get(config['url'], params=params) as response:
                    return response.status == 200
                    
            else:
                # Test RSS feeds
                async with self.session.get(config['url']) as response:
                    return response.status == 200
                    
        except Exception:
            return False
    
    async def collect_all_news(self):
        """Collect news from all configured sources"""
        try:
            logger.info("Starting news collection cycle")
            
            # Collect from all enabled sources
            collection_tasks = []
            
            for source_name, config in self.news_sources.items():
                if config.get('enabled', True):
                    if source_name == 'newsapi':
                        collection_tasks.append(self._collect_from_newsapi())
                    elif source_name.endswith('_rss'):
                        collection_tasks.append(self._collect_from_rss(source_name, config['url']))
            
            # Run collections in parallel
            results = await asyncio.gather(*collection_tasks, return_exceptions=True)
            
            # Count successful collections
            successful_collections = sum(1 for r in results if not isinstance(r, Exception))
            
            logger.info("News collection cycle completed", 
                       successful=successful_collections, 
                       total=len(collection_tasks))
            
            # Reset error counter on successful collection
            if successful_collections > 0:
                self.collection_errors = 0
                self.last_collection_time = datetime.utcnow()
            else:
                self.collection_errors += 1
                logger.warning("No successful news collections", 
                             consecutive_errors=self.collection_errors)
            
        except Exception as e:
            self.collection_errors += 1
            logger.error("News collection failed", error=str(e), consecutive_errors=self.collection_errors)
            
            if self.collection_errors >= self.max_consecutive_errors:
                logger.critical("Too many consecutive news collection errors", errors=self.collection_errors)
    
    async def _collect_from_newsapi(self):
        """Collect news from NewsAPI.org"""
        if not settings.NEWS_API_KEY:
            logger.debug("NewsAPI key not configured, skipping")
            return
        
        try:
            # Collect crypto-related news
            crypto_keywords = ['bitcoin', 'ethereum', 'cryptocurrency', 'crypto', 'blockchain', 'DeFi']
            
            for keyword in crypto_keywords:
                params = {
                    'q': keyword,
                    'apiKey': settings.NEWS_API_KEY,
                    'language': 'en',
                    'sortBy': 'publishedAt',
                    'pageSize': 20,
                    'from': (datetime.utcnow() - timedelta(hours=6)).isoformat()
                }
                
                async with self.session.get(self.news_sources['newsapi']['url'], params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('status') == 'ok':
                            articles = data.get('articles', [])
                            
                            for article in articles:
                                await self._process_news_article({
                                    'title': article.get('title'),
                                    'description': article.get('description'),
                                    'url': article.get('url'),
                                    'source': article.get('source', {}).get('name', 'NewsAPI'),
                                    'published_at': article.get('publishedAt'),
                                    'author': article.get('author'),
                                    'content': article.get('content'),
                                    'keyword': keyword
                                })
                            
                            logger.debug("NewsAPI articles collected", keyword=keyword, count=len(articles))
                        else:
                            logger.warning("NewsAPI error response", error=data.get('message'))
                    else:
                        logger.warning("NewsAPI request failed", status=response.status)
                
                # Rate limiting
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error("NewsAPI collection failed", error=str(e))
            raise
    
    async def _collect_from_rss(self, source_name: str, rss_url: str):
        """Collect news from RSS feeds"""
        try:
            async with self.session.get(rss_url) as response:
                if response.status == 200:
                    content = await response.text()
                    
                    # Parse RSS with BeautifulSoup
                    soup = BeautifulSoup(content, 'xml')
                    items = soup.find_all('item')
                    
                    for item in items:
                        # Extract article data from RSS
                        title = item.find('title')
                        description = item.find('description')
                        link = item.find('link')
                        pub_date = item.find('pubDate')
                        author = item.find('author') or item.find('dc:creator')
                        
                        await self._process_news_article({
                            'title': title.text if title else None,
                            'description': description.text if description else None,
                            'url': link.text if link else None,
                            'source': source_name.replace('_rss', '').title(),
                            'published_at': pub_date.text if pub_date else None,
                            'author': author.text if author else None,
                            'content': None,
                            'keyword': 'rss_feed'
                        })
                    
                    logger.debug("RSS articles collected", source=source_name, count=len(items))
                else:
                    logger.warning("RSS request failed", source=source_name, status=response.status)
                    
        except Exception as e:
            logger.error("RSS collection failed", source=source_name, error=str(e))
            raise
    
    async def _process_news_article(self, article_data: Dict[str, Any]):
        """Process and store a news article"""
        try:
            # Skip if no URL or title
            if not article_data.get('url') or not article_data.get('title'):
                return
            
            url = article_data['url']
            
            # Generate unique hash for deduplication
            article_hash = hashlib.md5(url.encode()).hexdigest()
            
            # Skip if already collected
            if article_hash in self.collected_urls:
                return
            
            # Add to collected set
            self.collected_urls.add(article_hash)
            
            # Parse publication date
            published_at = self._parse_publish_date(article_data.get('published_at'))
            
            # Extract domain for source classification
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            
            # Classify article relevance and sentiment
            relevance_score = self._calculate_relevance_score(
                article_data.get('title', ''),
                article_data.get('description', ''),
                article_data.get('keyword', '')
            )
            
            # Store article data
            await self._store_news_article({
                'title': article_data.get('title'),
                'description': article_data.get('description'),
                'url': url,
                'source': article_data.get('source'),
                'domain': domain,
                'author': article_data.get('author'),
                'published_at': published_at,
                'collected_at': datetime.utcnow(),
                'relevance_score': relevance_score,
                'keyword': article_data.get('keyword'),
                'article_hash': article_hash
            })
            
        except Exception as e:
            logger.error("Failed to process news article", error=str(e), url=article_data.get('url'))
    
    def _parse_publish_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse publication date from various formats"""
        if not date_str:
            return None
        
        try:
            # Handle ISO format (NewsAPI)
            if 'T' in date_str and 'Z' in date_str:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            
            # Handle RFC 2822 format (RSS)
            from email.utils import parsedate_tz, mktime_tz
            parsed = parsedate_tz(date_str)
            if parsed:
                return datetime.fromtimestamp(mktime_tz(parsed))
            
            # Fallback to current time
            return datetime.utcnow()
            
        except Exception:
            return datetime.utcnow()
    
    def _calculate_relevance_score(self, title: str, description: str, keyword: str) -> float:
        """Calculate relevance score for cryptocurrency trading"""
        
        # Combine title and description for analysis
        content = f"{title or ''} {description or ''}".lower()
        
        # Cryptocurrency keywords with weights
        crypto_keywords = {
            'bitcoin': 1.0,
            'btc': 1.0,
            'ethereum': 0.9,
            'eth': 0.9,
            'crypto': 0.8,
            'cryptocurrency': 0.8,
            'blockchain': 0.7,
            'defi': 0.8,
            'altcoin': 0.7,
            'trading': 0.6,
            'price': 0.5,
            'market': 0.5,
            'bull': 0.6,
            'bear': 0.6,
            'rally': 0.6,
            'crash': 0.7,
            'adoption': 0.6,
            'regulation': 0.8
        }
        
        # Market impact keywords
        impact_keywords = {
            'sec': 0.9,
            'etf': 0.8,
            'institutional': 0.7,
            'bank': 0.6,
            'government': 0.7,
            'ban': 0.9,
            'approval': 0.8,
            'partnership': 0.6
        }
        
        # Calculate base relevance score
        relevance_score = 0.1  # Base score
        
        # Check crypto keywords
        for kw, weight in crypto_keywords.items():
            if kw in content:
                relevance_score += weight
        
        # Check impact keywords
        for kw, weight in impact_keywords.items():
            if kw in content:
                relevance_score += weight
        
        # Boost score if keyword match
        if keyword and keyword.lower() in content:
            relevance_score += 0.3
        
        # Normalize to 0-1 range
        return min(1.0, relevance_score / 3.0)
    
    async def _store_news_article(self, article_data: Dict[str, Any]):
        """Store news article in database"""
        try:
            async with db_manager.get_session() as session:
                # This would insert into the news_articles table
                # The actual implementation would depend on the database models
                
                logger.debug("News article stored", 
                           title=article_data['title'][:50] + "..." if len(article_data.get('title', '')) > 50 else article_data.get('title'),
                           source=article_data['source'],
                           relevance=article_data['relevance_score'])
                
                await session.commit()
                
        except Exception as e:
            logger.error("Failed to store news article", error=str(e))
    
    async def get_recent_news(
        self,
        limit: int = 50,
        min_relevance: float = 0.3,
        hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """Get recent news articles"""
        try:
            # This would query the database for recent articles
            # For now, return mock data
            return [
                {
                    'title': 'Bitcoin reaches new all-time high',
                    'source': 'CoinDesk',
                    'relevance_score': 0.95,
                    'published_at': datetime.utcnow() - timedelta(hours=2),
                    'url': 'https://example.com/bitcoin-ath'
                }
            ]
            
        except Exception as e:
            logger.error("Failed to get recent news", error=str(e))
            return []
    
    async def get_news_stats(self) -> Dict[str, Any]:
        """Get news collection statistics"""
        return {
            'last_collection': self.last_collection_time.isoformat() if self.last_collection_time else None,
            'consecutive_errors': self.collection_errors,
            'collected_urls_count': len(self.collected_urls),
            'enabled_sources': [name for name, config in self.news_sources.items() if config.get('enabled')],
            'collection_status': 'healthy' if self.collection_errors < self.max_consecutive_errors else 'unhealthy'
        }
    
    async def health_check(self) -> bool:
        """Check news collector health"""
        try:
            # Check if session is active
            if not self.session:
                return False
            
            # Check error rate
            if self.collection_errors >= self.max_consecutive_errors:
                return False
            
            # Check if we have enabled sources
            enabled_sources = [name for name, config in self.news_sources.items() if config.get('enabled')]
            if not enabled_sources:
                return False
            
            return True
            
        except Exception:
            return False
    
    async def close(self):
        """Close the news collector and cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None
        
        self.collected_urls.clear()
        logger.info("News collector closed")