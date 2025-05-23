# Screen WebApp 生产环境部署指南

## 🎯 概述

本指南将指导您在腾讯云（4 GPUs, 16GB RAM）上部署优化的Screen WebApp，包含Celery+Redis异步任务处理和gunicorn+gevent高并发配置。

## 📋 系统要求

- **操作系统**: Ubuntu 20.04+ / CentOS 8+ 
- **内存**: 16GB RAM
- **CPU**: 多核心处理器（推荐8核心+）
- **存储**: 100GB+ SSD
- **网络**: 稳定的互联网连接

## 🛠️ 部署步骤

### 1. 系统准备

#### 更新系统
```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS/RHEL
sudo yum update -y
```

#### 安装必要软件
```bash
# Ubuntu/Debian
sudo apt install -y python3 python3-pip python3-venv git redis-server nginx supervisor

# CentOS/RHEL
sudo yum install -y python3 python3-pip git redis nginx supervisor
sudo systemctl enable redis nginx supervisor
```

### 2. 克隆项目并设置虚拟环境

```bash
# 克隆项目（请替换为您的实际仓库地址）
cd /opt
sudo git clone YOUR_GITHUB_REPO_URL screen_webapp
sudo chown -R $USER:$USER /opt/screen_webapp
cd /opt/screen_webapp

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Redis配置

#### 备份原配置并使用优化配置
```bash
sudo cp /etc/redis/redis.conf /etc/redis/redis.conf.backup
sudo cp redis.conf.example /etc/redis/redis.conf
sudo chown redis:redis /etc/redis/redis.conf
sudo chmod 640 /etc/redis/redis.conf

# 启动Redis服务
sudo systemctl start redis-server
sudo systemctl enable redis-server
sudo systemctl status redis-server

# 验证Redis连接
redis-cli ping  # 应该返回: PONG
```

### 4. 环境变量配置

```bash
# 复制示例配置
cp env.example .env

# 编辑配置文件（请根据实际情况修改）
nano .env
```

必须修改的关键配置项：
```
FLASK_SECRET_KEY=your_very_strong_secret_key_here
FLASK_ENV=production
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

更多配置详情请参考完整的DEPLOYMENT文档。 