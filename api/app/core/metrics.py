"""
Prometheus metrics configuration for the AI Trading Bot
"""
import time
from typing import Dict, Any
from prometheus_client import Counter, Histogram, Gauge, Info
from fastapi import FastAPI, Request
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Metrics definitions
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)

active_connections = Gauge(
    "active_connections_total",
    "Total active connections"
)

trading_orders_total = Counter(
    "trading_orders_total",
    "Total trading orders",
    ["order_type", "status", "symbol"]
)

portfolio_value = Gauge(
    "portfolio_value_euros",
    "Current portfolio value in EUR",
    ["user_id"]
)

ai_analysis_requests_total = Counter(
    "ai_analysis_requests_total",
    "Total AI analysis requests",
    ["ai_model", "analysis_type"]
)

ai_analysis_duration_seconds = Histogram(
    "ai_analysis_duration_seconds",
    "AI analysis duration in seconds",
    ["ai_model", "analysis_type"]
)

bitpanda_api_requests_total = Counter(
    "bitpanda_api_requests_total",
    "Total Bitpanda API requests",
    ["endpoint", "status_code"]
)

risk_alerts_total = Counter(
    "risk_alerts_total",
    "Total risk alerts",
    ["alert_type", "severity"]
)

app_info = Info(
    "app_info",
    "Application information"
)


def setup_metrics(app: FastAPI):
    """Setup application metrics"""
    
    # Set application info
    app_info.info({
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "python_version": "3.11"
    })
    
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        """Middleware to collect HTTP metrics"""
        
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Record metrics
        method = request.method
        endpoint = request.url.path
        status_code = str(response.status_code)
        
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code
        ).inc()
        
        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
        
        return response
    
    logger.info("Metrics setup completed")


def record_trading_order(order_type: str, status: str, symbol: str):
    """Record trading order metric"""
    trading_orders_total.labels(
        order_type=order_type,
        status=status,
        symbol=symbol
    ).inc()


def update_portfolio_value(user_id: str, value: float):
    """Update portfolio value metric"""
    portfolio_value.labels(user_id=user_id).set(value)


def record_ai_analysis_request(ai_model: str, analysis_type: str, duration: float = None):
    """Record AI analysis request metrics"""
    ai_analysis_requests_total.labels(
        ai_model=ai_model,
        analysis_type=analysis_type
    ).inc()
    
    if duration is not None:
        ai_analysis_duration_seconds.labels(
            ai_model=ai_model,
            analysis_type=analysis_type
        ).observe(duration)


def record_bitpanda_api_request(endpoint: str, status_code: str):
    """Record Bitpanda API request metric"""
    bitpanda_api_requests_total.labels(
        endpoint=endpoint,
        status_code=status_code
    ).inc()


def record_risk_alert(alert_type: str, severity: str):
    """Record risk alert metric"""
    risk_alerts_total.labels(
        alert_type=alert_type,
        severity=severity
    ).inc()