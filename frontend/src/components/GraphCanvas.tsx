"use client";

import React, { useRef, useEffect, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { colorMap } from '@/lib/agentData';

// Dynamically import to avoid SSR issues with Canvas
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

export default function GraphCanvas({ data, onNodeClick, onBgClick }: { data: any, onNodeClick: (node: any) => void, onBgClick: () => void }) {
  const fgRef = useRef<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    // Fit to container
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

  const handleNodeClick = useCallback((node: any) => {
    onNodeClick(node);
    if (fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 1000);
      fgRef.current.zoom(2, 1000);
    }
  }, [onNodeClick]);

  return (
    <div className="absolute inset-0 z-0">
      <ForceGraph2D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={data}
        nodeLabel={(node: any) => `${node.name}\n${node.books?.join(', ') || ''}`}
        nodeColor={(node: any) => node.type === 'merged' ? colorMap.merged : (colorMap[node.source as keyof typeof colorMap] || '#64748b')}
        nodeRelSize={4}
        linkColor={(link: any) => colorMap[link.type as keyof typeof colorMap] || '#334155'}
        linkWidth={(link: any) => link.type === 'Application' ? 2.2 : 1.3}
        linkDirectionalArrowLength={5}
        linkDirectionalArrowRelPos={1}
        onNodeClick={handleNodeClick}
        onBackgroundClick={onBgClick}
        nodeCanvasObject={(node: any, ctx, globalScale) => {
          const rawLabel = String(node.name || '');
          const nodeRadius = Math.max(4, node.val || 4);
          
          // Draw Circle
          ctx.beginPath();
          ctx.arc(node.x, node.y, nodeRadius, 0, 2 * Math.PI, false);
          ctx.fillStyle = node.type === 'merged' ? colorMap.merged : (colorMap[node.source as keyof typeof colorMap] || '#64748b');
          ctx.fill();
          
          // Glow effect for merged
          if(node.type === 'merged') {
            ctx.shadowColor = colorMap.merged;
            ctx.shadowBlur = 10;
            ctx.fill();
            ctx.shadowBlur = 0; // reset
          }

          // Draw Text ONLY if zoomed in enough (reduce dense clutter)
          if (globalScale >= 0.8) {
            // Font size scales with node, but has a readable minimum
            const fontSize = Math.max(4, nodeRadius * 0.6);
            ctx.font = `${fontSize}px Inter, Sans-Serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = '#f8fafc';
            
            // Truncate based on zoom level
            const maxLength = globalScale > 2 ? 15 : 8;
            const label = rawLabel.length > maxLength ? rawLabel.substring(0, maxLength) + '...' : rawLabel;
            
            // Shadow for text readability
            ctx.shadowColor = '#000';
            ctx.shadowBlur = 4;
            // Draw text BELOW the node
            ctx.fillText(label, node.x, node.y + nodeRadius + fontSize);
            ctx.shadowBlur = 0;
          }
        }}
        d3VelocityDecay={0.3} // Make it more fluid
      />
    </div>
  );
}
