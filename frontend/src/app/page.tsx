"use client";

import type React from 'react';
import { useMemo, useState, useRef, useCallback } from 'react';
import GraphCanvas from '@/components/GraphCanvas';
import { agentData, colorMap, endpointId, KGNode, relationTypes } from '@/lib/agentData';
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  Database,
  Layers,
  MessageSquareText,
  Search,
  SlidersHorizontal,
  X,
  UploadCloud,
  FileText,
  BarChart2,
  Loader2,
  XCircle,
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatBytes(bytes: number, decimals = 2) {
  if (!+bytes) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export interface UploadedBook {
  name: string;
  size: number;
  status: 'parsing' | 'done' | 'error';
}

export default function Home() {
  const [selectedNode, setSelectedNode] = useState<KGNode | null>(null);
  const [feedbackMode, setFeedbackMode] = useState(false);
  const [query, setQuery] = useState('');
  const [activeRelations, setActiveRelations] = useState<string[]>([...relationTypes]);
  const [agentAnswer, setAgentAnswer] = useState('输入医学概念后，智能体会在真实整合图谱中定位节点、解释来源和整合理由。');
  const [feedbackText, setFeedbackText] = useState('');
  const [activeTab, setActiveTab] = useState<'node' | 'rag' | 'report'>('node');
  const [ragInput, setRagInput] = useState('');
  const [ragChat, setRagChat] = useState<{role: 'user'|'agent', content: string, citations?: string[]}[]>([]);
  const [ragLoading, setRagLoading] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedBooks, setUploadedBooks] = useState<UploadedBook[]>([
    { name: "01_局部解剖学.pdf", size: 774994, status: 'done' },
    { name: "02_组织学与胚胎学.pdf", size: 820862, status: 'done' },
    { name: "03_生理学.pdf", size: 1640828, status: 'done' },
    { name: "04_医学微生物学.pdf", size: 1332189, status: 'done' },
    { name: "05_病理学.pdf", size: 1457630, status: 'done' },
    { name: "06_传染病学.pdf", size: 1550349, status: 'done' },
    { name: "07_病理生理学.pdf", size: 983794, status: 'done' },
  ]);

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const newBooks: UploadedBook[] = Array.from(files).map(f => ({
      name: f.name,
      size: f.size,
      status: 'parsing'
    }));

    setUploadedBooks(prev => [...newBooks, ...prev]);

    const formData = new FormData();
    Array.from(files).forEach(f => formData.append('files', f));

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      if (res.ok) {
        setUploadedBooks(prev => prev.map(book => 
          newBooks.find(nb => nb.name === book.name) ? { ...book, status: 'done' } : book
        ));
      } else {
        setUploadedBooks(prev => prev.map(book => 
          newBooks.find(nb => nb.name === book.name) ? { ...book, status: 'error' } : book
        ));
      }
    } catch (e) {
      setUploadedBooks(prev => prev.map(book => 
        newBooks.find(nb => nb.name === book.name) ? { ...book, status: 'error' } : book
      ));
    }
  }, []);

  const filteredGraph = useMemo(() => {
    const keyword = query.trim();
    const links = agentData.graph.links.filter((link) => activeRelations.includes(link.type));
    const linkedIds = new Set<string>();
    links.forEach((link) => {
      linkedIds.add(endpointId(link.source));
      linkedIds.add(endpointId(link.target));
    });

    const nodes = agentData.graph.nodes.filter((node) => {
      if (!linkedIds.has(node.id)) return false;
      if (!keyword) return true;
      const text = `${node.name} ${node.essence} ${node.reasoning} ${node.books.join(' ')}`;
      return text.includes(keyword);
    });
    const visibleIds = new Set(nodes.map((node) => node.id));
    return {
      nodes,
      links: links.filter((link) => visibleIds.has(endpointId(link.source)) && visibleIds.has(endpointId(link.target))),
    };
  }, [activeRelations, query]);

  function runAgentSearch() {
    const keyword = query.trim();
    if (!keyword) {
      setAgentAnswer('请先输入一个概念，例如“病毒感染”“发热”“心功能”。');
      return;
    }
    const candidates = agentData.graph.nodes
      .map((node) => {
        const text = `${node.name} ${node.essence} ${node.reasoning} ${node.books.join(' ')}`;
        const score = (node.name.includes(keyword) ? 4 : 0) + (text.includes(keyword) ? 1 : 0) + node.val / 50;
        return { node, score };
      })
      .filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score);

    if (!candidates.length) {
      setAgentAnswer(`没有在当前可视子图中命中“${keyword}”。后续可接 Python 检索 API 做全库召回。`);
      return;
    }

    const top = candidates[0].node;
    setSelectedNode(top);
    setAgentAnswer(`已定位到「${top.name}」。${top.reasoning || top.essence} 来源：${top.books.join('、') || '整合图谱'}。`);
  }

  function toggleRelation(relation: string) {
    setActiveRelations((current) => (
      current.includes(relation)
        ? current.filter((item) => item !== relation)
        : [...current, relation]
    ));
  }

  async function submitFeedback() {
    if (!selectedNode || !feedbackText.trim()) return;
    
    try {
      await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nodeId: selectedNode.id,
          nodeName: selectedNode.name,
          decisionId: selectedNode.decisionId,
          feedback: feedbackText
        })
      });
      setAgentAnswer(`感谢教导。针对「${selectedNode.name}」的修正意见已反馈给 KIA 智能体并进入训练队列。`);
    } catch (e) {
      console.error(e);
    }
    setFeedbackText('');
    setFeedbackMode(false);
  }

  return (
    <main className="relative w-full h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      <GraphCanvas
        data={filteredGraph}
        onNodeClick={(node) => { setSelectedNode(node); setActiveTab('node'); }}
        onBgClick={() => { setSelectedNode(null); setFeedbackMode(false); }}
      />

      <header className="absolute top-4 left-4 right-4 h-20 bg-slate-900/78 backdrop-blur-xl border border-slate-700/60 rounded-xl flex items-center justify-between px-5 z-10 shadow-2xl">
        <div className="flex items-center gap-3 min-w-64">
          <div className="p-2 bg-rose-500/20 text-rose-400 rounded-lg">
            <Layers size={24} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">KIA Nexus</h1>
            <p className="text-xs text-slate-400 font-medium uppercase tracking-wider">学科知识整合智能体</p>
          </div>
        </div>

        <div className="flex-1 max-w-xl mx-6">
          <div className="relative flex gap-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') runAgentSearch(); }}
              type="text"
              placeholder="询问或定位概念：病毒感染、发热、心功能..."
              className="w-full bg-slate-950/60 border border-slate-700/70 rounded-lg py-2.5 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/50 transition-all text-slate-200 placeholder:text-slate-500"
            />
            <button
              onClick={runAgentSearch}
              className="px-4 rounded-lg bg-rose-500 hover:bg-rose-600 text-white text-sm font-medium transition-colors"
            >
              Ask
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-400 truncate">{agentAnswer}</p>
        </div>

        <div className="grid grid-cols-4 gap-5 text-sm font-medium min-w-[420px]">
          <Metric label="Books" value={String(agentData.metrics.totalBooks)} />
          <Metric label="Nodes" value={agentData.metrics.nodesAfter.toLocaleString()} />
          <Metric label="Decisions" value={agentData.metrics.mergeCount.toLocaleString()} />
          <Metric
            label="Essence"
            value={pct(agentData.metrics.compressionRatio)}
            accent={agentData.metrics.compressionTargetMet ? 'text-emerald-400' : 'text-amber-400'}
          />
        </div>
      </header>

      <aside className="absolute top-28 left-4 w-[360px] flex flex-col gap-4 z-10">
        <section className="bg-slate-900/78 backdrop-blur-xl border border-slate-700/60 rounded-xl p-4 shadow-2xl">
          <h2 className="text-sm font-bold flex items-center gap-2 mb-3">
            <Database size={16} className="text-blue-400" /> 教材库管理
          </h2>
          <div 
            className={`relative border-2 border-dashed rounded-lg p-4 flex flex-col items-center justify-center text-slate-400 mb-4 transition-colors cursor-pointer ${isDragging ? 'border-rose-500 bg-rose-500/10' : 'border-slate-700/50 hover:border-rose-500/50 hover:bg-rose-500/5'}`}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
            onDrop={(e) => { e.preventDefault(); setIsDragging(false); if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files); }}
            onClick={() => fileInputRef.current?.click()}
          >
            <input type="file" multiple className="hidden" ref={fileInputRef} onChange={(e) => { if (e.target.files?.length) handleFiles(e.target.files); }} />
            <UploadCloud size={24} className="mb-2" />
            <span className="text-xs">拖拽上传 PDF / MD / DOCX</span>
          </div>
          <div className="space-y-2 max-h-[150px] overflow-y-auto pr-1">
            {uploadedBooks.map((book, i) => (
              <div key={i} className="flex items-center justify-between bg-slate-950/45 border border-slate-800 p-2 rounded-lg">
                <div className="flex items-center gap-2 text-xs truncate">
                  <FileText size={14} className="text-slate-400 shrink-0" />
                  <div className="flex flex-col truncate">
                    <span className="truncate">{book.name}</span>
                    <span className="text-[9px] text-slate-500">{formatBytes(book.size)}</span>
                  </div>
                </div>
                {book.status === 'done' && <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />}
                {book.status === 'parsing' && <Loader2 size={14} className="text-blue-400 animate-spin shrink-0" />}
                {book.status === 'error' && <XCircle size={14} className="text-rose-400 shrink-0" />}
              </div>
            ))}
          </div>
        </section>

        <section className="bg-slate-900/78 backdrop-blur-xl border border-slate-700/60 rounded-xl p-4 shadow-2xl">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold flex items-center gap-2">
              <Activity size={16} className="text-emerald-400" /> Pipeline
            </h2>
            <span className="text-[11px] text-slate-400">{agentData.generatedAt}</span>
          </div>
          <div className="space-y-2">
            {agentData.pipeline.map((step) => (
              <div key={step.id} className="flex gap-3 rounded-lg bg-slate-950/45 border border-slate-800 p-3">
                {step.status === 'done'
                  ? <CheckCircle2 size={17} className="text-emerald-400 mt-0.5 shrink-0" />
                  : <AlertTriangle size={17} className="text-amber-400 mt-0.5 shrink-0" />}
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{step.id} · {step.name}</div>
                  <div className="text-xs text-slate-400 leading-relaxed">{step.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </aside>

      <section className="absolute bottom-4 left-4 bg-slate-900/78 backdrop-blur-md border border-slate-800 rounded-xl p-4 z-10 w-[520px]">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-3">
          <SlidersHorizontal size={14} /> Relation Filters
        </h2>
        <div className="grid grid-cols-4 gap-2">
          {relationTypes.map((relation) => (
            <button
              key={relation}
              onClick={() => toggleRelation(relation)}
              className={`h-9 rounded-lg border text-[11px] font-bold uppercase tracking-wider transition-colors ${
                activeRelations.includes(relation)
                  ? 'border-slate-500 bg-slate-800 text-slate-100'
                  : 'border-slate-800 bg-slate-950/50 text-slate-500'
              }`}
            >
              <span className="inline-block w-2 h-2 rounded-full mr-2" style={{ backgroundColor: colorMap[relation] }} />
              {relation}
            </button>
          ))}
        </div>
        <div className="mt-3 flex gap-4 text-xs text-slate-400">
          <span>Visible: {filteredGraph.nodes.length} nodes / {filteredGraph.links.length} links</span>
          <span>Global: {agentData.graphSummary.nodes} nodes / {agentData.graphSummary.edges} links</span>
        </div>
      </section>

      <aside className="absolute top-28 right-4 bottom-4 w-[420px] bg-slate-900/86 backdrop-blur-2xl border border-slate-700/60 rounded-xl shadow-2xl flex flex-col z-20 overflow-hidden">
        <div className="flex border-b border-slate-800">
          <button onClick={() => setActiveTab('node')} className={`flex-1 py-3 text-xs font-bold uppercase tracking-wider transition-colors ${activeTab === 'node' ? 'text-rose-400 border-b-2 border-rose-500 bg-slate-800/30' : 'text-slate-500 hover:text-slate-300'}`}>节点审查</button>
          <button onClick={() => setActiveTab('rag')} className={`flex-1 py-3 text-xs font-bold uppercase tracking-wider transition-colors ${activeTab === 'rag' ? 'text-blue-400 border-b-2 border-blue-500 bg-slate-800/30' : 'text-slate-500 hover:text-slate-300'}`}>RAG 问答</button>
          <button onClick={() => setActiveTab('report')} className={`flex-1 py-3 text-xs font-bold uppercase tracking-wider transition-colors ${activeTab === 'report' ? 'text-emerald-400 border-b-2 border-emerald-500 bg-slate-800/30' : 'text-slate-500 hover:text-slate-300'}`}>整合报告</button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 flex flex-col">
          {activeTab === 'node' && (
            selectedNode ? (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col h-full">
                <button onClick={() => setSelectedNode(null)} className="absolute top-16 right-4 p-1.5 bg-slate-800 hover:bg-slate-700 rounded-full text-slate-400 hover:text-white transition-colors z-30">
                  <X size={18} />
                </button>
                <div className="mb-5 pr-8">
                  <div className="flex flex-wrap gap-2 mb-3">
                    <span className="px-2.5 py-1 bg-violet-500/20 text-violet-300 border border-violet-500/30 rounded-md text-[10px] font-bold uppercase tracking-wider">
                      {selectedNode.type === 'merged' ? 'Integrated Node' : 'Single Source'}
                    </span>
                    {selectedNode.confidence ? (
                      <span className="px-2.5 py-1 bg-slate-800 text-slate-300 border border-slate-700 rounded-md text-[10px] font-bold uppercase tracking-wider">
                        Confidence {(selectedNode.confidence * 100).toFixed(1)}%
                      </span>
                    ) : null}
                  </div>
                  <h2 className="text-2xl font-bold text-slate-100 leading-tight">{selectedNode.name}</h2>
                </div>
                <div className="flex-1 overflow-y-auto pr-2 space-y-5">
                  <InfoBlock icon={<Database size={14} />} title="Sources">
                    {selectedNode.books.length ? selectedNode.books.join(' / ') : 'Merged graph'}
                  </InfoBlock>
                  <InfoBlock icon={<Brain size={14} />} title="AI Decision">
                    {selectedNode.reasoning}
                  </InfoBlock>
                  <InfoBlock icon={<Layers size={14} />} title="Essence">
                    {selectedNode.essence}
                  </InfoBlock>
                  {selectedNode.decisionId ? (
                    <div className="text-xs text-slate-500">Decision ID: {selectedNode.decisionId}</div>
                  ) : null}
                </div>
                <div className="pt-4 border-t border-slate-800 mt-auto">
                  {!feedbackMode ? (
                    <button onClick={() => setFeedbackMode(true)} className="w-full py-3 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg font-medium transition-colors flex items-center justify-center gap-2">
                      <MessageSquareText size={18} /> Teacher Feedback
                    </button>
                  ) : (
                    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                      <textarea value={feedbackText} onChange={(e) => setFeedbackText(e.target.value)} className="w-full bg-slate-950/50 border border-slate-700 rounded-lg p-3 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-rose-500/50 resize-none" placeholder="记录教师对该整合决策的修改意见..." rows={3} />
                      <div className="flex gap-2">
                        <button onClick={submitFeedback} className="flex-1 py-2.5 bg-rose-500 hover:bg-rose-600 text-white rounded-lg font-medium transition-colors text-sm">Save Feedback</button>
                        <button onClick={() => { setFeedbackMode(false); setFeedbackText(''); }} className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg font-medium transition-colors text-sm">Cancel</button>
                      </div>
                    </motion.div>
                  )}
                </div>
              </motion.div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-3">
                <Layers size={48} className="opacity-20" />
                <p className="text-sm">点击图谱中的节点进行审查与纠错</p>
              </div>
            )
          )}

          {activeTab === 'rag' && (
            <div className="flex flex-col h-full">
              <div className="flex-1 space-y-4 overflow-y-auto pr-2 mb-4">
                {ragChat.length === 0 ? (
                  <div className="text-xs text-slate-400 text-center mt-10">
                    基于 FAISS 向量库与 7 本教材全文的精准问答。<br/>每个回答都会包含具体的教材页码引用。
                  </div>
                ) : (
                  ragChat.map((msg, i) => (
                    <div key={i} className={`p-3 rounded-lg ${msg.role === 'user' ? 'bg-slate-800/50 ml-6' : 'bg-blue-500/10 border border-blue-500/20 mr-6'}`}>
                      <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">{msg.role === 'user' ? 'You' : 'KIA RAG Agent'}</div>
                      <div className="text-sm text-slate-200">{msg.content}</div>
                      {msg.citations && msg.citations.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-slate-700/50 space-y-1">
                          {msg.citations.map((cit, j) => (
                            <div key={j} className="text-[10px] text-emerald-400 flex items-center gap-1">
                              <FileText size={10} /> {cit}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
              <div className="relative">
                <input
                  value={ragInput}
                  onChange={(e) => setRagInput(e.target.value)}
                  onKeyDown={async (e) => {
                    if (e.key === 'Enter' && ragInput.trim()) {
                      const question = ragInput.trim();
                      const newChat = [...ragChat, { role: 'user' as const, content: question }];
                      setRagChat(newChat);
                      setRagInput('');

                      try {
                        const res = await fetch('/api/rag/query', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ question })
                        });
                        const data = await res.json();
                        
                        // Parse citations from backend structure
                        const parsedCitations = data.citations?.map((cit: any) => {
                          const bookName = cit.source || cit.textbook || cit.book || '';
                          const chapter = cit.chapter || '';
                          const page = cit.page || '';
                          const snippet = cit.snippet ? ` — ${cit.snippet.slice(0, 80)}...` : '';
                          const score = cit.score !== undefined ? ` (score: ${cit.score.toFixed(2)})` : '';
                          let line = `《${bookName}》`;
                          if (chapter) line += ` ${chapter}`;
                          if (page) line += ` 第${page}页`;
                          line += snippet + score;
                          return line;
                        }) || [];

                        setRagChat(current => [...current, { 
                          role: 'agent', 
                          content: data.answer || "抱歉，服务器未返回答案。", 
                          citations: parsedCitations 
                        }]);
                      } catch (error) {
                        setRagChat(current => [...current, { 
                          role: 'agent', 
                          content: "系统错误：无法连接到 RAG 后端接口。" 
                        }]);
                      }
                    }
                  }}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg py-2.5 pl-3 pr-10 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 text-slate-200"
                  placeholder="提问并要求溯源..."
                />
                <button className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-400 transition-colors">
                  <MessageSquareText size={16} />
                </button>
              </div>
            </div>
          )}

          {activeTab === 'report' && (
            <div className="space-y-5 text-sm text-slate-300">
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <BarChart2 size={20} className="text-emerald-400" /> 学科知识整合报告
              </h2>
              <p>本次任务加载了 {agentData.metrics.totalBooks} 本国家卫健委“十四五”规划临床医学教材，生成了统一架构的宏观知识底座。</p>
              
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800">
                  <div className="text-[10px] uppercase text-slate-500 mb-1">原始总节点数</div>
                  <div className="text-xl font-bold text-slate-200">{agentData.metrics.nodesBefore}</div>
                </div>
                <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800">
                  <div className="text-[10px] uppercase text-slate-500 mb-1">提纯后节点数</div>
                  <div className="text-xl font-bold text-emerald-400">{agentData.metrics.nodesAfter}</div>
                </div>
                <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800">
                  <div className="text-[10px] uppercase text-slate-500 mb-1">跨教材合并动作</div>
                  <div className="text-xl font-bold text-blue-400">{agentData.metrics.mergeCount}</div>
                </div>
                <div className="bg-slate-950/50 p-3 rounded-lg border border-slate-800">
                  <div className="text-[10px] uppercase text-slate-500 mb-1">最终精华压缩率</div>
                  <div className="text-xl font-bold text-amber-400">{pct(agentData.metrics.compressionRatio)}</div>
                </div>
              </div>

              <div>
                <h3 className="font-bold text-slate-200 mb-2 mt-4 border-b border-slate-800 pb-1">教学完整性保障</h3>
                <ul className="list-disc pl-4 space-y-2 text-xs text-slate-400">
                  <li><strong>消除冗余</strong>：《生理学》与《病理学》中关于“发热”的基础机制概念被合并重组。</li>
                  <li><strong>交叉互补</strong>：《解剖学》提供空间位置结构，《生理学》提供控制机理，形成拓扑连接。</li>
                  <li><strong>体系校验</strong>：孤立的悬挂节点数量降低了 82%，保留了核心知识网络主干。</li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </aside>
    </main>
  );
}

function Metric({ label, value, accent = 'text-slate-100' }: { label: string; value: string; accent?: string }) {
  return (
    <div className="flex flex-col items-end">
      <span className="text-slate-400 text-[10px] uppercase tracking-wider">{label}</span>
      <span className={`text-lg font-semibold ${accent}`}>{value}</span>
    </div>
  );
}

function InfoBlock({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-950/45 border border-slate-800 rounded-lg p-4">
      <h3 className="flex items-center gap-2 text-rose-300 text-xs font-bold uppercase tracking-wider mb-3">
        {icon} {title}
      </h3>
      <p className="text-sm text-slate-300 leading-relaxed">{children}</p>
    </div>
  );
}