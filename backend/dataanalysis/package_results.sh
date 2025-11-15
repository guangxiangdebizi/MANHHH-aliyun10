#!/bin/bash
# 打包数据分析结果

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="MANHHH_分析报告_${TIMESTAMP}.zip"

cd "$(dirname "$0")"

echo "📦 正在打包分析结果..."
zip -r "$OUTPUT_FILE" output/ README.md

echo "✅ 打包完成: $OUTPUT_FILE"
echo "📊 文件大小: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "📥 下载方式："
echo "   scp ec2-user@your-server:/home/ec2-user/AIWebHere/MANHHH-aliyun10/backend/dataanalysis/$OUTPUT_FILE ."
echo ""
echo "   或直接访问："
echo "   /home/ec2-user/AIWebHere/MANHHH-aliyun10/backend/dataanalysis/$OUTPUT_FILE"

