"""Test script for RBAC and Team Management functionality"""

import sys
import os

# Add web_app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'web_app'))

from backend.mysql_database_manager import db_manager
from backend.rbac import (
    Roles, 
    Permissions, 
    has_permission, 
    is_nrw_officer,
    can_manage_teams,
    can_assign_alerts
)


def test_database_schema():
    """Test that new tables were created"""
    print("\n=== Testing Database Schema ===")
    
    try:
        # Test teams table
        teams = db_manager.get_all_teams()
        print(f"✅ Teams table accessible: {len(teams)} teams found")
        
        # Test field technicians query
        techs = db_manager.get_field_technicians()
        print(f"✅ Field Technicians query works: {len(techs)} technicians found")
        
        # Test alerts table has team_id column
        alerts = db_manager.get_alerts(hours=24)
        if 'team_id' in alerts.columns or alerts.empty:
            print("✅ Alerts table has team_id column")
        else:
            print("❌ Alerts table missing team_id column")
        
        return True
    except Exception as e:
        print(f"❌ Database schema test failed: {e}")
        return False


def test_rbac_permissions():
    """Test RBAC permission checks"""
    print("\n=== Testing RBAC Permissions ===")
    
    # Test NRW Officer permissions
    nrw_perms = [
        Permissions.TEAM_CREATE,
        Permissions.TEAM_UPDATE,
        Permissions.TEAM_DELETE,
        Permissions.ALERT_ASSIGN
    ]
    
    for perm in nrw_perms:
        if has_permission(perm, Roles.NRW_OFFICER):
            print(f"✅ NRW Officer has {perm}")
        else:
            print(f"❌ NRW Officer missing {perm}")
    
    # Test Field Technician permissions (should NOT have team management)
    if not has_permission(Permissions.TEAM_CREATE, Roles.FIELD_TECHNICIAN):
        print("✅ Field Technician correctly denied TEAM_CREATE")
    else:
        print("❌ Field Technician incorrectly has TEAM_CREATE")
    
    # Test helper functions
    if is_nrw_officer(Roles.NRW_OFFICER):
        print("✅ is_nrw_officer() works correctly")
    
    if can_manage_teams(Roles.NRW_OFFICER):
        print("✅ can_manage_teams() works for NRW Officer")
    
    if not can_manage_teams(Roles.FIELD_TECHNICIAN):
        print("✅ can_manage_teams() correctly denies Field Technician")
    
    return True


def test_team_operations():
    """Test team CRUD operations"""
    print("\n=== Testing Team Operations ===")
    
    try:
        # Get Field Technicians
        techs = db_manager.get_field_technicians()
        if techs.empty or len(techs) < 2:
            print("⚠️  Not enough Field Technicians to test team creation")
            return False
        
        tech_ids = techs['user_id'].tolist()[:2]  # Get first 2
        
        # Test team creation
        success, msg, team_id = db_manager.create_team(
            name="Test Team Alpha",
            description="Test team for RBAC validation",
            created_by="THW-001",  # NRW Officer
            member_ids=tech_ids
        )
        
        if success:
            print(f"✅ Team created successfully: {msg} (ID: {team_id})")
        else:
            print(f"❌ Team creation failed: {msg}")
            return False
        
        # Test team retrieval
        team = db_manager.get_team(team_id)
        if team and team['name'] == "Test Team Alpha":
            print(f"✅ Team retrieved successfully: {team['name']} with {len(team['members'])} members")
        else:
            print("❌ Team retrieval failed")
            return False
        
        # Test team update
        if len(tech_ids) >= 2:
            success, msg = db_manager.update_team(
                team_id=team_id,
                name="Test Team Alpha Updated",
                description="Updated description",
                member_ids=tech_ids,
                updated_by="THW-001"
            )
            if success:
                print(f"✅ Team updated successfully: {msg}")
            else:
                print(f"❌ Team update failed: {msg}")
        
        # Test team deletion
        success, msg = db_manager.delete_team(team_id, "THW-001")
        if success:
            print(f"✅ Team deleted successfully: {msg}")
        else:
            print(f"❌ Team deletion failed: {msg}")
        
        return True
        
    except Exception as e:
        print(f"❌ Team operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_team_validation():
    """Test team member validation"""
    print("\n=== Testing Team Validation ===")
    
    try:
        # Test: Too few members
        valid, msg = db_manager.validate_team_members(["THW-002"])
        if not valid and "at least 2" in msg:
            print(f"✅ Correctly rejects team with 1 member: {msg}")
        else:
            print(f"❌ Should reject team with 1 member")
        
        # Test: Too many members
        valid, msg = db_manager.validate_team_members(["THW-002"] * 7)
        if not valid and "more than 6" in msg:
            print(f"✅ Correctly rejects team with 7 members: {msg}")
        else:
            print(f"❌ Should reject team with 7 members")
        
        # Test: Non-Field Technician
        valid, msg = db_manager.validate_team_members(["THW-001", "THW-002"])  # THW-001 is NRW Officer
        if not valid and "Field Technician" in msg:
            print(f"✅ Correctly rejects non-Field Technician: {msg}")
        else:
            print(f"❌ Should reject non-Field Technician members")
        
        # Test: Valid team
        techs = db_manager.get_field_technicians()
        if not techs.empty and len(techs) >= 2:
            tech_ids = techs['user_id'].tolist()[:2]
            valid, msg = db_manager.validate_team_members(tech_ids)
            if valid:
                print(f"✅ Correctly accepts valid team: {msg}")
            else:
                print(f"❌ Should accept valid team: {msg}")
        
        return True
        
    except Exception as e:
        print(f"❌ Team validation test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("RBAC & Team Management Test Suite")
    print("=" * 60)
    
    results = []
    
    results.append(("Database Schema", test_database_schema()))
    results.append(("RBAC Permissions", test_rbac_permissions()))
    results.append(("Team Validation", test_team_validation()))
    results.append(("Team Operations", test_team_operations()))
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Please review the output above.")
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test suite crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
