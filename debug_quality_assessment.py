#!/usr/bin/env python3
"""
Debug script for quality assessment issues
This script helps diagnose missing assessment IDs and 404 errors

Usage: python debug_quality_assessment.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def debug_assessment_data():
    """Debug assessment data issues"""
    print("🔍 MetaScreener Quality Assessment Diagnostic Tool")
    print("=" * 60)
    
    try:
        # Create Flask app context
        from app import app
        with app.app_context():
            from quality_assessment.services import _assessments_db
            from quality_assessment.redis_storage import list_all_batches, get_redis_client
            
            print(f"1️⃣  Checking assessment database...")
            print(f"   📊 Found {len(_assessments_db)} assessments in memory storage")
            
            if _assessments_db:
                print(f"   📋 Assessment IDs: {list(_assessments_db.keys())}")
                print(f"   📋 ID range: {min(_assessments_db.keys())} - {max(_assessments_db.keys())}")
                
                # Check for the specific problematic IDs
                problematic_ids = ['70', '71']
                for aid in problematic_ids:
                    if aid in _assessments_db:
                        status = _assessments_db[aid].get('status', 'unknown')
                        filename = _assessments_db[aid].get('filename', 'unknown')
                        print(f"   ✅ Assessment {aid}: {status} - {filename}")
                    else:
                        print(f"   ❌ Assessment {aid}: NOT FOUND")
            else:
                print(f"   ⚠️  No assessments found in memory storage")
            
            print(f"\n2️⃣  Checking Redis batch storage...")
            redis_batches = list_all_batches()
            print(f"   📊 Found {len(redis_batches)} batches in Redis")
            
            if redis_batches:
                for batch_id, batch_data in redis_batches.items():
                    assessment_ids = batch_data.get('assessment_ids', [])
                    filenames = batch_data.get('successful_filenames', [])
                    print(f"   📦 Batch {batch_id[:12]}...: {len(assessment_ids)} assessments")
                    print(f"      Assessment IDs: {assessment_ids}")
                    print(f"      Filenames: {filenames}")
                    
                    # Check if problematic IDs are in any batch
                    for prob_id in problematic_ids:
                        if prob_id in assessment_ids:
                            print(f"      ✅ Found problematic ID {prob_id} in this batch")
            
            print(f"\n3️⃣  Testing Redis connectivity...")
            try:
                redis_client = get_redis_client()
                redis_client.ping()
                print(f"   ✅ Redis connection successful")
                
                # Test batch operations
                test_batch_id = "diagnostic_test_12345"
                test_data = {"test": True, "diagnostic": "success"}
                from quality_assessment.redis_storage import save_batch_status, get_batch_status, delete_batch_status
                
                save_batch_status(test_batch_id, test_data)
                retrieved = get_batch_status(test_batch_id)
                if retrieved and retrieved.get("test"):
                    print(f"   ✅ Redis batch operations working")
                    delete_batch_status(test_batch_id)
                else:
                    print(f"   ❌ Redis batch operations failed")
                    
            except Exception as e:
                print(f"   ❌ Redis connection failed: {e}")
            
            print(f"\n4️⃣  URL routing diagnostic...")
            from flask import url_for
            
            try:
                # Test quality assessment URLs
                upload_url = url_for('quality_assessment.upload_document_for_assessment')
                print(f"   ✅ Upload URL: {upload_url}")
                
                test_assessment_id = "999"
                status_url = url_for('quality_assessment.assessment_status', assessment_id=test_assessment_id)
                print(f"   ✅ Status URL: {status_url}")
                
                if redis_batches:
                    first_batch_id = list(redis_batches.keys())[0]
                    batch_url = url_for('quality_assessment.view_batch_status', batch_id=first_batch_id)
                    print(f"   ✅ Batch URL: {batch_url}")
                
            except Exception as e:
                print(f"   ❌ URL generation failed: {e}")
            
            print(f"\n📋 Diagnostic Summary:")
            print(f"   • Assessment database: {len(_assessments_db)} records")
            print(f"   • Redis batches: {len(redis_batches)} batches")
            print(f"   • Problematic IDs 70,71: {'Found' if any(str(pid) in _assessments_db for pid in [70, 71]) else 'Missing'}")
            
            return True
            
    except Exception as e:
        print(f"❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def suggest_fixes():
    """Suggest fixes for common issues"""
    print(f"\n💡 Common Fixes:")
    print(f"   1. If assessment IDs are missing:")
    print(f"      - They may have been lost during server restart")
    print(f"      - Check if persistent storage is working")
    print(f"      - Consider re-uploading the documents")
    
    print(f"\n   2. If getting 404 errors:")
    print(f"      - URL prefix should be /quality_assessment/ not /quality/")
    print(f"      - Check browser cache and refresh page")
    print(f"      - Verify the assessment ID exists in database")
    
    print(f"\n   3. If Redis issues:")
    print(f"      - Ensure Redis service is running")
    print(f"      - Check Redis connection string in .env")
    print(f"      - Run: redis-cli ping")
    
    print(f"\n   4. If API key issues:")
    print(f"      - Re-enter API key in LLM Configuration")
    print(f"      - Check if session expired")
    print(f"      - Verify API key is valid")

def cleanup_orphaned_data():
    """Clean up orphaned or corrupted data"""
    print(f"\n🧹 Cleanup Options:")
    print(f"   WARNING: This will remove data. Backup first if needed.")
    
    response = input("   Do you want to clean up orphaned data? (yes/no): ")
    if response.lower() != 'yes':
        print("   Cleanup cancelled.")
        return
    
    try:
        from app import app
        with app.app_context():
            from quality_assessment.services import _assessments_db, _save_assessments_to_file
            from quality_assessment.redis_storage import list_all_batches, delete_batch_status
            
            # Clean up assessments with error status
            error_assessments = []
            for aid, data in _assessments_db.items():
                if data.get('status') == 'error':
                    error_assessments.append(aid)
            
            if error_assessments:
                print(f"   Found {len(error_assessments)} error assessments")
                for aid in error_assessments:
                    del _assessments_db[aid]
                    print(f"   🗑️  Removed error assessment {aid}")
                
                _save_assessments_to_file()
                print(f"   ✅ Cleaned up error assessments")
            else:
                print(f"   ℹ️  No error assessments to clean")
            
            # Clean up expired batches (older than 7 days would already be auto-expired)
            print(f"   ℹ️  Redis batches auto-expire after 7 days")
            
    except Exception as e:
        print(f"   ❌ Cleanup failed: {e}")

if __name__ == "__main__":
    success = debug_assessment_data()
    
    if success:
        suggest_fixes()
        cleanup_response = input("\n🤔 Would you like to see cleanup options? (yes/no): ")
        if cleanup_response.lower() == 'yes':
            cleanup_orphaned_data()
    
    print(f"\n✨ Diagnostic completed!")
    print(f"   If issues persist, check the deployment logs and Redis status.") 