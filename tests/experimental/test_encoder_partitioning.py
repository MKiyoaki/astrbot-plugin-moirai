import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_similarity

def load_chat():
    path = Path("tests/mock_data/mock_chat.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_experiment():
    print("Loading BGE-small model...")
    model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    
    chat_data = load_chat()
    # For clustering, we include sender info to help distinguish interleaved speakers
    texts = [f"{m['nickname']}: {m['content']}" for m in chat_data]
    raw_texts = [m['content'] for m in chat_data]
    
    print(f"Encoding {len(texts)} messages...")
    embeddings = model.encode(texts, normalize_embeddings=True)
    
    # 1. Sequential Boundary Detection (Cosine similarity pulses)
    print("\n--- Sequential Boundary Detection ---")
    similarities = []
    for i in range(len(embeddings) - 1):
        sim = cosine_similarity([embeddings[i]], [embeddings[i+1]])[0][0]
        similarities.append(sim)
        
    threshold = 0.6  # Example threshold
    print(f"{'Index':<6} | {'Sim':<6} | {'Status':<10} | {'Content'}")
    print("-" * 60)
    for i, sim in enumerate(similarities):
        status = "BREAK" if sim < threshold else ""
        content = texts[i+1][:50]
        print(f"{i:<6} | {sim:.3f} | {status:<10} | {content}")

    # 2. De-interleaving using DBSCAN
    print("\n--- Topic De-interleaving (Clustering) ---")
    # eps is the maximum distance between two samples for one to be considered as in the neighborhood of the other.
    # For cosine similarity, distance = 1 - similarity.
    # So similarity 0.7 means distance 0.3.
    clustering = DBSCAN(eps=0.3, min_samples=2, metric="cosine").fit(embeddings)
    labels = clustering.labels_
    
    clusters = {}
    for i, label in enumerate(labels):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(texts[i])
        
    for label, msgs in clusters.items():
        name = f"Topic {label}" if label != -1 else "Noise/Outliers"
        print(f"\n[{name}]")
        for m in msgs:
            print(f"  - {m}")

if __name__ == "__main__":
    run_experiment()
