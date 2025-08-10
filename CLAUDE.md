# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Bitpanda Trading Bot** project that aims to create an AI-powered automated trading system. The bot is designed to:

- Integrate multiple AI services (Azure OpenAI GPT-4, DeepSeek-R1, Ollama with Gemini/Mistral)
- Use web scraping and social media monitoring for market intelligence
- Execute trades via the Bitpanda API
- Operate with a budget of 500-800€ targeting short-term profitable trades (3 days to 3 months)
- Include Austrian tax considerations (future feature)

**⚠️ Important Security Note**: This project involves financial trading and API integrations. Always follow security best practices and never commit API keys or sensitive credentials.

## Project Status

**Current State**: Early planning phase
- Repository contains only initial documentation files (Claude-chat-0.1.md, LICENSE, Claude-files-0.0.1)
- No implementation code exists yet
- Comprehensive architecture planning completed in Claude-chat-0.1.md with detailed technical specifications
- Licensed under GPL-3.0

## Planned Architecture

Based on the planning documentation, this will be a microservices architecture with:

### Core Components
- **FastAPI Backend**: Main API server with Bitpanda integration
- **AI Analysis Engine**: Multi-AI consensus system for market analysis
- **Trading Engine**: Order management and risk assessment
- **Web Dashboard**: React-based frontend with real-time charts
- **Data Pipeline**: News scraping and social media monitoring

### Technology Stack
- **Backend**: Python with FastAPI, SQLAlchemy, Alembic
- **Database**: PostgreSQL with TimescaleDB for time-series data
- **Frontend**: React with TradingView charts
- **Infrastructure**: Docker, Kubernetes, Docker Compose
- **CI/CD**: GitHub Actions
- **Monitoring**: Prometheus/Grafana stack

### Key APIs & AI Services
- **Bitpanda Pro API**: Trading execution and portfolio management  
- **AI Analysis Pipeline**:
  - Azure OpenAI API (GPT-4) - Primary analysis
  - DeepSeek-R1 API - Secondary analysis  
  - Ollama (Gemini/Mistral) - Local analysis
  - Multi-AI consensus algorithm for decision making
- **Data Sources**: News APIs, social media monitoring (Twitter, Reddit)
- **Market Data**: Real-time price feeds and technical indicators

## Development Guidelines

### Project Structure (Planned)
```
ai-trading-bot/
├── backend/           # FastAPI application
├── frontend/          # React dashboard
├── ai-engine/         # AI analysis services
├── trading-engine/    # Trading logic
├── data-pipeline/     # Data collection services
├── infrastructure/    # Docker, K8s configs
└── docs/             # Technical documentation
```

### Security Requirements
- Use environment variables for all API keys and secrets
- Implement proper authentication and authorization
- Follow financial software security standards
- Never log sensitive trading data or API credentials

### Austrian Legal Compliance
- Future feature: Tax reporting integration
- Ensure compliance with Austrian financial regulations
- Implement audit trails for all trades

## Development Setup (When Implemented)

This section will be updated once the codebase is implemented with:
- Local development setup instructions
- Docker Compose configuration for PostgreSQL + TimescaleDB
- Environment variable setup (.env files for different environments)
- Database migration commands using Alembic
- Testing procedures with pytest
- Paper trading mode for safe development

### Expected Development Commands (Planned)
```bash
# Development setup
make setup-dev          # Install dependencies and setup environment
make db-migrate         # Run database migrations  
make test               # Run test suite
make lint               # Run linting (ruff, mypy)
make format             # Format code (black, ruff)

# Running services
make dev                # Start development environment with Docker Compose
make trading-bot        # Start trading bot in paper mode
make dashboard          # Start React dashboard

# Production
make build              # Build all Docker images
make deploy             # Deploy to Kubernetes
```

## Testing Strategy (Planned)

- Paper trading mode for safe testing
- Unit tests for all trading logic
- Integration tests for API connections
- Load testing for real-time data processing
- Security testing for API endpoints

## Deployment (Planned)

### Local Development
- Docker Compose with PostgreSQL + TimescaleDB + Redis
- Paper trading mode enabled by default
- Hot reload for all services

### Production Deployment  
- Kubernetes cluster with microservices architecture
- Automated CI/CD with GitHub Actions
- Multi-environment support (staging/production)
- Horizontal Pod Autoscaler for high-frequency trading
- Persistent volumes for database and time-series data
- Ingress with SSL/TLS termination
- Monitoring stack (Prometheus, Grafana, Jaeger)

### Environment Configuration
- Separate .env files for each environment
- Kubernetes secrets for API keys and credentials
- ConfigMaps for non-sensitive configuration

## Implementation Notes

When implementing this system:

1. **Start with Core Backend**: FastAPI with basic Bitpanda API integration
2. **Security First**: Never commit API keys; use environment variables exclusively  
3. **Paper Trading**: Implement and test all logic in paper trading mode first
4. **Incremental AI Integration**: Add AI services one at a time with fallback mechanisms
5. **Database Design**: Use TimescaleDB for efficient time-series data storage
6. **Error Handling**: Implement comprehensive error handling for all API calls
7. **Monitoring**: Add logging and metrics from day one
8. **Testing**: Write tests for all trading logic before live deployment

## Important Development Reminders

- This is a financial application - prioritize security and data integrity
- Test thoroughly in paper trading mode before any live trading
- Follow Austrian financial compliance requirements
- All trading decisions should be auditable and logged
- Implement circuit breakers and risk management controls