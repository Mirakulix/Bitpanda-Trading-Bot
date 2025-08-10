"""
Tests for authentication and authorization functionality
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.routers.auth import verify_password, get_password_hash, create_access_token


class TestAuthRouter:
    """Test authentication router endpoints"""
    
    @pytest.mark.auth
    def test_register_user_success(self, test_client: TestClient):
        """Test successful user registration"""
        user_data = {
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "newpassword123",
            "full_name": "New User"
        }
        
        response = test_client.post("/auth/register", json=user_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == user_data["email"]
        assert data["username"] == user_data["username"]
        assert data["full_name"] == user_data["full_name"]
        assert "id" in data
        assert "password" not in data
        assert "hashed_password" not in data
    
    @pytest.mark.auth
    def test_register_user_duplicate_email(self, test_client: TestClient, test_user: User):
        """Test registration with duplicate email"""
        user_data = {
            "email": test_user.email,
            "username": "differentuser", 
            "password": "password123",
            "full_name": "Different User"
        }
        
        response = test_client.post("/auth/register", json=user_data)
        
        assert response.status_code == 400
        assert "email already registered" in response.json()["detail"].lower()
    
    @pytest.mark.auth
    def test_login_success(self, test_client: TestClient, test_user: User):
        """Test successful login"""
        login_data = {
            "username": test_user.email,
            "password": "testpassword123"
        }
        
        response = test_client.post("/auth/login", data=login_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
    
    @pytest.mark.auth
    def test_login_invalid_credentials(self, test_client: TestClient):
        """Test login with invalid credentials"""
        login_data = {
            "username": "nonexistent@example.com",
            "password": "wrongpassword"
        }
        
        response = test_client.post("/auth/login", data=login_data)
        
        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()
    
    @pytest.mark.auth
    def test_get_current_user_success(self, test_client: TestClient, auth_headers: dict):
        """Test getting current user with valid token"""
        response = test_client.get("/auth/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["username"] == "testuser"
    
    @pytest.mark.auth
    def test_get_current_user_no_token(self, test_client: TestClient):
        """Test getting current user without token"""
        response = test_client.get("/auth/me")
        
        assert response.status_code == 401
    
    @pytest.mark.auth
    def test_get_current_user_invalid_token(self, test_client: TestClient):
        """Test getting current user with invalid token"""
        headers = {"Authorization": "Bearer invalid_token"}
        response = test_client.get("/auth/me", headers=headers)
        
        assert response.status_code == 401
    
    @pytest.mark.auth
    def test_update_profile_success(self, test_client: TestClient, auth_headers: dict):
        """Test updating user profile"""
        update_data = {
            "full_name": "Updated Name",
            "bio": "This is my updated bio"
        }
        
        response = test_client.put("/auth/me", json=update_data, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Name"
        assert data["bio"] == "This is my updated bio"
    
    @pytest.mark.auth
    def test_change_password_success(self, test_client: TestClient, auth_headers: dict):
        """Test changing password"""
        password_data = {
            "current_password": "testpassword123",
            "new_password": "newtestpassword123"
        }
        
        response = test_client.post("/auth/change-password", json=password_data, headers=auth_headers)
        
        assert response.status_code == 200
        assert "success" in response.json()["message"].lower()
    
    @pytest.mark.auth
    def test_change_password_wrong_current(self, test_client: TestClient, auth_headers: dict):
        """Test changing password with wrong current password"""
        password_data = {
            "current_password": "wrongpassword",
            "new_password": "newtestpassword123"
        }
        
        response = test_client.post("/auth/change-password", json=password_data, headers=auth_headers)
        
        assert response.status_code == 400
        assert "current password" in response.json()["detail"].lower()


class TestPasswordUtils:
    """Test password hashing and verification utilities"""
    
    @pytest.mark.unit
    def test_password_hashing(self):
        """Test password hashing"""
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        assert hashed != password
        assert len(hashed) > 50  # Bcrypt hashes are typically 60 characters
        assert hashed.startswith("$2b$")  # Bcrypt prefix
    
    @pytest.mark.unit
    def test_password_verification_success(self):
        """Test successful password verification"""
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    @pytest.mark.unit
    def test_password_verification_failure(self):
        """Test failed password verification"""
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = get_password_hash(password)
        
        assert verify_password(wrong_password, hashed) is False


class TestJWTTokens:
    """Test JWT token creation and validation"""
    
    @pytest.mark.unit
    def test_create_access_token(self):
        """Test access token creation"""
        data = {"sub": "test@example.com"}
        token = create_access_token(data=data)
        
        assert isinstance(token, str)
        assert len(token) > 100  # JWT tokens are typically long
        assert token.count(".") == 2  # JWT has 3 parts separated by dots
    
    @pytest.mark.unit
    def test_create_access_token_with_expiry(self):
        """Test access token creation with custom expiry"""
        from datetime import timedelta
        
        data = {"sub": "test@example.com"}
        expires_delta = timedelta(hours=1)
        token = create_access_token(data=data, expires_delta=expires_delta)
        
        assert isinstance(token, str)
        assert len(token) > 100


class TestAuthMiddleware:
    """Test authentication middleware and dependencies"""
    
    @pytest.mark.auth
    def test_protected_endpoint_requires_auth(self, test_client: TestClient):
        """Test that protected endpoints require authentication"""
        response = test_client.get("/portfolio/")
        
        assert response.status_code == 401
    
    @pytest.mark.auth
    def test_protected_endpoint_with_valid_token(self, test_client: TestClient, auth_headers: dict):
        """Test protected endpoint with valid authentication"""
        response = test_client.get("/portfolio/", headers=auth_headers)
        
        # Should not be 401 (authentication should pass)
        assert response.status_code != 401
    
    @pytest.mark.auth
    def test_admin_endpoint_requires_admin(self, test_client: TestClient, auth_headers: dict):
        """Test that admin endpoints require admin privileges"""
        # Assuming there's an admin endpoint
        response = test_client.get("/admin/users", headers=auth_headers)
        
        # Regular user should get 403 (forbidden) not 401 (unauthorized)
        assert response.status_code == 403
    
    @pytest.mark.auth
    def test_admin_endpoint_with_admin_user(self, test_client: TestClient, admin_user: User):
        """Test admin endpoint with admin user"""
        from app.routers.auth import create_access_token
        
        token = create_access_token(data={"sub": admin_user.email})
        headers = {"Authorization": f"Bearer {token}"}
        
        # This would test an actual admin endpoint
        response = test_client.get("/admin/users", headers=headers)
        
        # Admin user should have access (or endpoint might not exist yet)
        assert response.status_code != 403


class TestUserRegistrationValidation:
    """Test user registration input validation"""
    
    @pytest.mark.unit
    @pytest.mark.auth
    def test_register_invalid_email(self, test_client: TestClient):
        """Test registration with invalid email format"""
        user_data = {
            "email": "invalid-email",
            "username": "testuser",
            "password": "password123",
            "full_name": "Test User"
        }
        
        response = test_client.post("/auth/register", json=user_data)
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.unit
    @pytest.mark.auth
    def test_register_weak_password(self, test_client: TestClient):
        """Test registration with weak password"""
        user_data = {
            "email": "test@example.com",
            "username": "testuser", 
            "password": "123",  # Too short
            "full_name": "Test User"
        }
        
        response = test_client.post("/auth/register", json=user_data)
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.unit
    @pytest.mark.auth
    def test_register_missing_required_fields(self, test_client: TestClient):
        """Test registration with missing required fields"""
        user_data = {
            "email": "test@example.com",
            # Missing username, password, full_name
        }
        
        response = test_client.post("/auth/register", json=user_data)
        
        assert response.status_code == 422  # Validation error


@pytest.mark.integration
class TestAuthIntegration:
    """Integration tests for authentication flow"""
    
    @pytest.mark.auth
    async def test_full_registration_login_flow(self, test_client: TestClient):
        """Test complete registration and login flow"""
        # 1. Register new user
        user_data = {
            "email": "integration@example.com",
            "username": "integrationuser",
            "password": "integrationpass123",
            "full_name": "Integration Test User"
        }
        
        register_response = test_client.post("/auth/register", json=user_data)
        assert register_response.status_code == 201
        
        # 2. Login with new user
        login_data = {
            "username": user_data["email"],
            "password": user_data["password"]
        }
        
        login_response = test_client.post("/auth/login", data=login_data)
        assert login_response.status_code == 200
        
        token_data = login_response.json()
        assert "access_token" in token_data
        
        # 3. Use token to access protected endpoint
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        me_response = test_client.get("/auth/me", headers=headers)
        
        assert me_response.status_code == 200
        user_info = me_response.json()
        assert user_info["email"] == user_data["email"]