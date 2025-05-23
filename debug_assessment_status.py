#!/usr/bin/env python3
"""
调试脚本：检查质量评估数据库状态
用于排查assessment_status API返回404错误的问题
"""

import os
import sys
import pickle
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_assessment_data():
    """检查assessment数据文件和内存状态"""
    
    # 数据文件路径
    data_dir = os.path.join(project_root, 'quality_assessment', 'data')
    assessments_file = os.path.join(data_dir, 'assessments.pickle')
    
    print("=== 质量评估数据库状态检查 ===")
    print(f"项目根目录: {project_root}")
    print(f"数据目录: {data_dir}")
    print(f"数据文件: {assessments_file}")
    print()
    
    # 检查数据目录
    if os.path.exists(data_dir):
        print(f"✓ 数据目录存在: {data_dir}")
        files = os.listdir(data_dir)
        print(f"  目录内容: {files}")
    else:
        print(f"✗ 数据目录不存在: {data_dir}")
        return
    
    # 检查数据文件
    if os.path.exists(assessments_file):
        print(f"✓ 数据文件存在: {assessments_file}")
        file_size = os.path.getsize(assessments_file)
        print(f"  文件大小: {file_size} bytes")
        
        try:
            # 尝试加载数据
            with open(assessments_file, 'rb') as f:
                loaded_db, next_id = pickle.load(f)
            
            print(f"✓ 数据文件加载成功")
            print(f"  下一个ID: {next_id}")
            print(f"  当前assessment数量: {len(loaded_db)}")
            
            if loaded_db:
                print("\n=== 当前Assessment列表 ===")
                for assessment_id, data in loaded_db.items():
                    status = data.get('status', 'unknown')
                    filename = data.get('filename', 'unknown')
                    doc_type = data.get('document_type', 'unknown')
                    print(f"  ID: {assessment_id} | 状态: {status} | 文件: {filename} | 类型: {doc_type}")
                
                # 特别检查缺失的ID
                print("\n=== 检查问题ID ===")
                problem_ids = ['85', '86', '87']
                for pid in problem_ids:
                    if pid in loaded_db:
                        print(f"  ✓ ID {pid} 存在")
                        data = loaded_db[pid]
                        print(f"    状态: {data.get('status')}")
                        print(f"    文件名: {data.get('filename')}")
                    else:
                        print(f"  ✗ ID {pid} 不存在")
            else:
                print("  数据库为空")
                
        except Exception as e:
            print(f"✗ 数据文件加载失败: {e}")
            
    else:
        print(f"✗ 数据文件不存在: {assessments_file}")
    
    print("\n=== 导入并检查运行时状态 ===")
    try:
        from quality_assessment.services import _assessments_db, get_assessment_result
        
        print(f"运行时_assessments_db包含 {len(_assessments_db)} 个条目")
        
        if _assessments_db:
            print("运行时Assessment列表:")
            for assessment_id, data in _assessments_db.items():
                status = data.get('status', 'unknown')
                filename = data.get('filename', 'unknown')
                print(f"  ID: {assessment_id} | 状态: {status} | 文件: {filename}")
        
        # 测试get_assessment_result函数
        print("\n=== 测试get_assessment_result函数 ===")
        problem_ids = ['85', '86', '87']
        for pid in problem_ids:
            result = get_assessment_result(pid)
            if result:
                print(f"  ✓ ID {pid}: {result.get('status', 'no status')}")
            else:
                print(f"  ✗ ID {pid}: None (这就是404错误的原因)")
                
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
    except Exception as e:
        print(f"✗ 运行时检查失败: {e}")

def check_recent_logs():
    """检查最近的日志以了解发生了什么"""
    print("\n=== 搜索相关日志信息 ===")
    
    # 搜索可能的日志文件位置
    possible_log_locations = [
        'app.log',
        'logs/app.log',
        'logs/quality_assessment.log',
        '/tmp/flask_app.log'
    ]
    
    for log_path in possible_log_locations:
        if os.path.exists(log_path):
            print(f"找到日志文件: {log_path}")
            # 这里可以添加日志分析逻辑
        else:
            print(f"日志文件不存在: {log_path}")

if __name__ == "__main__":
    check_assessment_data()
    check_recent_logs()
    
    print("\n=== 建议解决方案 ===")
    print("1. 如果assessment数据丢失，需要重新上传文档或从备份恢复")
    print("2. 如果数据文件损坏，需要清理并重新开始")
    print("3. 检查服务器日志，了解数据丢失的原因")
    print("4. 考虑添加更好的错误处理和数据持久化机制") 