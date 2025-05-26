#!/usr/bin/env python3
"""
修复批量PDF筛选会话存储问题
解决"Batch PDF screening results not found or may have expired"错误
"""

import os
import sys
import redis
import pickle
import json
import time
from datetime import datetime, timedelta

def get_redis_client():
    """获取Redis客户端"""
    try:
        # 尝试不同的Redis配置
        redis_configs = [
            {'host': 'localhost', 'port': 6379, 'db': 0, 'decode_responses': False},
            {'host': 'localhost', 'port': 6379, 'db': 1, 'decode_responses': False},
            {'host': '127.0.0.1', 'port': 6379, 'db': 0, 'decode_responses': False},
        ]
        
        for config in redis_configs:
            try:
                client = redis.Redis(**config)
                client.ping()
                print(f"✓ Redis连接成功: {config}")
                return client
            except Exception as e:
                print(f"✗ Redis连接失败: {config} - {e}")
                continue
        
        print("✗ 无法连接到Redis")
        return None
        
    except Exception as e:
        print(f"✗ Redis连接错误: {e}")
        return None

def check_existing_sessions(redis_client):
    """检查现有的会话数据"""
    print("\n" + "=" * 50)
    print("检查现有会话数据")
    print("=" * 50)
    
    try:
        # 检查full_screening会话
        full_screening_keys = redis_client.keys("full_screening:*")
        print(f"找到 {len(full_screening_keys)} 个full_screening会话")
        
        batch_pdf_sessions = []
        for key in full_screening_keys:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                session_id = key.replace("full_screening:", "")
                data = redis_client.get(key)
                
                if data:
                    session_data = pickle.loads(data)
                    if session_data.get('is_batch_pdf_result', False):
                        batch_pdf_sessions.append({
                            'session_id': session_id,
                            'data': session_data,
                            'key': key
                        })
                        print(f"  ✓ 批量PDF会话: {session_id}")
                        print(f"    文件数: {len(session_data.get('results', []))}")
                        print(f"    描述: {session_data.get('filename', 'Unknown')}")
                
            except Exception as e:
                print(f"  ✗ 处理会话失败 {key}: {e}")
        
        # 检查pdf_batch_results
        pdf_batch_keys = redis_client.keys("pdf_batch_results:*")
        print(f"\n找到 {len(pdf_batch_keys)} 个pdf_batch_results")
        
        for key in pdf_batch_keys:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                batch_id = key.replace("pdf_batch_results:", "")
                print(f"  ✓ PDF批量结果: {batch_id}")
            except Exception as e:
                print(f"  ✗ 处理批量结果失败 {key}: {e}")
        
        return batch_pdf_sessions
        
    except Exception as e:
        print(f"✗ 检查会话数据失败: {e}")
        return []

def restore_sessions_from_redis(redis_client):
    """从Redis恢复会话到内存"""
    print("\n" + "=" * 50)
    print("从Redis恢复会话")
    print("=" * 50)
    
    try:
        # 添加项目路径到Python路径
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, project_root)
        
        # 导入应用模块
        from app.core.app import full_screening_sessions
        
        # 获取所有full_screening会话
        full_screening_keys = redis_client.keys("full_screening:*")
        restored_count = 0
        
        for key in full_screening_keys:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                session_id = key.replace("full_screening:", "")
                data = redis_client.get(key)
                
                if data:
                    session_data = pickle.loads(data)
                    full_screening_sessions[session_id] = session_data
                    restored_count += 1
                    
                    if session_data.get('is_batch_pdf_result', False):
                        print(f"  ✓ 恢复批量PDF会话: {session_id}")
                    else:
                        print(f"  ✓ 恢复普通会话: {session_id}")
                
            except Exception as e:
                print(f"  ✗ 恢复会话失败 {key}: {e}")
        
        print(f"\n总共恢复了 {restored_count} 个会话")
        return restored_count
        
    except Exception as e:
        print(f"✗ 恢复会话失败: {e}")
        return 0

def extend_session_expiry(redis_client, session_ids=None, days=7):
    """延长会话过期时间"""
    print("\n" + "=" * 50)
    print(f"延长会话过期时间 ({days}天)")
    print("=" * 50)
    
    try:
        if session_ids is None:
            # 获取所有会话
            keys = redis_client.keys("full_screening:*")
        else:
            keys = [f"full_screening:{sid}" for sid in session_ids]
        
        extended_count = 0
        expiry_seconds = days * 24 * 60 * 60  # 转换为秒
        
        for key in keys:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                # 设置新的过期时间
                redis_client.expire(key, expiry_seconds)
                extended_count += 1
                print(f"  ✓ 延长过期时间: {key}")
                
            except Exception as e:
                print(f"  ✗ 延长过期时间失败 {key}: {e}")
        
        print(f"\n总共延长了 {extended_count} 个会话的过期时间")
        return extended_count
        
    except Exception as e:
        print(f"✗ 延长过期时间失败: {e}")
        return 0

def create_test_session(redis_client):
    """创建测试会话"""
    print("\n" + "=" * 50)
    print("创建测试会话")
    print("=" * 50)
    
    try:
        import uuid
        
        test_session_id = str(uuid.uuid4())
        test_data = {
            'filename': 'Test Batch PDF Results (2 files processed)',
            'filter_applied': 'all uploaded files',
            'results': [
                {
                    'original_index': 0,
                    'filename': 'test_document_1.pdf',
                    'title_for_display': 'Test Document 1',
                    'decision': 'INCLUDE',
                    'reasoning': 'This is a test document that meets inclusion criteria.'
                },
                {
                    'original_index': 1,
                    'filename': 'test_document_2.pdf',
                    'title_for_display': 'Test Document 2',
                    'decision': 'EXCLUDE',
                    'reasoning': 'This is a test document that does not meet inclusion criteria.'
                }
            ],
            'is_batch_pdf_result': True,
            'created_at': time.time()
        }
        
        # 存储到Redis
        redis_client.setex(
            f"full_screening:{test_session_id}",
            7 * 24 * 60 * 60,  # 7天过期
            pickle.dumps(test_data)
        )
        
        print(f"✓ 创建测试会话: {test_session_id}")
        print(f"  访问URL: /show_batch_pdf_results/{test_session_id}")
        
        return test_session_id
        
    except Exception as e:
        print(f"✗ 创建测试会话失败: {e}")
        return None

def cleanup_expired_sessions(redis_client):
    """清理过期会话"""
    print("\n" + "=" * 50)
    print("清理过期会话")
    print("=" * 50)
    
    try:
        # 获取所有会话键
        all_keys = redis_client.keys("full_screening:*")
        cleaned_count = 0
        
        for key in all_keys:
            try:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                # 检查TTL
                ttl = redis_client.ttl(key)
                if ttl == -2:  # 键不存在
                    continue
                elif ttl == -1:  # 键存在但没有过期时间
                    print(f"  ! 键没有过期时间: {key}")
                    # 设置默认过期时间
                    redis_client.expire(key, 7 * 24 * 60 * 60)  # 7天
                elif ttl < 3600:  # 小于1小时
                    print(f"  ! 键即将过期: {key} (TTL: {ttl}秒)")
                
            except Exception as e:
                print(f"  ✗ 检查键失败 {key}: {e}")
        
        print(f"清理检查完成")
        
    except Exception as e:
        print(f"✗ 清理过期会话失败: {e}")

def fix_session_storage_mechanism():
    """修复会话存储机制"""
    print("\n" + "=" * 50)
    print("修复会话存储机制")
    print("=" * 50)
    
    try:
        # 检查应用代码中的存储函数
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_file = os.path.join(project_root, 'app', 'core', 'app.py')
        
        if os.path.exists(app_file):
            print("✓ 找到应用文件")
            
            # 读取文件内容
            with open(app_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查关键函数
            if 'store_full_screening_session' in content:
                print("✓ 找到store_full_screening_session函数")
            else:
                print("✗ 未找到store_full_screening_session函数")
            
            if 'get_full_screening_session' in content:
                print("✓ 找到get_full_screening_session函数")
            else:
                print("✗ 未找到get_full_screening_session函数")
            
            # 检查Redis存储逻辑
            if 'redis_client.set(f"full_screening:' in content:
                print("✓ 找到Redis存储逻辑")
            else:
                print("✗ 未找到Redis存储逻辑")
        
        else:
            print("✗ 未找到应用文件")
        
    except Exception as e:
        print(f"✗ 检查存储机制失败: {e}")

def generate_recovery_commands(batch_sessions):
    """生成恢复命令"""
    print("\n" + "=" * 50)
    print("生成恢复命令")
    print("=" * 50)
    
    if not batch_sessions:
        print("没有找到批量PDF会话，无需生成恢复命令")
        return
    
    recovery_script = """#!/bin/bash
# 批量PDF会话恢复脚本

echo "开始恢复批量PDF会话..."

# 重启Redis服务
sudo systemctl restart redis-server
sleep 2

# 重启应用服务
sudo systemctl restart metascreener
sleep 5

echo "服务重启完成"

# 检查会话状态
python3 deployment/fix_batch_pdf_sessions.py --check-only

echo "恢复完成！"
"""
    
    with open('recovery_batch_sessions.sh', 'w') as f:
        f.write(recovery_script)
    
    os.chmod('recovery_batch_sessions.sh', 0o755)
    print("✓ 生成恢复脚本: recovery_batch_sessions.sh")
    
    # 生成手动恢复说明
    manual_recovery = f"""
手动恢复批量PDF会话说明
========================

找到的批量PDF会话:
"""
    
    for session in batch_sessions:
        manual_recovery += f"""
会话ID: {session['session_id']}
文件数: {len(session['data'].get('results', []))}
描述: {session['data'].get('filename', 'Unknown')}
访问URL: /show_batch_pdf_results/{session['session_id']}
"""
    
    manual_recovery += """
恢复步骤:
1. 重启Redis: sudo systemctl restart redis-server
2. 重启应用: sudo systemctl restart metascreener
3. 检查会话: python3 deployment/fix_batch_pdf_sessions.py --check-only
4. 如果仍有问题，运行: python3 deployment/fix_batch_pdf_sessions.py --restore

如果问题持续存在:
1. 检查Redis配置: redis-cli config get "*"
2. 检查应用日志: tail -f logs/gunicorn.log
3. 手动创建测试会话: python3 deployment/fix_batch_pdf_sessions.py --create-test
"""
    
    with open('manual_recovery_guide.txt', 'w') as f:
        f.write(manual_recovery)
    
    print("✓ 生成手动恢复指南: manual_recovery_guide.txt")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='修复批量PDF筛选会话存储问题')
    parser.add_argument('--check-only', action='store_true', help='仅检查现有会话')
    parser.add_argument('--restore', action='store_true', help='恢复会话到内存')
    parser.add_argument('--extend-expiry', type=int, default=7, help='延长过期时间(天)')
    parser.add_argument('--create-test', action='store_true', help='创建测试会话')
    parser.add_argument('--cleanup', action='store_true', help='清理过期会话')
    
    args = parser.parse_args()
    
    print("批量PDF会话修复工具")
    print("=" * 50)
    
    # 获取Redis客户端
    redis_client = get_redis_client()
    if not redis_client:
        print("无法连接到Redis，请检查Redis服务状态")
        return 1
    
    # 检查现有会话
    batch_sessions = check_existing_sessions(redis_client)
    
    if args.check_only:
        print("\n仅检查模式，不执行修复操作")
        return 0
    
    if args.create_test:
        test_session_id = create_test_session(redis_client)
        if test_session_id:
            print(f"\n测试会话创建成功！")
            print(f"访问URL: http://your-server/show_batch_pdf_results/{test_session_id}")
        return 0
    
    if args.cleanup:
        cleanup_expired_sessions(redis_client)
        return 0
    
    if args.restore:
        restored_count = restore_sessions_from_redis(redis_client)
        print(f"恢复了 {restored_count} 个会话")
    
    # 延长过期时间
    if args.extend_expiry > 0:
        extend_session_expiry(redis_client, days=args.extend_expiry)
    
    # 修复存储机制
    fix_session_storage_mechanism()
    
    # 生成恢复命令
    generate_recovery_commands(batch_sessions)
    
    print("\n" + "=" * 50)
    print("修复总结")
    print("=" * 50)
    
    if batch_sessions:
        print(f"✓ 找到 {len(batch_sessions)} 个批量PDF会话")
        print("✓ 已延长会话过期时间")
        print("✓ 生成了恢复脚本和指南")
        print("\n建议操作:")
        print("1. 运行恢复脚本: ./recovery_batch_sessions.sh")
        print("2. 查看手动指南: cat manual_recovery_guide.txt")
        print("3. 测试访问会话URL")
    else:
        print("✗ 未找到批量PDF会话")
        print("建议:")
        print("1. 创建测试会话: python3 deployment/fix_batch_pdf_sessions.py --create-test")
        print("2. 检查应用日志: tail -f logs/gunicorn.log")
        print("3. 重新运行PDF筛选")
    
    return 0

if __name__ == "__main__":
    exit(main()) 