# MetaScreener 云端部署指南

## 🎯 概述

本指南将帮助您将本地的API优化更新同步到腾讯云服务器，确保生产环境能够正常运行所有新增的依赖和优化功能。

## 📋 更新内容总结

### 新增依赖包
- `openai==1.82.0` - OpenAI API客户端
- `gevent==25.5.1` - 异步网络库（版本更新）
- `celery==5.4.0` - 分布式任务队列（版本更新）
- `kombu==5.4.2` - 消息传递库（版本更新）
- `redis==6.1.0` - Redis客户端（版本更新）
- `greenlet>=3.2.2` - 轻量级协程（版本更新）
- `billiard>=4.2.1` - 多进程库（版本更新）

### 新增Celery相关依赖
- `vine>=5.1.0`
- `click-didyoumean>=0.3.0`
- `click-repl>=0.2.0`
- `click-plugins>=1.1.1`
- `prompt-toolkit>=3.0.36`
- `wcwidth>=0.2.13`
- `amqp>=5.3.1`
- `zope.event>=5.0`
- `zope.interface>=7.2`

### 新增优化文件
- `app/utils/enhanced_api_optimizer.py` - 核心优化引擎
- `app/utils/optimized_api_integration.py` - 集成包装器
- `test_enhanced_optimization_standalone.py` - 独立测试脚本
- `test_requirements.py` - 依赖测试脚本

## 🚀 部署步骤

### 步骤1: 本地准备
```bash
# 1. 确认所有依赖测试通过
python test_requirements.py

# 2. 确认应用可以正常启动
python run.py

# 3. 提交所有更改到Git
git add .
git commit -m "feat: 添加增强API优化功能和更新依赖"
git push origin main
```

### 步骤2: 云端同步
```bash
# 在腾讯云服务器上执行以下命令

# 1. 进入项目目录
cd /path/to/screen_webapp

# 2. 备份当前环境（可选但推荐）
cp requirements.txt requirements.txt.backup.$(date +%Y%m%d_%H%M%S)

# 3. 拉取最新代码
git pull origin main

# 4. 激活虚拟环境
source venv/bin/activate  # 或者您使用的虚拟环境激活命令

# 5. 更新依赖
pip install -r requirements.txt

# 6. 验证依赖安装
python test_requirements.py
```

### 步骤3: 服务重启
```bash
# 重启相关服务（根据您的部署方式调整）

# 如果使用systemd
sudo systemctl restart metascreener
sudo systemctl restart metascreener-celery  # 如果有Celery服务

# 如果使用supervisor
sudo supervisorctl restart metascreener
sudo supervisorctl restart metascreener-celery

# 如果使用Docker
docker-compose down
docker-compose up -d

# 如果直接使用gunicorn
pkill -f gunicorn
nohup gunicorn --config gunicorn.conf.py wsgi:app &
```

### 步骤4: 验证部署
```bash
# 1. 检查服务状态
curl -I http://localhost:5000/  # 或您的域名

# 2. 检查日志
tail -f logs/app.log

# 3. 运行API优化状态检查
python test_api_optimization_status.py

# 4. 测试增强优化功能
python test_enhanced_optimization_standalone.py
```

## ⚠️ 注意事项

### 依赖兼容性
- **Redis版本**: 确保云端Redis服务器版本兼容（建议6.0+）
- **Python版本**: 确保使用Python 3.10+
- **系统依赖**: 某些包可能需要系统级依赖

### 可能的问题和解决方案

#### 1. Gevent编译问题
```bash
# 如果遇到gevent编译错误，安装系统依赖
sudo apt-get update
sudo apt-get install python3-dev libevent-dev libssl-dev
pip install --upgrade gevent
```

#### 2. Redis连接问题
```bash
# 检查Redis服务状态
sudo systemctl status redis
redis-cli ping

# 如果需要配置Redis
sudo nano /etc/redis/redis.conf
sudo systemctl restart redis
```

#### 3. Celery权限问题
```bash
# 确保Celery用户有正确权限
sudo chown -R celery:celery /path/to/screen_webapp
sudo chmod +x /path/to/screen_webapp/celery_worker.py
```

#### 4. 内存不足
```bash
# 如果安装依赖时内存不足，创建swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

## 🔧 配置调整

### 生产环境配置
确保以下配置适合生产环境：

```python
# config/config.py 中的生产环境设置
PRODUCTION_CONFIG = {
    "DEBUG": False,
    "TESTING": False,
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/1",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/2"
}
```

### 性能优化配置
```python
# 根据服务器资源调整
GUNICORN_CONFIG = {
    "workers": 4,  # CPU核心数 × 2
    "worker_class": "gevent",
    "worker_connections": 1000,
    "max_requests": 1000,
    "max_requests_jitter": 100
}
```

## 📊 监控和验证

### 关键指标监控
```bash
# 1. 应用响应时间
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:5000/

# 2. 内存使用
ps aux | grep python | grep -v grep

# 3. Redis连接数
redis-cli info clients

# 4. Celery任务状态
celery -A app.celery_tasks inspect active
```

### 日志监控
```bash
# 实时监控应用日志
tail -f logs/app.log | grep -E "(ERROR|WARNING|API)"

# 监控Celery日志
tail -f logs/celery.log

# 监控系统资源
htop
```

## 🔄 回滚计划

如果部署出现问题，可以快速回滚：

```bash
# 1. 恢复旧的requirements.txt
cp requirements.txt.backup.YYYYMMDD_HHMMSS requirements.txt

# 2. 重新安装旧版本依赖
pip install -r requirements.txt

# 3. 回滚代码
git reset --hard HEAD~1  # 回滚到上一个提交

# 4. 重启服务
sudo systemctl restart metascreener
```

## ✅ 部署检查清单

### 部署前检查
- [ ] 本地测试通过 (`python test_requirements.py`)
- [ ] 应用可以正常启动 (`python run.py`)
- [ ] 代码已提交到Git仓库
- [ ] 备份了生产环境配置

### 部署中检查
- [ ] 代码成功拉取
- [ ] 依赖安装无错误
- [ ] 依赖测试通过
- [ ] 服务成功重启

### 部署后检查
- [ ] 应用可以正常访问
- [ ] API优化功能正常
- [ ] 日志无严重错误
- [ ] 性能指标正常

## 📞 故障排除

### 常见错误和解决方案

#### ImportError: No module named 'xxx'
```bash
# 重新安装依赖
pip install --force-reinstall -r requirements.txt
```

#### Redis连接失败
```bash
# 检查Redis配置和状态
redis-cli ping
sudo systemctl status redis
```

#### Celery任务失败
```bash
# 重启Celery worker
sudo systemctl restart metascreener-celery
celery -A app.celery_tasks purge  # 清理任务队列
```

#### 内存不足
```bash
# 增加swap空间或升级服务器配置
free -h
sudo swapon --show
```

## 🎉 部署完成

部署成功后，您的MetaScreener应用将具备：

- ✅ **增强的API优化功能** - 熔断器、自适应速率限制、负载均衡等
- ✅ **更新的依赖包** - 所有必要的依赖都已正确安装
- ✅ **向后兼容性** - 现有功能完全保持不变
- ✅ **生产就绪** - 经过全面测试，可以安全运行

**恭喜！您的MetaScreener应用现在已经完全优化并部署到云端！** 🚀

---

**技术支持**: 如果在部署过程中遇到任何问题，请检查日志文件并参考本指南的故障排除部分。 