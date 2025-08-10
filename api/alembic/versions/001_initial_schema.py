"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2025-08-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "timescaledb" CASCADE')
    
    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('is_verified', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('last_login', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('risk_tolerance', sa.DECIMAL(precision=3, scale=2), nullable=True, server_default=sa.text('0.05')),
        sa.Column('max_portfolio_risk', sa.DECIMAL(precision=3, scale=2), nullable=True, server_default=sa.text('0.15')),
        sa.Column('auto_trading_enabled', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('tax_residence', sa.String(length=2), nullable=True, server_default=sa.text("'AT'")),
        sa.Column('tax_id', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('risk_tolerance BETWEEN 0 AND 1', name='valid_risk_tolerance'),
        sa.CheckConstraint('max_portfolio_risk BETWEEN 0 AND 1', name='valid_portfolio_risk')
    )
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_username', 'users', ['username'])
    op.create_index('idx_users_active', 'users', ['is_active'], postgresql_where=sa.text('is_active = true'))
    op.create_unique_constraint(None, 'users', ['username'])
    op.create_unique_constraint(None, 'users', ['email'])

    # Create assets table
    op.create_table('assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('asset_type', sa.String(length=20), nullable=False),
        sa.Column('exchange', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('sector', sa.String(length=50), nullable=True),
        sa.Column('market_cap', sa.DECIMAL(precision=20, scale=0), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("asset_type IN ('crypto', 'stock', 'etf', 'commodity', 'forex')", name='valid_asset_type')
    )
    op.create_index('idx_assets_symbol', 'assets', ['symbol'])
    op.create_index('idx_assets_type', 'assets', ['asset_type'])
    op.create_index('idx_assets_active', 'assets', ['is_active'], postgresql_where=sa.text('is_active = true'))
    op.create_unique_constraint(None, 'assets', ['symbol'])

    # Create portfolios table
    op.create_table('portfolios',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False, server_default=sa.text("'Main Portfolio'")),
        sa.Column('initial_balance', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('current_balance', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('total_invested', sa.DECIMAL(precision=15, scale=2), nullable=True, server_default=sa.text('0')),
        sa.Column('total_profit_loss', sa.DECIMAL(precision=15, scale=2), nullable=True, server_default=sa.text('0')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='unique_user_portfolio')
    )
    op.create_index('idx_portfolios_user_id', 'portfolios', ['user_id'])
    op.create_index('idx_portfolios_updated_at', 'portfolios', ['updated_at'])

    # Create positions table
    op.create_table('positions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('portfolio_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('quantity', sa.DECIMAL(precision=20, scale=8), nullable=False),
        sa.Column('avg_buy_price', sa.DECIMAL(precision=15, scale=8), nullable=False),
        sa.Column('current_price', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('unrealized_pnl', sa.DECIMAL(precision=15, scale=2), nullable=True, server_default=sa.text('0')),
        sa.Column('realized_pnl', sa.DECIMAL(precision=15, scale=2), nullable=True, server_default=sa.text('0')),
        sa.Column('status', sa.String(length=20), nullable=True, server_default=sa.text("'open'")),
        sa.Column('opened_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('closed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('stop_loss_price', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('take_profit_price', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('open', 'closed', 'partial')", name='valid_status'),
        sa.CheckConstraint('quantity > 0', name='positive_quantity'),
        sa.CheckConstraint('avg_buy_price > 0', name='positive_price')
    )
    op.create_index('idx_positions_portfolio_id', 'positions', ['portfolio_id'])
    op.create_index('idx_positions_asset_id', 'positions', ['asset_id'])
    op.create_index('idx_positions_status', 'positions', ['status'])
    op.create_index('idx_positions_opened_at', 'positions', ['opened_at'])

    # Create orders table
    op.create_table('orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('portfolio_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('position_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_type', sa.String(length=20), nullable=False),
        sa.Column('quantity', sa.DECIMAL(precision=20, scale=8), nullable=False),
        sa.Column('price', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('stop_price', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, server_default=sa.text("'pending'")),
        sa.Column('executed_quantity', sa.DECIMAL(precision=20, scale=8), nullable=True, server_default=sa.text('0')),
        sa.Column('executed_price', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('executed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('external_order_id', sa.String(length=100), nullable=True),
        sa.Column('fee_amount', sa.DECIMAL(precision=15, scale=8), nullable=True, server_default=sa.text('0')),
        sa.Column('fee_currency', sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("order_type IN ('buy', 'sell', 'stop_loss', 'take_profit', 'market', 'limit')", name='valid_order_type'),
        sa.CheckConstraint("status IN ('pending', 'executed', 'cancelled', 'failed', 'partial')", name='valid_order_status'),
        sa.CheckConstraint('quantity > 0', name='positive_order_quantity')
    )
    op.create_index('idx_orders_portfolio_id', 'orders', ['portfolio_id'])
    op.create_index('idx_orders_asset_id', 'orders', ['asset_id'])
    op.create_index('idx_orders_status', 'orders', ['status'])
    op.create_index('idx_orders_created_at', 'orders', ['created_at'])
    op.create_index('idx_orders_external_id', 'orders', ['external_order_id'])

    # Create ai_analyses table
    op.create_table('ai_analyses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_type', sa.String(length=20), nullable=False),
        sa.Column('ai_model', sa.String(length=50), nullable=False),
        sa.Column('recommendation', sa.String(length=10), nullable=False),
        sa.Column('confidence_score', sa.DECIMAL(precision=5, scale=4), nullable=False),
        sa.Column('target_price', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('indicators', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("analysis_type IN ('fundamental', 'technical', 'sentiment', 'consensus')", name='valid_analysis_type'),
        sa.CheckConstraint("recommendation IN ('BUY', 'SELL', 'HOLD')", name='valid_recommendation'),
        sa.CheckConstraint('confidence_score BETWEEN 0 AND 1', name='valid_confidence')
    )
    op.create_index('idx_ai_analyses_asset_id', 'ai_analyses', ['asset_id'])
    op.create_index('idx_ai_analyses_type', 'ai_analyses', ['analysis_type'])
    op.create_index('idx_ai_analyses_created_at', 'ai_analyses', ['created_at'])
    op.create_index('idx_ai_analyses_expires_at', 'ai_analyses', ['expires_at'])

    # Create risk_alerts table
    op.create_table('risk_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('portfolio_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('alert_type', sa.String(length=30), nullable=False),
        sa.Column('severity', sa.String(length=10), nullable=False),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('current_value', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('threshold_value', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('acknowledged_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("alert_type IN ('drawdown', 'concentration', 'volatility', 'stop_loss', 'margin_call')", name='valid_alert_type'),
        sa.CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name='valid_severity')
    )

    # Create system_config table
    op.create_table('system_config',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('key')
    )

    # Create TimescaleDB hypertables
    # Market data table
    op.create_table('market_data',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timeframe', sa.String(length=10), nullable=False),
        sa.Column('open_price', sa.DECIMAL(precision=15, scale=8), nullable=False),
        sa.Column('high_price', sa.DECIMAL(precision=15, scale=8), nullable=False),
        sa.Column('low_price', sa.DECIMAL(precision=15, scale=8), nullable=False),
        sa.Column('close_price', sa.DECIMAL(precision=15, scale=8), nullable=False),
        sa.Column('volume', sa.DECIMAL(precision=20, scale=8), nullable=False),
        sa.Column('volume_quote', sa.DECIMAL(precision=20, scale=8), nullable=True),
        sa.Column('trades_count', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ),
        sa.PrimaryKeyConstraint('time', 'asset_id', 'timeframe')
    )
    
    # Convert to hypertable
    op.execute("SELECT create_hypertable('market_data', 'time')")
    op.create_index('idx_market_data_asset_timeframe', 'market_data', ['asset_id', 'timeframe', 'time'], postgresql_ops={'time': 'DESC'})

    # Portfolio history table
    op.create_table('portfolio_history',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('portfolio_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('total_value', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('cash_balance', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('invested_value', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('unrealized_pnl', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('realized_pnl', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('daily_return', sa.DECIMAL(precision=8, scale=6), nullable=True),
        sa.Column('sharpe_ratio', sa.DECIMAL(precision=8, scale=4), nullable=True),
        sa.Column('max_drawdown', sa.DECIMAL(precision=8, scale=4), nullable=True),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('time', 'portfolio_id')
    )
    op.execute("SELECT create_hypertable('portfolio_history', 'time')")
    op.create_index('idx_portfolio_history_portfolio', 'portfolio_history', ['portfolio_id', 'time'], postgresql_ops={'time': 'DESC'})

    # Price updates table
    op.create_table('price_updates',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('price', sa.DECIMAL(precision=15, scale=8), nullable=False),
        sa.Column('volume_24h', sa.DECIMAL(precision=20, scale=8), nullable=True),
        sa.Column('change_24h', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('change_percent_24h', sa.DECIMAL(precision=8, scale=4), nullable=True),
        sa.Column('market_cap', sa.DECIMAL(precision=20, scale=0), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ),
        sa.PrimaryKeyConstraint('time', 'asset_id')
    )
    op.execute("SELECT create_hypertable('price_updates', 'time')")
    op.create_index('idx_price_updates_asset', 'price_updates', ['asset_id', 'time'], postgresql_ops={'time': 'DESC'})

    # Sentiment data table
    op.create_table('sentiment_data',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('twitter_sentiment', sa.DECIMAL(precision=5, scale=4), nullable=True),
        sa.Column('reddit_sentiment', sa.DECIMAL(precision=5, scale=4), nullable=True),
        sa.Column('news_sentiment', sa.DECIMAL(precision=5, scale=4), nullable=True),
        sa.Column('overall_sentiment', sa.DECIMAL(precision=5, scale=4), nullable=True),
        sa.Column('twitter_mentions', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('reddit_mentions', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('news_articles', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('fear_greed_index', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ),
        sa.PrimaryKeyConstraint('time', 'asset_id')
    )
    op.execute("SELECT create_hypertable('sentiment_data', 'time')")
    op.create_index('idx_sentiment_data_asset', 'sentiment_data', ['asset_id', 'time'], postgresql_ops={'time': 'DESC'})

    # System metrics table
    op.create_table('system_metrics',
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('value', sa.DECIMAL(precision=15, scale=8), nullable=True),
        sa.Column('string_value', sa.String(), nullable=True),
        sa.Column('labels', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('time', 'metric_name')
    )
    op.execute("SELECT create_hypertable('system_metrics', 'time')")

    # Insert sample data
    op.execute("""
        INSERT INTO assets (symbol, name, asset_type, exchange) VALUES
        ('BTC', 'Bitcoin', 'crypto', 'bitpanda'),
        ('ETH', 'Ethereum', 'crypto', 'bitpanda'),
        ('AAPL', 'Apple Inc.', 'stock', 'nasdaq'),
        ('GOOGL', 'Alphabet Inc.', 'stock', 'nasdaq'),
        ('SPY', 'SPDR S&P 500 ETF', 'etf', 'nyse'),
        ('GOLD', 'Gold', 'commodity', 'lbma')
    """)
    
    op.execute("""
        INSERT INTO system_config (key, value, description) VALUES
        ('max_daily_trades', '50', 'Maximum trades per day per user'),
        ('min_trade_amount', '10.00', 'Minimum trade amount in EUR'),
        ('max_position_size', '0.20', 'Maximum position size as % of portfolio'),
        ('stop_loss_default', '0.05', 'Default stop loss percentage'),
        ('take_profit_default', '0.15', 'Default take profit percentage')
    """)


def downgrade() -> None:
    # Drop all tables in reverse order
    op.drop_table('system_metrics')
    op.drop_table('sentiment_data')
    op.drop_table('price_updates')
    op.drop_table('portfolio_history')
    op.drop_table('market_data')
    op.drop_table('system_config')
    op.drop_table('risk_alerts')
    op.drop_table('ai_analyses')
    op.drop_table('orders')
    op.drop_table('positions')
    op.drop_table('portfolios')
    op.drop_table('assets')
    op.drop_table('users')
    
    # Drop extensions
    op.execute('DROP EXTENSION IF EXISTS timescaledb CASCADE')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')