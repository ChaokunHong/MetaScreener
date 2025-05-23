#!/usr/bin/env python3
"""
查找孤立的批次数据脚本
找到包含不存在assessment ID的批次，这是404错误的根本原因
"""

import os
import sys
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def find_orphaned_batches():
    """查找包含孤立assessment ID的批次"""
    
    print("=== 查找孤立批次数据 ===")
    
    try:
        # 创建Flask应用上下文
        from app import app
        with app.app_context():
            from quality_assessment.services import _assessments_db
            from quality_assessment.redis_storage import list_all_batches, delete_batch_status
            
            # 获取所有有效的assessment ID
            valid_assessment_ids = set(_assessments_db.keys())
            print(f"✓ 当前有效的assessment ID: {len(valid_assessment_ids)} 个")
            print(f"  ID范围: {sorted(valid_assessment_ids)}")
            
            # 获取所有Redis批次
            redis_batches = list_all_batches()
            print(f"✓ 找到Redis批次: {len(redis_batches)} 个")
            
            orphaned_batches = []
            total_orphaned_ids = set()
            
            for batch_id, batch_data in redis_batches.items():
                assessment_ids = batch_data.get('assessment_ids', [])
                batch_orphaned_ids = []
                
                # 检查每个assessment ID是否存在
                for aid in assessment_ids:
                    if aid not in valid_assessment_ids:
                        batch_orphaned_ids.append(aid)
                        total_orphaned_ids.add(aid)
                
                if batch_orphaned_ids:
                    orphaned_batches.append({
                        'batch_id': batch_id,
                        'orphaned_ids': batch_orphaned_ids,
                        'total_ids': len(assessment_ids),
                        'successful_filenames': batch_data.get('successful_filenames', []),
                        'status': batch_data.get('status', 'unknown')
                    })
            
            # 显示结果
            print(f"\n=== 检查结果 ===")
            print(f"孤立批次数量: {len(orphaned_batches)}")
            print(f"孤立assessment ID总数: {len(total_orphaned_ids)}")
            
            if total_orphaned_ids:
                print(f"所有孤立的assessment ID: {sorted(total_orphaned_ids)}")
                
                # 特别检查问题ID
                problem_ids = {'85', '86', '87'}
                found_problem_ids = problem_ids.intersection(total_orphaned_ids)
                if found_problem_ids:
                    print(f"🎯 找到问题ID: {found_problem_ids}")
                
            print(f"\n=== 孤立批次详情 ===")
            for idx, batch in enumerate(orphaned_batches, 1):
                print(f"\n{idx}. 批次ID: {batch['batch_id'][:12]}...")
                print(f"   状态: {batch['status']}")
                print(f"   总assessment数: {batch['total_ids']}")
                print(f"   孤立ID数: {len(batch['orphaned_ids'])}")
                print(f"   孤立ID: {batch['orphaned_ids']}")
                print(f"   文件名: {batch['successful_filenames']}")
            
            return orphaned_batches, total_orphaned_ids
            
    except Exception as e:
        print(f"✗ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return [], set()

def clean_orphaned_batches(orphaned_batches):
    """清理孤立的批次数据"""
    
    if not orphaned_batches:
        print("没有需要清理的孤立批次。")
        return
    
    print(f"\n=== 清理选项 ===")
    print(f"找到 {len(orphaned_batches)} 个包含孤立assessment ID的批次")
    print("可选操作:")
    print("1. 删除所有孤立批次")
    print("2. 只删除完全孤立的批次（所有assessment ID都不存在）")
    print("3. 手动选择要删除的批次")
    print("4. 取消清理")
    
    choice = input("\n请选择操作 (1-4): ").strip()
    
    if choice == '4':
        print("取消清理操作。")
        return
    
    try:
        from app import app
        with app.app_context():
            from quality_assessment.redis_storage import delete_batch_status
            from quality_assessment.services import _assessments_db
            
            valid_ids = set(_assessments_db.keys())
            batches_to_delete = []
            
            if choice == '1':
                # 删除所有孤立批次
                batches_to_delete = orphaned_batches
                
            elif choice == '2':
                # 只删除完全孤立的批次
                for batch in orphaned_batches:
                    assessment_ids = set(batch['orphaned_ids'])
                    # 检查是否batch中的所有ID都是孤立的
                    total_batch_ids = batch['total_ids']
                    if len(batch['orphaned_ids']) == total_batch_ids:
                        batches_to_delete.append(batch)
                        
            elif choice == '3':
                # 手动选择
                print(f"\n手动选择要删除的批次:")
                for idx, batch in enumerate(orphaned_batches, 1):
                    print(f"{idx}. 批次 {batch['batch_id'][:12]}... (孤立ID: {len(batch['orphaned_ids'])}/{batch['total_ids']})")
                
                selected = input("输入要删除的批次序号 (用逗号分隔, 如: 1,3,5): ").strip()
                if selected:
                    try:
                        indices = [int(x.strip()) - 1 for x in selected.split(',')]
                        batches_to_delete = [orphaned_batches[i] for i in indices if 0 <= i < len(orphaned_batches)]
                    except ValueError:
                        print("无效的输入格式。")
                        return
            
            # 执行删除
            if batches_to_delete:
                print(f"\n开始删除 {len(batches_to_delete)} 个批次...")
                
                for batch in batches_to_delete:
                    batch_id = batch['batch_id']
                    try:
                        success = delete_batch_status(batch_id)
                        if success:
                            print(f"✓ 已删除批次: {batch_id[:12]}...")
                        else:
                            print(f"✗ 删除失败: {batch_id[:12]}...")
                    except Exception as e:
                        print(f"✗ 删除批次 {batch_id[:12]}... 时出错: {e}")
                
                print(f"\n🎉 清理完成！删除了 {len(batches_to_delete)} 个孤立批次。")
                print("404错误应该已经解决。")
                
            else:
                print("没有选择要删除的批次。")
            
    except Exception as e:
        print(f"✗ 清理失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    print("🔍 MetaScreener 孤立批次检测工具")
    print("=" * 50)
    
    # 查找孤立批次
    orphaned_batches, total_orphaned_ids = find_orphaned_batches()
    
    if not orphaned_batches:
        print("\n🎉 好消息！没有找到孤立的批次数据。")
        print("404错误可能由其他原因引起。")
        return
    
    # 显示问题总结
    print(f"\n🚨 发现问题！")
    print(f"找到 {len(orphaned_batches)} 个包含孤立assessment ID的批次")
    print(f"这些批次引用了 {len(total_orphaned_ids)} 个不存在的assessment ID")
    print("这就是导致404错误的根本原因。")
    
    # 检查是否包含用户报告的问题ID
    problem_ids = {'85', '86', '87'}
    found_problem_ids = problem_ids.intersection(total_orphaned_ids)
    if found_problem_ids:
        print(f"\n🎯 确认：找到了用户报告的问题ID: {found_problem_ids}")
    
    # 询问是否清理
    clean_choice = input(f"\n是否要清理这些孤立的批次数据？(y/n): ").strip().lower()
    if clean_choice in ['y', 'yes', '是']:
        clean_orphaned_batches(orphaned_batches)
    else:
        print("保留孤立批次数据。404错误仍会继续出现。")
        print("\n💡 解决方案:")
        print("1. 运行此脚本并选择清理孤立数据")
        print("2. 或手动删除相关的Redis批次数据")
        print("3. 或重新上传对应的文档以重新创建assessment")

if __name__ == "__main__":
    main() 