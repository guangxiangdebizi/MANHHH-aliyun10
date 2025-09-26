// markdown-renderer.js - Markdown渲染模块
class MarkdownRenderer {
    constructor() {
        this.escapeHtml = this.escapeHtml.bind(this);
    }

    // 实时markdown渲染方法
    renderMarkdownContent(content, isFinal = false) {
        if (typeof marked === 'undefined') {
            // 如果marked.js未加载，使用原始文本显示
            return this.escapeHtml(content);
        }
        
        try {
            let renderedContent = '';
            
            if (isFinal) {
                // 最终渲染，直接处理所有内容
                renderedContent = marked.parse(content);
            } else {
                // 实时渲染，需要智能处理不完整的markdown
                renderedContent = this.renderPartialMarkdown(content);
            }
            
            return renderedContent;
                
        } catch (error) {
            console.warn('Markdown渲染错误:', error);
            // 出错时使用原始文本
            return this.escapeHtml(content);
        }
    }
    
    // 渲染部分markdown内容（处理不完整的语法）
    renderPartialMarkdown(content) {
        // 检测可能不完整的markdown模式
        const patterns = [
            { regex: /```[\s\S]*?```/g, type: 'codeblock' },  // 代码块
            { regex: /`[^`\n]*`/g, type: 'code' },            // 行内代码
            { regex: /\*\*[^*\n]*\*\*/g, type: 'bold' },      // 粗体
            { regex: /\*[^*\n]*\*/g, type: 'italic' },        // 斜体
            { regex: /^#{1,6}\s+.*/gm, type: 'heading' },     // 标题
            { regex: /^\*.+$/gm, type: 'list' },              // 列表
            { regex: /^\d+\..+$/gm, type: 'orderedlist' },    // 有序列表
            { regex: /^>.+$/gm, type: 'quote' }               // 引用
        ];
        
        let lastCompletePos = 0;
        
        // 找到最后一个完整的markdown元素位置
        for (let pattern of patterns) {
            const matches = [...content.matchAll(pattern.regex)];
            for (let match of matches) {
                const endPos = match.index + match[0].length;
                if (this.isCompleteMarkdown(match[0], pattern.type)) {
                    lastCompletePos = Math.max(lastCompletePos, endPos);
                }
            }
        }
        
        if (lastCompletePos > 0) {
            // 分割内容：完整部分用markdown渲染，不完整部分用原始文本
            const completeContent = content.substring(0, lastCompletePos);
            const incompleteContent = content.substring(lastCompletePos);
            
            const renderedComplete = marked.parse(completeContent);
            const escapedIncomplete = this.escapeHtml(incompleteContent);
            
            return renderedComplete + escapedIncomplete;
        } else {
            // 没有完整的markdown，使用原始文本
            return this.escapeHtml(content);
        }
    }
    
    // 检查markdown元素是否完整
    isCompleteMarkdown(text, type) {
        switch (type) {
            case 'codeblock':
                return text.startsWith('```') && text.endsWith('```') && text.length > 6;
            case 'code':
                return text.startsWith('`') && text.endsWith('`') && text.length > 2;
            case 'bold':
                return text.startsWith('**') && text.endsWith('**') && text.length > 4;
            case 'italic':
                return text.startsWith('*') && text.endsWith('*') && text.length > 2 && !text.startsWith('**');
            case 'heading':
                return text.match(/^#{1,6}\s+.+$/);
            case 'list':
                return text.match(/^\*\s+.+$/);
            case 'orderedlist':
                return text.match(/^\d+\.\s+.+$/);
            case 'quote':
                return text.match(/^>\s*.+$/);
            default:
                return true;
        }
    }

    // Post-process container: render Mermaid diagrams and add copy buttons for code blocks
    afterRender(containerEl, isFinal = true) {
        try {
            if (!containerEl || !isFinal) return;

            // Convert <pre><code class="language-mermaid">...</code></pre> to <div class="mermaid">...</div>
            const codeBlocks = containerEl.querySelectorAll('pre > code.language-mermaid');
            codeBlocks.forEach(codeEl => {
                try {
                    const pre = codeEl.parentElement;
                    if (!pre) return;
                    const wrapper = document.createElement('div');
                    wrapper.className = 'mermaid';
                    wrapper.textContent = codeEl.textContent || '';
                    pre.replaceWith(wrapper);
                } catch {}
            });

            // Convert <pre><code class="language-echarts|language-echart">...</code></pre> to ECharts div
            const echartsBlocks = containerEl.querySelectorAll("pre > code[class*='language-echart']");
            echartsBlocks.forEach(codeEl => {
                try {
                    const pre = codeEl.parentElement;
                    if (!pre) return;

                    const raw = codeEl.textContent || '';
                    let option;
                    try {
                        option = JSON.parse(raw);
                    } catch (_e) {
                        // 兼容宽松写法：去注释、替换智能引号、去尾逗号、将单引号替换为双引号
                        const sanitized = (raw || '')
                          .replace(/\/\/.*$/gm, '')
                          .replace(/\/\*[\s\S]*?\*\//g, '')
                          .replace(/[“”]/g, '"').replace(/[‘’]/g, '\'')
                          .replace(/'([^'\\\n]+)'\s*:/g, '"$1":')
                          .replace(/:\s*'([^'\\\n]*)'/g, ': "$1"')
                          .replace(/,\s*([}\]])/g, '$1');
                        option = JSON.parse(sanitized);
                    }
                    // 支持 { option: {...} } 或直接 {...}
                    if (option && option.option && typeof option.option === 'object') {
                        option = option.option;
                    }

                    // 容器
                    const wrapper = document.createElement('div');
                    wrapper.className = 'chart-container';
                    wrapper.style.position = 'relative';
                    wrapper.style.maxWidth = '100%';
                    wrapper.style.maxHeight = '400px';
                    const chartDiv = document.createElement('div');
                    chartDiv.style.width = '100%';
                    chartDiv.style.height = '100%';
                    wrapper.appendChild(chartDiv);
                    pre.replaceWith(wrapper);

                    // 渲染 ECharts
                    if (window.echarts && typeof echarts.init === 'function') {
                        let chart;
                        try {
                            chart = echarts.init(chartDiv);
                        } catch (e) {
                            console.warn('ECharts init failed:', e);
                            return;
                        }
                        try {
                            chart.setOption(option || {});
                        } catch (e) {
                            console.warn('ECharts setOption failed:', e);
                            return;
                        }
                        setTimeout(() => { try { chart.resize(); } catch(_){} }, 0);
                        try {
                            if (window.ResizeObserver) {
                                const ro = new ResizeObserver(() => { try { chart.resize(); } catch(_){} });
                                ro.observe(wrapper);
                            } else {
                                window.addEventListener('resize', () => { try { chart.resize(); } catch(_){} });
                            }
                        } catch(_){ }
                    } else {
                        const warn = document.createElement('div');
                        warn.style.padding = '8px';
                        warn.style.color = '#b45309';
                        warn.style.background = '#fffbeb';
                        warn.style.border = '1px solid #fcd34d';
                        warn.style.borderRadius = '6px';
                        warn.textContent = 'ECharts 脚本未加载，无法渲染图表。请检查网络或CDN。';
                        wrapper.innerHTML = '';
                        wrapper.appendChild(warn);
                    }
                } catch (e) {
                    console.warn('ECharts render failed:', e);
                }
            });

            // Convert <pre><code class="language-chartjs">...</code></pre> (and language-chart) to Chart.js canvas
            const chartBlocks = containerEl.querySelectorAll("pre > code[class*='language-chart']");
            chartBlocks.forEach(codeEl => {
                try {
                    const pre = codeEl.parentElement;
                    if (!pre) return;
                    
                    const raw = codeEl.textContent || '';
                    let chartData;
                    try {
                        chartData = JSON.parse(raw);
                    } catch (_e) {
                        // 兼容宽松写法：去注释、替换智能引号、去尾逗号、将单引号替换为双引号
                        const sanitized = (raw || '')
                          // 去除 // 和 /* */ 注释
                          .replace(/\/\/.*$/gm, '')
                          .replace(/\/\*[\s\S]*?\*\//g, '')
                          // 智能引号 -> 普通引号
                          .replace(/[“”]/g, '"').replace(/[‘’]/g, '\'')
                          // 对键名的单引号 -> 双引号
                          .replace(/'([^'\\\n]+)'\s*:/g, '"$1":')
                          // 值的单引号 -> 双引号（粗略处理）
                          .replace(/:\s*'([^'\\\n]*)'/g, ': "$1"')
                          // 去掉对象/数组尾部逗号
                          .replace(/,\s*([}\]])/g, '$1');
                        chartData = JSON.parse(sanitized);
                    }
                    const canvas = document.createElement('canvas');
                    // 关闭Chart.js的全局动画尺寸调整，避免hover时触发父容器重排
                    if (!chartData.options) chartData.options = {};
                    chartData.options.maintainAspectRatio = false;
                    if (!chartData.options.animation) chartData.options.animation = {};
                    if (chartData.options.animation.resize === undefined) chartData.options.animation.resize = false;

                    // 对金融K线数据增加通用解析配置（x、o/h/l/c）
                    try {
                        if (/^(candlestick|ohlc)$/i.test(String(chartData.type))) {
                            chartData.data = chartData.data || {};
                            const datasets = chartData.data.datasets || [];
                            for (let i = 0; i < datasets.length; i++) {
                                const ds = datasets[i] || {};
                                ds.parsing = ds.parsing || {};
                                if (ds.parsing.xAxisKey === undefined) ds.parsing.xAxisKey = 'x';
                                if (ds.parsing.yAxisKey === undefined) ds.parsing.yAxisKey = undefined; // not used
                                if (ds.parsing.openKey === undefined) ds.parsing.openKey = 'o';
                                if (ds.parsing.highKey === undefined) ds.parsing.highKey = 'h';
                                if (ds.parsing.lowKey === undefined) ds.parsing.lowKey = 'l';
                                if (ds.parsing.closeKey === undefined) ds.parsing.closeKey = 'c';
                            }
                            // 若x是类似“09-05”，给出刻度解析：按category显示
                            chartData.options = chartData.options || {};
                            chartData.options.scales = chartData.options.scales || {};
                            const x = chartData.options.scales.x = chartData.options.scales.x || {};
                            x.type = x.type || 'category';
                        }
                    } catch(_){}
                    
                    const wrapper = document.createElement('div');
                    wrapper.className = 'chart-container';
                    wrapper.style.position = 'relative';
                    wrapper.style.maxWidth = '100%';
                    wrapper.style.maxHeight = '400px';
                    wrapper.appendChild(canvas);
                    
                    pre.replaceWith(wrapper);
                    
                    // Render Chart.js
                    if (window.Chart) {
                        // 若是金融K线/ohlc，确保已注册金融图表元素；若未加载插件则提示
                        const isFinancial = chartData && chartData.type && /^(candlestick|ohlc)$/i.test(String(chartData.type));
                        if (isFinancial) {
                            let pluginRegistered = false;
                            try {
                                // Chart.js v4 正确注册方式
                                if (typeof Chart.register === 'function') {
                                    const candidates = [
                                        Chart.FinancialController,
                                        Chart.CandlestickController,
                                        Chart.OhlcController,
                                        Chart.CandlestickElement,
                                        Chart.OhlcElement,
                                    ].filter(Boolean);
                                    if (candidates.length) {
                                        Chart.register(...candidates);
                                        pluginRegistered = true;
                                    }
                                }
                            } catch(_) {}

                            if (!pluginRegistered) {
                                // 插件脚本可能未加载到，给出友好提示
                                if (!document.querySelector('script[src*="chartjs-chart-financial"]')) {
                                    const warn = document.createElement('div');
                                    warn.style.padding = '8px';
                                    warn.style.color = '#b45309';
                                    warn.style.background = '#fffbeb';
                                    warn.style.border = '1px solid #fcd34d';
                                    warn.style.borderRadius = '6px';
                                    warn.textContent = 'K线图渲染需要 chartjs-chart-financial 插件，CDN未加载到或被拦截。';
                                    wrapper.innerHTML = '';
                                    wrapper.appendChild(warn);
                                    return;
                                }
                            }
                        }

                        const ctx = canvas.getContext('2d');
                        let chart;
                        try {
                            chart = new Chart(ctx, chartData);
                        } catch (err) {
                            // 若因未注册控制器失败，最后再尝试一次注册后重试
                            try {
                                if (typeof Chart.register === 'function') {
                                    const candidates = [
                                        Chart.FinancialController,
                                        Chart.CandlestickController,
                                        Chart.OhlcController,
                                        Chart.CandlestickElement,
                                        Chart.OhlcElement,
                                    ].filter(Boolean);
                                    if (candidates.length) Chart.register(...candidates);
                                }
                                chart = new Chart(ctx, chartData);
                            } catch (err2) {
                                console.warn('Chart.js create failed:', err2);
                                return;
                            }
                        }
                        // 处理图表在隐藏容器中首次渲染尺寸不正确的问题
                        // 若父元素后来可见，触发一次resize
                        setTimeout(() => { try { chart.resize(); } catch(_){} }, 0);
                    }
                } catch (e) {
                    console.warn('Chart.js render failed:', e);
                    // Keep original code block if parsing fails
                }
            });

            // Run Mermaid on newly created diagrams in this container only
            if (window.mermaid) {
                const targets = containerEl.querySelectorAll('.mermaid');
                if (targets && targets.length) {
                    try {
                        if (typeof mermaid.run === 'function') {
                            mermaid.run({ nodes: targets });
                        } else if (typeof mermaid.init === 'function') {
                            mermaid.init(undefined, targets);
                        }
                    } catch (e) {
                        console.warn('Mermaid render failed:', e);
                    }
                }
            }

            // Add code toolbar with per-block copy buttons
            const codeNodes = containerEl.querySelectorAll('pre > code');
            codeNodes.forEach(codeEl => {
                try {
                    if (codeEl.classList.contains('language-mermaid')) return; // already handled
                    if (/\blanguage-chart/i.test(codeEl.className)) return; // chart/chartjs handled
                    if (/\blanguage-echart/i.test(codeEl.className)) return; // echarts handled
                    const pre = codeEl.parentElement;
                    if (!pre || pre.getAttribute('data-has-toolbar') === '1') return;

                    // Wrap with container
                    const wrapper = document.createElement('div');
                    wrapper.className = 'code-block';
                    const toolbar = document.createElement('div');
                    toolbar.className = 'code-toolbar';
                    const label = document.createElement('span');
                    label.className = 'code-lang';
                    const m = (codeEl.className || '').match(/language-([a-zA-Z0-9+#.-]+)/);
                    label.textContent = (m && m[1]) ? m[1] : 'code';
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'code-copy-btn';
                    btn.textContent = '复制';
                    toolbar.appendChild(label);
                    toolbar.appendChild(btn);

                    pre.setAttribute('data-has-toolbar', '1');

                    const parent = pre.parentElement;
                    if (!parent) return;
                    parent.insertBefore(wrapper, pre);
                    wrapper.appendChild(toolbar);
                    wrapper.appendChild(pre);

                    btn.addEventListener('click', async (e) => {
                        e.stopPropagation();
                        const raw = codeEl.innerText || codeEl.textContent || '';
                        try {
                            if (navigator.clipboard && window.isSecureContext) {
                                await navigator.clipboard.writeText(raw);
                            } else {
                                const ta = document.createElement('textarea');
                                ta.value = raw;
                                document.body.appendChild(ta);
                                ta.select();
                                document.execCommand('copy');
                                document.body.removeChild(ta);
                            }
                            const old = btn.textContent;
                            btn.textContent = '已复制';
                            setTimeout(() => { btn.textContent = old; }, 1200);
                        } catch (err) {
                            console.warn('复制代码失败', err);
                        }
                    });
                } catch {}
            });
        } catch (e) {
            console.warn('afterRender failed', e);
        }
    }

    // HTML转义
    escapeHtml(text) {
        if (text === null || text === undefined) {
            return '';
        }
        return text.toString()
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#039;");
    }
}
