#!/bin/bash
# MANHHH 数据分析一键运行脚本

echo "=========================================="
echo "  MANHHH 项目数据分析系统"
echo "=========================================="
echo ""

cd "$(dirname "$0")"

# 激活虚拟环境
source ../../venv/bin/activate

# 运行分析
echo "🚀 开始数据分析..."
python analyze.py

if [ $? -eq 0 ]; then
    echo ""
    echo "📝 生成 HTML 报告..."
    python generate_html_report.py
    
    echo ""
    echo "📦 打包分析结果..."
    ./package_results.sh
    
    echo ""
    echo "=========================================="
    echo "  ✅ 分析完成！"
    echo "=========================================="
    echo ""
    echo "📁 输出目录: $(pwd)/output/"
    echo ""
    echo "📊 生成的文件："
    echo "   - analysis_report.txt    (文本报告)"
    echo "   - analysis_report.html   (HTML可视化报告)"
    echo "   - analysis_data.json     (原始JSON数据)"
    echo "   - questions_wordcloud.png (用户提问词云)"
    echo "   - user_growth.png        (用户增长趋势)"
    echo "   - chat_activity.png      (聊天活跃度)"
    echo "   - tool_usage.png         (工具使用统计)"
    echo ""
    echo "💡 提示："
    echo "   - 在浏览器中打开 analysis_report.html 查看完整报告"
    echo "   - 使用最新的 .zip 文件下载所有结果"
    echo ""
else
    echo ""
    echo "❌ 分析失败，请查看错误信息"
    exit 1
fi

