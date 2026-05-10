// Colors mapping
const styleGuide = {
    colors: {
        'Prerequisite': '#ef4444',
        'Parallel': '#eab308',
        'Inclusion': '#10b981',
        'Application': '#a855f7',
        'merged': '#fb7185',
        '01': '#38bdf8', // 局解
        '03': '#fb923c', // 生理
        '05': '#c084fc', // 病理
        '07': '#facc15'  // 病生
    }
};

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Cytoscape
    const cy = cytoscape({
        container: document.getElementById('cy'),
        elements: mockElements,
        style: [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'width': 'data(size)',
                    'height': 'data(size)',
                    'background-color': (ele) => {
                        const type = ele.data('type');
                        const source = ele.data('source');
                        if(type === 'merged') return styleGuide.colors['merged'];
                        return styleGuide.colors[source] || '#94a3b8';
                    },
                    'color': '#f8fafc',
                    'font-size': '12px',
                    'font-family': 'Inter',
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'text-outline-width': 2,
                    'text-outline-color': '#0f172a',
                    'border-width': 2,
                    'border-color': 'rgba(255,255,255,0.5)',
                    'shadow-blur': 15,
                    'shadow-color': (ele) => {
                        const type = ele.data('type');
                        return type === 'merged' ? styleGuide.colors['merged'] : '#000';
                    },
                    'shadow-opacity': 0.8
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 3,
                    'line-color': (ele) => styleGuide.colors[ele.data('type')] || '#64748b',
                    'target-arrow-color': (ele) => styleGuide.colors[ele.data('type')] || '#64748b',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'label': 'data(label)',
                    'font-size': '10px',
                    'color': '#cbd5e1',
                    'text-background-opacity': 1,
                    'text-background-color': '#0f172a',
                    'text-background-padding': '3px',
                    'text-background-shape': 'roundrectangle',
                    'edge-text-rotation': 'autorotate'
                }
            },
            {
                selector: ':selected',
                style: {
                    'border-width': 4,
                    'border-color': '#fff',
                    'shadow-blur': 20,
                    'shadow-color': '#fff'
                }
            }
        ],
        layout: {
            name: 'cose',
            animate: true,
            nodeRepulsion: 400000,
            idealEdgeLength: 100,
            edgeElasticity: 100
        }
    });

    // Update Stats
    document.getElementById('stat-nodes').innerText = cy.nodes().length;
    document.getElementById('stat-edges').innerText = cy.edges().length;

    // Node Click Event -> Show Details
    const detailPanel = document.getElementById('detail-panel');
    const nodeInfo = document.getElementById('node-info');
    
    cy.on('tap', 'node', function(evt){
        const node = evt.target;
        const data = node.data();
        
        // Hide context menu if open
        hideContextMenu();
        
        detailPanel.classList.remove('hidden');
        
        let tagsHtml = '';
        if(data.type === 'merged') {
            tagsHtml = `<span class="badge" style="background:#fb7185;color:#fff">融合节点</span>`;
        } else {
            tagsHtml = `<span class="badge" style="background:#475569;color:#fff">单一来源 (${data.source})</span>`;
        }
        
        nodeInfo.innerHTML = `
            <div class="node-title">${data.label}</div>
            <div class="node-meta">${tagsHtml}</div>
            <div class="reasoning-box">
                <div class="reasoning-title"><i class="fa-solid fa-brain"></i> AI 整合决策</div>
                <div class="reasoning-text">${data.reasoning}</div>
            </div>
            <div class="essence-text">
                <strong>精华提纯内容：</strong><br/>
                ${data.essence}
            </div>
        `;
        
        // Center the graph on the node
        cy.animate({
            center: { eles: node },
            zoom: 1.5
        }, { duration: 500 });
    });

    // Deselect
    cy.on('tap', function(event){
        if(event.target === cy){
            detailPanel.classList.add('hidden');
            hideContextMenu();
        }
    });

    // Layout Controls
    document.getElementById('btn-layout-cose').addEventListener('click', () => {
        cy.layout({ name: 'cose', animate: true, nodeRepulsion: 400000 }).run();
    });
    
    document.getElementById('btn-layout-dagre').addEventListener('click', () => {
        cy.layout({ name: 'dagre', animate: true, nodeSep: 50, rankSep: 100, rankDir: 'TB' }).run();
    });
    
    document.getElementById('btn-layout-circle').addEventListener('click', () => {
        cy.layout({ name: 'circle', animate: true }).run();
    });
    
    document.getElementById('btn-reset').addEventListener('click', () => {
        cy.fit();
    });

    // Filter Controls
    const filters = document.querySelectorAll('.rel-filter');
    filters.forEach(filter => {
        filter.addEventListener('change', (e) => {
            const type = e.target.value;
            const checked = e.target.checked;
            if(checked) {
                cy.edges(`[type = "${type}"]`).restore();
            } else {
                cy.edges(`[type = "${type}"]`).remove();
            }
        });
    });

    // Context Menu (Teacher Loop Demo)
    const contextMenu = document.getElementById('context-menu');
    let contextNode = null;

    cy.on('cxttap', 'node', function(event){
        const node = event.target;
        contextNode = node;
        const pos = event.originalEvent;
        
        contextMenu.style.left = pos.clientX + 'px';
        contextMenu.style.top = pos.clientY + 'px';
        contextMenu.classList.remove('hidden');
    });

    function hideContextMenu() {
        contextMenu.classList.add('hidden');
        contextNode = null;
    }

    // Context Menu Actions
    document.getElementById('ctx-feedback').addEventListener('click', () => {
        if(contextNode) {
            const feedback = prompt(`请对节点 "${contextNode.data('label')}" 输入教学反馈 (模拟 Teacher Loop)：`);
            if(feedback) {
                alert(`收到反馈："${feedback}"。\nKIA 将根据您的反馈重新运行该节点的提纯算法并更新知识图谱。`);
            }
        }
        hideContextMenu();
    });
    
    document.getElementById('ctx-expand').addEventListener('click', () => {
        alert('展开下级节点功能 (动态加载 RAG 数据库中相关的子节点)...');
        hideContextMenu();
    });

    document.getElementById('ctx-remove').addEventListener('click', () => {
        if(contextNode && confirm(`确定要向智能体建议剔除节点 "${contextNode.data('label')}" 吗？这会影响压缩率计算。`)) {
            cy.remove(contextNode);
            // Update stats
            document.getElementById('stat-nodes').innerText = cy.nodes().length;
            document.getElementById('stat-edges').innerText = cy.edges().length;
        }
        hideContextMenu();
    });
});
