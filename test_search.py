from search_engine import MedicalSearchEngine
import sys

def main():
    engine = MedicalSearchEngine()
    engine.load('medical_index')
    
    query = sys.argv[1] if len(sys.argv) > 1 else "二尖瓣狭窄的临床表现"
    print(f"\nSearching for: {query}\n")
    
    results = engine.search(query, top_k=3)
    
    for i, res in enumerate(results):
        print(f"--- Result {i+1} (Score: {res['score']:.4f}) ---")
        print(f"Path: {res['path']}")
        print(f"Content: {res['content']}\n")

if __name__ == "__main__":
    main()
