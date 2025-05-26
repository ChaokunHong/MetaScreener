#!/bin/bash

# MetaScreener PDF筛选问题快速修复脚本
# 解决云端部署后PDF筛选不显示结果的问题

set -e

echo "=========================================="
echo "MetaScreener PDF筛选问题修复工具"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为root用户
check_permissions() {
    if [[ $EUID -eq 0 ]]; then
        log_warn "以root用户运行，请确保这是必要的"
    fi
}

# 1. 安装系统依赖
install_system_dependencies() {
    log_info "安装系统依赖..."
    
    # 更新包列表
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -qq
        
        # 安装Tesseract OCR
        if ! command -v tesseract &> /dev/null; then
            log_info "安装Tesseract OCR..."
            sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim
        else
            log_info "Tesseract OCR已安装"
        fi
        
        # 安装其他依赖
        sudo apt-get install -y \
            libffi-dev \
            libssl-dev \
            python3-dev \
            build-essential \
            pkg-config \
            libfreetype6-dev \
            libjpeg-dev \
            zlib1g-dev
            
    elif command -v yum &> /dev/null; then
        # CentOS/RHEL
        sudo yum update -y
        sudo yum install -y tesseract tesseract-langpack-eng tesseract-langpack-chi_sim
        sudo yum groupinstall -y "Development Tools"
        sudo yum install -y python3-devel libffi-devel openssl-devel
    else
        log_error "不支持的包管理器，请手动安装依赖"
        return 1
    fi
    
    log_info "系统依赖安装完成"
}

# 2. 安装Python包
install_python_packages() {
    log_info "安装Python包..."
    
    # 确保pip是最新的
    python3 -m pip install --upgrade pip
    
    # 安装PDF处理相关包
    python3 -m pip install --upgrade \
        PyMuPDF \
        Pillow \
        pytesseract \
        psutil
    
    # 安装其他必要包
    python3 -m pip install --upgrade \
        redis \
        flask \
        gevent \
        gunicorn
    
    log_info "Python包安装完成"
}

# 3. 配置Redis
configure_redis() {
    log_info "配置Redis..."
    
    # 检查Redis是否安装
    if ! command -v redis-server &> /dev/null; then
        log_info "安装Redis..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get install -y redis-server
        elif command -v yum &> /dev/null; then
            sudo yum install -y redis
        fi
    fi
    
    # 启动Redis服务
    if command -v systemctl &> /dev/null; then
        sudo systemctl start redis-server 2>/dev/null || sudo systemctl start redis
        sudo systemctl enable redis-server 2>/dev/null || sudo systemctl enable redis
        log_info "Redis服务已启动并设置为开机自启"
    else
        log_warn "无法使用systemctl，请手动启动Redis"
    fi
    
    # 测试Redis连接
    if redis-cli ping &> /dev/null; then
        log_info "Redis连接测试成功"
    else
        log_error "Redis连接测试失败"
    fi
}

# 4. 创建必要目录和设置权限
setup_directories() {
    log_info "设置目录和权限..."
    
    # 创建必要目录
    mkdir -p uploads logs
    
    # 设置权限
    chmod 755 uploads logs
    
    # 确保当前用户有写入权限
    if [[ -w uploads && -w logs ]]; then
        log_info "目录权限设置成功"
    else
        log_error "目录权限设置失败"
    fi
}

# 5. 检查环境变量
check_environment() {
    log_info "检查环境变量..."
    
    # 检查重要的环境变量
    if [[ -z "$REDIS_URL" ]]; then
        log_warn "REDIS_URL未设置，使用默认值"
        export REDIS_URL="redis://localhost:6379/0"
    fi
    
    if [[ -z "$FLASK_ENV" ]]; then
        log_warn "FLASK_ENV未设置，设置为production"
        export FLASK_ENV="production"
    fi
    
    log_info "环境变量检查完成"
}

# 6. 测试PDF处理功能
test_pdf_processing() {
    log_info "测试PDF处理功能..."
    
    # 运行Python诊断脚本
    if [[ -f "deployment/diagnose_pdf_issues.py" ]]; then
        python3 deployment/diagnose_pdf_issues.py
    else
        log_warn "诊断脚本不存在，跳过详细测试"
    fi
}

# 7. 重启应用服务
restart_application() {
    log_info "重启应用服务..."
    
    # 尝试不同的重启方法
    if systemctl is-active --quiet screen_webapp; then
        sudo systemctl restart screen_webapp
        log_info "通过systemctl重启应用"
    elif pgrep -f "gunicorn.*screen_webapp" > /dev/null; then
        pkill -f "gunicorn.*screen_webapp"
        sleep 2
        log_info "已停止现有Gunicorn进程，请手动启动应用"
    else
        log_warn "未找到运行中的应用，请手动启动"
    fi
}

# 8. 验证修复结果
verify_fix() {
    log_info "验证修复结果..."
    
    # 检查关键组件
    checks_passed=0
    total_checks=5
    
    # 检查Tesseract
    if command -v tesseract &> /dev/null; then
        log_info "✓ Tesseract OCR: 可用"
        ((checks_passed++))
    else
        log_error "✗ Tesseract OCR: 不可用"
    fi
    
    # 检查Python包
    if python3 -c "import fitz, PIL, pytesseract, redis" &> /dev/null; then
        log_info "✓ Python包: 已安装"
        ((checks_passed++))
    else
        log_error "✗ Python包: 缺失"
    fi
    
    # 检查Redis
    if redis-cli ping &> /dev/null; then
        log_info "✓ Redis: 运行中"
        ((checks_passed++))
    else
        log_error "✗ Redis: 未运行"
    fi
    
    # 检查目录权限
    if [[ -w uploads && -w logs ]]; then
        log_info "✓ 目录权限: 正常"
        ((checks_passed++))
    else
        log_error "✗ 目录权限: 异常"
    fi
    
    # 检查应用进程
    if pgrep -f "gunicorn.*screen_webapp" > /dev/null || systemctl is-active --quiet screen_webapp; then
        log_info "✓ 应用进程: 运行中"
        ((checks_passed++))
    else
        log_warn "? 应用进程: 未检测到"
    fi
    
    echo
    log_info "验证结果: $checks_passed/$total_checks 项检查通过"
    
    if [[ $checks_passed -eq $total_checks ]]; then
        log_info "🎉 修复成功！PDF筛选功能应该正常工作了"
    elif [[ $checks_passed -ge 3 ]]; then
        log_warn "⚠️ 部分修复成功，可能需要手动处理剩余问题"
    else
        log_error "❌ 修复失败，请检查错误信息并手动处理"
    fi
}

# 9. 显示后续建议
show_recommendations() {
    echo
    log_info "后续建议:"
    echo "1. 检查应用日志:"
    echo "   tail -f logs/gunicorn.log"
    echo "   tail -f logs/app.log"
    echo
    echo "2. 测试PDF筛选功能:"
    echo "   访问应用的全文PDF筛选页面"
    echo "   上传一个测试PDF文件"
    echo
    echo "3. 如果问题仍然存在:"
    echo "   运行诊断脚本: python3 deployment/diagnose_pdf_issues.py"
    echo "   检查网络连接和API密钥配置"
    echo
    echo "4. 性能优化:"
    echo "   运行: ./deployment/apply_performance_optimizations.sh"
}

# 主函数
main() {
    log_info "开始修复PDF筛选问题..."
    
    # 检查权限
    check_permissions
    
    # 执行修复步骤
    install_system_dependencies
    install_python_packages
    configure_redis
    setup_directories
    check_environment
    test_pdf_processing
    restart_application
    
    # 验证和建议
    verify_fix
    show_recommendations
    
    log_info "修复脚本执行完成！"
}

# 错误处理
trap 'log_error "脚本执行失败，请检查错误信息"; exit 1' ERR

# 运行主函数
main "$@" 