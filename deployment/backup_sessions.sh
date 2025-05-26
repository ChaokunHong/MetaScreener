#!/bin/bash

# 会话数据备份脚本
# 每天运行一次，备份重要的会话数据

BACKUP_DIR="/home/ubuntu/MetaScreener/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# 创建备份目录
mkdir -p "$BACKUP_DIR"

echo "开始备份会话数据..."

# 备份Redis数据
redis-cli --rdb "$BACKUP_DIR/redis_backup_$DATE.rdb"

# 导出会话键
redis-cli keys "full_screening:*" > "$BACKUP_DIR/session_keys_$DATE.txt"
redis-cli keys "pdf_batch_results:*" > "$BACKUP_DIR/batch_keys_$DATE.txt"

# 清理7天前的备份
find "$BACKUP_DIR" -name "*.rdb" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.txt" -mtime +7 -delete

echo "备份完成: $BACKUP_DIR" 