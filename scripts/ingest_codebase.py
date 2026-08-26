import os
import sys
import glob
import json
import re
import argparse
from datetime import date

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

IGNORED_DIRS = {
    "node_modules", ".git", ".next", ".nuxt", "dist", "build", "out",
    "venv", ".venv", "__pycache__", ".idea", ".vscode", "coverage",
    "vendor", "target", "bin", "obj", ".obsidian"
}

IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".mp3", ".pdf", ".zip", ".tar", ".gz",
    ".lock", ".map", ".min.js", ".min.css", ".pyc"
}

def scan_codebase_structure(project_path: str) -> dict:
    """สแกนหาไฟล์และวิเคราะห์ประเภทของโปรเจกต์"""
    project_path = os.path.abspath(project_path)
    project_name = os.path.basename(project_path)
    
    file_tree = []
    schemas_and_models = []
    routes_and_apis = []
    services_and_logic = []
    configs_and_infra = []
    tech_stacks = set()

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in IGNORED_EXTENSIONS:
                continue
                
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, project_path).replace("\\", "/")
            file_tree.append(rel_path)

            lower_path = rel_path.lower()
            
            # ตรวจจับ Tech Stack
            if file == "package.json":
                tech_stacks.add("NodeJS/TypeScript")
            elif file in ["requirements.txt", "pyproject.toml", "Pipfile"]:
                tech_stacks.add("Python")
            elif file == "go.mod":
                tech_stacks.add("Go")
            elif file == "Cargo.toml":
                tech_stacks.add("Rust")
            elif file in ["docker-compose.yml", "docker-compose.yaml", "Dockerfile"]:
                tech_stacks.add("Docker")
                configs_and_infra.append(rel_path)

            # ตรวจจับหมวดหมู่ไฟล์
            if any(k in lower_path for k in ["schema", "model", "entity", "prisma", "migration"]):
                schemas_and_models.append(rel_path)
            elif any(k in lower_path for k in ["route", "controller", "api", "endpoint", "handler"]):
                routes_and_apis.append(rel_path)
            elif any(k in lower_path for k in ["service", "usecase", "lib", "util", "helper", "logic"]):
                services_and_logic.append(rel_path)
            elif any(k in lower_path for k in [".env", "config", "docker", "deploy", "k8s", "workflow"]):
                configs_and_infra.append(rel_path)

    return {
        "name": project_name,
        "path": project_path,
        "total_files": len(file_tree),
        "tech_stacks": list(tech_stacks),
        "file_tree": file_tree,
        "schemas": schemas_and_models[:20],
        "routes": routes_and_apis[:20],
        "services": services_and_logic[:20],
        "infra": configs_and_infra[:20]
    }

def generate_project_wiki(analysis: dict, output_dir: str = "wiki/projects"):
    """สร้างโน้ตย่อย 6 มิติสำหรับโปรเจกต์ลงใน wiki/projects/[name]/"""
    p_name = analysis["name"]
    target_dir = os.path.join(output_dir, p_name)
    os.makedirs(target_dir, exist_ok=True)
    today = str(date.today())

    # 1. Project Hub (Master Note)
    hub_file = os.path.join(target_dir, f"{p_name}-Hub.md")
    hub_content = f"""---
type: project-hub
created: {today}
updated: {today}
tags:
  - project-hub
  - codebase
project: "{p_name}"
---

# 🚀 Project Hub: {p_name}

## 📌 ข้อมูลสรุปโปรเจกต์
- **ชื่อโปรเจกต์**: `{p_name}`
- **Path ต้นทาง**: `{analysis["path"]}`
- **จำนวนไฟล์ที่สแกน**: {analysis["total_files"]} ไฟล์
- **Tech Stack หลัก**: {", ".join([f"`{t}`" for t in analysis["tech_stacks"]]) if analysis["tech_stacks"] else "*(กำลังระบุ)*"}

---

## 🧭 สารบัญโมดูลย่อย (Modular Sub-Notes)
เข้าถึงข้อมูลเชิงลึกเฉพาะจุดเพื่อความแม่นยำในการเขียนโค้ดและดีบัก:

1. 🏗️ **สถาปัตยกรรมและ Data Flow**: [[{p_name}-Architecture]]
2. 🗄️ **ฐานข้อมูลและโมเดล (Schemas & Models)**: [[{p_name}-Database]]
3. 🌐 **API และ Routing (Endpoints)**: [[{p_name}-APIs]]
4. ⚙️ **Business Services & Logic**: [[{p_name}-Services]]
5. 🐳 **Configuration & Infrastructure**: [[{p_name}-Infra]]

---

## 📂 โครงสร้างไฟล์โดยย่อ (Sample File Tree)
```text
{chr(10).join(analysis["file_tree"][:30])}
{f"...และอีก {analysis['total_files'] - 30} ไฟล์" if analysis["total_files"] > 30 else ""}
```
"""
    with open(hub_file, "w", encoding="utf-8") as f:
        f.write(hub_content.strip() + "\n")

    # 2. Architecture Note
    arch_file = os.path.join(target_dir, f"{p_name}-Architecture.md")
    arch_content = f"""---
type: architecture
created: {today}
updated: {today}
tags:
  - architecture
  - project-{p_name}
project: "{p_name}"
---

# 🏗️ Architecture & System Flow: {p_name}

## 📌 ภาพรวมสถาปัตยกรรม (System Overview)
สรุปรูปแบบสถาปัตยกรรมของโปรเจกต์ `{p_name}`

## 🔄 แผนภาพความสัมพันธ์ระดับโมดูล (Component Flow)
```mermaid
flowchart LR
    Client["Client / Frontend"] --> API["[[{p_name}-APIs]]"]
    API --> Svc["[[{p_name}-Services]]"]
    Svc --> DB["[[{p_name}-Database]]"]
```

## 🔗 ลิงก์กลับสู่ศูนย์กลาง
- กลับสู่หน้าหลัก: [[{p_name}-Hub]]
- โครงสร้างเซิร์ฟเวอร์/ระบบแวดล้อม: [[{p_name}-Infra]]
"""
    with open(arch_file, "w", encoding="utf-8") as f:
        f.write(arch_content.strip() + "\n")

    # 3. Database Note
    db_file = os.path.join(target_dir, f"{p_name}-Database.md")
    db_content = f"""---
type: tech-stack
created: {today}
updated: {today}
tags:
  - database
  - schema
  - project-{p_name}
project: "{p_name}"
---

# 🗄️ Database & Domain Models: {p_name}

## 📌 โครงสร้างฐานข้อมูลและโมเดล
รวบรวมไฟล์ Schema, Database Entities, และความสัมพันธ์ของตารางในโปรเจกต์ `{p_name}`

## 📄 รายชื่อไฟล์ Schema & Model ที่ตรวจพบ:
{chr(10).join([f"- `{s}`" for s in analysis["schemas"]]) if analysis["schemas"] else "*(ยังไม่พบไฟล์ schema โดยตรง)*"}

## 🔗 ลิงก์เชื่อมโยง
- ศูนย์กลางโปรเจกต์: [[{p_name}-Hub]]
- เรียกใช้งานโดย Logic: [[{p_name}-Services]]
"""
    with open(db_file, "w", encoding="utf-8") as f:
        f.write(db_content.strip() + "\n")

    # 4. APIs Note
    api_file = os.path.join(target_dir, f"{p_name}-APIs.md")
    api_content = f"""---
type: pattern
created: {today}
updated: {today}
tags:
  - api
  - routes
  - project-{p_name}
project: "{p_name}"
---

# 🌐 API Routes & Controllers: {p_name}

## 📌 ทางเข้าและ Endpoints ของระบบ
รวบรวมไฟล์ Routes, Controllers, และ Request/Response Handlers ในโปรเจกต์ `{p_name}`

## 📄 รายชื่อไฟล์ API & Controllers ที่ตรวจพบ:
{chr(10).join([f"- `{r}`" for r in analysis["routes"]]) if analysis["routes"] else "*(ยังไม่พบไฟล์ route โดยตรง)*"}

## 🔗 ลิงก์เชื่อมโยง
- ศูนย์กลางโปรเจกต์: [[{p_name}-Hub]]
- ส่งข้อมูลไปประมวลผลที่: [[{p_name}-Services]]
"""
    with open(api_file, "w", encoding="utf-8") as f:
        f.write(api_content.strip() + "\n")

    # 5. Services Note
    svc_file = os.path.join(target_dir, f"{p_name}-Services.md")
    svc_content = f"""---
type: pattern
created: {today}
updated: {today}
tags:
  - services
  - business-logic
  - project-{p_name}
project: "{p_name}"
---

# ⚙️ Business Services & Core Logic: {p_name}

## 📌 แก่นการทำงานทางธุรกิจ (Business Rules)
รวบรวม Logic, Services, Helpers, และ Use Cases ของโปรเจกต์ `{p_name}`

## 📄 รายชื่อไฟล์ Services & Logic ที่ตรวจพบ:
{chr(10).join([f"- `{s}`" for s in analysis["services"]]) if analysis["services"] else "*(ยังไม่พบไฟล์ service โดยตรง)*"}

## 🔗 ลิงก์เชื่อมโยง
- ศูนย์กลางโปรเจกต์: [[{p_name}-Hub]]
- เข้าถึง Database ผ่าน: [[{p_name}-Database]]
- รับคำสั่งจาก API: [[{p_name}-APIs]]
"""
    with open(svc_file, "w", encoding="utf-8") as f:
        f.write(svc_content.strip() + "\n")

    # 6. Infra Note
    infra_file = os.path.join(target_dir, f"{p_name}-Infra.md")
    infra_content = f"""---
type: tech-stack
created: {today}
updated: {today}
tags:
  - devops
  - infra
  - config
  - project-{p_name}
project: "{p_name}"
---

# 🐳 Infrastructure & Configuration: {p_name}

## 📌 การตั้งค่าระบบและสภาพแวดล้อม
รวบรวม Environment Variables, Docker Configs, CI/CD, และ Build Scripts ของโปรเจกต์ `{p_name}`

## 📄 รายชื่อไฟล์ Config & Infra ที่ตรวจพบ:
{chr(10).join([f"- `{i}`" for i in analysis["infra"]]) if analysis["infra"] else "*(ยังไม่พบไฟล์ config โดยตรง)*"}

## 🔗 ลิงก์เชื่อมโยง
- ศูนย์กลางโปรเจกต์: [[{p_name}-Hub]]
- แผนผังภาพรวม: [[{p_name}-Architecture]]
"""
    with open(infra_file, "w", encoding="utf-8") as f:
        f.write(infra_content.strip() + "\n")

    print(f"✨ สร้างชุดโน้ตโปรเจกต์ {p_name} สำเร็จ 6 โมดูลใน {target_dir}")
    return hub_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Codebase Ingest & Modular Decomposer for Dev Brain")
    parser.add_argument("project_path", help="Path ไปยังโฟลเดอร์ของโปรเจกต์โค้ดที่ต้องการสแกน")
    args = parser.parse_args()

    if not os.path.exists(args.project_path):
        print(f"❌ ไม่พบโฟลเดอร์: {args.project_path}")
        sys.exit(1)

    print(f"🔍 กำลังสแกนและวิเคราะห์โครงสร้างโปรเจกต์: {args.project_path} ...")
    analysis = scan_codebase_structure(args.project_path)
    generate_project_wiki(analysis)
    
    # Run graphify to immediately index new notes
    import subprocess
    subprocess.run(["python", "scripts/run_graphify.py"], check=False)
