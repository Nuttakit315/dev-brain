import os
import sys
import json
import glob
import re
import math
from collections import Counter, defaultdict

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SEMANTIC_RELATION_PATTERNS = [
    (r'(?:^|\n)\s*[-*]?\s*(?:solves|แก้ปัญหา|แก้บั๊ก)::\s*\[\[(.*?)\]\]', "solves", 0.95),
    (r'(?:^|\n)\s*[-*]?\s*(?:mitigates|บรรเทา|ป้องกัน)::\s*\[\[(.*?)\]\]', "mitigates", 0.90),
    (r'(?:^|\n)\s*[-*]?\s*(?:commonly_causes|causes|ก่อให้เกิด|สาเหตุ)::\s*\[\[(.*?)\]\]', "commonly_causes", 0.90),
    (r'(?:^|\n)\s*[-*]?\s*(?:symptom_of|อาการของ)::\s*\[\[(.*?)\]\]', "symptom_of", 0.90),
    (r'(?:^|\n)\s*[-*]?\s*(?:uses|depends_on|ใช้งาน|ขึ้นกับ)::\s*\[\[(.*?)\]\]', "uses", 0.85),
    (r'(?:^|\n)\s*[-*]?\s*(?:alternative_to|ทางเลือกอื่น|เปรียบเทียบ)::\s*\[\[(.*?)\]\]', "alternative_to", 0.90),
    (r'(?:^|\n)\s*[-*]?\s*(?:implements|implement_of|สร้างตาม)::\s*\[\[(.*?)\]\]', "implements", 0.90),
    (r'(?:^|\n)\s*[-*]?\s*(?:part_of|ส่วนหนึ่งของ)::\s*\[\[(.*?)\]\]', "part_of", 0.85),
]

def tokenize(text: str) -> list[str]:
    """
    Enhanced Multilingual & Code-aware Tokenizer:
    1. ตัด Markdown tags และ Wikilinks
    2. ทำความสะอาดเครื่องหมายพิเศษ แต่คงตัวระบุ code/terms
    3. สำหรับภาษาไทย สกัด N-grams เสริม
    """
    text = text.lower()
    text = re.sub(r'\[\[(.*?)\]\]', r'\1', text)
    text = re.sub(r'[#*`_~>\-\[\]\(\)\{\}\:\.\,\!\?]', ' ', text)
    
    raw_tokens = re.findall(r'[\u0E00-\u0E7Fa-zA-Z0-9_]+', text)
    tokens = []

    for t in raw_tokens:
        if len(t) <= 1:
            continue
        tokens.append(t)
        
        if re.search(r'[\u0E00-\u0E7F]', t) and len(t) > 6:
            for n in [3, 4, 5]:
                for i in range(len(t) - n + 1):
                    tokens.append(t[i:i+n])

    return tokens

def parse_frontmatter(content: str) -> tuple[dict, str]:
    content = content.lstrip('\ufeff').strip()
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    
    fm_text = parts[1].strip()
    body_text = parts[2].strip()
    
    fm_data = {}
    try:
        import yaml
        loaded = yaml.safe_load(fm_text)
        if isinstance(loaded, dict):
            fm_data = loaded
    except Exception:
        # Fallback simple parser
        current_key = None
        for line in fm_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- ") and current_key:
                val = line[2:].strip().strip('"').strip("'")
                fm_data.setdefault(current_key, []).append(val)
            elif ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if v:
                    fm_data[k] = v.strip('"').strip("'")
                    current_key = None
                else:
                    current_key = k
                    fm_data[k] = []

    return fm_data, body_text

def get_doc_type(clean_path: str) -> str:
    if "/architecture/" in clean_path:
        return "Architecture"
    elif "/patterns/" in clean_path:
        return "Pattern"
    elif "/tech-stacks/" in clean_path:
        return "TechStack"
    elif "/playbooks/" in clean_path:
        return "Playbook"
    elif "/cheatsheets/" in clean_path:
        return "Cheatsheet"
    elif "/decisions/" in clean_path:
        return "Decision"
    elif "/projects/" in clean_path:
        return "Project"
    elif "/summaries/" in clean_path:
        return "Summary"
    elif "/synthesis/" in clean_path:
        return "Synthesis"
    elif "/concepts/" in clean_path:
        return "Concept"
    elif "/entities/" in clean_path:
        return "Entity"
    return "Document"

def infer_heuristic_relation(source_type: str, target_type: str, target_name: str) -> str:
    """ประเมินความสัมพันธ์อัตโนมัติแบบมีหลักการตามประเภทเอกสาร"""
    if source_type == "Playbook":
        if target_type == "TechStack":
            return "symptom_of"
        elif target_type in ["Pattern", "Architecture"]:
            return "mitigated_by"
        return "solves"
    elif source_type == "Pattern":
        if target_type == "TechStack":
            return "implements"
        elif target_type == "Architecture":
            return "part_of"
        return "implements"
    elif source_type == "Decision":
        return "alternative_to" if "vs" in target_name.lower() else "evaluates"
    elif source_type == "Project":
        if target_type == "TechStack":
            return "uses"
        elif target_type == "Architecture":
            return "implements"
    return "links_to"

def build_knowledge_graph_and_search_index():
    wiki_files = glob.glob("wiki/**/*.md", recursive=True) + glob.glob("wiki/*.md")
    wiki_files = list(set([f for f in wiki_files if not os.path.basename(f).startswith(".")]))
    
    nodes = []
    edges = []
    seen_nodes = {}
    in_degree = Counter()
    out_degree = Counter()
    
    documents_index = []
    all_doc_tokens = []
    doc_freq = Counter()

    print(f"🔍 เริ่มสแกนไฟล์ Markdown ใน Dev Brain wiki/ ทั้งหมด {len(wiki_files)} ไฟล์ (Schema v2.0)...")

    # Pass 1: สร้างโหนดจากไฟล์จริงทั้งหมด
    for file_path in wiki_files:
        doc_name = os.path.splitext(os.path.basename(file_path))[0]
        clean_path = file_path.replace("\\", "/")
        doc_type = get_doc_type(clean_path)

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            print(f"⚠️ ไม่สามารถอ่านไฟล์ {file_path}: {e}")
            continue

        fm, body = parse_frontmatter(content)
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]

        node_data = {
            "id": doc_name,
            "label": fm.get("title", doc_name),
            "type": fm.get("type", doc_type).capitalize(),
            "path": clean_path,
            "tags": tags,
            "created": str(fm.get("created", "")),
            "updated": str(fm.get("updated", ""))
        }
        seen_nodes[doc_name] = node_data

    # Pass 2: สกัด Typed Relations & Edges
    for file_path in wiki_files:
        doc_name = os.path.splitext(os.path.basename(file_path))[0]
        clean_path = file_path.replace("\\", "/")
        source_type = seen_nodes[doc_name]["type"]

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        fm, body = parse_frontmatter(content)
        extracted_edges_for_doc = []
        captured_targets = set()

        # 1. สกัดจาก YAML Frontmatter (ทั้งแบบ relations list และ top-level relation keys)
        REL_KEYS = ["depends_on", "part_of", "uses", "used_by", "solves", "mitigates", "mitigated_by", "commonly_causes", "symptom_of", "implements", "alternative_to"]
        for rk in REL_KEYS:
            targets = fm.get(rk, [])
            if isinstance(targets, str):
                targets = [targets]
            if isinstance(targets, list):
                for t in targets:
                    if isinstance(t, str):
                        clean_t = t.replace("[[", "").replace("]]", "").strip()
                        if clean_t and clean_t != doc_name and clean_t not in captured_targets:
                            captured_targets.add(clean_t)
                            extracted_edges_for_doc.append({
                                "source": doc_name,
                                "target": clean_t,
                                "relation": rk,
                                "confidence": 0.95,
                                "weight": 1.0,
                                "context": f"Frontmatter {rk}"
                            })

        fm_relations = fm.get("relations", [])
        if isinstance(fm_relations, list):
            for rel in fm_relations:
                if isinstance(rel, dict) and "target" in rel:
                    target_name = rel["target"].replace("[[", "").replace("]]", "").strip()
                    rel_type = rel.get("type", "links_to")
                    conf = float(rel.get("confidence", 0.95))
                    context = rel.get("context", "")
                    
                    if target_name and target_name != doc_name and target_name not in captured_targets:
                        captured_targets.add(target_name)
                        extracted_edges_for_doc.append({
                            "source": doc_name,
                            "target": target_name,
                            "relation": rel_type,
                            "confidence": conf,
                            "weight": 1.0,
                            "context": context
                        })

        # 2. สกัดจาก Inline Semantic Annotations (- relation:: [[Node]])
        for pattern, rel_type, conf in SEMANTIC_RELATION_PATTERNS:
            matches = re.findall(pattern, content, flags=re.IGNORECASE)
            for target_match in matches:
                clean_target = target_match.split("|")[0].split("#")[0].strip()
                if clean_target and clean_target != doc_name and clean_target not in captured_targets:
                    captured_targets.add(clean_target)
                    extracted_edges_for_doc.append({
                        "source": doc_name,
                        "target": clean_target,
                        "relation": rel_type,
                        "confidence": conf,
                        "weight": 0.9,
                        "context": f"Inline semantic relation: {rel_type}"
                    })

        # 3. สกัดจาก Regular [[Wikilinks]] ที่เหลือ (Heuristic Inference)
        raw_links = re.findall(r'\[\[(.*?)\]\]', content)
        for link in raw_links:
            clean_link = link.split("|")[0].split("#")[0].strip()
            if not clean_link or clean_link == doc_name or clean_link in captured_targets:
                continue

            target_type = seen_nodes.get(clean_link, {}).get("type", "Concept")
            inferred_rel = infer_heuristic_relation(source_type, target_type, clean_link)
            
            captured_targets.add(clean_link)
            extracted_edges_for_doc.append({
                "source": doc_name,
                "target": clean_link,
                "relation": inferred_rel,
                "confidence": 0.70,
                "weight": 0.7,
                "context": "Heuristic inference from wikilink"
            })

        # จัดการ Target Nodes ที่อาจยังไม่เคยมีใน Note
        for edge in extracted_edges_for_doc:
            tgt = edge["target"]
            if tgt not in seen_nodes:
                seen_nodes[tgt] = {
                    "id": tgt,
                    "label": tgt,
                    "type": "Concept",
                    "path": "",
                    "tags": [],
                    "created": "",
                    "updated": ""
                }
            edges.append(edge)
            out_degree[edge["source"]] += 1
            in_degree[edge["target"]] += 1

        # เตรียมข้อมูลสำหรับ Search Index
        clean_preview = re.sub(r'---[\s\S]*?---', '', content).strip()
        snippet = clean_preview[:250].replace("\n", " ").strip() + "..." if len(clean_preview) > 250 else clean_preview

        tokens = tokenize(content)
        token_counts = Counter(tokens)
        for t in set(tokens):
            doc_freq[t] += 1

        documents_index.append({
            "id": doc_name,
            "path": clean_path,
            "type": source_type,
            "snippet": snippet,
            "links": list(captured_targets),
            "token_counts": token_counts,
            "total_tokens": len(tokens)
        })
        all_doc_tokens.append(tokens)

    # คำนวณ Degrees & Centrality Score
    for node_id, node_data in seen_nodes.items():
        node_data["in_degree"] = in_degree[node_id]
        node_data["out_degree"] = out_degree[node_id]
        node_data["degree"] = in_degree[node_id] + out_degree[node_id]
        node_data["centrality_score"] = round(math.log(1 + node_data["degree"]), 3)
        nodes.append(node_data)

    os.makedirs("graph", exist_ok=True)

    # 1. บันทึก Knowledge Graph v2.0
    graph_data = {
        "schema_version": "2.0",
        "metadata": {
            "engine": "Dev Brain Semantic Knowledge Graph",
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "supported_relations": [
                "solves", "mitigates", "commonly_causes", "symptom_of",
                "uses", "depends_on", "alternative_to", "implements", "part_of", "links_to"
            ]
        },
        "nodes": nodes,
        "edges": edges
    }
    with open("graph/graph.json", "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)

    # 2. บันทึก Hybrid Lexical & TF-IDF Graph Search Index
    num_docs = max(1, len(documents_index))
    search_docs = []
    for doc in documents_index:
        tfidf = {}
        for token, count in doc["token_counts"].items():
            tf = count / max(1, doc["total_tokens"])
            idf = math.log((num_docs + 1) / (doc_freq[token] + 1)) + 1
            tfidf[token] = round(tf * idf, 4)

        node_meta = seen_nodes.get(doc["id"], {})
        search_docs.append({
            "id": doc["id"],
            "path": doc["path"],
            "type": doc["type"],
            "snippet": doc["snippet"],
            "links": doc["links"],
            "centrality_score": node_meta.get("centrality_score", 0.0),
            "tfidf": tfidf
        })

    search_index_data = {
        "schema_version": "2.0",
        "metadata": {
            "engine": "Dev Brain Hybrid Lexical & Semantic Graph Search Index",
            "total_documents": len(search_docs),
            "total_terms": len(doc_freq)
        },
        "documents": search_docs
    }
    with open("graph/search_index.json", "w", encoding="utf-8") as f:
        json.dump(search_index_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Dev Brain Graph & Search Indexing v2.0 เสร็จสมบูรณ์!")
    print(f"   📊 โหนดทั้งหมด (Nodes): {len(nodes)}")
    print(f"   🔗 เส้นเชื่อมเชิงความหมาย (Semantic Edges): {len(edges)}")
    print(f"   🔎 ดัชนีสืบค้น Hybrid Index: graph/search_index.json ({len(search_docs)} เอกสาร)")

if __name__ == "__main__":
    build_knowledge_graph_and_search_index()


