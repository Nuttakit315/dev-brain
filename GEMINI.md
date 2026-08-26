# 🧠 GEMINI.md — Dev Brain Agent Schema & Operating Protocol (v1.0)

เอกสารนี้คือ **Schema & Operating Manual** หลักสำหรับ AI Agent (Antigravity / Gemini / Claude / ChatGPT) ในการบริหารจัดการคลังความรู้การพัฒนาซอฟต์แวร์และการเขียนโค้ด (**Dev Brain / Engineering Second Brain v1.0**) ตามปรัชญา **LLM Wiki Pattern & Semantic Graph Reasoning (Developer Edition)**

---

## 🏛️ 1. สถาปัตยกรรม 4 เสาหลัก (The 4 Pillars of Dev Brain)

```mermaid
flowchart TD
    subgraph Ingest["1. Autonomous Learning Loop & Sources"]
        A1["Raw Articles & Docs<br>(raw/articles/)"]
        A2["Error Logs & Traces<br>(raw/errors-and-logs/)"]
        A3["Codebases & Repos<br>(raw/snippets/ & Repos)"]
        A2 -->|scripts/learn_error.py| B
        A3 -->|scripts/sync_projects.py| B
        A1 -->|Smart Ingest| B
    end

    subgraph Wiki["2. Dev Knowledge Base (wiki/)"]
        B["• architecture/ (System Design)<br>• patterns/ (Clean Code, Concurrency)<br>• tech-stacks/ (Languages, DBs, Frameworks)<br>• playbooks/ (Root Cause & Fix)<br>• cheatsheets/ (CLI, Commands, SQL)<br>• decisions/ (ADRs & Tech Comparisons)<br>• summaries/ & synthesis/"]
    end

    subgraph Graph["3. Typed Semantic Graph & Search (graph/)"]
        B -->|scripts/run_graphify.py| G["graph/graph.json (Schema v2.0)<br>• Typed Edges: solves, causes, uses, alternative_to<br>• Confidence & Edge Weights"]
        B -->|Indexer| SI["graph/search_index.json<br>• Hybrid TF-IDF & Node Centrality Boost"]
    end

    subgraph Agent["4. Multi-Hop Graph Traversal & Co-Pilot"]
        SI & G -->|scripts/search_wiki.py --traverse| R["Multi-Hop Subgraph Retrieval<br>(Anchor Finding -> BFS Traversal -> Reasoning Path)"]
        R --> AGT["AI Agent (Antigravity / Co-Pilot)<br>• Synthesizes Answer with Graph Provenance<br>• Closed-Loop Self-Healing"]
        AGT -.->|Feedback / New Playbook| A2
    end
```

---

## ⚙️ 2. กฎเหล็กในการทำงานของ Dev Brain Agent (Core Rules)

1. **AI เป็นผู้ดูแลและเขียน Dev Wiki (AI-Maintained)**: เมื่อผู้ใช้ป้อนโค้ด, บทความ, หรือถามวิธีแก้บั๊ก AI มีหน้าที่สกัด, สรุป, จัดหมวดหมู่, และอัปเดตข้ามหน้าทันที
2. **Graph-First Retrieval Before Answering**: ก่อนตอบคำถามเชิงสถาปัตยกรรมหรือวิธีแก้บั๊ก AI ควรสืบค้นความรู้เดิมใน Dev Brain ผ่าน `python scripts/search_wiki.py "<query>" --traverse` เพื่อดึง Subgraph และประสบการณ์ที่เคยบันทึกไว้มาใช้
3. **Typed Semantic Relationships**: ทุกหน้าที่สร้างหรือแก้ไข ควรกำหนดความสัมพันธ์แบบมีประเภท (Typed Relations) ผ่าน YAML Frontmatter `relations:` หรือ Inline syntax (`- solves:: [[...]]`, `- symptom_of:: [[...]]`, `- alternative_to:: [[...]]`, `- uses:: [[...]]`)
4. **Evergreen Smart Merging (Anti-Data-Loss)**: เมื่อมีเทคนิคหรือข้อมูลใหม่ **ต้องทำการ Smart Merge หลอมรวมเนื้อหาเข้ากับหน้าเดิม** โดยรักษาโค้ดและข้อเท็จจริงเดิมไว้ครบถ้วน ห้ามเขียนทับจนข้อมูลสูญหาย
5. **Cross-Referencing ด้วย `[[Wikilinks]]`**: เชื่อมโยงบริบทข้ามเทคโนโลยีเพื่อให้ Obsidian Graph View และ AI Traversal ทำงานได้อย่างเต็มประสิทธิภาพ
6. **Continuous Indexing & Linting**:
   - อัปเดต `index.md` เสมอเมื่อมีหน้าใหม่หรือสาระสำคัญเปลี่ยน
   - บันทึกกิจกรรมลงใน `log.md` ในรูปแบบ `## [YYYY-MM-DD] action | Details` เสมอ
   - รัน Linter `python scripts/lint_wiki.py` และ `python scripts/run_graphify.py` ทุกครั้งหลังอัปเดต
7. **Autonomous Environment Bootstrap & Zero-Dependency Runtime**: คลังสมอง Dev Brain ถูกออกแบบมาให้ทำงานด้วย **Python Standard Library ล้วน (Zero External Dependencies)** จึงไม่ต้องใช้คำสั่ง `pip install` ใด ๆ ทั้งสิ้น หากตรวจสอบพบว่าเครื่องปลายทางยังไม่ได้ติดตั้ง Python ให้ Agent ดำเนินการติดตั้ง Python 3.12 อัตโนมัติทันทีผ่าน Package Manager ของระบบปฏิบัติการ (เช่น `winget install Python.Python.3.12 --silent` บน Windows, `brew install python3` บน macOS, หรือ `apt install -y python3` บน Linux) แล้วเริ่มทำงานต่อได้ทันทีโดยไม่ต้องรอให้ผู้ใช้ลงมือเอง


---

## 🔄 3. มาตรฐานขั้นตอนการทำงาน (Workflows)

### 📥 3.1 The Autonomous Learning Loop (เมื่อพบปัญหา / Error Trace)
1. **Trigger Ingestion**: รัน `python scripts/learn_error.py` หรือบันทึกลง `raw/errors-and-logs/`
2. **Auto-Generate Playbook**: สกัด Symptoms, Root Cause, Fix Code และ Best Practice
3. **Assign Typed Relations**:
   - `- symptom_of:: [[TechStack-Name]]`
   - `- solves:: [[Playbook-Name]]`
   - `- mitigated_by:: [[Pattern-or-Tool]]`
4. **Re-index Graph**: รัน `python scripts/run_graphify.py` เพื่อให้สมองจำได้ทันที

### 🔍 3.2 การตอบคำถามและการสืบค้น (Query & Co-pilot)
1. สกัด Keyword และ Intent ของคำถาม
2. รัน `python scripts/search_wiki.py "<query>" --traverse --depth 2`
3. เดินตาม Reasoning Chain เพื่อดึง Playbook และ Pattern ที่เกี่ยวข้อง
4. ตอบคำถามพร้อมอ้างอิง `[[Wikilinks]]` และโค้ดตัวอย่างที่ตรงกับบริบทของระบบ

---

## 📝 4. ข้อกำหนดความสัมพันธ์เชิงความหมาย (Standard Relation Vocabulary)

| Relation | ความหมาย | ตัวอย่างการใช้งาน |
| :--- | :--- | :--- |
| `solves` | แก้ไขปัญหาหรือบั๊กนี้โดยตรง | `Playbook-PostgreSQL-Connection-Leak` ──solves──► `Connection-Timeout` |
| `mitigates` / `mitigated_by` | บรรเทาหรือป้องกันไม่ให้เกิด | `PostgreSQL-Connection-Leak` ──mitigated_by──► `PgBouncer` |
| `commonly_causes` | เทคโนโลยีหรือการกระทำนี้มักก่อให้เกิดปัญหานี้ | `Unclosed-Connection` ──commonly_causes──► `Connection-Pool-Exhaustion` |
| `symptom_of` | เป็นอาการที่แสดงออกของปัญหานี้ | `High-CPU-Spike` ──symptom_of──► `Infinite-Re-render` |
| `uses` / `depends_on` | เรียกใช้งานหรือขึ้นต่อกัน | `ScoAPI` ──uses──► `PostgreSQL` |
| `alternative_to` | เป็นทางเลือกทดแทนซึ่งกันและกัน | `Drizzle-ORM` ──alternative_to──► `Prisma` |
| `implements` | นำ Pattern หรือ Architecture ไปสร้างจริง | `UserService` ──implements──► `Repository-Pattern` |

---

## 📝 5. เทมเพลตมาตรฐานสำหรับ Dev Notes (Schema v2.0)

```markdown
---
type: playbook # architecture, pattern, tech-stack, playbook, cheatsheet, decision, summary, synthesis
title: "PostgreSQL Connection Pool Exhaustion Fix"
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags:
  - database
  - postgresql
  - performance
relations:
  - target: "PostgreSQL"
    type: "symptom_of"
    confidence: 0.95
  - target: "PgBouncer"
    type: "mitigated_by"
    confidence: 0.95
sources:
  - "raw/errors-and-logs/YYYY-MM-DD-postgres-pool.log"
---

# 🛠️ PostgreSQL Connection Pool Exhaustion Fix

## 🚨 1. อาการและข้อความผิดพลาด (Symptoms & Error Trace)
...

## 🔍 2. การวิเคราะห์สาเหตุที่แท้จริง (Root Cause Analysis)
...

## 🛠️ 3. แนวทางแก้ไขและตัวอย่างโค้ด (Resolution & Implementation)
...

## 🔗 4. ความสัมพันธ์เชิงความหมาย (Semantic Knowledge Links)
- symptom_of:: [[PostgreSQL]]
- mitigated_by:: [[PgBouncer]]
- solves:: [[PostgreSQL-Connection-Pool-Exhaustion-Fix]]
```

---

## 🎯 6. ปฏิญญาของ Dev Brain Agent
> *"ฉันจะรักษาทุกบทเรียนการเขียนโค้ด สถาปัตยกรรมระบบ และสูตรการแก้บั๊ก เพื่อให้ Dev Brain แห่งนี้พัฒนาเป็นสุดยอดคลังสมองวิศวกรรมซอฟต์แวร์ที่ไม่เคยลืม"*

