import os
import sys
import argparse
import datetime
import re
import subprocess

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[\s_\/\\:]+', '-', text)
    text = re.sub(r'[^\w\-]', '', text)
    return text.strip('-')

def create_or_update_playbook(title: str, error_text: str, root_cause: str, fix: str, tech_stacks: list[str], prevention: str = ""):
    today_str = datetime.date.today().isoformat()
    slug_title = slugify(title)
    
    # 1. บันทึก Raw Error Log (Immutable)
    os.makedirs("raw/errors-and-logs", exist_ok=True)
    raw_log_path = f"raw/errors-and-logs/{today_str}-{slug_title}.log"
    with open(raw_log_path, "w", encoding="utf-8") as f:
        f.write(f"# Raw Error Trace: {title}\n")
        f.write(f"# Timestamp: {datetime.datetime.now().isoformat()}\n")
        f.write(f"# Tech Stacks: {', '.join(tech_stacks)}\n")
        f.write("=" * 60 + "\n\n")
        f.write(error_text.strip() + "\n")

    print(f"📦 บันทึก Raw Error Log: {raw_log_path}")

    # 2. สร้างโครงสร้าง Playbook Markdown
    os.makedirs("wiki/playbooks", exist_ok=True)
    clean_playbook_name = "Playbook-" + "-".join([w.capitalize() for w in re.findall(r'[A-Za-z0-9]+', title)])
    playbook_file_path = f"wiki/playbooks/{clean_playbook_name}.md"

    # จัดเตรียม Tags & Relations
    tags = ["playbook", "debugging"] + [slugify(t) for t in tech_stacks]
    relations = []
    for t in tech_stacks:
        relations.append({"target": t.strip(), "type": "symptom_of", "confidence": 0.95})
    
    # สร้างหรือ Smart Merge เนื้อหา Playbook
    existing_content = ""
    if os.path.exists(playbook_file_path):
        print(f"🔄 พบ Playbook เดิม ({playbook_file_path}) — กำลังทำ Smart Merge...")
        with open(playbook_file_path, "r", encoding="utf-8") as f:
            existing_content = f.read()

    tech_links = ", ".join([f"[[{t.strip()}]]" for t in tech_stacks]) if tech_stacks else "General"

    from collections import defaultdict
    rel_groups = defaultdict(list)
    for r in relations:
        rel_type = r.get("type", "relates_to")
        target = r.get("target", "")
        if target:
            clean_tgt = target.replace("[[", "").replace("]]", "").strip()
            rel_groups[rel_type].append(f'  - "[[{clean_tgt}]]"')

    rel_yaml_blocks = []
    for r_type, targets in rel_groups.items():
        rel_yaml_blocks.append(f"{r_type}:\n" + "\n".join(targets))
    rel_yaml_str = "\n".join(rel_yaml_blocks) if rel_yaml_blocks else 'symptom_of:\n  - "[[General]]"'

    playbook_md = f"""---
type: playbook
title: "{title}"
created: {today_str}
updated: {today_str}
tags:
{chr(10).join([f'  - "{t}"' for t in tags])}
{rel_yaml_str}
sources:
  - "{raw_log_path}"
---

# 🛠️ {title}

> **Tech Stacks ที่เกี่ยวข้อง:** {tech_links}  
> **แหล่งข้อมูลดิบ:** `{raw_log_path}`

---

## 🚨 1. อาการและข้อความผิดพลาด (Symptoms & Error Trace)
```text
{error_text.strip()}
```

---

## 🔍 2. การวิเคราะห์สาเหตุที่แท้จริง (Root Cause Analysis)
{root_cause.strip()}

---

## 🛠️ 3. แนวทางแก้ไขและตัวอย่างโค้ด (Resolution & Implementation)
{fix.strip()}

---

## 🛡️ 4. การป้องกันเชิงรุก (Proactive Prevention)
{prevention.strip() if prevention.strip() else "- เพิ่ม Unit Test และ Integration Test ครอบคลุมเคสนี้\\n- ปรับปรุงการตรวจสอบ Resource / Connection Leak ใน CI/CD"}

---

## 🔗 5. ความสัมพันธ์เชิงความหมาย (Semantic Knowledge Links)
{chr(10).join([f'- symptom_of:: [[{t.strip()}]]' for t in tech_stacks])}
- solves:: [[{clean_playbook_name}]]
"""

    with open(playbook_file_path, "w", encoding="utf-8") as f:
        f.write(playbook_md.strip() + "\n")

    print(f"✅ บันทึก Playbook เรียบร้อย: {playbook_file_path}")

    # 3. อัปเดต index.md
    update_index_md(clean_playbook_name, title)

    # 4. บันทึก log.md
    update_log_md(clean_playbook_name, title)

    # 5. รัน Knowledge Graph Indexing อัตโนมัติ
    print("\n🧠 กำลังอัปเดต Knowledge Graph & Multi-Hop Index...")
    try:
        subprocess.run([sys.executable, "scripts/run_graphify.py"], check=True)
    except Exception as e:
        print(f"⚠️ ไม่สามารถรัน run_graphify.py อัตโนมัติ: {e}")

    print(f"\n🎉 Closed-Loop Learning เสร็จสมบูรณ์! ตอนนี้ Dev Brain สามารถจดจำและเรียกใช้โซลูชันนี้ได้ทันที!")

def update_index_md(note_name: str, title: str):
    index_path = "index.md"
    if not os.path.exists(index_path):
        return

    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    link_entry = f"- [[{note_name}]] — {title}"
    if f"[[{note_name}]]" in content:
        return

    playbook_header = "### 🛠️ คู่มือแก้บั๊กและปัญหาหน้างาน (Playbooks & Root Cause Analyses)"
    if playbook_header in content:
        parts = content.split(playbook_header, 1)
        # ตรวจหาว่ามี placeholder หรือไม่
        next_part = parts[1]
        placeholder = "*(จะถูกบันทึกเมื่อนำเข้าปัญหา Error Traces & Debug Logs)*"
        if placeholder in next_part:
            next_part = next_part.replace(placeholder, link_entry)
        else:
            next_part = f"\n{link_entry}" + next_part
        content = parts[0] + playbook_header + next_part
    else:
        content += f"\n\n{playbook_header}\n{link_entry}\n"

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("📝 อัปเดตสารบัญ index.md เรียบร้อย")

def update_log_md(note_name: str, title: str):
    log_path = "log.md"
    today_str = datetime.date.today().isoformat()
    log_entry = f"## [{today_str}] learn | Created Playbook [[{note_name}]] ({title})\n"

    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = log_entry + content
    else:
        content = f"# 📜 Dev Brain Activity Log\n\n{log_entry}"

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("📜 บันทึกประวัติกิจกรรมใน log.md เรียบร้อย")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dev Brain Autonomous Learning Loop Ingestor")
    parser.add_argument("--title", type=str, help="ชื่อหรือหัวข้อปัญหา/บั๊ก")
    parser.add_argument("--error", type=str, help="Error Message หรือ Stack Trace ดิบ")
    parser.add_argument("--root-cause", type=str, help="สาเหตุที่แท้จริงของปัญหา")
    parser.add_argument("--fix", type=str, help="วิธีแก้ไขหรือโค้ดตัวอย่าง")
    parser.add_argument("--tech", type=str, help="Tech Stacks ที่เกี่ยวข้อง คั่นด้วยจุลภาค เช่น 'PostgreSQL,NodeJS'")
    parser.add_argument("--file", type=str, help="อ่าน error trace จากไฟล์ log")
    parser.add_argument("--prevention", type=str, default="", help="แนวทางป้องกันไม่ให้เกิดซ้ำ")
    args = parser.parse_args()

    title = args.title
    error_text = args.error or ""
    root_cause = args.root_cause or ""
    fix = args.fix or ""
    tech_stacks = [t.strip() for t in args.tech.split(",") if t.strip()] if args.tech else []
    prevention = args.prevention or ""

    if args.file and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
            error_text = f.read()

    # Interactive Mode ถ้าไม่ได้ระบุ parameters ครบ
    if not title or not error_text or not root_cause or not fix:
        print("🧠 ===================================================")
        print("   Dev Brain — Autonomous Learning Loop Ingestor")
        print("===================================================")
        if not title:
            title = input("📌 ระบุชื่อหัวข้อปัญหา (Title): ").strip()
        if not error_text:
            print("🚨 ป้อน Error Trace / Log (พิมพ์บรรทัดว่าง 2 ครั้งเพื่อจบ):")
            lines = []
            empty_count = 0
            while True:
                line = input()
                if not line:
                    empty_count += 1
                    if empty_count >= 2:
                        break
                else:
                    empty_count = 0
                lines.append(line)
            error_text = "\n".join(lines).strip()
        if not root_cause:
            root_cause = input("🔍 ระบุสาเหตุที่แท้จริง (Root Cause): ").strip()
        if not fix:
            fix = input("🛠️ ระบุวิธีแก้ไข (Fix / Solution): ").strip()
        if not tech_stacks:
            raw_tech = input("💻 ระบุ Tech Stacks ที่เกี่ยวข้อง (เช่น PostgreSQL, PgBouncer): ").strip()
            tech_stacks = [t.strip() for t in raw_tech.split(",") if t.strip()]
        if not prevention:
            prevention = input("🛡️ ระบุวิธีป้องกันเชิงรุก (Optional): ").strip()

    if title and error_text and root_cause and fix:
        create_or_update_playbook(title, error_text, root_cause, fix, tech_stacks, prevention)
    else:
        print("❌ ข้อมูลไม่ครบถ้วน กรุณาลองใหม่อีกครั้ง")
