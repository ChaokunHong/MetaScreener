#!/bin/bash
# MetaScreener 端到端演示脚本
# 使用前设置: export OPENROUTER_API_KEY="sk-or-v1-你的key"
set -e

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DEMO_DIR/.."

echo "============================================"
echo "  MetaScreener 端到端演示"
echo "============================================"

# 检查 API key
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "错误: 请先设置 OPENROUTER_API_KEY"
    echo "  export OPENROUTER_API_KEY='sk-or-v1-你的key'"
    echo ""
    echo "获取方式: https://openrouter.ai/settings/keys"
    exit 1
fi
echo "✓ API key 已设置"
echo ""

# ============================================
# 测试 1: 从文本生成 PICO 标准 (init --criteria)
# ============================================
echo "--- 测试 1: 生成筛选标准 ---"
echo "输入: demo/criteria.txt"
echo "这会调用 4 个 LLM 模型生成结构化的 criteria.yaml"
echo ""
uv run metascreener init --criteria demo/criteria.txt --output demo/criteria.yaml
echo ""
echo "✓ 标准已保存到 demo/criteria.yaml"
echo ""
cat demo/criteria.yaml
echo ""

# ============================================
# 测试 2: 从主题生成标准 (init --topic)
# ============================================
echo "--- 测试 2: 从主题生成标准 ---"
uv run metascreener init --topic "antimicrobial resistance in ICU patients" --output demo/criteria_from_topic.yaml
echo ""
echo "✓ 标准已保存到 demo/criteria_from_topic.yaml"
echo ""

# ============================================
# 测试 3: Title/Abstract 筛选 (screen)
# ============================================
echo "--- 测试 3: Title/Abstract 筛选 ---"
echo "输入: 5 篇论文 (2 相关, 1 蛋白质, 1 社论, 1 儿科)"
echo "期望: 2 INCLUDE, 2-3 EXCLUDE, 0-1 HUMAN_REVIEW"
echo ""
uv run metascreener screen \
    --input demo/test_papers.ris \
    --criteria demo/criteria.yaml \
    --output demo/results \
    --stage ta \
    --seed 42
echo ""
echo "✓ 筛选结果: demo/results/screening_results.json"
echo "✓ 审计记录: demo/results/audit_trail.json"
echo ""

# 显示结果摘要
echo "--- 筛选结果摘要 ---"
python3 -c "
import json
with open('demo/results/screening_results.json') as f:
    results = json.load(f)
for r in results:
    print(f\"  {r.get('record_id', 'N/A')[:8]}  {r['decision']:13s}  tier={r['tier']}  score={r.get('final_score', 'N/A'):.3f}  conf={r.get('ensemble_confidence', 'N/A'):.3f}\")
"
echo ""

# ============================================
# 测试 4: 导出结果
# ============================================
echo "--- 测试 4: 导出结果 ---"
uv run metascreener export \
    --results demo/results/screening_results.json \
    --format csv,json
echo ""
echo "✓ 导出完成"
echo ""

echo "============================================"
echo "  所有测试完成!"
echo "============================================"
echo ""
echo "生成的文件:"
ls -la demo/criteria*.yaml demo/results/ 2>/dev/null || true
