"use client";

import React, { useRef, useEffect, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { colorMap } from '@/lib/agentData';
import { LayoutGrid, Grid3X3, ArrowDownUp } from 'lucide-react';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

interface ContextMenu {
  x: number;
  y: number;
  node: any;
}

function drawHexagon(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 6;
    const px = x + r * Math.cos(angle);
    const py = y + r * Math.sin(angle);
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  }
  ctx.closePath();
}

export default function GraphCanvas({ data, onNodeClick, onBgClick, onNodeFeedback, onNodeExpand }: {
  data: any,
  onNodeClick: (node: any) => void,
  onBgClick: () => void,
  onNodeFeedback?: (node: any) => void,
  onNodeExpand?: (node: any) => void,
}) {
  const fgRef = useRef<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [dagMode, setDagMode] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenu | null>(null);

  useEffect(() => {
    const updateDimensions = () => {
      setDimensions({
        width: window.innerWidth,
        height: window.innerHeight,
      });
    };
    window.addEventListener('resize', updateDimensions);
    updateDimensions();
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  useEffect(() => {
    const close = () => setContextMenu(null);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, []);

  const handleNodeClick = useCallback((node: any) => {
    setContextMenu(null);
    onNodeClick(node);
    if (fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 1000);
      fgRef.current.zoom(2, 1000);
    }
  }, [onNodeClick]);

  const handleNodeRightClick = useCallback((node: any, event: MouseEvent) => {
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY, node });
  }, []);

  return (
    <div className="absolute inset-0 z-0">
      {/* Layout switcher */}
      <div className="absolute top-4 right-4 z-20 flex gap-1 bg-slate-900/80 backdrop-blur rounded-lg border border-slate-700/60 p-1">
        {([
          { mode: null, icon: <Grid3X3 size={14} />, label: '力导向' },
          { mode: 'td', icon: <ArrowDownUp size={14} />, label: '自上而下' },
          { mode: 'lr', icon: <ArrowDownUp size={14} className="rotate-90" />, label: '左至右' },
        ] as const).map(({ mode, icon, label }) => (
          <button
            key={label}
            onClick={() => setDagMode(mode)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors ${
              dagMode === mode ? 'bg-rose-500/30 text-rose-300' : 'text-slate-400 hover:text-slate-200'
            }`}
            title={label}
          >
            {icon} {label}
          </button>
        ))}
      </div>

      {/* Right-click context menu */}
      {contextMenu && (
        <div
          className="absolute z-30 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl py-1 min-w-[140px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-white flex items-center gap-2"
            onClick={() => { onNodeClick(contextMenu.node); setContextMenu(null); }}
          >
            查看详情
          </button>
          {onNodeFeedback && (
            <button
              className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-white flex items-center gap-2"
              onClick={() => { onNodeFeedback(contextMenu.node); setContextMenu(null); }}
            >
              提供教学反馈
            </button>
          )}
          {onNodeExpand && (
            <button
              className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-white flex items-center gap-2"
              onClick={() => { onNodeExpand(contextMenu.node); setContextMenu(null); }}
            >
              展开邻接节点
            </button>
          )}
          <button
            className="w-full text-left px-3 py-2 text-xs text-rose-400 hover:bg-rose-500/10 flex items-center gap-2"
            onClick={() => setContextMenu(null)}
          >
            关闭
          </button>
        </div>
      )}

      <ForceGraph2D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={data}
        dagMode={dagMode as any}
        dagLevelDistance={dagMode ? 80 : undefined}
        nodeLabel={(node: any) => `${node.name}\n${node.books?.join(', ') || ''}`}
        nodeColor={(node: any) => node.type === 'merged' ? colorMap.merged : (colorMap[node.source as keyof typeof colorMap] || '#64748b')}
        nodeRelSize={8}
        linkColor={(link: any) => colorMap[link.type as keyof typeof colorMap] || '#334155'}
        linkWidth={(link: any) => link.type === 'Application' ? 2.5 : 1.8}
        linkDirectionalArrowLength={6}
        linkDirectionalArrowRelPos={1}
        onNodeClick={handleNodeClick}
        onNodeRightClick={handleNodeRightClick}
        onBackgroundClick={() => { onBgClick(); setContextMenu(null); }}
        nodeCanvasObject={(node: any, ctx, globalScale) => {
          const rawLabel = String(node.name || '');
          const nodeRadius = Math.max(8, (node.val || 4) * 1.5);
          const fillColor = node.type === 'merged' ? colorMap.merged : (colorMap[node.source as keyof typeof colorMap] || '#64748b');

          if (node.type === 'merged') {
            drawHexagon(ctx, node.x!, node.y!, nodeRadius);
            ctx.fillStyle = fillColor;
            ctx.shadowColor = colorMap.merged;
            ctx.shadowBlur = 14;
            ctx.fill();
            ctx.shadowBlur = 0;
          } else {
            ctx.beginPath();
            ctx.arc(node.x!, node.y!, nodeRadius, 0, 2 * Math.PI, false);
            ctx.fillStyle = fillColor;
            ctx.fill();
          }

          // Always show text, scale with zoom
          const fontSize = Math.max(8, Math.min(24, nodeRadius * 0.8 / Math.max(globalScale, 0.3)));
          ctx.font = `600 ${fontSize}px Inter, Sans-Serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = '#f8fafc';
          const maxLength = Math.max(6, Math.floor(12 / Math.max(globalScale, 0.5)));
          const label = rawLabel.length > maxLength ? rawLabel.substring(0, maxLength) + '…' : rawLabel;
          ctx.shadowColor = '#000';
          ctx.shadowBlur = 6;
          ctx.fillText(label, node.x!, node.y! + nodeRadius + fontSize * 0.7);
          ctx.shadowBlur = 0;
        }}
        d3VelocityDecay={0.3}
      />
    </div>
  );
}
