import os
import jieba
import pickle
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
import faiss
from tqdm import tqdm

class MedicalSearchEngine:
    def __init__(self, model_name='shibing624/text2vec-base-chinese'):
        self.model = SentenceTransformer(model_name)
        self.bm25 = None
        self.faiss_index = None
        self.chunks = []
        self.chunk_paths = []

    def load_chunks(self, root_dir):
        print("Loading chunks...")
        self.chunks = []
        self.chunk_paths = []
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if file.endswith('.md'):
                    path = os.path.join(root, file)
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if len(content.strip()) > 20:
                            self.chunks.append(content)
                            self.chunk_paths.append(path)
        print(f"Loaded {len(self.chunks)} chunks.")

    def build_bm25(self):
        print("Building BM25 index...")
        tokenized_corpus = [list(jieba.cut(doc)) for doc in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def build_semantic(self):
        print("Building Semantic index (this may take a while on CPU)...")
        embeddings = self.model.encode(self.chunks, show_progress_bar=True)
        dimension = embeddings.shape[1]
        self.faiss_index = faiss.IndexFlatL2(dimension)
        self.faiss_index.add(embeddings.astype('float32'))

    def save(self, path_prefix='medical_index'):
        print(f"Saving index to {path_prefix}...")
        with open(f"{path_prefix}_meta.pkl", 'wb') as f:
            pickle.dump({
                'chunks': self.chunks,
                'chunk_paths': self.chunk_paths,
                'bm25': self.bm25
            }, f)
        faiss.write_index(self.faiss_index, f"{path_prefix}_faiss.index")

    def load(self, path_prefix='medical_index'):
        print(f"Loading index from {path_prefix}...")
        with open(f"{path_prefix}_meta.pkl", 'rb') as f:
            data = pickle.load(f)
            self.chunks = data['chunks']
            self.chunk_paths = data['chunk_paths']
            self.bm25 = data['bm25']
        self.faiss_index = faiss.read_index(f"{path_prefix}_faiss.index")

    def search(self, query, top_k=5, alpha=0.5):
        # 1. BM25 Search
        tokenized_query = list(jieba.cut(query))
        bm25_scores = self.bm25.get_scores(tokenized_query)
        
        # 2. Semantic Search
        query_embedding = self.model.encode([query])
        distances, indices = self.faiss_index.search(query_embedding.astype('float32'), len(self.chunks))
        
        # Normalize scores
        bm25_scores = (bm25_scores - np.min(bm25_scores)) / (np.max(bm25_scores) - np.min(bm25_scores) + 1e-6)
        
        # FAISS distances to scores (lower distance = higher score)
        semantic_scores = np.zeros(len(self.chunks))
        max_dist = np.max(distances)
        for i, idx in enumerate(indices[0]):
            semantic_scores[idx] = 1 - (distances[0][i] / (max_dist + 1e-6))
            
        # 3. Hybrid Reranking
        hybrid_scores = alpha * bm25_scores + (1 - alpha) * semantic_scores
        top_indices = np.argsort(hybrid_scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            results.append({
                'score': hybrid_scores[idx],
                'path': self.chunk_paths[idx],
                'content': self.chunks[idx][:500] + "..." # Snippet
            })
        return results

if __name__ == "__main__":
    engine = MedicalSearchEngine()
    engine.load_chunks('生医黑客松/chunks')
    engine.build_bm25()
    engine.build_semantic()
    engine.save()
