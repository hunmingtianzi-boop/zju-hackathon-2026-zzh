import rawAgentData from './agentData.json';

export type PipelineStatus = 'done' | 'warning' | 'pending';

export interface PipelineStep {
  id: string;
  name: string;
  status: PipelineStatus;
  detail: string;
}

export interface KGNode {
  id: string;
  name: string;
  val: number;
  type: 'merged' | 'single';
  source: string;
  books: string[];
  essence: string;
  reasoning: string;
  decisionId?: string | null;
  confidence?: number | null;
}

export interface KGEdge {
  source: string | KGNode;
  target: string | KGNode;
  label: 'Prerequisite' | 'Parallel' | 'Inclusion' | 'Application' | string;
  type: 'Prerequisite' | 'Parallel' | 'Inclusion' | 'Application' | string;
  books?: string[];
}

export interface AgentData {
  generatedAt: string;
  pipeline: PipelineStep[];
  metrics: {
    totalBooks: number;
    nodesBefore: number;
    nodesAfter: number;
    edgesAfter: number;
    mergeCount: number;
    conflictCount: number;
    complementCount: number;
    dedupRatio: number;
    compressionRatio: number;
    rawCompressionRatio: number;
    compressionTargetMet: boolean;
  };
  graph: {
    nodes: KGNode[];
    links: KGEdge[];
  };
  graphSummary: {
    nodes: number;
    edges: number;
    visibleNodes: number;
    visibleEdges: number;
    relationCounts: Record<string, number>;
    singleBookGraphs: number;
    singleBookCycles: number;
  };
  essence: {
    originalChars: number;
    compressedChars: number;
    compressionRatio: number;
    rawCompressionRatio: number;
    targetMet: boolean;
    tierDistribution: Record<string, number>;
    method: string;
    strict: boolean;
  };
  decisions: Array<{
    decision_id: string;
    type: string;
    nodes: string[];
    books: string[];
    confidence: number;
    rationale: string;
    evidence: string[];
  }>;
}

export const agentData = rawAgentData as AgentData;
export const relationTypes = ['Prerequisite', 'Parallel', 'Inclusion', 'Application'] as const;

export const colorMap: Record<string, string> = {
  Prerequisite: '#f43f5e',
  Parallel: '#0ea5e9',
  Inclusion: '#10b981',
  Application: '#d946ef',
  merged: '#8b5cf6',
  single: '#64748b',
  done: '#10b981',
  warning: '#f59e0b',
};

export function endpointId(value: string | KGNode): string {
  return typeof value === 'string' ? value : value.id;
}
