#!/usr/bin/env python3
"""
PDF筛选问题诊断脚本
用于检查云端环境的依赖、配置和潜在问题
"""

import os
import sys
import subprocess
import tempfile
import traceback
from pathlib import Path

def check_python_packages():
    """检查Python包依赖"""
    print("=" * 50)
    print("检查Python包依赖")
    print("=" * 50)
    
    required_packages = [
        'fitz',  # PyMuPDF
        'PIL',   # Pillow
        'pytesseract',
        'redis',
        'flask',
        'gevent'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package}: 已安装")
        except ImportError as e:
            print(f"✗ {package}: 未安装 - {e}")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n缺少的包: {', '.join(missing_packages)}")
        print("安装命令:")
        if 'fitz' in missing_packages:
            print("pip install PyMuPDF")
        if 'PIL' in missing_packages:
            print("pip install Pillow")
        if 'pytesseract' in missing_packages:
            print("pip install pytesseract")
        print("pip install redis flask gevent")
    
    return len(missing_packages) == 0

def check_system_dependencies():
    """检查系统依赖"""
    print("\n" + "=" * 50)
    print("检查系统依赖")
    print("=" * 50)
    
    # 检查Tesseract
    try:
        result = subprocess.run(['tesseract', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✓ Tesseract OCR: 已安装")
            print(f"  版本: {result.stdout.split()[1]}")
        else:
            print("✗ Tesseract OCR: 未正确安装")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("✗ Tesseract OCR: 未找到")
        print("  安装命令: sudo apt-get install tesseract-ocr tesseract-ocr-eng")
    
    # 检查Redis
    try:
        result = subprocess.run(['redis-cli', 'ping'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and 'PONG' in result.stdout:
            print("✓ Redis: 运行中")
        else:
            print("✗ Redis: 未运行或连接失败")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("✗ Redis: 未找到或未运行")
        print("  启动命令: sudo systemctl start redis-server")

def test_pdf_processing():
    """测试PDF处理功能"""
    print("\n" + "=" * 50)
    print("测试PDF处理功能")
    print("=" * 50)
    
    try:
        import fitz
        print("✓ PyMuPDF导入成功")
        
        # 创建测试PDF
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Test PDF content for screening", fontsize=12)
        
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            doc.save(tmp_file.name)
            test_pdf_path = tmp_file.name
        
        doc.close()
        
        # 测试文本提取
        with open(test_pdf_path, 'rb') as f:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from app.utils.utils import extract_text_from_pdf
            
            extracted_text = extract_text_from_pdf(f)
            if extracted_text and "Test PDF content" in extracted_text:
                print("✓ PDF文本提取: 成功")
            else:
                print("✗ PDF文本提取: 失败")
                print(f"  提取结果: {extracted_text}")
        
        # 清理临时文件
        os.unlink(test_pdf_path)
        
    except Exception as e:
        print(f"✗ PDF处理测试失败: {e}")
        traceback.print_exc()

def test_redis_connection():
    """测试Redis连接"""
    print("\n" + "=" * 50)
    print("测试Redis连接")
    print("=" * 50)
    
    try:
        import redis
        
        # 测试不同的Redis配置
        redis_configs = [
            {'host': 'localhost', 'port': 6379, 'db': 0},
            {'host': 'localhost', 'port': 6379, 'db': 1},
            {'host': '127.0.0.1', 'port': 6379, 'db': 0},
        ]
        
        for config in redis_configs:
            try:
                r = redis.Redis(**config)
                r.ping()
                print(f"✓ Redis连接成功: {config}")
                
                # 测试基本操作
                r.set('test_key', 'test_value')
                value = r.get('test_key')
                if value == b'test_value':
                    print("  ✓ Redis读写测试成功")
                r.delete('test_key')
                break
                
            except Exception as e:
                print(f"✗ Redis连接失败: {config} - {e}")
        
    except ImportError:
        print("✗ Redis包未安装")

def check_file_permissions():
    """检查文件权限"""
    print("\n" + "=" * 50)
    print("检查文件权限")
    print("=" * 50)
    
    # 检查上传目录
    upload_dirs = [
        'uploads',
        '/tmp',
        'logs'
    ]
    
    for dir_path in upload_dirs:
        try:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
            
            # 测试写入权限
            test_file = os.path.join(dir_path, 'test_write.tmp')
            with open(test_file, 'w') as f:
                f.write('test')
            
            # 测试读取权限
            with open(test_file, 'r') as f:
                content = f.read()
            
            os.unlink(test_file)
            print(f"✓ {dir_path}: 读写权限正常")
            
        except Exception as e:
            print(f"✗ {dir_path}: 权限问题 - {e}")

def check_environment_variables():
    """检查环境变量"""
    print("\n" + "=" * 50)
    print("检查环境变量")
    print("=" * 50)
    
    important_vars = [
        'FLASK_ENV',
        'REDIS_URL',
        'CELERY_BROKER_URL',
        'CELERY_RESULT_BACKEND'
    ]
    
    for var in important_vars:
        value = os.environ.get(var)
        if value:
            print(f"✓ {var}: {value}")
        else:
            print(f"✗ {var}: 未设置")

def test_llm_api_connectivity():
    """测试LLM API连接"""
    print("\n" + "=" * 50)
    print("测试LLM API连接")
    print("=" * 50)
    
    import requests
    
    api_endpoints = {
        "DeepSeek": "https://api.deepseek.com",
        "OpenAI": "https://api.openai.com",
        "Claude": "https://api.anthropic.com",
        "Gemini": "https://generativelanguage.googleapis.com"
    }
    
    for name, url in api_endpoints.items():
        try:
            response = requests.get(url, timeout=10)
            print(f"✓ {name}: 可访问 (状态码: {response.status_code})")
        except Exception as e:
            print(f"✗ {name}: 连接失败 - {e}")

def check_memory_usage():
    """检查内存使用情况"""
    print("\n" + "=" * 50)
    print("检查系统资源")
    print("=" * 50)
    
    try:
        import psutil
        
        # 内存信息
        memory = psutil.virtual_memory()
        print(f"总内存: {memory.total / (1024**3):.1f} GB")
        print(f"可用内存: {memory.available / (1024**3):.1f} GB")
        print(f"内存使用率: {memory.percent}%")
        
        # 磁盘信息
        disk = psutil.disk_usage('/')
        print(f"磁盘总空间: {disk.total / (1024**3):.1f} GB")
        print(f"磁盘可用空间: {disk.free / (1024**3):.1f} GB")
        print(f"磁盘使用率: {(disk.used / disk.total) * 100:.1f}%")
        
        # CPU信息
        cpu_percent = psutil.cpu_percent(interval=1)
        print(f"CPU使用率: {cpu_percent}%")
        print(f"CPU核心数: {psutil.cpu_count()}")
        
    except ImportError:
        print("psutil包未安装，无法检查系统资源")
        print("安装命令: pip install psutil")

def generate_fix_script():
    """生成修复脚本"""
    print("\n" + "=" * 50)
    print("生成修复脚本")
    print("=" * 50)
    
    fix_script = """#!/bin/bash
# PDF筛选问题修复脚本

echo "开始修复PDF筛选问题..."

# 1. 安装系统依赖
echo "安装系统依赖..."
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng

# 2. 安装Python包
echo "安装Python包..."
pip install PyMuPDF Pillow pytesseract psutil

# 3. 启动Redis
echo "启动Redis..."
sudo systemctl start redis-server
sudo systemctl enable redis-server

# 4. 创建必要目录
echo "创建目录..."
mkdir -p uploads logs

# 5. 设置权限
echo "设置权限..."
chmod 755 uploads logs

# 6. 重启应用
echo "重启应用..."
sudo systemctl restart screen_webapp || echo "请手动重启应用"

echo "修复完成！"
"""
    
    with open('fix_pdf_issues.sh', 'w') as f:
        f.write(fix_script)
    
    os.chmod('fix_pdf_issues.sh', 0o755)
    print("✓ 修复脚本已生成: fix_pdf_issues.sh")
    print("  运行命令: ./fix_pdf_issues.sh")

def main():
    """主函数"""
    print("PDF筛选问题诊断工具")
    print("=" * 50)
    
    all_checks_passed = True
    
    # 执行所有检查
    checks = [
        check_python_packages,
        check_system_dependencies,
        test_pdf_processing,
        test_redis_connection,
        check_file_permissions,
        check_environment_variables,
        test_llm_api_connectivity,
        check_memory_usage
    ]
    
    for check in checks:
        try:
            result = check()
            if result is False:
                all_checks_passed = False
        except Exception as e:
            print(f"检查失败: {e}")
            all_checks_passed = False
    
    # 生成修复脚本
    generate_fix_script()
    
    print("\n" + "=" * 50)
    print("诊断总结")
    print("=" * 50)
    
    if all_checks_passed:
        print("✓ 所有检查通过，PDF筛选功能应该正常工作")
    else:
        print("✗ 发现问题，请查看上述检查结果并运行修复脚本")
        print("  修复命令: ./fix_pdf_issues.sh")
    
    print("\n如果问题仍然存在，请检查应用日志:")
    print("  tail -f logs/gunicorn.log")
    print("  tail -f logs/app.log")

if __name__ == "__main__":
    main() 