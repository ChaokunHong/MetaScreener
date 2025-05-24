#!/usr/bin/env python3

"""
Debug script to check Redis assessment data
用于排查assessment_status API返回404错误的问题
"""

import redis
import pickle
import os
import sys
import time
import threading

def check_environment_variables():
    """检查关键环境变量"""
    print("=== 环境变量检查 ===")
    env_vars = [
        'CELERY_BROKER_URL',
        'CELERY_RESULT_BACKEND', 
        'REDIS_URL',
        'FLASK_ENV',
        'FLASK_APP'
    ]
    
    for var in env_vars:
        value = os.getenv(var, 'NOT_SET')
        print(f"{var}: {value}")

def check_redis_assessments():
    print("=== Redis Assessment Data Debug ===")
    
    # 检查多个Redis数据库
    redis_configs = [
        {'url': 'redis://localhost:6379/0', 'desc': 'DB 0 (默认)'},
        {'url': 'redis://localhost:6379/1', 'desc': 'DB 1 (Celery)'},
        {'url': os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'), 'desc': 'CELERY_BROKER_URL环境变量'},
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
                
            # 检查batch数据
            print(f"\n   === Batch Status ===")
            batch_keys = r.keys("qa_batch:*")
            print(f"   找到 {len(batch_keys)} 个批次键")
            
            for key in batch_keys[:3]:  # 只显示前3个
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
        {'url': 'redis://localhost:6379/1', 'db': 1},
        {'url': os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'), 'db': 'CELERY_BROKER_URL'}
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

def monitor_redis_activity():
    """实时监控Redis的写入活动"""
    print(f"\n=== 实时Redis监控 (按Ctrl+C停止) ===")
    
    # 使用CELERY_BROKER_URL作为主要监控目标
    redis_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1')
    print(f"监控Redis: {redis_url}")
    
    try:
        r = redis.Redis.from_url(redis_url, decode_responses=False)
        
        def monitor_worker():
            """后台监控worker"""
            last_keys = set()
            while True:
                try:
                    current_keys = set(r.keys("qa_assessment:*"))
                    new_keys = current_keys - last_keys
                    deleted_keys = last_keys - current_keys
                    
                    if new_keys:
                        for key in new_keys:
                            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                            print(f"🆕 新增assessment: {key_str}")
                    
                    if deleted_keys:
                        for key in deleted_keys:
                            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                            print(f"🗑️ 删除assessment: {key_str}")
                    
                    last_keys = current_keys
                    time.sleep(2)  # 每2秒检查一次
                except Exception as e:
                    print(f"监控错误: {e}")
                    time.sleep(5)
        
        # 启动监控线程
        monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
        monitor_thread.start()
        
        print("监控已启动，请在另一个终端进行质量评估上传测试...")
        print("按Enter键停止监控")
        
        input()  # 等待用户按Enter
        
    except KeyboardInterrupt:
        print("\n监控已停止")
    except Exception as e:
        print(f"监控启动失败: {e}")

if __name__ == "__main__":
    check_environment_variables()
    check_redis_assessments()
    test_assessment_creation()
    
    # 询问是否要启动实时监控
    try:
        response = input("\n是否启动实时Redis监控? (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            monitor_redis_activity()
    except KeyboardInterrupt:
        print("\n程序结束") 