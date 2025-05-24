#!/bin/bash

# MetaScreener Performance Optimization Script
# 用于云端部署的性能优化自动配置脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "MetaScreener 性能优化脚本"
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

# 检查是否以root权限运行
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warn "建议不要以root用户运行此脚本，除非确实需要修改系统配置"
        read -p "是否继续? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# 备份配置文件
backup_configs() {
    log_info "备份现有配置文件..."
    
    BACKUP_DIR="$PROJECT_DIR/deployment/config_backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # 备份Redis配置
    if [[ -f /etc/redis/redis.conf ]]; then
        sudo cp /etc/redis/redis.conf "$BACKUP_DIR/" 2>/dev/null || log_warn "无法备份Redis配置"
    fi
    
    # 备份系统配置
    if [[ -f /etc/sysctl.conf ]]; then
        sudo cp /etc/sysctl.conf "$BACKUP_DIR/" 2>/dev/null || log_warn "无法备份sysctl配置"
    fi
    
    log_info "配置文件已备份到: $BACKUP_DIR"
}

# 优化Redis配置
optimize_redis() {
    log_info "优化Redis配置..."
    
    if ! command -v redis-cli &> /dev/null; then
        log_error "Redis未安装，跳过Redis优化"
        return 1
    fi
    
    # 测试Redis连接
    if ! redis-cli ping &> /dev/null; then
        log_error "无法连接到Redis服务，请检查Redis是否正在运行"
        return 1
    fi
    
    # 创建Redis优化配置
    cat > /tmp/redis_optimization.conf << 'EOF'
# MetaScreener Redis Performance Optimization

# 内存优化
maxmemory 2gb
maxmemory-policy allkeys-lru

# 网络优化
tcp-keepalive 300
timeout 0

# 性能优化
save 900 1
save 300 10
save 60 10000

# 日志级别
loglevel notice

# 客户端连接优化
tcp-backlog 2048
EOF

    # 应用Redis配置（需要管理员权限）
    if [[ -w /etc/redis/redis.conf ]]; then
        cat /tmp/redis_optimization.conf >> /etc/redis/redis.conf
        log_info "Redis配置已更新"
        
        # 重启Redis服务
        if command -v systemctl &> /dev/null; then
            sudo systemctl restart redis-server 2>/dev/null || sudo systemctl restart redis
            log_info "Redis服务已重启"
        fi
    else
        log_warn "无法写入Redis配置文件，请手动应用以下配置:"
        cat /tmp/redis_optimization.conf
    fi
    
    rm -f /tmp/redis_optimization.conf
}

# 优化系统内核参数
optimize_kernel() {
    log_info "优化系统内核参数..."
    
    # 创建内核优化配置
    cat > /tmp/sysctl_optimization.conf << 'EOF'
# MetaScreener Kernel Performance Optimization

# 网络优化
net.core.somaxconn = 2048
net.core.netdev_max_backlog = 2048
net.ipv4.tcp_max_syn_backlog = 2048

# 内存优化
vm.overcommit_memory = 1
vm.swappiness = 10

# 文件系统优化
fs.file-max = 1000000
EOF

    # 应用内核参数（需要管理员权限）
    if [[ -w /etc/sysctl.conf ]]; then
        cat /tmp/sysctl_optimization.conf >> /etc/sysctl.conf
        sudo sysctl -p
        log_info "内核参数已更新"
    else
        log_warn "无法写入sysctl配置，请手动应用以下配置:"
        cat /tmp/sysctl_optimization.conf
    fi
    
    rm -f /tmp/sysctl_optimization.conf
}

# 创建性能监控脚本
create_monitoring_scripts() {
    log_info "创建性能监控脚本..."
    
    MONITOR_DIR="$PROJECT_DIR/deployment/monitoring"
    mkdir -p "$MONITOR_DIR"
    
    # 创建基础监控脚本
    cat > "$MONITOR_DIR/check_performance.sh" << 'EOF'
#!/bin/bash
# MetaScreener 性能检查脚本

echo "=========================================="
echo "MetaScreener 性能状态检查"
echo "时间: $(date)"
echo "=========================================="

echo
echo "=== Redis 状态 ==="
if command -v redis-cli &> /dev/null; then
    echo "Redis连接: $(redis-cli ping 2>/dev/null || echo 'FAILED')"
    if redis-cli ping &> /dev/null; then
        echo "Redis内存使用: $(redis-cli info memory | grep used_memory_human | cut -d: -f2)"
        echo "Redis连接数: $(redis-cli info clients | grep connected_clients | cut -d: -f2)"
    fi
else
    echo "Redis未安装"
fi

echo
echo "=== 系统资源 ==="
echo "CPU使用率: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')%"
echo "内存使用: $(free -h | grep Mem | awk '{print $3 "/" $2}')"
echo "磁盘使用: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')"

echo
echo "=== 网络连接 ==="
echo "应用端口(5000): $(ss -tuln | grep :5000 | wc -l) 个连接"

echo
echo "=== 应用进程 ==="
if pgrep -f "gunicorn.*screen_webapp" > /dev/null; then
    echo "Gunicorn状态: 运行中"
    echo "Worker进程数: $(pgrep -f "gunicorn.*screen_webapp" | wc -l)"
else
    echo "Gunicorn状态: 未运行"
fi

echo
echo "检查完成"
echo "=========================================="
EOF

    chmod +x "$MONITOR_DIR/check_performance.sh"
    
    # 创建Redis延迟测试脚本
    cat > "$MONITOR_DIR/test_redis_latency.sh" << 'EOF'
#!/bin/bash
# Redis延迟测试脚本

echo "测试Redis延迟 (按Ctrl+C停止)..."
redis-cli --latency-history -i 1
EOF

    chmod +x "$MONITOR_DIR/test_redis_latency.sh"
    
    log_info "监控脚本已创建在: $MONITOR_DIR"
}

# 优化应用配置
optimize_app_config() {
    log_info "优化应用配置..."
    
    # 检查Gunicorn配置
    GUNICORN_CONFIG="$PROJECT_DIR/deployment/gunicorn_config.py"
    if [[ -f "$GUNICORN_CONFIG" ]]; then
        log_info "检查Gunicorn配置..."
        
        # 确保超时时间足够长
        if ! grep -q "timeout = 3600" "$GUNICORN_CONFIG"; then
            log_warn "建议检查Gunicorn timeout设置"
        fi
        
        # 确保worker数量合适
        WORKER_COUNT=$(grep "workers = " "$GUNICORN_CONFIG" | head -1 | grep -o '[0-9]*' || echo "unknown")
        log_info "当前Worker数量配置: $WORKER_COUNT"
    fi
}

# 创建部署验证脚本
create_validation_script() {
    log_info "创建部署验证脚本..."
    
    cat > "$PROJECT_DIR/deployment/validate_optimization.sh" << 'EOF'
#!/bin/bash
# 优化效果验证脚本

echo "=========================================="
echo "MetaScreener 优化效果验证"
echo "=========================================="

PASSED=0
FAILED=0

# 测试函数
test_check() {
    local name="$1"
    local command="$2"
    local expected="$3"
    
    echo -n "检查 $name... "
    
    if eval "$command" &> /dev/null; then
        echo "✓ 通过"
        ((PASSED++))
    else
        echo "✗ 失败"
        ((FAILED++))
    fi
}

# Redis连接测试
test_check "Redis连接" "redis-cli ping" "PONG"

# Redis内存配置
test_check "Redis内存限制" "redis-cli config get maxmemory | grep -v '^maxmemory$' | grep -v '^0$'"

# 系统参数检查
test_check "网络连接队列" "sysctl net.core.somaxconn | grep 2048"

# 应用进程检查
test_check "应用进程运行" "pgrep -f 'gunicorn.*screen_webapp'"

# 端口监听检查
test_check "应用端口监听" "ss -tuln | grep :5000"

echo
echo "=========================================="
echo "验证结果: $PASSED 项通过, $FAILED 项失败"
echo "=========================================="

if [[ $FAILED -eq 0 ]]; then
    echo "✓ 所有检查项都已通过！"
    exit 0
else
    echo "✗ 部分检查项失败，请检查配置"
    exit 1
fi
EOF

    chmod +x "$PROJECT_DIR/deployment/validate_optimization.sh"
    log_info "验证脚本已创建: $PROJECT_DIR/deployment/validate_optimization.sh"
}

# 显示优化建议
show_recommendations() {
    log_info "性能优化建议:"
    
    echo
    echo "1. 定期监控性能:"
    echo "   ./deployment/monitoring/check_performance.sh"
    echo
    echo "2. 测试Redis延迟:"
    echo "   ./deployment/monitoring/test_redis_latency.sh"
    echo
    echo "3. 验证优化效果:"
    echo "   ./deployment/validate_optimization.sh"
    echo
    echo "4. 查看应用日志:"
    echo "   tail -f logs/gunicorn.log | grep -E '(ULTRA_QUICK|REDIS_STORAGE)'"
    echo
    echo "5. 如果遇到问题，检查备份配置:"
    echo "   ls -la deployment/config_backup_*"
    echo
}

# 主函数
main() {
    log_info "开始应用性能优化..."
    
    # 检查权限
    check_root
    
    # 备份配置
    backup_configs
    
    # 应用优化
    optimize_redis
    optimize_kernel
    optimize_app_config
    
    # 创建监控工具
    create_monitoring_scripts
    create_validation_script
    
    # 显示建议
    show_recommendations
    
    log_info "性能优化应用完成！"
    log_info "建议重启应用服务以确保所有配置生效"
    log_info "运行 ./deployment/validate_optimization.sh 验证优化效果"
}

# 运行主函数
main "$@" 