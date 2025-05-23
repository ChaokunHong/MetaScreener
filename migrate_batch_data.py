#!/usr/bin/env python3
"""
Migration script to move batch assessment data from memory to Redis storage
Run this script after upgrading to Redis-based storage to preserve existing batch data

Usage: python migrate_batch_data.py
"""

import os
import sys
import json
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set environment variables
os.environ.setdefault('FLASK_ENV', 'production')

def migrate_batch_data():
    """Migrate existing batch data to Redis"""
    try:
        # Import after setting up the path
        from quality_assessment.redis_storage import save_batch_status, get_redis_client, list_all_batches
        from quality_assessment.routes import _batch_assessments_status
        
        print("🔄 Starting batch data migration to Redis...")
        
        # Check Redis connection
        try:
            redis_client = get_redis_client()
            redis_client.ping()
            print("✅ Redis connection successful")
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            print("Please ensure Redis is running and accessible")
            return False
        
        # Check existing Redis data
        existing_batches = list_all_batches()
        print(f"📊 Found {len(existing_batches)} existing batches in Redis")
        
        # Check memory data
        memory_batches = len(_batch_assessments_status)
        print(f"📊 Found {memory_batches} batches in memory storage")
        
        if memory_batches == 0:
            print("ℹ️  No batch data in memory to migrate")
            return True
        
        # Migrate data
        migrated_count = 0
        skipped_count = 0
        
        for batch_id, batch_data in _batch_assessments_status.items():
            if batch_id in existing_batches:
                print(f"⏭️  Skipping batch {batch_id[:8]}... (already exists in Redis)")
                skipped_count += 1
                continue
            
            try:
                success = save_batch_status(batch_id, batch_data)
                if success:
                    print(f"✅ Migrated batch {batch_id[:8]}... ({len(batch_data.get('assessment_ids', []))} assessments)")
                    migrated_count += 1
                else:
                    print(f"❌ Failed to migrate batch {batch_id[:8]}...")
            except Exception as e:
                print(f"❌ Error migrating batch {batch_id[:8]}...: {e}")
        
        print(f"\n🎉 Migration completed!")
        print(f"   ✅ Migrated: {migrated_count} batches")
        print(f"   ⏭️  Skipped: {skipped_count} batches")
        print(f"   📊 Total in Redis: {len(list_all_batches())} batches")
        
        if migrated_count > 0:
            print(f"\n💡 Migration successful! Your batch assessment data is now persistent.")
            print(f"   Server restarts will no longer cause data loss.")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Please ensure you're running this from the project root directory")
        return False
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

def verify_migration():
    """Verify the migration was successful"""
    try:
        from quality_assessment.redis_storage import list_all_batches
        from quality_assessment.routes import _batch_assessments_status
        
        redis_batches = list_all_batches()
        memory_batches = _batch_assessments_status
        
        print(f"\n🔍 Migration verification:")
        print(f"   Redis storage: {len(redis_batches)} batches")
        print(f"   Memory storage: {len(memory_batches)} batches")
        
        # Check if all memory batches are in Redis
        missing_in_redis = []
        for batch_id in memory_batches:
            if batch_id not in redis_batches:
                missing_in_redis.append(batch_id)
        
        if missing_in_redis:
            print(f"   ⚠️  {len(missing_in_redis)} batches still missing in Redis")
            for batch_id in missing_in_redis[:3]:  # Show first 3
                print(f"      - {batch_id[:8]}...")
        else:
            print(f"   ✅ All memory batches found in Redis")
        
        return len(missing_in_redis) == 0
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 MetaScreener Batch Data Migration Tool")
    print("=" * 50)
    
    # Run migration
    success = migrate_batch_data()
    
    if success:
        # Verify migration
        verify_migration()
        print(f"\n✨ Migration process completed!")
        print(f"   Your quality assessment batches are now persistent across server restarts.")
    else:
        print(f"\n💥 Migration failed. Please check the errors above.")
        sys.exit(1) 