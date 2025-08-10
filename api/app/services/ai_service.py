"""
AI service clients for market analysis integration
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# ================================
# AI SERVICE INTERFACES
# ================================

class AIServiceInterface(ABC):
    """Abstract base class for AI services"""
    
    @abstractmethod
    async def analyze_market(
        self, 
        symbol: str, 
        timeframe: str, 
        analysis_type: str,
        market_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze market for a given symbol"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the AI service is available"""
        pass

# ================================
# AZURE OPENAI SERVICE
# ================================

class AzureOpenAIService(AIServiceInterface):
    """Azure OpenAI GPT-4 integration service"""
    
    def __init__(self):
        self.api_key = settings.AZURE_OPENAI_API_KEY
        self.endpoint = settings.AZURE_OPENAI_ENDPOINT
        self.api_version = settings.AZURE_OPENAI_API_VERSION
        self.deployment_name = settings.AZURE_OPENAI_DEPLOYMENT_NAME
        self.model = "gpt-4"
        
    async def analyze_market(
        self, 
        symbol: str, 
        timeframe: str, 
        analysis_type: str,
        market_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze market using GPT-4"""
        
        if not self.api_key or not self.endpoint:
            logger.warning("Azure OpenAI credentials not configured")
            return self._get_fallback_analysis(symbol, analysis_type)
        
        try:
            # Prepare context for GPT-4
            context = self._prepare_market_context(symbol, timeframe, analysis_type, market_data)
            
            # Create system prompt
            system_prompt = self._create_system_prompt(analysis_type)
            
            # Prepare request payload
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                "max_tokens": 1500,
                "temperature": 0.7,
                "top_p": 0.95,
                "frequency_penalty": 0,
                "presence_penalty": 0
            }
            
            # Make API request
            url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "api-key": self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    params={"api-version": self.api_version},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_gpt_response(data, symbol, analysis_type)
                    else:
                        error_text = await response.text()
                        logger.error("Azure OpenAI API error", status=response.status, error=error_text)
                        return self._get_fallback_analysis(symbol, analysis_type)
                        
        except Exception as e:
            logger.error("Azure OpenAI service error", error=str(e))
            return self._get_fallback_analysis(symbol, analysis_type)
    
    def _create_system_prompt(self, analysis_type: str) -> str:
        """Create system prompt based on analysis type"""
        
        base_prompt = """You are a professional financial analyst and trading expert. 
        Provide detailed, objective market analysis based on the given data. 
        Be specific with your recommendations and provide concrete reasoning."""
        
        if analysis_type == "technical":
            return f"""{base_prompt}
            Focus on technical analysis including:
            - Price action and chart patterns
            - Support and resistance levels
            - Technical indicators (RSI, MACD, moving averages)
            - Volume analysis
            - Momentum and trend analysis
            Provide a clear BUY/SELL/HOLD recommendation with confidence level (0-1)."""
            
        elif analysis_type == "fundamental":
            return f"""{base_prompt}
            Focus on fundamental analysis including:
            - Asset valuation and metrics
            - Market conditions and economic factors
            - News and events impact
            - Long-term growth prospects
            - Risk assessment
            Provide a clear BUY/SELL/HOLD recommendation with confidence level (0-1)."""
            
        elif analysis_type == "sentiment":
            return f"""{base_prompt}
            Focus on market sentiment analysis including:
            - Social media sentiment and trends
            - News sentiment and media coverage
            - Market psychology and fear/greed indicators
            - Community discussion analysis
            - Overall market mood assessment
            Provide a clear BUY/SELL/HOLD recommendation with confidence level (0-1)."""
            
        else:  # consensus
            return f"""{base_prompt}
            Provide a comprehensive consensus analysis combining:
            - Technical analysis insights
            - Fundamental factors
            - Market sentiment
            - Risk-reward assessment
            - Market timing considerations
            Provide a clear BUY/SELL/HOLD recommendation with confidence level (0-1)."""
    
    def _prepare_market_context(
        self, 
        symbol: str, 
        timeframe: str, 
        analysis_type: str,
        market_data: Dict[str, Any]
    ) -> str:
        """Prepare market context for analysis"""
        
        context = f"Asset: {symbol}\nTimeframe: {timeframe}\nAnalysis Type: {analysis_type}\n\n"
        
        if market_data:
            if "price" in market_data:
                context += f"Current Price: ${market_data['price']}\n"
            if "volume_24h" in market_data:
                context += f"24h Volume: ${market_data['volume_24h']:,.2f}\n"
            if "change_24h" in market_data:
                context += f"24h Change: {market_data['change_24h']}%\n"
            if "market_cap" in market_data:
                context += f"Market Cap: ${market_data['market_cap']:,.0f}\n"
                
            # Add OHLCV data if available
            if "ohlcv" in market_data:
                context += "\nRecent Price Data:\n"
                for i, candle in enumerate(market_data["ohlcv"][-5:]):  # Last 5 candles
                    context += f"Period {i+1}: O: ${candle['open']} H: ${candle['high']} L: ${candle['low']} C: ${candle['close']} V: {candle['volume']}\n"
                    
            # Add indicators if available
            if "indicators" in market_data:
                context += "\nTechnical Indicators:\n"
                for indicator, value in market_data["indicators"].items():
                    context += f"{indicator}: {value}\n"
        
        context += "\nPlease provide a detailed analysis and clear recommendation."
        return context
    
    def _parse_gpt_response(self, response_data: Dict[str, Any], symbol: str, analysis_type: str) -> Dict[str, Any]:
        """Parse GPT-4 response into structured format"""
        
        try:
            content = response_data["choices"][0]["message"]["content"]
            
            # Extract recommendation (simple keyword search)
            recommendation = "HOLD"
            content_upper = content.upper()
            
            if any(word in content_upper for word in ["STRONG BUY", "BUY", "BULLISH", "POSITIVE"]):
                if "STRONG BUY" in content_upper:
                    recommendation = "BUY"
                    confidence_boost = 0.1
                else:
                    recommendation = "BUY"
                    confidence_boost = 0.0
            elif any(word in content_upper for word in ["SELL", "BEARISH", "NEGATIVE"]):
                recommendation = "SELL"
                confidence_boost = 0.0
            else:
                recommendation = "HOLD"
                confidence_boost = 0.0
            
            # Extract confidence level (look for patterns like "confidence: 0.8" or "80% confident")
            import re
            confidence_matches = re.findall(r'confidence[:\s]+([0-9.]+)', content.lower())
            percent_matches = re.findall(r'([0-9.]+)%\s+confident', content.lower())
            
            confidence_score = 0.75  # Default confidence
            
            if confidence_matches:
                confidence_score = min(1.0, float(confidence_matches[0]) + confidence_boost)
            elif percent_matches:
                confidence_score = min(1.0, float(percent_matches[0]) / 100.0 + confidence_boost)
            
            # Extract target price if mentioned
            target_price = None
            price_matches = re.findall(r'target[:\s]+\$?([0-9,]+\.?[0-9]*)', content.lower())
            if price_matches:
                try:
                    target_price = float(price_matches[0].replace(',', ''))
                except:
                    target_price = None
            
            return {
                "recommendation": recommendation,
                "confidence_score": Decimal(str(round(confidence_score, 4))),
                "target_price": Decimal(str(target_price)) if target_price else None,
                "reasoning": content,
                "indicators": {
                    "ai_model": self.model,
                    "response_length": len(content),
                    "analysis_type": analysis_type,
                    "processed_at": datetime.utcnow().isoformat()
                },
                "expires_at": datetime.utcnow() + timedelta(hours=4)
            }
            
        except Exception as e:
            logger.error("Error parsing GPT response", error=str(e))
            return self._get_fallback_analysis(symbol, analysis_type)
    
    async def health_check(self) -> bool:
        """Check Azure OpenAI service health"""
        if not self.api_key or not self.endpoint:
            return False
        
        try:
            url = f"{self.endpoint}/openai/deployments/{self.deployment_name}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "api-key": self.api_key
            }
            
            # Simple health check request
            payload = {
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    params={"api-version": self.api_version},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except:
            return False
    
    def _get_fallback_analysis(self, symbol: str, analysis_type: str) -> Dict[str, Any]:
        """Return fallback analysis when API fails"""
        return {
            "recommendation": "HOLD",
            "confidence_score": Decimal("0.5"),
            "target_price": None,
            "reasoning": f"Azure OpenAI service unavailable. Fallback analysis for {symbol}.",
            "indicators": {
                "ai_model": f"{self.model}_fallback",
                "analysis_type": analysis_type,
                "fallback": True,
                "processed_at": datetime.utcnow().isoformat()
            },
            "expires_at": datetime.utcnow() + timedelta(minutes=30)
        }

# ================================
# DEEPSEEK SERVICE
# ================================

class DeepSeekService(AIServiceInterface):
    """DeepSeek-R1 API integration service"""
    
    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = settings.DEEPSEEK_BASE_URL
        self.model = "deepseek-r1"
        
    async def analyze_market(
        self, 
        symbol: str, 
        timeframe: str, 
        analysis_type: str,
        market_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze market using DeepSeek-R1"""
        
        if not self.api_key:
            logger.warning("DeepSeek API key not configured")
            return self._get_fallback_analysis(symbol, analysis_type)
        
        try:
            # Prepare request
            context = self._prepare_context(symbol, timeframe, analysis_type, market_data)
            
            payload = {
                "model": "deepseek-reasoner",
                "messages": [
                    {"role": "system", "content": "You are an expert financial analyst."},
                    {"role": "user", "content": context}
                ],
                "max_tokens": 1000,
                "temperature": 0.3
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_response(data, symbol, analysis_type)
                    else:
                        logger.error("DeepSeek API error", status=response.status)
                        return self._get_fallback_analysis(symbol, analysis_type)
                        
        except Exception as e:
            logger.error("DeepSeek service error", error=str(e))
            return self._get_fallback_analysis(symbol, analysis_type)
    
    def _prepare_context(self, symbol: str, timeframe: str, analysis_type: str, market_data: Dict[str, Any]) -> str:
        """Prepare analysis context"""
        context = f"Analyze {symbol} for {analysis_type} analysis on {timeframe} timeframe. "
        
        if market_data:
            context += f"Current price: ${market_data.get('price', 'N/A')}, "
            context += f"24h change: {market_data.get('change_24h', 'N/A')}%. "
        
        context += "Provide BUY/SELL/HOLD recommendation with confidence 0-1 and reasoning."
        return context
    
    def _parse_response(self, response_data: Dict[str, Any], symbol: str, analysis_type: str) -> Dict[str, Any]:
        """Parse DeepSeek response"""
        try:
            content = response_data["choices"][0]["message"]["content"]
            
            # Simple parsing logic
            recommendation = "HOLD"
            if "BUY" in content.upper():
                recommendation = "BUY"
            elif "SELL" in content.upper():
                recommendation = "SELL"
            
            return {
                "recommendation": recommendation,
                "confidence_score": Decimal("0.75"),
                "target_price": None,
                "reasoning": content,
                "indicators": {
                    "ai_model": self.model,
                    "analysis_type": analysis_type
                },
                "expires_at": datetime.utcnow() + timedelta(hours=4)
            }
        except:
            return self._get_fallback_analysis(symbol, analysis_type)
    
    async def health_check(self) -> bool:
        """Check DeepSeek service health"""
        if not self.api_key:
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/models",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except:
            return False
    
    def _get_fallback_analysis(self, symbol: str, analysis_type: str) -> Dict[str, Any]:
        """Fallback analysis"""
        return {
            "recommendation": "HOLD",
            "confidence_score": Decimal("0.5"),
            "target_price": None,
            "reasoning": f"DeepSeek service unavailable. Fallback analysis for {symbol}.",
            "indicators": {
                "ai_model": f"{self.model}_fallback",
                "analysis_type": analysis_type,
                "fallback": True
            },
            "expires_at": datetime.utcnow() + timedelta(minutes=30)
        }

# ================================
# OLLAMA SERVICE
# ================================

class OllamaService(AIServiceInterface):
    """Ollama local AI service integration"""
    
    def __init__(self):
        self.endpoint = settings.OLLAMA_ENDPOINT
        self.model = "gemma:7b"  # Default model
        
    async def analyze_market(
        self, 
        symbol: str, 
        timeframe: str, 
        analysis_type: str,
        market_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze market using Ollama local models"""
        
        try:
            context = self._prepare_context(symbol, timeframe, analysis_type, market_data)
            
            payload = {
                "model": self.model,
                "prompt": context,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_k": 10,
                    "top_p": 0.9
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.endpoint}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_response(data, symbol, analysis_type)
                    else:
                        logger.error("Ollama API error", status=response.status)
                        return self._get_fallback_analysis(symbol, analysis_type)
                        
        except Exception as e:
            logger.error("Ollama service error", error=str(e))
            return self._get_fallback_analysis(symbol, analysis_type)
    
    def _prepare_context(self, symbol: str, timeframe: str, analysis_type: str, market_data: Dict[str, Any]) -> str:
        """Prepare analysis context"""
        context = f"As a financial analyst, analyze {symbol} for {analysis_type} trading recommendation. "
        
        if market_data:
            context += f"Price: ${market_data.get('price', 'N/A')}, "
            context += f"24h change: {market_data.get('change_24h', 'N/A')}%. "
        
        context += "Respond with BUY, SELL, or HOLD and brief reasoning."
        return context
    
    def _parse_response(self, response_data: Dict[str, Any], symbol: str, analysis_type: str) -> Dict[str, Any]:
        """Parse Ollama response"""
        try:
            content = response_data.get("response", "")
            
            recommendation = "HOLD"
            if "BUY" in content.upper():
                recommendation = "BUY"
            elif "SELL" in content.upper():
                recommendation = "SELL"
            
            return {
                "recommendation": recommendation,
                "confidence_score": Decimal("0.70"),
                "target_price": None,
                "reasoning": content,
                "indicators": {
                    "ai_model": self.model,
                    "analysis_type": analysis_type
                },
                "expires_at": datetime.utcnow() + timedelta(hours=4)
            }
        except:
            return self._get_fallback_analysis(symbol, analysis_type)
    
    async def health_check(self) -> bool:
        """Check Ollama service health"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.endpoint}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except:
            return False
    
    def _get_fallback_analysis(self, symbol: str, analysis_type: str) -> Dict[str, Any]:
        """Fallback analysis"""
        return {
            "recommendation": "HOLD",
            "confidence_score": Decimal("0.5"),
            "target_price": None,
            "reasoning": f"Ollama service unavailable. Fallback analysis for {symbol}.",
            "indicators": {
                "ai_model": f"{self.model}_fallback",
                "analysis_type": analysis_type,
                "fallback": True
            },
            "expires_at": datetime.utcnow() + timedelta(minutes=30)
        }

# ================================
# AI SERVICE MANAGER
# ================================

class AIServiceManager:
    """Manager for all AI services with consensus logic"""
    
    def __init__(self):
        self.services = {
            "azure_openai": AzureOpenAIService(),
            "deepseek": DeepSeekService(),
            "ollama": OllamaService()
        }
        self.service_weights = {
            "azure_openai": 0.5,  # GPT-4 gets highest weight
            "deepseek": 0.3,
            "ollama": 0.2
        }
    
    async def analyze_with_consensus(
        self,
        symbol: str,
        timeframe: str,
        analysis_type: str,
        market_data: Dict[str, Any] = None,
        services: List[str] = None
    ) -> Dict[str, Any]:
        """Perform analysis with multiple AI services and create consensus"""
        
        if services is None:
            services = list(self.services.keys())
        
        results = {}
        
        # Run analyses in parallel
        tasks = []
        for service_name in services:
            if service_name in self.services:
                task = self.services[service_name].analyze_market(
                    symbol, timeframe, analysis_type, market_data
                )
                tasks.append((service_name, task))
        
        # Collect results
        for service_name, task in tasks:
            try:
                result = await task
                results[service_name] = result
                logger.info("AI analysis completed", service=service_name, symbol=symbol)
            except Exception as e:
                logger.error("AI service failed", service=service_name, error=str(e))
        
        # Create consensus
        return self._create_consensus(results, symbol, analysis_type)
    
    def _create_consensus(
        self,
        results: Dict[str, Dict[str, Any]],
        symbol: str,
        analysis_type: str
    ) -> Dict[str, Any]:
        """Create consensus from multiple AI analyses"""
        
        if not results:
            return {
                "recommendation": "HOLD",
                "confidence_score": Decimal("0.0"),
                "target_price": None,
                "reasoning": "No AI services available for analysis",
                "indicators": {
                    "ai_model": "consensus_fallback",
                    "analysis_type": analysis_type,
                    "services_used": [],
                    "consensus_method": "fallback"
                },
                "expires_at": datetime.utcnow() + timedelta(hours=1)
            }
        
        # Calculate weighted recommendations
        buy_weight = 0
        sell_weight = 0
        hold_weight = 0
        
        total_confidence = Decimal("0")
        target_prices = []
        reasoning_parts = []
        
        for service_name, result in results.items():
            weight = self.service_weights.get(service_name, 0.1)
            confidence = result.get("confidence_score", Decimal("0.5"))
            weighted_confidence = confidence * Decimal(str(weight))
            
            recommendation = result.get("recommendation", "HOLD")
            if recommendation == "BUY":
                buy_weight += weighted_confidence
            elif recommendation == "SELL":
                sell_weight += weighted_confidence
            else:
                hold_weight += weighted_confidence
            
            total_confidence += weighted_confidence
            
            if result.get("target_price"):
                target_prices.append(result["target_price"])
            
            reasoning_parts.append(f"{service_name}: {result.get('reasoning', 'No reasoning')[:100]}...")
        
        # Determine consensus recommendation
        if buy_weight > sell_weight and buy_weight > hold_weight:
            consensus_recommendation = "BUY"
            consensus_confidence = buy_weight
        elif sell_weight > buy_weight and sell_weight > hold_weight:
            consensus_recommendation = "SELL"
            consensus_confidence = sell_weight
        else:
            consensus_recommendation = "HOLD"
            consensus_confidence = hold_weight
        
        # Calculate consensus target price
        consensus_target_price = None
        if target_prices:
            consensus_target_price = sum(target_prices) / len(target_prices)
        
        # Create consensus reasoning
        consensus_reasoning = f"Consensus analysis for {symbol} based on {len(results)} AI models:\n"
        consensus_reasoning += f"BUY weight: {buy_weight:.3f}, SELL weight: {sell_weight:.3f}, HOLD weight: {hold_weight:.3f}\n\n"
        consensus_reasoning += "\n".join(reasoning_parts)
        
        return {
            "recommendation": consensus_recommendation,
            "confidence_score": min(Decimal("1.0"), consensus_confidence),
            "target_price": consensus_target_price,
            "reasoning": consensus_reasoning,
            "indicators": {
                "ai_model": "consensus",
                "analysis_type": analysis_type,
                "services_used": list(results.keys()),
                "individual_results": results,
                "buy_weight": float(buy_weight),
                "sell_weight": float(sell_weight),
                "hold_weight": float(hold_weight),
                "total_confidence": float(total_confidence),
                "consensus_method": "weighted_average"
            },
            "expires_at": datetime.utcnow() + timedelta(hours=4)
        }
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all AI services"""
        results = {}
        
        for name, service in self.services.items():
            try:
                results[name] = await service.health_check()
            except Exception as e:
                logger.error("Health check failed", service=name, error=str(e))
                results[name] = False
        
        return results

# ================================
# SERVICE INSTANCES
# ================================

# Global service manager instance
ai_service_manager = AIServiceManager()