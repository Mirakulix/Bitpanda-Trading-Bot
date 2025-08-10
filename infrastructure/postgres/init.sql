-- AI Trading Bot Database Initialization Script
-- This script sets up the database for development and production environments

-- ================================
-- EXTENSIONS
-- ================================

-- Create required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "timescaledb" CASCADE;

-- Enable pgcrypto for additional security features
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enable pg_stat_statements for query performance monitoring
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- ================================
-- ROLES AND PERMISSIONS
-- ================================

-- Create application roles
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_bot_app') THEN
        CREATE ROLE trading_bot_app;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_bot_readonly') THEN
        CREATE ROLE trading_bot_readonly;
    END IF;
END
$$;

-- ================================
-- UTILITY FUNCTIONS
-- ================================

-- Function to calculate portfolio performance metrics
CREATE OR REPLACE FUNCTION calculate_portfolio_performance(
    p_portfolio_id UUID,
    p_start_date TIMESTAMPTZ DEFAULT NOW() - INTERVAL '30 days'
)
RETURNS TABLE(
    total_return DECIMAL(8,4),
    annualized_return DECIMAL(8,4),
    sharpe_ratio DECIMAL(8,4),
    max_drawdown DECIMAL(8,4),
    volatility DECIMAL(8,4)
) AS $$
DECLARE
    start_value DECIMAL(15,2);
    end_value DECIMAL(15,2);
    days_count INTEGER;
    daily_returns DECIMAL[];
    avg_return DECIMAL;
    return_std DECIMAL;
    risk_free_rate DECIMAL := 0.02; -- 2% annual risk-free rate
BEGIN
    -- Get the number of days
    days_count := EXTRACT(days FROM (NOW() - p_start_date));
    
    -- Get start and end portfolio values
    SELECT total_value INTO start_value
    FROM portfolio_history 
    WHERE portfolio_id = p_portfolio_id 
        AND time >= p_start_date 
    ORDER BY time ASC 
    LIMIT 1;
    
    SELECT total_value INTO end_value
    FROM portfolio_history 
    WHERE portfolio_id = p_portfolio_id 
    ORDER BY time DESC 
    LIMIT 1;
    
    -- Handle case where no data is available
    IF start_value IS NULL OR end_value IS NULL THEN
        RETURN QUERY SELECT 
            0.0::DECIMAL(8,4) as total_return,
            0.0::DECIMAL(8,4) as annualized_return,
            0.0::DECIMAL(8,4) as sharpe_ratio,
            0.0::DECIMAL(8,4) as max_drawdown,
            0.0::DECIMAL(8,4) as volatility;
        RETURN;
    END IF;
    
    -- Calculate basic metrics
    total_return := (end_value - start_value) / start_value;
    annualized_return := (POWER((end_value / start_value), (365.0 / days_count)) - 1);
    
    -- For now, return basic calculations
    -- TODO: Implement proper Sharpe ratio, max drawdown, and volatility calculations
    RETURN QUERY SELECT 
        total_return,
        annualized_return,
        0.0::DECIMAL(8,4) as sharpe_ratio,
        0.0::DECIMAL(8,4) as max_drawdown,
        0.0::DECIMAL(8,4) as volatility;
END;
$$ LANGUAGE plpgsql;

-- Trigger function to update position P&L when current_price changes
CREATE OR REPLACE FUNCTION update_position_pnl()
RETURNS TRIGGER AS $$
BEGIN
    -- Update unrealized P&L when current_price changes
    NEW.unrealized_pnl = (NEW.current_price - NEW.avg_buy_price) * NEW.quantity;
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger function to update portfolio updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to get current portfolio summary
CREATE OR REPLACE FUNCTION get_portfolio_summary(p_portfolio_id UUID)
RETURNS TABLE(
    portfolio_id UUID,
    total_value DECIMAL(15,2),
    cash_balance DECIMAL(15,2),
    invested_value DECIMAL(15,2),
    unrealized_pnl DECIMAL(15,2),
    realized_pnl DECIMAL(15,2),
    positions_count BIGINT,
    active_orders_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id as portfolio_id,
        p.current_balance + COALESCE(SUM(pos.quantity * pos.current_price), 0) as total_value,
        p.current_balance as cash_balance,
        COALESCE(SUM(pos.quantity * pos.current_price), 0) as invested_value,
        COALESCE(SUM(pos.unrealized_pnl), 0) as unrealized_pnl,
        COALESCE(SUM(pos.realized_pnl), 0) as realized_pnl,
        COUNT(pos.id) as positions_count,
        (SELECT COUNT(*) FROM orders o WHERE o.portfolio_id = p.id AND o.status = 'pending') as active_orders_count
    FROM portfolios p
    LEFT JOIN positions pos ON p.id = pos.portfolio_id AND pos.status = 'open'
    WHERE p.id = p_portfolio_id
    GROUP BY p.id, p.current_balance;
END;
$$ LANGUAGE plpgsql;

-- ================================
-- DATA RETENTION POLICIES
-- ================================

-- Function to setup data retention policies (called after hypertables are created)
CREATE OR REPLACE FUNCTION setup_retention_policies()
RETURNS void AS $$
BEGIN
    -- Set up retention policies for TimescaleDB hypertables
    -- Keep detailed market data for 1 year
    PERFORM add_retention_policy('market_data', INTERVAL '1 year');
    
    -- Keep sentiment data for 6 months
    PERFORM add_retention_policy('sentiment_data', INTERVAL '6 months');
    
    -- Keep system metrics for 3 months
    PERFORM add_retention_policy('system_metrics', INTERVAL '3 months');
    
    -- Portfolio history is kept indefinitely for compliance
    -- Price updates kept for 1 year
    PERFORM add_retention_policy('price_updates', INTERVAL '1 year');
    
EXCEPTION
    WHEN OTHERS THEN
        -- Log the error but don't fail the initialization
        RAISE NOTICE 'Could not set up retention policies: %', SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- ================================
-- VIEWS FOR COMMON QUERIES
-- ================================

-- View for current portfolio overview
CREATE OR REPLACE VIEW current_portfolio_view AS
SELECT 
    p.id as portfolio_id,
    p.user_id,
    p.name as portfolio_name,
    p.current_balance,
    COUNT(pos.id) as positions_count,
    COALESCE(SUM(pos.quantity * pos.current_price), 0) as total_invested_value,
    COALESCE(SUM(pos.unrealized_pnl), 0) as total_unrealized_pnl,
    (p.current_balance + COALESCE(SUM(pos.quantity * pos.current_price), 0)) as total_portfolio_value,
    p.created_at,
    p.updated_at
FROM portfolios p
LEFT JOIN positions pos ON p.id = pos.portfolio_id AND pos.status = 'open'
GROUP BY p.id, p.user_id, p.name, p.current_balance, p.created_at, p.updated_at;

-- View for latest AI consensus
CREATE OR REPLACE VIEW latest_ai_consensus AS
SELECT DISTINCT ON (aa.asset_id)
    aa.asset_id,
    a.symbol,
    a.name as asset_name,
    aa.recommendation,
    aa.confidence_score,
    aa.target_price,
    aa.reasoning,
    aa.ai_model,
    aa.created_at,
    aa.expires_at
FROM ai_analyses aa
JOIN assets a ON aa.asset_id = a.id
WHERE aa.analysis_type = 'consensus'
    AND (aa.expires_at IS NULL OR aa.expires_at > NOW())
ORDER BY aa.asset_id, aa.created_at DESC;

-- View for active risk alerts
CREATE OR REPLACE VIEW active_risk_alerts AS
SELECT 
    ra.*,
    u.username,
    u.email,
    p.name as portfolio_name
FROM risk_alerts ra
JOIN users u ON ra.user_id = u.id
LEFT JOIN portfolios p ON ra.portfolio_id = p.id
WHERE ra.is_active = true
    AND ra.resolved_at IS NULL
ORDER BY 
    CASE ra.severity 
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        WHEN 'low' THEN 4
        ELSE 5
    END,
    ra.created_at DESC;

-- View for trading performance summary
CREATE OR REPLACE VIEW trading_performance_view AS
SELECT 
    p.id as portfolio_id,
    p.user_id,
    COUNT(o.id) as total_orders,
    COUNT(CASE WHEN o.status = 'executed' THEN 1 END) as executed_orders,
    COUNT(CASE WHEN o.order_type = 'buy' AND o.status = 'executed' THEN 1 END) as buy_orders,
    COUNT(CASE WHEN o.order_type = 'sell' AND o.status = 'executed' THEN 1 END) as sell_orders,
    COALESCE(SUM(CASE WHEN o.status = 'executed' THEN o.fee_amount ELSE 0 END), 0) as total_fees,
    AVG(CASE WHEN o.status = 'executed' THEN o.executed_price END) as avg_execution_price
FROM portfolios p
LEFT JOIN orders o ON p.id = o.portfolio_id
WHERE o.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY p.id, p.user_id;

-- ================================
-- NOTIFICATION FUNCTIONS
-- ================================

-- Function to notify about risk alerts
CREATE OR REPLACE FUNCTION notify_risk_alert()
RETURNS TRIGGER AS $$
BEGIN
    -- Send notification for critical and high severity alerts
    IF NEW.severity IN ('critical', 'high') THEN
        PERFORM pg_notify('risk_alert', 
            json_build_object(
                'alert_id', NEW.id,
                'user_id', NEW.user_id,
                'portfolio_id', NEW.portfolio_id,
                'alert_type', NEW.alert_type,
                'severity', NEW.severity,
                'message', NEW.message
            )::text
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ================================
-- SAMPLE DATA FOR DEVELOPMENT
-- ================================

-- Function to insert sample development data
CREATE OR REPLACE FUNCTION insert_sample_data()
RETURNS void AS $$
BEGIN
    -- Only insert sample data if we're in development mode
    IF current_setting('app.environment', true) = 'development' THEN
        
        -- Sample user (password hash for 'password123')
        INSERT INTO users (username, email, password_hash, is_verified) 
        VALUES (
            'demo_user', 
            'demo@tradingbot.local', 
            '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewaBnBdmcCzg5Ye2', 
            true
        ) ON CONFLICT (username) DO NOTHING;
        
        -- Sample portfolio
        INSERT INTO portfolios (user_id, name, initial_balance, current_balance)
        SELECT u.id, 'Demo Portfolio', 1000.00, 1000.00
        FROM users u WHERE u.username = 'demo_user'
        ON CONFLICT (user_id, name) DO NOTHING;
        
        RAISE NOTICE 'Sample development data inserted successfully';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ================================
-- HEALTH CHECK FUNCTIONS
-- ================================

-- Function to check database health
CREATE OR REPLACE FUNCTION health_check()
RETURNS TABLE(
    component TEXT,
    status TEXT,
    details JSONB
) AS $$
BEGIN
    -- Check basic connectivity
    RETURN QUERY SELECT 
        'database'::TEXT as component,
        'healthy'::TEXT as status,
        json_build_object(
            'timestamp', NOW(),
            'version', version(),
            'active_connections', (SELECT count(*) FROM pg_stat_activity)
        )::JSONB as details;
    
    -- Check TimescaleDB extension
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        RETURN QUERY SELECT 
            'timescaledb'::TEXT as component,
            'healthy'::TEXT as status,
            json_build_object(
                'version', (SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'),
                'hypertables', (SELECT count(*) FROM _timescaledb_catalog.hypertable)
            )::JSONB as details;
    ELSE
        RETURN QUERY SELECT 
            'timescaledb'::TEXT as component,
            'missing'::TEXT as status,
            '{}'::JSONB as details;
    END IF;
    
    -- Check table counts
    RETURN QUERY SELECT 
        'data_integrity'::TEXT as component,
        'healthy'::TEXT as status,
        json_build_object(
            'users', (SELECT count(*) FROM users),
            'portfolios', (SELECT count(*) FROM portfolios),
            'assets', (SELECT count(*) FROM assets),
            'positions', (SELECT count(*) FROM positions),
            'orders', (SELECT count(*) FROM orders)
        )::JSONB as details;
        
END;
$$ LANGUAGE plpgsql;

-- ================================
-- PERFORMANCE MONITORING
-- ================================

-- Function to get database performance metrics
CREATE OR REPLACE FUNCTION get_performance_metrics()
RETURNS TABLE(
    metric_name TEXT,
    metric_value DECIMAL,
    description TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'active_connections'::TEXT,
        (SELECT count(*)::DECIMAL FROM pg_stat_activity WHERE state = 'active'),
        'Number of active database connections'::TEXT
    UNION ALL
    SELECT 
        'total_connections'::TEXT,
        (SELECT count(*)::DECIMAL FROM pg_stat_activity),
        'Total number of database connections'::TEXT
    UNION ALL
    SELECT 
        'cache_hit_ratio'::TEXT,
        ROUND((sum(blks_hit) * 100.0 / sum(blks_hit + blks_read))::DECIMAL, 2),
        'Database cache hit ratio percentage'::TEXT
    FROM pg_stat_database
    WHERE datname = current_database()
    UNION ALL
    SELECT 
        'database_size_mb'::TEXT,
        ROUND((pg_database_size(current_database()) / 1024.0 / 1024.0)::DECIMAL, 2),
        'Database size in megabytes'::TEXT;
END;
$$ LANGUAGE plpgsql;

-- ================================
-- INITIALIZATION COMPLETION
-- ================================

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'AI Trading Bot database initialization completed successfully';
    RAISE NOTICE 'Extensions created: uuid-ossp, timescaledb, pgcrypto, pg_stat_statements';
    RAISE NOTICE 'Utility functions created: calculate_portfolio_performance, health_check, get_performance_metrics';
    RAISE NOTICE 'Views created: current_portfolio_view, latest_ai_consensus, active_risk_alerts, trading_performance_view';
    RAISE NOTICE 'Ready for application connection';
END;
$$;