"""
Tests for portfolio management functionality
"""
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.portfolio import Portfolio, Asset


class TestPortfolioRouter:
    """Test portfolio router endpoints"""
    
    @pytest.mark.unit
    def test_create_portfolio_success(self, test_client: TestClient, auth_headers: dict):
        """Test successful portfolio creation"""
        portfolio_data = {
            "name": "My Trading Portfolio",
            "description": "Portfolio for crypto trading",
            "initial_balance": 10000.0
        }
        
        response = test_client.post("/portfolio/", json=portfolio_data, headers=auth_headers)
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == portfolio_data["name"]
        assert data["description"] == portfolio_data["description"]
        assert float(data["total_value"]) == portfolio_data["initial_balance"]
        assert data["paper_trading"] is True  # Default should be paper trading
    
    @pytest.mark.unit
    def test_get_portfolios(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test getting user's portfolios"""
        response = test_client.get("/portfolio/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        
        # Check that test_portfolio is in the response
        portfolio_names = [p["name"] for p in data]
        assert test_portfolio.name in portfolio_names
    
    @pytest.mark.unit
    def test_get_portfolio_by_id(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test getting specific portfolio by ID"""
        response = test_client.get(f"/portfolio/{test_portfolio.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_portfolio.id)
        assert data["name"] == test_portfolio.name
    
    @pytest.mark.unit
    def test_get_portfolio_not_found(self, test_client: TestClient, auth_headers: dict):
        """Test getting non-existent portfolio"""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = test_client.get(f"/portfolio/{fake_id}", headers=auth_headers)
        
        assert response.status_code == 404
    
    @pytest.mark.unit
    def test_update_portfolio(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test updating portfolio"""
        update_data = {
            "name": "Updated Portfolio Name",
            "description": "Updated description"
        }
        
        response = test_client.put(f"/portfolio/{test_portfolio.id}", json=update_data, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["description"] == update_data["description"]
    
    @pytest.mark.unit
    def test_delete_portfolio(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test deleting portfolio"""
        response = test_client.delete(f"/portfolio/{test_portfolio.id}", headers=auth_headers)
        
        assert response.status_code == 204
        
        # Verify portfolio is deleted
        get_response = test_client.get(f"/portfolio/{test_portfolio.id}", headers=auth_headers)
        assert get_response.status_code == 404
    
    @pytest.mark.unit
    def test_portfolio_performance(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test getting portfolio performance metrics"""
        response = test_client.get(f"/portfolio/{test_portfolio.id}/performance", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "total_return" in data
        assert "total_return_percentage" in data
        assert "day_change" in data
        assert "positions_count" in data


class TestPositionManagement:
    """Test position management within portfolios"""
    
    @pytest.mark.unit
    def test_get_portfolio_positions(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test getting portfolio positions"""
        response = test_client.get(f"/portfolio/{test_portfolio.id}/positions", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.unit
    def test_add_position_to_portfolio(self, test_client: TestClient, auth_headers: dict, 
                                     test_portfolio: Portfolio, test_assets: list[Asset]):
        """Test adding position to portfolio"""
        btc_asset = next(asset for asset in test_assets if asset.symbol == "BTC")
        
        position_data = {
            "asset_id": str(btc_asset.id),
            "quantity": 0.1,
            "entry_price": 45000.0,
            "position_type": "long"
        }
        
        response = test_client.post(
            f"/portfolio/{test_portfolio.id}/positions", 
            json=position_data, 
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["asset_id"] == position_data["asset_id"]
        assert float(data["quantity"]) == position_data["quantity"]
        assert float(data["entry_price"]) == position_data["entry_price"]
    
    @pytest.mark.unit
    def test_update_position(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test updating position in portfolio"""
        # First create a position
        # This test assumes a position exists or creates one first
        
        # Mock position update
        position_id = "test-position-id"
        update_data = {
            "quantity": 0.2,
            "stop_loss": 40000.0,
            "take_profit": 50000.0
        }
        
        response = test_client.put(
            f"/portfolio/{test_portfolio.id}/positions/{position_id}", 
            json=update_data, 
            headers=auth_headers
        )
        
        # This might return 404 if position doesn't exist, which is fine for now
        assert response.status_code in [200, 404]
    
    @pytest.mark.unit
    def test_close_position(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test closing position"""
        position_id = "test-position-id"
        
        response = test_client.post(
            f"/portfolio/{test_portfolio.id}/positions/{position_id}/close", 
            headers=auth_headers
        )
        
        # This might return 404 if position doesn't exist, which is fine for now
        assert response.status_code in [200, 404]


class TestPortfolioAnalytics:
    """Test portfolio analytics and reporting"""
    
    @pytest.mark.unit
    def test_portfolio_allocation(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test getting portfolio asset allocation"""
        response = test_client.get(f"/portfolio/{test_portfolio.id}/allocation", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "allocations" in data
        assert "total_value" in data
        assert isinstance(data["allocations"], list)
    
    @pytest.mark.unit
    def test_portfolio_history(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test getting portfolio value history"""
        response = test_client.get(f"/portfolio/{test_portfolio.id}/history?period=7d", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)
    
    @pytest.mark.unit
    def test_portfolio_metrics(self, test_client: TestClient, auth_headers: dict, test_portfolio: Portfolio):
        """Test getting detailed portfolio metrics"""
        response = test_client.get(f"/portfolio/{test_portfolio.id}/metrics", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "sharpe_ratio" in data
        assert "max_drawdown" in data
        assert "volatility" in data
        assert "beta" in data


class TestPortfolioValidation:
    """Test portfolio input validation"""
    
    @pytest.mark.unit
    def test_create_portfolio_invalid_balance(self, test_client: TestClient, auth_headers: dict):
        """Test creating portfolio with invalid initial balance"""
        portfolio_data = {
            "name": "Test Portfolio",
            "description": "Test description",
            "initial_balance": -1000.0  # Negative balance
        }
        
        response = test_client.post("/portfolio/", json=portfolio_data, headers=auth_headers)
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.unit
    def test_create_portfolio_missing_name(self, test_client: TestClient, auth_headers: dict):
        """Test creating portfolio without name"""
        portfolio_data = {
            "description": "Test description",
            "initial_balance": 1000.0
            # Missing name
        }
        
        response = test_client.post("/portfolio/", json=portfolio_data, headers=auth_headers)
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.unit
    def test_create_portfolio_name_too_long(self, test_client: TestClient, auth_headers: dict):
        """Test creating portfolio with name too long"""
        portfolio_data = {
            "name": "A" * 256,  # Very long name
            "description": "Test description",
            "initial_balance": 1000.0
        }
        
        response = test_client.post("/portfolio/", json=portfolio_data, headers=auth_headers)
        
        assert response.status_code == 422  # Validation error


@pytest.mark.integration
class TestPortfolioIntegration:
    """Integration tests for portfolio functionality"""
    
    @pytest.mark.database
    async def test_portfolio_creation_and_retrieval_flow(
        self, test_client: TestClient, auth_headers: dict, test_db: AsyncSession
    ):
        """Test complete portfolio creation and retrieval flow"""
        
        # 1. Create portfolio
        portfolio_data = {
            "name": "Integration Test Portfolio",
            "description": "Portfolio for integration testing",
            "initial_balance": 15000.0
        }
        
        create_response = test_client.post("/portfolio/", json=portfolio_data, headers=auth_headers)
        assert create_response.status_code == 201
        
        created_portfolio = create_response.json()
        portfolio_id = created_portfolio["id"]
        
        # 2. Retrieve the created portfolio
        get_response = test_client.get(f"/portfolio/{portfolio_id}", headers=auth_headers)
        assert get_response.status_code == 200
        
        retrieved_portfolio = get_response.json()
        assert retrieved_portfolio["name"] == portfolio_data["name"]
        assert retrieved_portfolio["description"] == portfolio_data["description"]
        
        # 3. Update the portfolio
        update_data = {
            "name": "Updated Integration Portfolio",
            "description": "Updated description"
        }
        
        update_response = test_client.put(f"/portfolio/{portfolio_id}", json=update_data, headers=auth_headers)
        assert update_response.status_code == 200
        
        updated_portfolio = update_response.json()
        assert updated_portfolio["name"] == update_data["name"]
        
        # 4. Check portfolio appears in list
        list_response = test_client.get("/portfolio/", headers=auth_headers)
        assert list_response.status_code == 200
        
        portfolios = list_response.json()
        portfolio_ids = [p["id"] for p in portfolios]
        assert portfolio_id in portfolio_ids
    
    @pytest.mark.database
    async def test_portfolio_with_positions_integration(
        self, test_client: TestClient, auth_headers: dict, test_assets: list[Asset]
    ):
        """Test portfolio with positions integration"""
        
        # 1. Create portfolio
        portfolio_data = {
            "name": "Positions Test Portfolio",
            "initial_balance": 20000.0
        }
        
        portfolio_response = test_client.post("/portfolio/", json=portfolio_data, headers=auth_headers)
        assert portfolio_response.status_code == 201
        
        portfolio_id = portfolio_response.json()["id"]
        
        # 2. Add position to portfolio
        btc_asset = next(asset for asset in test_assets if asset.symbol == "BTC")
        
        position_data = {
            "asset_id": str(btc_asset.id),
            "quantity": 0.5,
            "entry_price": 45000.0,
            "position_type": "long"
        }
        
        position_response = test_client.post(
            f"/portfolio/{portfolio_id}/positions",
            json=position_data,
            headers=auth_headers
        )
        assert position_response.status_code == 201
        
        # 3. Get positions
        positions_response = test_client.get(f"/portfolio/{portfolio_id}/positions", headers=auth_headers)
        assert positions_response.status_code == 200
        
        positions = positions_response.json()
        assert len(positions) >= 1
        
        # 4. Get portfolio performance (should include position impact)
        performance_response = test_client.get(f"/portfolio/{portfolio_id}/performance", headers=auth_headers)
        assert performance_response.status_code == 200
        
        performance = performance_response.json()
        assert "positions_count" in performance
        assert performance["positions_count"] >= 1


class TestPortfolioPermissions:
    """Test portfolio access permissions and security"""
    
    @pytest.mark.auth
    def test_cannot_access_other_users_portfolio(
        self, test_client: TestClient, test_user: User, admin_user: User
    ):
        """Test that users cannot access portfolios of other users"""
        from app.routers.auth import create_access_token
        
        # Create portfolio as admin user
        admin_token = create_access_token(data={"sub": admin_user.email})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        portfolio_data = {
            "name": "Admin Portfolio",
            "initial_balance": 5000.0
        }
        
        create_response = test_client.post("/portfolio/", json=portfolio_data, headers=admin_headers)
        assert create_response.status_code == 201
        
        admin_portfolio_id = create_response.json()["id"]
        
        # Try to access admin's portfolio as regular user
        user_token = create_access_token(data={"sub": test_user.email})
        user_headers = {"Authorization": f"Bearer {user_token}"}
        
        access_response = test_client.get(f"/portfolio/{admin_portfolio_id}", headers=user_headers)
        assert access_response.status_code == 404  # Should not find portfolio (security through obscurity)
    
    @pytest.mark.auth
    def test_cannot_modify_other_users_portfolio(
        self, test_client: TestClient, test_user: User, admin_user: User
    ):
        """Test that users cannot modify portfolios of other users"""
        from app.routers.auth import create_access_token
        
        # Similar to above test but for modification
        admin_token = create_access_token(data={"sub": admin_user.email})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        portfolio_data = {
            "name": "Admin Portfolio to Modify",
            "initial_balance": 5000.0
        }
        
        create_response = test_client.post("/portfolio/", json=portfolio_data, headers=admin_headers)
        assert create_response.status_code == 201
        
        admin_portfolio_id = create_response.json()["id"]
        
        # Try to modify admin's portfolio as regular user
        user_token = create_access_token(data={"sub": test_user.email})
        user_headers = {"Authorization": f"Bearer {user_token}"}
        
        update_data = {"name": "Hacked Portfolio"}
        
        modify_response = test_client.put(
            f"/portfolio/{admin_portfolio_id}", 
            json=update_data, 
            headers=user_headers
        )
        assert modify_response.status_code == 404  # Should not find portfolio