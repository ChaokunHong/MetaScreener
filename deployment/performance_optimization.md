# MetaScreener 云端性能优化指南

## 问题描述
本地运行时文件上传跳转快速，云端部署后上传文件需要较长时间才能跳转到进度页面。

## 解决方案总结

### 1. 核心优化 - Ultra-Fast Upload Mode
- **原理**: 将文件内容先读取到内存，立即生成batch_id并跳转，后台异步处理文件保存和处理
- **改进**: 消除阻塞的磁盘I/O操作，减少Redis往返次数
- **效果**: 跳转时间从3-10秒降低到0.5-1秒

### 2. Redis性能优化
- **Pipeline操作**: 使用Redis pipeline减少网络往返
- **批量操作**: 支持批量读写操作
- **连接池**: 复用Redis连接，减少连接开销

### 3. 前端体验优化
- **新状态支持**: 添加"uploading"状态显示
- **自动刷新**: 检测状态变化并自动更新页面
- **实时反馈**: 提供更详细的进度信息

## 部署建议

### 腾讯云服务器配置建议

#### 1. Redis优化
```bash
# 修改Redis配置 /etc/redis/redis.conf
# 内存优化
maxmemory 2gb
maxmemory-policy allkeys-lru

# 网络优化
tcp-keepalive 300
timeout 0

# 持久化优化（根据数据重要性）
save 900 1
save 300 10
save 60 10000
```

#### 2. 系统内核参数优化
```bash
# 编辑 /etc/sysctl.conf
# 网络优化
net.core.somaxconn = 2048
net.core.netdev_max_backlog = 2048
net.ipv4.tcp_max_syn_backlog = 2048

# 内存优化
vm.overcommit_memory = 1
vm.swappiness = 10

# 应用配置
sysctl -p
```

#### 3. Nginx优化（如果使用）
```nginx
# 在nginx.conf中添加
client_max_body_size 100M;
client_body_timeout 300;
client_header_timeout 300;
send_timeout 300;

# 启用gzip压缩
gzip on;
gzip_types text/plain text/css application/json application/javascript;
```

### 监控和排查

#### 1. 性能监控脚本
```bash
#!/bin/bash
# monitor_performance.sh
echo "=== Redis 连接测试 ==="
redis-cli ping

echo "=== Redis 内存使用 ==="
redis-cli info memory | grep used_memory_human

echo "=== 系统负载 ==="
uptime

echo "=== 磁盘I/O ==="
iostat -x 1 3

echo "=== 网络连接 ==="
ss -tuln | grep :5000
```

#### 2. 应用日志监控
```bash
# 查看关键日志
tail -f logs/gunicorn.log | grep -E "(ULTRA_QUICK|REDIS_STORAGE|ERROR)"

# 查看Redis操作延迟
tail -f logs/app.log | grep "REDIS_STORAGE.*ms"
```

### 性能基准

#### 本地环境基准
- 文件上传响应时间: < 0.5秒
- Redis操作延迟: < 10ms
- 页面跳转时间: < 0.3秒

#### 云端环境目标
- 文件上传响应时间: < 1.5秒
- Redis操作延迟: < 50ms
- 页面跳转时间: < 1秒

#### 性能测试命令
```bash
# 测试Redis延迟
redis-cli --latency-history -i 1

# 测试文件上传
time curl -X POST -F "pdf_files=@test.pdf" \
  -F "upload_mode=quick" \
  http://your-server:5000/quality_assessment/upload

# 测试页面响应
curl -w "@curl-format.txt" -s -o /dev/null \
  http://your-server:5000/quality_assessment/upload
```

## 故障排除

### 常见问题及解决方案

#### 1. 上传仍然很慢
- 检查磁盘空间: `df -h`
- 检查磁盘I/O: `iostat -x 1 5`
- 检查Redis连接: `redis-cli ping`

#### 2. Redis连接失败
- 检查Redis服务: `systemctl status redis`
- 检查Redis配置: `redis-cli config get "*"`
- 检查网络连接: `telnet localhost 6379`

#### 3. 内存不足
- 检查内存使用: `free -h`
- 检查进程内存: `ps aux --sort=-%mem | head`
- 调整Gunicorn worker数量

### 回滚方案
如果新的优化导致问题，可以快速回滚：

```bash
# 停止服务
sudo systemctl stop screen_webapp

# 切换到之前的代码版本
git checkout previous-stable-tag

# 重启服务
sudo systemctl start screen_webapp
```

## 监控指标

### 关键指标监控
1. **上传响应时间**: 目标 < 1.5秒
2. **Redis延迟**: 目标 < 50ms
3. **CPU使用率**: 目标 < 80%
4. **内存使用率**: 目标 < 80%
5. **磁盘I/O**: 目标 < 80%

### 自动化监控脚本
```bash
#!/bin/bash
# performance_alert.sh
REDIS_LATENCY=$(redis-cli --latency -i 1 -c 1 | tail -1 | awk '{print $NF}')
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')

if (( $(echo "$REDIS_LATENCY > 50" | bc -l) )); then
    echo "ALERT: Redis latency high: ${REDIS_LATENCY}ms"
fi

if (( $(echo "$CPU_USAGE > 80" | bc -l) )); then
    echo "ALERT: CPU usage high: ${CPU_USAGE}%"
fi

if (( $(echo "$MEMORY_USAGE > 80" | bc -l) )); then
    echo "ALERT: Memory usage high: ${MEMORY_USAGE}%"
fi
``` 