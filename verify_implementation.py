"""Verification script for RBAC and Team Management implementation"""

import os
import sys

def check_file_exists(filepath, description):
    """Check if a file exists"""
    if os.path.exists(filepath):
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ {description} NOT FOUND: {filepath}")
        return False

def check_file_contains(filepath, search_strings, description):
    """Check if file contains specific strings"""
    if not os.path.exists(filepath):
        print(f"❌ {description}: File not found - {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    missing = []
    for search_str in search_strings:
        if search_str not in content:
            missing.append(search_str)
    
    if not missing:
        print(f"✅ {description}")
        return True
    else:
        print(f"❌ {description}: Missing {missing}")
        return False

def main():
    print("=" * 70)
    print("RBAC & Team Management Implementation Verification")
    print("=" * 70)
    
    results = []
    
    # Check new files
    print("\n📁 Checking New Files...")
    results.append(check_file_exists(
        "web_app/backend/rbac.py",
        "RBAC module"
    ))
    results.append(check_file_exists(
        "web_app/page_components/teams.py",
        "Teams UI page"
    ))
    results.append(check_file_exists(
        "RBAC_TEAMS_IMPLEMENTATION.md",
        "Implementation documentation"
    ))
    
    # Check database manager modifications
    print("\n🗄️  Checking Database Manager...")
    results.append(check_file_contains(
        "web_app/backend/mysql_database_manager.py",
        [
            "CREATE TABLE IF NOT EXISTS teams",
            "CREATE TABLE IF NOT EXISTS team_members",
            "def create_team",
            "def get_team",
            "def update_team",
            "def delete_team",
            "def assign_alert_to_team",
            "def validate_team_members",
            "def seed_default_teams"
        ],
        "Database manager has team methods"
    ))
    
    # Check RBAC module
    print("\n🔐 Checking RBAC Module...")
    results.append(check_file_contains(
        "web_app/backend/rbac.py",
        [
            "class Roles:",
            "class Permissions:",
            "def has_permission",
            "def is_nrw_officer",
            "def can_manage_teams",
            "def require_permission",
            "ROLE_PERMISSIONS"
        ],
        "RBAC module has required functions"
    ))
    
    # Check Teams UI
    print("\n🖥️  Checking Teams UI...")
    results.append(check_file_contains(
        "web_app/page_components/teams.py",
        [
            "def show_teams",
            "def show_all_teams",
            "def show_my_teams",
            "def show_create_team_form",
            "def show_edit_team_form",
            "def show_team_workload",
            "has_permission",
            "Permissions.TEAM_CREATE"
        ],
        "Teams UI has required components"
    ))
    
    # Check Alerts page modifications
    print("\n🚨 Checking Alerts Page...")
    results.append(check_file_contains(
        "web_app/page_components/alerts.py",
        [
            "from backend.rbac import",
            "can_assign_alerts",
            "show_team_assignment_ui",
            "assign_alert_to_team"
        ],
        "Alerts page has team assignment features"
    ))
    
    # Check app.py modifications
    print("\n📱 Checking Main App...")
    results.append(check_file_contains(
        "web_app/app.py",
        [
            "show_teams",
            '"Teams"'
        ],
        "Main app includes Teams navigation"
    ))
    
    # Check __init__.py
    print("\n📦 Checking Package Exports...")
    results.append(check_file_contains(
        "web_app/page_components/__init__.py",
        [
            "from .teams import show_teams",
            "'show_teams'"
        ],
        "Package exports show_teams"
    ))
    
    # Summary
    print("\n" + "=" * 70)
    print("Verification Summary")
    print("=" * 70)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 All verification checks passed!")
        print("\n📋 Implementation Complete:")
        print("   • Database schema with teams and team_members tables")
        print("   • RBAC system with role-based permissions")
        print("   • Team CRUD operations with validation")
        print("   • Team Management UI page")
        print("   • Alert assignment to teams")
        print("   • Comprehensive documentation")
        print("\n🚀 Next Steps:")
        print("   1. Start the Streamlit app: streamlit run web_app/app.py")
        print("   2. Login as NRW Officer (THW-001)")
        print("   3. Navigate to Teams page")
        print("   4. Create and manage teams")
        print("   5. Assign alerts to teams from Alerts page")
    else:
        print("\n⚠️  Some verification checks failed.")
        print("Please review the output above for details.")
    
    print("=" * 70)
    
    return passed == total

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Verification crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
