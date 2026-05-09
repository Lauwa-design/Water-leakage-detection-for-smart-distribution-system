"""Role-Based Access Control (RBAC) Module for THIWASCO Leak Detection System"""

import streamlit as st
from functools import wraps
from typing import Callable, List, Optional


# Role definitions
class Roles:
    """User role constants"""
    NRW_OFFICER = "Non-Revenue Water Officer"
    FIELD_TECHNICIAN = "Field Technician"
    SYSTEM_ADMIN = "System Administrator"
    
    ALL_ROLES = [NRW_OFFICER, FIELD_TECHNICIAN, SYSTEM_ADMIN]


# Permission definitions
class Permissions:
    """Permission constants for different resources"""
    
    # Team permissions
    TEAM_CREATE = "team:create"
    TEAM_READ = "team:read"
    TEAM_UPDATE = "team:update"
    TEAM_DELETE = "team:delete"
    
    # Alert permissions
    ALERT_ASSIGN = "alert:assign"
    ALERT_READ = "alert:read"
    ALERT_UPDATE = "alert:update"
    
    # Zone permissions
    ZONE_CREATE = "zone:create"
    ZONE_READ = "zone:read"
    ZONE_UPDATE = "zone:update"
    ZONE_DELETE = "zone:delete"


# Role-Permission mapping
ROLE_PERMISSIONS = {
    Roles.NRW_OFFICER: [
        # Team permissions - Full CRUD
        Permissions.TEAM_CREATE,
        Permissions.TEAM_READ,
        Permissions.TEAM_UPDATE,
        Permissions.TEAM_DELETE,
        
        # Alert permissions
        Permissions.ALERT_ASSIGN,
        Permissions.ALERT_READ,
        Permissions.ALERT_UPDATE,
        
        # Zone permissions
        Permissions.ZONE_CREATE,
        Permissions.ZONE_READ,
        Permissions.ZONE_UPDATE,
        Permissions.ZONE_DELETE,
    ],
    
    Roles.FIELD_TECHNICIAN: [
        # Team permissions - Read only (own teams)
        Permissions.TEAM_READ,
        
        # Alert permissions - Read only
        Permissions.ALERT_READ,
        
        # Zone permissions - Read only
        Permissions.ZONE_READ,
    ],
    
    Roles.SYSTEM_ADMIN: [
        # Team permissions - Read only
        Permissions.TEAM_READ,
        
        # Alert permissions - Full access
        Permissions.ALERT_READ,
        Permissions.ALERT_UPDATE,
        
        # Zone permissions - Full CRUD
        Permissions.ZONE_CREATE,
        Permissions.ZONE_READ,
        Permissions.ZONE_UPDATE,
        Permissions.ZONE_DELETE,
    ],
}


def get_current_user_role() -> Optional[str]:
    """Get the current user's role from session state"""
    return st.session_state.get("user_role")


def get_current_user_id() -> Optional[str]:
    """Get the current user's ID from session state"""
    return st.session_state.get("user_id")


def get_current_user_name() -> Optional[str]:
    """Get the current user's name from session state"""
    return st.session_state.get("user_name")


def has_permission(permission: str, user_role: Optional[str] = None) -> bool:
    """
    Check if a user has a specific permission
    
    Args:
        permission: Permission string (e.g., Permissions.TEAM_CREATE)
        user_role: User role (defaults to current user's role)
    
    Returns:
        bool: True if user has permission, False otherwise
    """
    if user_role is None:
        user_role = get_current_user_role()
    
    if not user_role:
        return False
    
    role_perms = ROLE_PERMISSIONS.get(user_role, [])
    return permission in role_perms


def has_any_permission(permissions: List[str], user_role: Optional[str] = None) -> bool:
    """
    Check if a user has any of the specified permissions
    
    Args:
        permissions: List of permission strings
        user_role: User role (defaults to current user's role)
    
    Returns:
        bool: True if user has at least one permission, False otherwise
    """
    return any(has_permission(perm, user_role) for perm in permissions)


def has_all_permissions(permissions: List[str], user_role: Optional[str] = None) -> bool:
    """
    Check if a user has all of the specified permissions
    
    Args:
        permissions: List of permission strings
        user_role: User role (defaults to current user's role)
    
    Returns:
        bool: True if user has all permissions, False otherwise
    """
    return all(has_permission(perm, user_role) for perm in permissions)


def is_nrw_officer(user_role: Optional[str] = None) -> bool:
    """Check if user is a Non-Revenue Water Officer"""
    if user_role is None:
        user_role = get_current_user_role()
    return user_role == Roles.NRW_OFFICER


def is_field_technician(user_role: Optional[str] = None) -> bool:
    """Check if user is a Field Technician"""
    if user_role is None:
        user_role = get_current_user_role()
    return user_role == Roles.FIELD_TECHNICIAN


def is_system_admin(user_role: Optional[str] = None) -> bool:
    """Check if user is a System Administrator"""
    if user_role is None:
        user_role = get_current_user_role()
    return user_role == Roles.SYSTEM_ADMIN


def require_permission(permission: str, error_message: Optional[str] = None):
    """
    Decorator to require a specific permission for a function
    
    Args:
        permission: Required permission string
        error_message: Custom error message (optional)
    
    Usage:
        @require_permission(Permissions.TEAM_CREATE)
        def create_team():
            # Function code
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not has_permission(permission):
                msg = error_message or f"You do not have permission to perform this action. Required: {permission}"
                st.error(msg)
                st.stop()
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_role(allowed_roles: List[str], error_message: Optional[str] = None):
    """
    Decorator to require specific roles for a function
    
    Args:
        allowed_roles: List of allowed role strings
        error_message: Custom error message (optional)
    
    Usage:
        @require_role([Roles.NRW_OFFICER, Roles.SYSTEM_ADMIN])
        def admin_function():
            # Function code
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_role = get_current_user_role()
            if current_role not in allowed_roles:
                msg = error_message or f"Access denied. Required roles: {', '.join(allowed_roles)}"
                st.error(msg)
                st.stop()
            return func(*args, **kwargs)
        return wrapper
    return decorator


def check_permission_ui(permission: str, show_error: bool = True) -> bool:
    """
    Check permission and optionally show error in UI
    
    Args:
        permission: Permission to check
        show_error: Whether to show error message if permission denied
    
    Returns:
        bool: True if user has permission, False otherwise
    """
    if has_permission(permission):
        return True
    
    if show_error:
        st.error(f"⛔ You do not have permission to perform this action.")
    
    return False


def show_permission_denied(action: str = "perform this action"):
    """Display a permission denied message"""
    st.error(f"⛔ Access Denied")
    st.warning(f"You do not have permission to {action}.")
    st.info(f"Current role: **{get_current_user_role()}**")


def get_user_permissions(user_role: Optional[str] = None) -> List[str]:
    """
    Get all permissions for a user role
    
    Args:
        user_role: User role (defaults to current user's role)
    
    Returns:
        List of permission strings
    """
    if user_role is None:
        user_role = get_current_user_role()
    
    return ROLE_PERMISSIONS.get(user_role, [])


def can_manage_teams(user_role: Optional[str] = None) -> bool:
    """Check if user can create, update, or delete teams"""
    return has_any_permission([
        Permissions.TEAM_CREATE,
        Permissions.TEAM_UPDATE,
        Permissions.TEAM_DELETE
    ], user_role)


def can_assign_alerts(user_role: Optional[str] = None) -> bool:
    """Check if user can assign alerts to teams"""
    return has_permission(Permissions.ALERT_ASSIGN, user_role)


def can_view_teams(user_role: Optional[str] = None) -> bool:
    """Check if user can view teams"""
    return has_permission(Permissions.TEAM_READ, user_role)
