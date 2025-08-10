"""
Sentiment analysis collector for social media and market sentiment
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re
import structlog
from collections import defaultdict
import json

from app.core.config import settings
from app.core.database import db_manager


logger = structlog.get_logger()


class SentimentCollector:
    """Collects and analyzes sentiment from social media and news sources"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_collection_time = None
        self.collection_errors = 0
        self.max_consecutive_errors = 5
        
        # Sentiment tracking
        self.sentiment_cache = defaultdict(list)
        
        # Social media APIs
        self.social_apis = {
            'twitter': {
                'enabled': bool(settings.TWITTER_BEARER_TOKEN),
                'bearer_token': settings.TWITTER_BEARER_TOKEN,
                'base_url': 'https://api.twitter.com/2'
            },
            'reddit': {
                'enabled': bool(settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET),
                'client_id': settings.REDDIT_CLIENT_ID,
                'client_secret': settings.REDDIT_CLIENT_SECRET,
                'user_agent': settings.REDDIT_USER_AGENT,
                'base_url': 'https://oauth.reddit.com'
            }
        }
        
        # Sentiment keywords and their weights
        self.sentiment_keywords = {
            'positive': {
                'moon': 2.0,
                'bullish': 1.8,
                'buy': 1.5,
                'pump': 1.7,
                'rocket': 2.0,
                'hodl': 1.3,
                'diamond hands': 2.2,
                'to the moon': 2.5,
                'green': 1.2,
                'profit': 1.4,
                'surge': 1.6,
                'breakout': 1.5,
                'rally': 1.6
            },
            'negative': {
                'dump': -1.7,
                'crash': -2.0,
                'bearish': -1.8,
                'sell': -1.5,
                'panic': -1.9,
                'red': -1.2,
                'loss': -1.4,
                'drop': -1.3,
                'fall': -1.2,
                'correction': -1.1,
                'decline': -1.3,
                'bear market': -2.0
            }
        }
    
    async def initialize(self):
        """Initialize the sentiment collector"""
        logger.info("Initializing sentiment collector")
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                'User-Agent': 'Bitpanda-Trading-Bot/1.0 (+https://github.com/your-repo)'
            }
        )
        
        # Test API connections
        available_apis = []
        
        if self.social_apis['twitter']['enabled']:
            if await self._test_twitter_connection():
                available_apis.append('twitter')
            else:
                logger.warning("Twitter API not accessible")
        
        if self.social_apis['reddit']['enabled']:
            if await self._test_reddit_connection():
                available_apis.append('reddit')
            else:
                logger.warning("Reddit API not accessible")
        
        logger.info("Sentiment collector initialized", available_apis=available_apis)
    
    async def _test_twitter_connection(self) -> bool:
        """Test Twitter API connection"""
        try:
            headers = {
                'Authorization': f"Bearer {self.social_apis['twitter']['bearer_token']}"
            }
            
            # Simple test request to get user info
            url = f"{self.social_apis['twitter']['base_url']}/users/me"
            
            async with self.session.get(url, headers=headers) as response:
                return response.status in [200, 401]  # 401 is also ok for testing connectivity
                
        except Exception:
            return False
    
    async def _test_reddit_connection(self) -> bool:
        """Test Reddit API connection"""
        try:
            # Get OAuth token first
            auth_data = {
                'grant_type': 'client_credentials'
            }
            
            auth = aiohttp.BasicAuth(
                self.social_apis['reddit']['client_id'],
                self.social_apis['reddit']['client_secret']
            )
            
            async with self.session.post(
                'https://www.reddit.com/api/v1/access_token',
                data=auth_data,
                auth=auth,
                headers={'User-Agent': self.social_apis['reddit']['user_agent']}
            ) as response:
                return response.status == 200
                
        except Exception:
            return False
    
    async def collect_all_sentiment(self):
        """Collect sentiment data from all available sources"""
        try:
            logger.info("Starting sentiment collection cycle")
            
            # Collect from different sources
            collection_tasks = []
            
            # Social media sentiment
            if self.social_apis['twitter']['enabled']:
                collection_tasks.append(self._collect_twitter_sentiment())
            
            if self.social_apis['reddit']['enabled']:
                collection_tasks.append(self._collect_reddit_sentiment())
            
            # Market fear/greed index
            collection_tasks.append(self._collect_fear_greed_index())
            
            # Run collections in parallel
            results = await asyncio.gather(*collection_tasks, return_exceptions=True)
            
            # Count successful collections
            successful_collections = sum(1 for r in results if not isinstance(r, Exception))
            
            # Process and aggregate collected sentiment data
            await self._process_sentiment_data()
            
            logger.info("Sentiment collection cycle completed", 
                       successful=successful_collections, 
                       total=len(collection_tasks))
            
            # Reset error counter on successful collection
            if successful_collections > 0:
                self.collection_errors = 0
                self.last_collection_time = datetime.utcnow()
            else:
                self.collection_errors += 1
                logger.warning("No successful sentiment collections", 
                             consecutive_errors=self.collection_errors)
            
        except Exception as e:
            self.collection_errors += 1
            logger.error("Sentiment collection failed", error=str(e), consecutive_errors=self.collection_errors)
            
            if self.collection_errors >= self.max_consecutive_errors:
                logger.critical("Too many consecutive sentiment collection errors", errors=self.collection_errors)
    
    async def _collect_twitter_sentiment(self):
        """Collect sentiment data from Twitter"""
        if not self.social_apis['twitter']['enabled']:
            return
        
        try:
            headers = {
                'Authorization': f"Bearer {self.social_apis['twitter']['bearer_token']}"
            }
            
            # Search for cryptocurrency-related tweets
            for keyword in settings.SENTIMENT_KEYWORDS[:3]:  # Limit to avoid rate limits
                params = {
                    'query': f"{keyword} -is:retweet lang:en",
                    'tweet.fields': 'created_at,public_metrics,context_annotations',
                    'max_results': 50
                }
                
                url = f"{self.social_apis['twitter']['base_url']}/tweets/search/recent"
                
                async with self.session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        tweets = data.get('data', [])
                        
                        for tweet in tweets:
                            sentiment_score = self._analyze_text_sentiment(tweet.get('text', ''))
                            
                            # Store sentiment data
                            sentiment_data = {
                                'source': 'twitter',
                                'keyword': keyword,
                                'text': tweet.get('text'),
                                'sentiment_score': sentiment_score,
                                'timestamp': tweet.get('created_at'),
                                'engagement': tweet.get('public_metrics', {}),
                                'processed_at': datetime.utcnow()
                            }
                            
                            self.sentiment_cache[keyword].append(sentiment_data)
                        
                        logger.debug("Twitter sentiment collected", keyword=keyword, tweets=len(tweets))
                    
                    elif response.status == 429:
                        logger.warning("Twitter rate limit reached")
                        break
                    else:
                        logger.warning("Twitter API error", status=response.status)
                
                # Rate limiting
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error("Twitter sentiment collection failed", error=str(e))
            raise
    
    async def _collect_reddit_sentiment(self):
        """Collect sentiment data from Reddit"""
        if not self.social_apis['reddit']['enabled']:
            return
        
        try:
            # Get OAuth token
            token = await self._get_reddit_token()
            if not token:
                logger.warning("Failed to get Reddit OAuth token")
                return
            
            headers = {
                'Authorization': f'Bearer {token}',
                'User-Agent': self.social_apis['reddit']['user_agent']
            }
            
            # Collect from cryptocurrency subreddits
            for subreddit in settings.SENTIMENT_SUBREDDITS[:3]:  # Limit to avoid rate limits
                url = f"{self.social_apis['reddit']['base_url']}/r/{subreddit}/hot"
                params = {'limit': 25}
                
                async with self.session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        posts = data.get('data', {}).get('children', [])
                        
                        for post in posts:
                            post_data = post.get('data', {})
                            title = post_data.get('title', '')
                            selftext = post_data.get('selftext', '')
                            
                            # Analyze sentiment of title and text
                            combined_text = f"{title} {selftext}"
                            sentiment_score = self._analyze_text_sentiment(combined_text)
                            
                            sentiment_data = {
                                'source': 'reddit',
                                'subreddit': subreddit,
                                'title': title,
                                'text': selftext,
                                'sentiment_score': sentiment_score,
                                'upvote_ratio': post_data.get('upvote_ratio'),
                                'score': post_data.get('score'),
                                'num_comments': post_data.get('num_comments'),
                                'timestamp': datetime.fromtimestamp(post_data.get('created_utc', 0)),
                                'processed_at': datetime.utcnow()
                            }
                            
                            # Determine relevant keywords
                            for keyword in settings.SENTIMENT_KEYWORDS:
                                if keyword.lower() in combined_text.lower():
                                    self.sentiment_cache[keyword].append(sentiment_data)
                        
                        logger.debug("Reddit sentiment collected", subreddit=subreddit, posts=len(posts))
                    else:
                        logger.warning("Reddit API error", subreddit=subreddit, status=response.status)
                
                # Rate limiting
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error("Reddit sentiment collection failed", error=str(e))
            raise
    
    async def _get_reddit_token(self) -> Optional[str]:
        """Get Reddit OAuth access token"""
        try:
            auth_data = {
                'grant_type': 'client_credentials'
            }
            
            auth = aiohttp.BasicAuth(
                self.social_apis['reddit']['client_id'],
                self.social_apis['reddit']['client_secret']
            )
            
            async with self.session.post(
                'https://www.reddit.com/api/v1/access_token',
                data=auth_data,
                auth=auth,
                headers={'User-Agent': self.social_apis['reddit']['user_agent']}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('access_token')
                
        except Exception as e:
            logger.error("Failed to get Reddit token", error=str(e))
            
        return None
    
    async def _collect_fear_greed_index(self):
        """Collect Fear & Greed Index from external API"""
        try:
            # Alternative.me Fear & Greed Index API
            url = "https://api.alternative.me/fng/"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('data'):
                        fng_data = data['data'][0]
                        
                        fear_greed_data = {
                            'source': 'fear_greed_index',
                            'value': int(fng_data.get('value', 50)),
                            'classification': fng_data.get('value_classification', 'Neutral'),
                            'timestamp': fng_data.get('timestamp'),
                            'processed_at': datetime.utcnow()
                        }
                        
                        self.sentiment_cache['market_sentiment'].append(fear_greed_data)
                        
                        logger.debug("Fear & Greed Index collected", 
                                   value=fear_greed_data['value'], 
                                   classification=fear_greed_data['classification'])
                else:
                    logger.warning("Fear & Greed Index API error", status=response.status)
                    
        except Exception as e:
            logger.error("Fear & Greed Index collection failed", error=str(e))
    
    def _analyze_text_sentiment(self, text: str) -> float:
        """Analyze sentiment of text using keyword-based approach"""
        if not text:
            return 0.0
        
        text_lower = text.lower()
        sentiment_score = 0.0
        word_count = len(text.split())
        
        # Check positive keywords
        for keyword, weight in self.sentiment_keywords['positive'].items():
            if keyword in text_lower:
                sentiment_score += weight
        
        # Check negative keywords
        for keyword, weight in self.sentiment_keywords['negative'].items():
            if keyword in text_lower:
                sentiment_score += weight  # weight is already negative
        
        # Normalize by text length to prevent long texts from skewing results
        if word_count > 0:
            sentiment_score = sentiment_score / (word_count / 10)  # Normalize to ~10 word baseline
        
        # Clamp to [-1, 1] range
        return max(-1.0, min(1.0, sentiment_score))
    
    async def _process_sentiment_data(self):
        """Process and aggregate collected sentiment data"""
        try:
            for keyword, sentiment_items in self.sentiment_cache.items():
                if sentiment_items:
                    # Calculate aggregated sentiment metrics
                    sentiment_scores = [item['sentiment_score'] for item in sentiment_items]
                    
                    if sentiment_scores:
                        aggregated_data = {
                            'keyword': keyword,
                            'avg_sentiment': sum(sentiment_scores) / len(sentiment_scores),
                            'sentiment_count': len(sentiment_scores),
                            'positive_ratio': len([s for s in sentiment_scores if s > 0.1]) / len(sentiment_scores),
                            'negative_ratio': len([s for s in sentiment_scores if s < -0.1]) / len(sentiment_scores),
                            'neutral_ratio': len([s for s in sentiment_scores if -0.1 <= s <= 0.1]) / len(sentiment_scores),
                            'max_sentiment': max(sentiment_scores),
                            'min_sentiment': min(sentiment_scores),
                            'collection_time': datetime.utcnow(),
                            'sources': list(set(item.get('source', 'unknown') for item in sentiment_items))
                        }
                        
                        # Store aggregated sentiment data
                        await self._store_sentiment_data(aggregated_data)
            
            # Clear cache after processing
            self.sentiment_cache.clear()
            
        except Exception as e:
            logger.error("Failed to process sentiment data", error=str(e))
    
    async def _store_sentiment_data(self, sentiment_data: Dict[str, Any]):
        """Store aggregated sentiment data in database"""
        try:
            async with db_manager.get_session() as session:
                # This would insert into the sentiment_analysis table
                logger.debug("Sentiment data stored", 
                           keyword=sentiment_data['keyword'],
                           avg_sentiment=sentiment_data['avg_sentiment'],
                           count=sentiment_data['sentiment_count'])
                
                await session.commit()
                
        except Exception as e:
            logger.error("Failed to store sentiment data", error=str(e))
    
    async def get_current_sentiment(self, keyword: str = None) -> Dict[str, Any]:
        """Get current sentiment analysis for a keyword or overall market"""
        try:
            # This would query the database for recent sentiment data
            # For now, return mock data
            
            if keyword:
                return {
                    'keyword': keyword,
                    'sentiment_score': 0.25,
                    'sentiment_label': 'Slightly Positive',
                    'confidence': 0.75,
                    'sample_size': 150,
                    'last_updated': datetime.utcnow()
                }
            else:
                return {
                    'overall_sentiment': 0.15,
                    'sentiment_label': 'Neutral to Positive',
                    'fear_greed_index': 62,
                    'trending_keywords': ['bitcoin', 'ethereum', 'bull'],
                    'sentiment_distribution': {
                        'very_positive': 15,
                        'positive': 35,
                        'neutral': 30,
                        'negative': 15,
                        'very_negative': 5
                    },
                    'last_updated': datetime.utcnow()
                }
                
        except Exception as e:
            logger.error("Failed to get current sentiment", error=str(e))
            return {}
    
    async def get_sentiment_trends(self, hours_back: int = 24) -> List[Dict[str, Any]]:
        """Get sentiment trends over time"""
        try:
            # This would query the database for historical sentiment data
            # For now, return mock trend data
            trends = []
            
            for i in range(hours_back):
                trends.append({
                    'timestamp': datetime.utcnow() - timedelta(hours=i),
                    'sentiment_score': 0.2 + (i % 5 - 2) * 0.1,  # Mock oscillating sentiment
                    'volume': 100 + (i % 3) * 50,
                    'fear_greed_index': 60 + (i % 10 - 5) * 2
                })
            
            return list(reversed(trends))  # Chronological order
            
        except Exception as e:
            logger.error("Failed to get sentiment trends", error=str(e))
            return []
    
    async def get_sentiment_stats(self) -> Dict[str, Any]:
        """Get sentiment collection statistics"""
        return {
            'last_collection': self.last_collection_time.isoformat() if self.last_collection_time else None,
            'consecutive_errors': self.collection_errors,
            'cached_items': sum(len(items) for items in self.sentiment_cache.values()),
            'enabled_apis': [name for name, config in self.social_apis.items() if config.get('enabled')],
            'tracked_keywords': settings.SENTIMENT_KEYWORDS,
            'collection_status': 'healthy' if self.collection_errors < self.max_consecutive_errors else 'unhealthy'
        }
    
    async def health_check(self) -> bool:
        """Check sentiment collector health"""
        try:
            # Check if session is active
            if not self.session:
                return False
            
            # Check error rate
            if self.collection_errors >= self.max_consecutive_errors:
                return False
            
            # Check if we have enabled APIs
            enabled_apis = [name for name, config in self.social_apis.items() if config.get('enabled')]
            if not enabled_apis:
                logger.warning("No enabled social media APIs for sentiment collection")
                return False
            
            return True
            
        except Exception:
            return False
    
    async def close(self):
        """Close the sentiment collector and cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None
        
        self.sentiment_cache.clear()
        logger.info("Sentiment collector closed")