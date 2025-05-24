#!/usr/bin/env python3

"""
Debug script to check Redis assessment data
用于排查assessment_status API返回404错误的问题
"""

import redis
import pickle
import os
import sys

def check_redis_assessments():
    print("=== Redis Assessment Data Debug ===")
    
    # 检查多个Redis数据库
    redis_configs = [
        {'url': 'redis://localhost:6379/0', 'desc': 'DB 0 (默认)'},
        {'url': 'redis://localhost:6379/1', 'desc': 'DB 1 (Celery)'},
        {'url': os.getenv('REDIS_URL', 'redis://localhost:6379/0'), 'desc': 'REDIS_URL环境变量'}
    ]
    
    for config in redis_configs:
        print(f"\n=== 检查 {config['desc']}: {config['url']} ===")
        
        try:
            # 连接Redis
            r = redis.Redis.from_url(config['url'], decode_responses=False)
            
            # 测试连接
            print(f"Redis连接测试: {r.ping()}")
            
            # 查找所有qa_assessment:*键
            keys = r.keys("qa_assessment:*")
            print(f"找到 {len(keys)} 个assessment键:")
            
            if not keys:
                print("   ⚠️  没有找到任何assessment数据!")
                continue
                
            for key in keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                assessment_id = key_str.replace('qa_assessment:', '')
                print(f"\n   📋 Assessment ID: {assessment_id}")
                
                try:
                    # 获取数据
                    data = r.get(key)
                    if data:
                        assessment_data = pickle.loads(data)
                        print(f"      状态: {assessment_data.get('status', 'N/A')}")
                        print(f"      文件名: {assessment_data.get('filename', 'N/A')}")
                        print(f"      文档类型: {assessment_data.get('document_type', 'N/A')}")
                        
                        # 检查progress
                        progress = assessment_data.get('progress', {})
                        if isinstance(progress, dict):
                            print(f"      进度: {progress.get('current', 0)}/{progress.get('total', 0)} - {progress.get('message', '')}")
                        
                        # 检查assessment_details
                        details = assessment_data.get('assessment_details')
                        if details:
                            if isinstance(details, list):
                                print(f"      评估详情: {len(details)} 项")
                            else:
                                print(f"      评估详情: {type(details).__name__}")
                        else:
                            print(f"      评估详情: 无")
                            
                    else:
                        print(f"      ❌ 键存在但无数据")
                        
                except Exception as e:
                    print(f"      ❌ 读取数据失败: {e}")
            
            # 检查Celery相关数据
            print(f"\n   === Celery Quality Results ===")
            celery_keys = r.keys("quality_results:*")
            print(f"   找到 {len(celery_keys)} 个Celery结果键")
            
            for key in celery_keys[:3]:  # 只显示前3个
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                print(f"      📦 {key_str}")
                
        except redis.ConnectionError as e:
            print(f"   ❌ Redis连接失败: {e}")
        except Exception as e:
            print(f"   ❌ 其他错误: {e}")

def test_assessment_creation():
    """测试在正确的数据库中创建assessment"""
    print(f"\n=== 测试Assessment创建 (多数据库) ===")
    
    # 测试两个数据库
    test_configs = [
        {'url': 'redis://localhost:6379/0', 'db': 0},
        {'url': 'redis://localhost:6379/1', 'db': 1}
    ]
    
    for config in test_configs:
        print(f"\n--- 测试数据库 {config['db']} ---")
        r = redis.Redis.from_url(config['url'], decode_responses=False)
        
        test_id = f"test_debug_db{config['db']}_123"
        test_data = {
            "status": "test",
            "filename": f"test_file_db{config['db']}.pdf",
            "document_type": "RCT",
            "progress": {"current": 0, "total": 5, "message": f"测试数据 DB{config['db']}"}
        }
        
        try:
            # 保存测试数据
            serialized = pickle.dumps(test_data)
            r.setex(f"qa_assessment:{test_id}", 300, serialized)  # 5分钟TTL
            print(f"   ✅ 测试数据已保存: qa_assessment:{test_id}")
            
            # 立即读取验证
            retrieved_data = r.get(f"qa_assessment:{test_id}")
            if retrieved_data:
                loaded_data = pickle.loads(retrieved_data)
                print(f"   ✅ 测试数据读取成功: {loaded_data['filename']}")
                
                # 清理测试数据
                r.delete(f"qa_assessment:{test_id}")
                print(f"   ✅ 测试数据已清理")
            else:
                print(f"   ❌ 测试数据读取失败")
                
        except Exception as e:
            print(f"   ❌ 测试失败: {e}")

if __name__ == "__main__":
    check_redis_assessments()
    test_assessment_creation() 