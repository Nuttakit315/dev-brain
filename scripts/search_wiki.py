import os
import sys
import json
import re
import argparse
from collections import Counter, defaultdict, deque

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r'\[\[(.*?)\]\]', r'\1', text)
    text = re.sub(r'[#*`_~>\-\[\]\(\)\{\}\:\.\,\!\?]', ' ', text)
    
    raw_tokens = re.findall(r'[\u0E00-\u0E7Fa-zA-Z0-9_]+', text)
    tokens = []

    for t in raw_tokens:
        if len(t) <= 1:
            continue
        tokens.append(t)
        if re.search(r'[\u0E00-\u0E7F]', t) and len(t) > 4:
            for n in [3, 4]:
                for i in range(len(t) - n + 1):
                    tokens.append(t[i:i+n])

    return tokens

def load_graph_and_index(graph_path="graph/graph.json", index_path="graph/search_index.json"):
    if not os.path.exists(index_path) or not os.path.exists(graph_path):
        import subprocess
        print("⚠️ กำลังสร้างดัชนี Graph & Search...")
        try:
            subprocess.run([sys.executable, "scripts/run_graphify.py"], check=True)
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดในการรัน run_graphify.py: {e}")
            return {}, {}

    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    with open(graph_path, "r", encoding="utf-8") as f:
        graph_data = json.load(f)

    return index_data, graph_data

def search_anchors(query: str, index_data: dict, top_k: int = 5) -> list[dict]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    q_counts = Counter(query_tokens)
    scored_results = []

    for doc in index_data.get("documents", []):
        score = 0.0
        doc_id = doc.get("id", "")
        doc_id_lower = doc_id.lower()
        doc_snippet_lower = doc.get("snippet", "").lower()
        doc_tfidf = doc.get("tfidf", {})
        centrality = doc.get("centrality_score", 0.0)

        for qt in query_tokens:
            if qt == doc_id_lower:
                score += 8.0
            elif qt in doc_id_lower:
                score += 4.0
            if qt in doc_snippet_lower:
                score += 1.5

        for token, count in q_counts.items():
            if token in doc_tfidf:
                score += doc_tfidf[token] * count * 3.5

        score += centrality * 0.25

        if score > 0.05:
            scored_results.append({
                "id": doc_id,
                "path": doc.get("path", "").replace("\\", "/"),
                "type": doc.get("type", "Document"),
                "score": round(score, 2),
                "snippet": doc.get("snippet", ""),
                "links": doc.get("links", [])
            })

    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results[:top_k]

def traverse_subgraph(anchor_ids: list[str], graph_data: dict, max_depth: int = 2, allowed_relations: set = None) -> dict:
    nodes_by_id = {n["id"]: n for n in graph_data.get("nodes", [])}
    edges = graph_data.get("edges", [])

    # สร้าง Adjacency List สำหรับกราฟแบบมีทิศทางและไร้ทิศทาง
    adj = defaultdict(list)
    for edge in edges:
        s = edge["source"]
        t = edge["target"]
        rel = edge.get("relation", "links_to")
        if allowed_relations and rel not in allowed_relations and rel != "links_to":
            continue
        adj[s].append((t, rel, edge.get("confidence", 1.0), "outgoing"))
        adj[t].append((s, rel, edge.get("confidence", 1.0), "incoming"))

    visited_nodes = set(anchor_ids)
    subgraph_nodes = {nid: nodes_by_id.get(nid, {"id": nid, "label": nid, "type": "Concept"}) for nid in anchor_ids}
    subgraph_edges = []
    reasoning_paths = []

    # BFS Traversal
    queue = deque([(nid, 0, [nid]) for nid in anchor_ids])

    while queue:
        curr_node, depth, path = queue.popleft()
        if depth >= max_depth:
            continue

        for neighbor, rel, conf, direction in adj.get(curr_node, []):
            edge_repr = {
                "source": curr_node if direction == "outgoing" else neighbor,
                "target": neighbor if direction == "outgoing" else curr_node,
                "relation": rel,
                "confidence": conf,
                "direction": direction
            }
            
            # หลีกเลี่ยง duplicate edges
            if not any(e["source"] == edge_repr["source"] and e["target"] == edge_repr["target"] and e["relation"] == rel for e in subgraph_edges):
                subgraph_edges.append(edge_repr)

            if neighbor not in visited_nodes:
                visited_nodes.add(neighbor)
                subgraph_nodes[neighbor] = nodes_by_id.get(neighbor, {"id": neighbor, "label": neighbor, "type": "Concept"})
                new_path = path + [f"──({rel})──►" if direction == "outgoing" else f"◄──({rel})───", neighbor]
                reasoning_paths.append(new_path)
                queue.append((neighbor, depth + 1, path + [neighbor]))

    return {
        "anchors": anchor_ids,
        "nodes": list(subgraph_nodes.values()),
        "edges": subgraph_edges,
        "reasoning_paths": reasoning_paths
    }

def format_terminal_output(query: str, anchors: list[dict], subgraph: dict):
    icon_map = {
        "Architecture": "🏗️",
        "Pattern": "🧩",
        "Techstack": "💻",
        "TechStack": "💻",
        "Playbook": "🛠️",
        "Cheatsheet": "⚡",
        "Decision": "⚖️",
        "Summary": "📄",
        "Synthesis": "💡",
        "Concept": "🧠",
        "Entity": "🏛️"
    }

    print(f"\n🧠 Dev Brain Multi-Hop Traversal Search: \"{query}\"")
    print("=" * 75)

    if not anchors:
        print("❌ ไม่พบความรู้ที่ตรงกับคำค้นหาใน Dev Brain")
        return

    print(f"🎯 จุดเกาะเกี่ยวหลัก (Anchor Nodes Found: {len(anchors)}):")
    for idx, r in enumerate(anchors, 1):
        type_icon = icon_map.get(r["type"], "📄")
        print(f" {idx}. {type_icon} [{r['type']}] [[{r['id']}]]  (Score: {r['score']})")
        if r.get("path"):
            print(f"    📂 File: {r['path']}")
        if r.get("snippet"):
            print(f"    📝 Snippet: {r['snippet']}")

    if subgraph and subgraph.get("edges"):
        print("\n🕸️ โครงข่ายความสัมพันธ์เชิงความหมาย (Semantic Subgraph Neighborhood):")
        print("-" * 75)
        for edge in subgraph.get("edges", [])[:12]:
            s_type = icon_map.get(edge.get("source_type", ""), "")
            print(f"  • [[{edge['source']}]] ──[{edge['relation']} (conf: {edge.get('confidence', 1.0):.2f})]──► [[{edge['target']}]]")

        if subgraph.get("reasoning_paths"):
            print("\n🛤️ เส้นทางอนุมานเชิงเหตุผล (Reasoning Chains):")
            for path in subgraph.get("reasoning_paths", [])[:6]:
                formatted_path = " ".join([f"[[{p}]]" if not p.startswith("─") and not p.startswith("◄") else p for p in path])
                print(f"  🔗 {formatted_path}")

    print("=" * 75)

def format_llm_context(query: str, anchors: list[dict], subgraph: dict) -> str:
    """จัดรูปแบบ Context Subgraph สำหรับส่งให้ AI Agent นำไปประมวลผลต่อ"""
    lines = [
        f"# Dev Brain Knowledge Context for Query: '{query}'",
        "",
        "## 1. Primary Anchor Documents",
    ]
    for a in anchors:
        lines.append(f"- **[[{a['id']}]]** ({a['type']}): {a.get('snippet', '')} (Path: `{a.get('path', '')}`)")

    lines.append("\n## 2. Connected Semantic Relations & Knowledge Paths")
    if subgraph and subgraph.get("edges"):
        for edge in subgraph.get("edges", []):
            lines.append(f"- `[[{edge['source']}]]` --[{edge['relation']}]--> `[[{edge['target']}]]`")

    lines.append("\n## 3. Inferred Reasoning Paths")
    if subgraph and subgraph.get("reasoning_paths"):
        for p in subgraph.get("reasoning_paths", []):
            lines.append(f"- {' '.join(p)}")

    return "\n".join(lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dev Brain Multi-Hop Graph Traversal & Search Engine")
    parser.add_argument("query", nargs="*", help="คำหรือประเด็นปัญหาที่ต้องการค้นหา")
    parser.add_argument("--top", type=int, default=5, help="จำนวนผลลัพธ์ Anchor หลัก (ค่าเริ่มต้น 5)")
    parser.add_argument("--depth", type=int, default=2, help="ความลึกในการเดิน Graph Traversal (ค่าเริ่มต้น 2)")
    parser.add_argument("--relation", type=str, default="", help="กรองเฉพาะประเภท relation เช่น solves,mitigates,commonly_causes")
    parser.add_argument("--traverse", action="store_true", default=True, help="เปิดใช้งาน Multi-Hop Graph Traversal (ค่าเริ่มต้นเปิด)")
    parser.add_argument("--json", action="store_true", help="ส่งออกผลลัพธ์เป็น JSON สำหรับ Subagent/API")
    parser.add_argument("--context", action="store_true", help="ส่งออกเฉพาะ LLM context string")
    args = parser.parse_args()

    query_str = " ".join(args.query).strip()
    if not query_str:
        query_str = input("🔍 ป้อนคำหรือปัญหาที่ต้องการสืบค้นใน Dev Brain: ").strip()

    if not query_str:
        print("กรุณาระบุคำค้นหา เช่น: python scripts/search_wiki.py 'PostgreSQL Connection Leak' --depth 2")
        sys.exit(0)

    index_data, graph_data = load_graph_and_index()
    anchors = search_anchors(query_str, index_data, top_k=args.top)
    
    subgraph = {}
    if args.traverse and anchors:
        anchor_ids = [a["id"] for a in anchors]
        allowed_rel = set(args.relation.split(",")) if args.relation else None
        subgraph = traverse_subgraph(anchor_ids, graph_data, max_depth=args.depth, allowed_relations=allowed_rel)

    if args.json:
        out = {
            "query": query_str,
            "anchors": anchors,
            "subgraph": subgraph
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif args.context:
        print(format_llm_context(query_str, anchors, subgraph))
    else:
        format_terminal_output(query_str, anchors, subgraph)

