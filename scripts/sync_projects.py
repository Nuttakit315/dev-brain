import os
import sys
import shutil
import subprocess
import argparse
import stat
import re
import json
from datetime import date
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

CACHE_DIR = ".cache/repos"
STATE_FILE = ".cache/sync_state.json"

IGNORED_DIRS = {
    "node_modules", ".git", ".next", ".nuxt", "dist", "build", "out",
    "venv", ".venv", "__pycache__", ".idea", ".vscode", "coverage",
    "vendor", "target", "bin", "obj", ".obsidian", ".cache"
}

IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".mp3", ".pdf", ".zip", ".tar", ".gz",
    ".lock", ".map", ".min.js", ".min.css", ".pyc"
}

def extract_project_name(target: str) -> str:
    """สกัดชื่อโปรเจกต์จาก Git URL หรือ Local Folder Path"""
    clean_target = target.strip().rstrip("/").rstrip("\\")
    if os.path.isdir(clean_target) or os.path.exists(clean_target):
        return os.path.basename(os.path.abspath(clean_target))
    if clean_target.endswith(".git"):
        clean_target = clean_target[:-4]
    name = clean_target.split("/")[-1].split("\\")[-1].split(":")[-1]
    return name

def extract_urls_from_markdown(content: str) -> list[dict]:
    """สกัด Git URLs และ Local Folder Paths จากไฟล์ Markdown (รองรับการตั้งชื่อ [Custom-Name](URL))"""
    targets = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            continue
        clean_line = re.sub(r"^[\-\*\d\.\s]+", "", line).strip()
        if not clean_line or clean_line.startswith("<!--") or clean_line.endswith("-->"):
            continue
        
        # 1. เช็ค Markdown Link [Custom-Name](url_or_path)
        md_match = re.search(r"\[([^\]]+)\]\((https?://[^\s\)]+|git@[^\s\)]+|[a-zA-Z]:[^\)\n]+|[/\.][^\)\n]+)\)", clean_line)
        if md_match:
            alias = md_match.group(1).strip()
            url_path = md_match.group(2).strip()
            targets.append({"target": url_path, "name": alias})
            continue

        # 2. เช็ค Git URL ทั่วไป
        raw_match = re.search(r"(https?://[^\s]+|git@[^\s]+)", clean_line)
        if raw_match:
            targets.append({"target": raw_match.group(1).strip(), "name": ""})
            continue

        # 3. เช็ค Local Path (เช่น C:/Projects/App หรือ D:\Code หรือ ./relative_dir)
        if os.path.exists(clean_line) or re.match(r"^[a-zA-Z]:[\\/]", clean_line) or clean_line.startswith(("./", "../", "/", "\\")):
            targets.append({"target": clean_line, "name": ""})

    return targets


from collections import defaultdict

INFRA_EXACT_NAMES = {
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", "render.yaml",
    "vercel.json", "netlify.toml", "web.config", ".editorconfig", ".dockerignore",
    ".gitignore", "package.json", "tsconfig.json", "requirements.txt", "pyproject.toml",
    "pipfile", "go.mod", "cargo.toml", "pom.xml", "build.gradle"
}

MODULE_CONTAINERS = [
    "pages/applications", "services/applications", "models/applications",
    "src/modules", "src/features", "src/components", "src/pages", "src/services", "src/models",
    "app/modules", "app/features", "app/controllers", "app/services", "app/models",
    "pkg", "modules", "controllers", "data"
]

SINGLE_MODULE_FOLDERS = {
    "pages/criteriaireport": "Reports & Criteria",
    "services/repository": "Core Repositories",
    "shared/component": "Shared Components",
    "pages/dialog": "Shared Dialogs",
    "models/dialog": "Dialog Models",
    "data/oracledata": "OracleData (Database Schema)",
    "data/dropdown": "Dropdown Options"
}

IGNORED_INJECTIONS = {
    "IJSRuntime", "NavigationManager", "HttpClient", "AuthenticationStateProvider",
    "ISnackbar", "IDialogService", "ILogger", "IConfiguration", "IWebHostEnvironment",
    "Radzen", "React", "Vue"
}

def extract_file_dependencies(file_path: str, ext: str) -> list[str]:
    """สกัดชื่อ Service หรือ Dependency ที่ไฟล์นั้นเรียกใช้งาน (Universal AST/Regex Parser)"""
    deps = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(30000)
            if ext in [".razor", ".cshtml", ".cs"]:
                injects = re.findall(r'@inject\s+([A-Za-z0-9_]+)', content)
                injects += re.findall(r'\[Inject\]\s+(?:protected|private|public)?\s*([A-Za-z0-9_<>]+)', content)
                injects += re.findall(r'\[FromServices\]\s+([A-Za-z0-9_<>]+)', content)
                
                # C# Constructor Dependency Injection: public SomeController(IService1 s1, IRepo r1)
                ctor_matches = re.findall(r'public\s+[A-Za-z0-9_]+\s*\(([^)]+)\)', content)
                for ctor in ctor_matches:
                    for param in ctor.split(","):
                        parts = param.strip().split()
                        if len(parts) >= 2:
                            p_type = parts[0].replace("?", "").strip()
                            if any(k in p_type.lower() for k in ["service", "repo", "context", "helper", "provider", "client", "processor", "manager", "db"]):
                                injects.append(p_type)
                
                # C# Field definitions: private readonly IUserService _userService;
                field_matches = re.findall(r'(?:private|protected)\s+(?:readonly\s+)?([A-Za-z0-9_<>]+)\s+[_a-zA-Z0-9]+;', content)
                for f_type in field_matches:
                    clean_f = f_type.replace("?", "").strip()
                    if any(k in clean_f.lower() for k in ["service", "repo", "context", "helper", "provider", "client", "processor", "manager", "db"]):
                        injects.append(clean_f)
                
                # Direct instantiations: new SomeService() / new SomeRepo()
                new_matches = re.findall(r'new\s+([A-Za-z0-9_]+Service|[A-Za-z0-9_]+Repo|[A-Za-z0-9_]+Repository)\s*\(', content)
                injects += new_matches

                for inj in injects:
                    clean_inj = inj.replace("?", "").replace("<", "").replace(">", "").strip()
                    if clean_inj and clean_inj not in IGNORED_INJECTIONS and len(clean_inj) > 2:
                        deps.append(clean_inj)

            elif ext in [".ts", ".tsx", ".js", ".jsx"]:
                imports = re.findall(r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]', content)
                for imp in imports:
                    if any(k in imp.lower() for k in ["service", "api", "repo", "store", "hook"]):
                        deps.append(imp.split("/")[-1])
            elif ext == ".py":
                imports = re.findall(r'(?:from|import)\s+([A-Za-z0-9_\.]+)', content)
                for imp in imports:
                    if any(k in imp.lower() for k in ["service", "repo", "crud", "api", "db"]):
                        deps.append(imp.split(".")[-1])
    except Exception:
        pass
    return sorted(list(dict.fromkeys(deps)))

def scan_codebase_structure(project_path: str, repo_url: str = "", custom_name: str = "") -> dict:
    """สแกนโครงสร้างโค้ดแบบ Universal Dynamic Module Discovery & Dependency Mapping (100% อัตโนมัติ)"""
    if not repo_url and os.path.exists(os.path.join(project_path, ".git")):
        try:
            res = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=project_path, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                repo_url = res.stdout.strip()
        except Exception:
            pass

    project_name = custom_name.strip() if custom_name else (extract_project_name(repo_url) if repo_url else os.path.basename(os.path.abspath(project_path)))
    file_tree = []
    infra_files = []
    modules = defaultdict(lambda: {"ui_pages": [], "dialogs": [], "services": [], "models": [], "other": []})
    page_dependencies = defaultdict(lambda: defaultdict(list))
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
            fname_lower = file.lower()
            parts = rel_path.split("/")

            # ตรวจจับ Tech Stack มาตรฐานสากล
            if file == "package.json":
                tech_stacks.add("TypeScript")
            elif file in ["requirements.txt", "pyproject.toml", "Pipfile"]:
                tech_stacks.add("Python")
            elif file == "go.mod":
                tech_stacks.add("Go")
            elif file == "Cargo.toml":
                tech_stacks.add("Rust")
            elif file.endswith(".csproj") or file.endswith(".sln"):
                tech_stacks.add("CSharp-DotNet")
            elif file.endswith(".razor"):
                tech_stacks.add("Blazor")
            elif file == "pom.xml" or file.endswith(".gradle"):
                tech_stacks.add("Java")

            if "docker" in fname_lower:
                tech_stacks.add("Docker")
            if "postgres" in lower_path or "npgsql" in lower_path:
                tech_stacks.add("PostgreSQL")
            if "mongo" in lower_path:
                tech_stacks.add("MongoDB")
            if "mysql" in lower_path:
                tech_stacks.add("MySQL")
            if "sqlite" in lower_path:
                tech_stacks.add("SQLite")
            if "redis" in lower_path:
                tech_stacks.add("Redis")
            if "dapper" in lower_path:
                tech_stacks.add("Dapper")
            if "prisma" in lower_path:
                tech_stacks.add("Prisma")

            # กรองไฟล์ Infrastructure & Config สากล
            is_infra = (
                fname_lower in INFRA_EXACT_NAMES or
                fname_lower.startswith("appsettings") or
                fname_lower.startswith(".env") or
                ".github" in lower_path or
                "deploy" in lower_path.split("/") or
                "k8s" in lower_path.split("/") or
                "terraform" in lower_path.split("/") or
                (ext in [".yml", ".yaml", ".sh", ".ps1"] and any(k in lower_path for k in ["ci", "cd", "deploy", "build", "pipeline"]))
            )
            if is_infra:
                infra_files.append(rel_path)
                continue

            # สกัดชื่อโมดูลแบบ Dynamic
            mod_name = None
            for sm_folder, sm_name in SINGLE_MODULE_FOLDERS.items():
                if lower_path.startswith(sm_folder):
                    mod_name = sm_name
                    break

            if not mod_name:
                for i in range(len(parts) - 1):
                    sub_prefix = "/".join(parts[:i+1]).lower()
                    for container in MODULE_CONTAINERS:
                        if sub_prefix == container:
                            if i + 1 < len(parts) - 1:
                                mod_name = parts[i+1] # เช่น Deposit, Finance, Loan, Auth, Billing
                            elif i + 1 < len(parts):
                                mod_name = parts[i]
                            break
                    if mod_name:
                        break

            if not mod_name:
                mod_name = parts[0] if len(parts) > 1 else "Root"

            # จัดประเภทไฟล์อย่างแม่นยำ
            is_controller = "controller" in lower_path or fname_lower.endswith("controller.cs") or fname_lower.endswith("endpoint.cs")
            if ext in [".razor", ".cshtml", ".vue", ".tsx", ".jsx", ".html"] or is_controller:
                if "dialog" in lower_path or "dlg" in fname_lower:
                    modules[mod_name]["dialogs"].append(rel_path)
                else:
                    modules[mod_name]["ui_pages"].append(rel_path)

            elif ext in [".cs", ".ts", ".js", ".py", ".go", ".rs", ".java", ".php", ".rb"]:
                if rel_path.endswith(".razor.cs"):
                    continue
                if any(k in lower_path for k in ["service", "logic", "usecase", "handler", "rule", "process", "repo"]):
                    modules[mod_name]["services"].append(rel_path)
                elif any(k in lower_path for k in ["model", "entity", "schema", "dto", "data", "table", "dbcontext"]):
                    modules[mod_name]["models"].append(rel_path)
                else:
                    modules[mod_name]["other"].append(rel_path)
            else:
                modules[mod_name]["other"].append(rel_path)

    # 🚀 Multi-Threaded Parallel Dependency Extraction
    dep_tasks = []
    for mod_name, m_data in modules.items():
        all_ui = m_data["ui_pages"] + m_data["dialogs"]
        for rel_f in all_ui:
            full_f = os.path.join(project_path, rel_f)
            ext = os.path.splitext(rel_f)[1].lower()
            base_p = os.path.splitext(os.path.basename(rel_f))[0]
            cs_behind = full_f + ".cs" if ext in [".razor", ".cshtml"] else ""
            dep_tasks.append((full_f, ext, mod_name, base_p, cs_behind))

    def _extract_task(task):
        f_path, f_ext, m_name, b_page, cs_b = task
        d = extract_file_dependencies(f_path, f_ext)
        if cs_b and os.path.exists(cs_b):
            d += extract_file_dependencies(cs_b, ".cs")
        clean_d = sorted(list(dict.fromkeys(d)))
        return m_name, b_page, clean_d

    if dep_tasks:
        max_workers = min(32, (os.cpu_count() or 4) * 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(_extract_task, dep_tasks)
            for m_name, b_page, clean_d in results:
                if clean_d:
                    page_dependencies[m_name][b_page] = clean_d

    sorted_modules = dict(sorted(
        modules.items(),
        key=lambda x: len(x[1]["ui_pages"]) + len(x[1]["dialogs"]) + len(x[1]["services"]) + len(x[1]["models"]),
        reverse=True
    ))

    return {
        "name": project_name,
        "repo_url": repo_url,
        "path": project_path,
        "total_files": len(file_tree),
        "tech_stacks": sorted(list(tech_stacks)),
        "file_tree": file_tree,
        "infra_files": sorted(list(dict.fromkeys(infra_files))),
        "modules": sorted_modules,
        "page_dependencies": page_dependencies
    }

def update_index_tech_stack(clean_name: str, display_name: str, index_path: str = "index.md"):
    """อัปเดต Tech Stack เข้าสู่ index.md อัตโนมัติ"""
    if not os.path.exists(index_path):
        return
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    tech_link = f"[[{clean_name}]]"
    tech_placeholder = "*(จะถูกสร้างอัตโนมัติเมื่อพบ Tech Stacks ในโปรเจกต์)*\n"
    if tech_link not in content:
        if tech_placeholder in content:
            content = content.replace(tech_placeholder, f"- {tech_link} — {display_name}\n")
        elif "### 💻 เทคโนโลยีและเครื่องมือ (Tech Stacks & Tools)\n" in content:
            content = content.replace(
                "### 💻 เทคโนโลยีและเครื่องมือ (Tech Stacks & Tools)\n",
                f"### 💻 เทคโนโลยีและเครื่องมือ (Tech Stacks & Tools)\n- {tech_link} — {display_name}\n"
            )
        elif "## 💻 เทคโนโลยีและเครื่องมือ (Tech Stacks & Tools)\n" in content:
            content = content.replace(
                "## 💻 เทคโนโลยีและเครื่องมือ (Tech Stacks & Tools)\n",
                f"## 💻 เทคโนโลยีและเครื่องมือ (Tech Stacks & Tools)\n- {tech_link} — {display_name}\n"
            )
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)

def ensure_tech_stack_note(tech: str, project_name: str, today: str):
    """สร้างโน้ตเทคโนโลยีส่วนกลางอัตโนมัติแบบ Organic พร้อม Typed Semantic Relations"""
    clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '', tech.replace(" ", "-").replace("/", "-").replace("#", "Sharp"))
    if not clean_name:
        return
    tech_file = os.path.join("wiki/tech-stacks", f"{clean_name}.md")
    if not os.path.exists(tech_file):
        content = f"""---
type: tech-stack
title: "{tech}"
created: {today}
updated: {today}
tags:
  - tech-stack
  - {clean_name.lower()}
used_by:
  - "[[{project_name}-Hub]]"
sources:
  - "[[{project_name}-Hub]]"
---

# 💻 {tech}

## 📌 ภาพรวมเทคโนโลยี (Overview)
บันทึกแนวคิด การตั้งค่า และ Best Practices ของ `{tech}` (ตรวจพบและสกัดมาจากโปรเจกต์ [[{project_name}-Hub]])

---

## 🔗 ความสัมพันธ์เชิงความหมาย (Semantic Knowledge Links)
- used_by:: [[{project_name}-Hub]]
"""
        with open(tech_file, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
        print(f"✨ สร้างโน้ตเทคโนโลยีส่วนกลางอัตโนมัติ: [[{clean_name}]]")
    update_index_tech_stack(clean_name, tech)

def generate_project_canvas(p_name: str, tech_links: list[str], analysis: dict):
    """สร้าง Obsidian JSON Canvas 1.0 อัตโนมัติสำหรับโปรเจกต์ (Visual Interactive Architecture)"""
    import json
    import random
    
    def gen_id():
        return f"{random.getrandbits(64):016x}"

    nodes = []
    edges = []

    # Hub Node (Center)
    hub_id = gen_id()
    nodes.append({
        "id": hub_id,
        "type": "file",
        "file": f"wiki/projects/{p_name}-Hub.md",
        "x": 400,
        "y": 0,
        "width": 380,
        "height": 260,
        "color": "6"
    })

    # Arch Node
    arch_id = gen_id()
    nodes.append({
        "id": arch_id,
        "type": "file",
        "file": f"wiki/architecture/{p_name}-Architecture.md",
        "x": 400,
        "y": 340,
        "width": 380,
        "height": 260,
        "color": "4"
    })
    edges.append({
        "id": gen_id(),
        "fromNode": hub_id,
        "fromSide": "bottom",
        "toNode": arch_id,
        "toSide": "top",
        "toEnd": "arrow",
        "label": "defines architecture"
    })

    # APIs Node (Left)
    api_id = gen_id()
    nodes.append({
        "id": api_id,
        "type": "file",
        "file": f"wiki/patterns/{p_name}-APIs.md",
        "x": -100,
        "y": 340,
        "width": 420,
        "height": 300,
        "color": "1"
    })
    edges.append({
        "id": gen_id(),
        "fromNode": arch_id,
        "fromSide": "left",
        "toNode": api_id,
        "toSide": "right",
        "toEnd": "arrow",
        "label": "routes & UI"
    })

    # Services Node (Middle)
    svc_id = gen_id()
    nodes.append({
        "id": svc_id,
        "type": "file",
        "file": f"wiki/patterns/{p_name}-Services.md",
        "x": 400,
        "y": 700,
        "width": 420,
        "height": 300,
        "color": "2"
    })
    edges.append({
        "id": gen_id(),
        "fromNode": api_id,
        "fromSide": "bottom",
        "toNode": svc_id,
        "toSide": "left",
        "toEnd": "arrow",
        "label": "calls logic"
    })

    # DB Node (Right)
    db_id = gen_id()
    nodes.append({
        "id": db_id,
        "type": "file",
        "file": f"wiki/tech-stacks/{p_name}-Database.md",
        "x": 900,
        "y": 700,
        "width": 420,
        "height": 300,
        "color": "5"
    })
    edges.append({
        "id": gen_id(),
        "fromNode": svc_id,
        "fromSide": "right",
        "toNode": db_id,
        "toSide": "left",
        "toEnd": "arrow",
        "label": "queries schema"
    })

    # Infra Node (Far Right Top)
    infra_id = gen_id()
    nodes.append({
        "id": infra_id,
        "type": "file",
        "file": f"wiki/cheatsheets/{p_name}-Infra.md",
        "x": 900,
        "y": 0,
        "width": 380,
        "height": 260,
        "color": "3"
    })
    edges.append({
        "id": gen_id(),
        "fromNode": hub_id,
        "fromSide": "right",
        "toNode": infra_id,
        "toSide": "left",
        "toEnd": "arrow",
        "label": "configured by"
    })

    canvas_data = {
        "nodes": nodes,
        "edges": edges
    }

    canvas_path = os.path.join("wiki/projects", f"{p_name}.canvas")
    with open(canvas_path, "w", encoding="utf-8") as f:
        json.dump(canvas_data, f, ensure_ascii=False, indent=2)
    print(f"🎨 สร้าง Obsidian Interactive Canvas: [[{p_name}.canvas]]")

def format_collapsible_file_list(files: list[str], sample_count: int = 5, item_prefix: str = "- ", label: str = "ไฟล์") -> str:
    """สร้างลิสต์ไฟล์แบบ Native Obsidian Subheadings (พับ/กางได้ 100% โดยไม่มี HTML Tags รกตา)"""
    if not files:
        return "*(ไม่พบไฟล์)*"
    
    sample = [f"{item_prefix}`{f}`" for f in files[:sample_count]]
    sample_str = "\n".join(sample)
    
    if len(files) > sample_count:
        rest = [f"{item_prefix}`{f}`" for f in files[sample_count:]]
        rest_str = "\n".join(rest)
        subheading_block = (
            f"\n\n#### 📁 รายชื่อ{label}ทั้งหมดที่เหลือ (+{len(files) - sample_count} รายการ)\n"
            f"{rest_str}"
        )
        return sample_str + subheading_block
    
    return sample_str

def generate_project_wiki(analysis: dict):
    """สร้างโน้ตสรุปโครงสร้างโปรเจกต์แบบ Schema v2.0 (Typed Semantic Relations & Collapsible Full Lists)"""
    p_name = analysis["name"]
    today = str(date.today())
    repo_url = analysis.get("repo_url", "")
    p_tag = f"project-{p_name.lower()}"
    modules = analysis.get("modules", {})
    infra_files = analysis.get("infra_files", [])

    os.makedirs("wiki/projects", exist_ok=True)
    os.makedirs("wiki/architecture", exist_ok=True)
    os.makedirs("wiki/tech-stacks", exist_ok=True)
    os.makedirs("wiki/patterns", exist_ok=True)
    os.makedirs("wiki/cheatsheets", exist_ok=True)

    for tech in analysis["tech_stacks"]:
        ensure_tech_stack_note(tech, p_name, today)

    clean_tech_ids = [re.sub(r'[^a-zA-Z0-9_\-]', '', t.replace(' ', '-').replace('/', '-').replace('#', 'Sharp')) for t in analysis["tech_stacks"]]
    tech_links = [f"[[{t}]]" for t in clean_tech_ids if t]

    mod_table_rows = []
    other_p, other_d, other_s, other_m = 0, 0, 0, 0
    for m_name, m_data in list(modules.items()):
        p_c = len(m_data["ui_pages"])
        d_c = len(m_data["dialogs"])
        s_c = len(m_data["services"])
        m_c = len(m_data["models"])
        total_count = p_c + d_c + s_c + m_c
        if total_count >= 5:
            mod_table_rows.append(f"| **{m_name}** | {p_c} หน้า | {d_c} จอ | {s_c} บริการ | {m_c} ตาราง/โมเดล |")
        elif total_count > 0:
            other_p += p_c
            other_d += d_c
            other_s += s_c
            other_m += m_c

    if other_p + other_d + other_s + other_m > 0:
        mod_table_rows.append(f"| **Other & Misc Helpers** | {other_p} หน้า | {other_d} จอ | {other_s} บริการ | {other_m} ตาราง/โมเดล |")

    mod_table_str = "\n".join(mod_table_rows) if mod_table_rows else "| *(General)* | - | - | - | - |"

    # 1. Project Hub -> wiki/projects/[name]-Hub.md
    hub_file = os.path.join("wiki/projects", f"{p_name}-Hub.md")
    hub_uses_yaml = "\n".join([
        f'  - "[[{p_name}-APIs]]"',
        f'  - "[[{p_name}-Services]]"',
        f'  - "[[{p_name}-Database]]"',
        f'  - "[[{p_name}-Infra]]"',
    ] + [f'  - "[[{t}]]"' for t in clean_tech_ids if t])

    hub_content = f"""---
type: project-hub
title: "Project Hub: {p_name}"
created: {today}
updated: {today}
tags:
  - project-hub
  - codebase
  - {p_tag}
project: "{p_name}"
implements:
  - "[[{p_name}-Architecture]]"
uses:
{hub_uses_yaml}
---

# 🚀 Project Hub: {p_name}

## 📌 ข้อมูลสรุปโปรเจกต์
- **ชื่อโปรเจกต์**: `{p_name}`
- **แหล่งต้นทาง Git**: {f"[{repo_url}]({repo_url})" if repo_url else "*(Local Path)*"}
- **จำนวนไฟล์ทั้งหมด**: `{analysis["total_files"]}` ไฟล์
- **Tech Stack หลัก**: {", ".join(tech_links) if tech_links else "*(กำลังระบุ)*"}
- **Interactive Visual Canvas**: [[{p_name}.canvas]] 🗺️

---

## 🧭 สารบัญโมดูลย่อยแยกตามหมวดหมู่ (Distributed Sub-Notes)
เข้าถึงข้อมูลเชิงลึกเฉพาะจุดในแต่ละโฟลเดอร์ความรู้:

1. 🏗️ **สถาปัตยกรรมระบบ**: [[{p_name}-Architecture]] *(ใน `wiki/architecture/`)*
2. 🗄️ **ฐานข้อมูลและโมเดล**: [[{p_name}-Database]] *(ใน `wiki/tech-stacks/`)*
3. 🌐 **หน้าจอและ API Routes**: [[{p_name}-APIs]] *(ใน `wiki/patterns/`)*
4. ⚙️ **บริการหลักและ Logic**: [[{p_name}-Services]] *(ใน `wiki/patterns/`)*
5. 🐳 **Configuration & Infra**: [[{p_name}-Infra]] *(ใน `wiki/cheatsheets/`)*

---

## 🏢 สรุปภาพรวมโมดูลธุรกิจ (Business Domains & True Metrics)

| หมวดหมู่โมดูล (Domain Module) | หน้าจอหลัก (UI Pages) | ไดอะล็อก/Popups | Business Services | Database Models |
| :--- | :--- | :--- | :--- | :--- |
{mod_table_str}

---

## 🔗 ความสัมพันธ์เชิงความหมาย (Semantic Knowledge Links)
- implements:: [[{p_name}-Architecture]]
- uses:: [[{p_name}-APIs]]
- uses:: [[{p_name}-Services]]
- uses:: [[{p_name}-Database]]
- uses:: [[{p_name}-Infra]]
{chr(10).join([f"- uses:: [[{t}]]" for t in clean_tech_ids if t])}
"""
    with open(hub_file, "w", encoding="utf-8") as f:
        f.write(hub_content.strip() + "\n")

    # 2. Architecture -> wiki/architecture/[name]-Architecture.md
    arch_file = os.path.join("wiki/architecture", f"{p_name}-Architecture.md")
    arch_content = f"""---
type: architecture
title: "Architecture: {p_name}"
created: {today}
updated: {today}
tags:
  - architecture
  - {p_tag}
project: "{p_name}"
part_of:
  - "[[{p_name}-Hub]]"
implements:
  - "[[{p_name}-APIs]]"
  - "[[{p_name}-Services]]"
  - "[[{p_name}-Database]]"
---

# 🏗️ Architecture & System Design: {p_name}

## 📌 ภาพรวมสถาปัตยกรรม (System Overview)
สรุปรูปแบบสถาปัตยกรรมและ Data Flow ของโปรเจกต์ `{p_name}`

---

## 🔄 แผนภาพความสัมพันธ์ระดับสถาปัตยกรรม (Architecture Flow)
```mermaid
flowchart TD
    subgraph UI ["🖥️ Presentation Layer"]
        Pages["[[{p_name}-APIs]]<br>UI Views, Pages & Dialogs"]
    end

    subgraph Core ["⚙️ Business Logic & Domain Layer"]
        Services["[[{p_name}-Services]]<br>Services, Handlers & Business Rules"]
    end

    subgraph Data ["🗄️ Persistence & Database Layer"]
        DB["[[{p_name}-Database]]<br>Database Schemas & Entities"]
    end

    subgraph Infra ["🐳 Hosting & Infrastructure"]
        Host["[[{p_name}-Infra]]<br>Containers, Configs & Environments"]
    end

    Pages --> Services
    Services --> DB
    Host -.-> Pages
```

---

## 🔗 ความสัมพันธ์เชิงความหมาย (Semantic Knowledge Links)
- part_of:: [[{p_name}-Hub]]
- implements:: [[{p_name}-APIs]]
- implements:: [[{p_name}-Services]]
- implements:: [[{p_name}-Database]]
"""
    with open(arch_file, "w", encoding="utf-8") as f:
        f.write(arch_content.strip() + "\n")

    # 3. Database -> wiki/tech-stacks/[name]-Database.md
    db_file = os.path.join("wiki/tech-stacks", f"{p_name}-Database.md")
    db_sections = []
    for m_name, m_data in list(modules.items())[:15]:
        if m_data["models"]:
            files_formatted = format_collapsible_file_list(m_data["models"], sample_count=5, item_prefix="- ", label="โมเดล/ตาราง")
            db_sections.append(f"### 🗄️ โมเดลกลุ่ม: **{m_name}** ({len(m_data['models'])} โมเดล/ตาราง)\n{files_formatted}")
    db_sections_str = "\n\n".join(db_sections) if db_sections else "*(ยังไม่พบโครงสร้าง Model)*"

    db_content = f"""---
type: tech-stack
title: "Database & Models: {p_name}"
created: {today}
updated: {today}
tags:
  - database
  - schema
  - {p_tag}
project: "{p_name}"
part_of:
  - "[[{p_name}-Hub]]"
used_by:
  - "[[{p_name}-Services]]"
---

# 🗄️ Database & Domain Models: {p_name}

## 📌 โครงสร้างฐานข้อมูลและโมเดล
รวบรวมไฟล์ Schema, Database Entities, และ Data Models ของโปรเจกต์ `{p_name}`

---

## 📂 โครงสร้างโมเดลจำแนกตามกลุ่มธุรกิจ (Data Entities by Domain)
{db_sections_str}

---

## 🔗 ความสัมพันธ์เชิงความหมาย (Semantic Knowledge Links)
- part_of:: [[{p_name}-Hub]]
- used_by:: [[{p_name}-Services]]
"""
    with open(db_file, "w", encoding="utf-8") as f:
        f.write(db_content.strip() + "\n")

    # 4. APIs -> wiki/patterns/[name]-APIs.md
    api_file = os.path.join("wiki/patterns", f"{p_name}-APIs.md")
    api_sections = []
    for m_name, m_data in list(modules.items())[:15]:
        all_ui = [f"📄 {f}" for f in m_data["ui_pages"]] + [f"🪟 {f}" for f in m_data["dialogs"]]
        if all_ui:
            files_formatted = format_collapsible_file_list(all_ui, sample_count=6, item_prefix="- ", label="หน้าจอ/ไดอะล็อก")
            api_sections.append(f"### 🌐 กลุ่มหน้าจอ: **{m_name}** ({len(m_data['ui_pages'])} หน้าหลัก, {len(m_data['dialogs'])} ไดอะล็อก)\n{files_formatted}")
    api_sections_str = "\n\n".join(api_sections) if api_sections else "*(ยังไม่พบโครงสร้าง UI)*"

    page_dependencies = analysis.get("page_dependencies", {})
    call_graph_sections = []
    mermaid_nodes_ui = []
    mermaid_nodes_svc = []
    mermaid_edges = []
    seen_services = set()
    edge_count = 0

    for m_name, pages_map in list(page_dependencies.items())[:12]:
        if pages_map:
            page_calls = []
            for page_name, svcs in list(pages_map.items())[:6]:
                svcs_links = [f"[[{p_name}-Services#{s}|{s}]]" for s in svcs]
                page_calls.append(f"  - 📄 `{page_name}` ➡️ " + ", ".join(svcs_links))
                
                if edge_count < 18:
                    p_clean = re.sub(r'[^a-zA-Z0-9_]', '_', page_name)
                    mermaid_nodes_ui.append(f'        {p_clean}["📄 {page_name}"]')
                    for s in svcs[:3]:
                        s_clean = re.sub(r'[^a-zA-Z0-9_]', '_', s)
                        if s_clean not in seen_services:
                            seen_services.add(s_clean)
                            mermaid_nodes_svc.append(f'        {s_clean}["⚙️ {s}"]')
                        mermaid_edges.append(f"    {p_clean} --> {s_clean}")
                        edge_count += 1

            if page_calls:
                call_graph_sections.append(f"### 🔗 แผนผังเรียกใช้ Service: **{m_name}**\n" + "\n".join(page_calls))

    call_graph_str = "\n\n".join(call_graph_sections) if call_graph_sections else "*(ไม่พบ Dependency การเรียกใช้ Service เพิ่มเติม)*"

    mermaid_diagram = ""
    if mermaid_edges:
        mermaid_diagram = (
            "```mermaid\n"
            "flowchart LR\n"
            "    subgraph UI [\"🌐 UI Pages / Controllers\"]\n" +
            "\n".join(mermaid_nodes_ui[:10]) + "\n"
            "    end\n"
            "    subgraph SVC [\"⚙️ Injected Services\"]\n" +
            "\n".join(mermaid_nodes_svc[:12]) + "\n"
            "    end\n" +
            "\n".join(mermaid_edges[:16]) + "\n"
            "```\n\n---\n"
        )

    api_content = f"""---
type: pattern
title: "Pages, Routes & APIs: {p_name}"
created: {today}
updated: {today}
tags:
  - api
  - routes
  - {p_tag}
project: "{p_name}"
depends_on:
  - "[[{p_name}-Services]]"
part_of:
  - "[[{p_name}-Hub]]"
uses:
  - "[[{p_name}-Database]]"
---

# 🌐 Pages, Routes & Service Dependencies: {p_name}

## 📌 โครงสร้างหน้าจอและทางเข้าของระบบ
รวบรวมหน้าจอหลัก (📄), Controllers และไดอะล็อก Popups (🪟) ของโปรเจกต์ `{p_name}` พร้อมแผนผังความเชื่อมโยงไปยัง Business Services

---

## 🗺️ แผนผัง Flowchart การเรียกใช้ Service (Visual Call Graph)
{mermaid_diagram}## 🔗 แผนผังความเชื่อมโยงระดับโค้ด (Code Dependency Call Map)
สกัดอัตโนมัติจาก Dependency Injections และ Imports ในซอร์สโค้ดจริง:

{call_graph_str}

---

## 📂 รายการหน้าจอจำแนกตามกลุ่มโมดูล (UI Components by Domain)
{api_sections_str}

---

## 🔗 ความสัมพันธ์เชิงความหมาย (Semantic Knowledge Links)
- depends_on:: [[{p_name}-Services]]
- part_of:: [[{p_name}-Hub]]
- uses:: [[{p_name}-Database]]
"""
    with open(api_file, "w", encoding="utf-8") as f:
        f.write(api_content.strip() + "\n")

    # 5. Services -> wiki/patterns/[name]-Services.md
    svc_file = os.path.join("wiki/patterns", f"{p_name}-Services.md")
    svc_sections = []
    for m_name, m_data in list(modules.items())[:15]:
        if m_data["services"]:
            files_formatted = format_collapsible_file_list(m_data["services"], sample_count=5, item_prefix="- ", label="บริการ/Logic")
            svc_sections.append(f"### ⚙️ บริการกลุ่ม: **{m_name}** ({len(m_data['services'])} บริการ)\n{files_formatted}")
    svc_sections_str = "\n\n".join(svc_sections) if svc_sections else "*(ยังไม่พบโครงสร้าง Services)*"

    svc_content = f"""---
type: pattern
title: "Business Services: {p_name}"
created: {today}
updated: {today}
tags:
  - services
  - business-logic
  - {p_tag}
project: "{p_name}"
depends_on:
  - "[[{p_name}-Database]]"
part_of:
  - "[[{p_name}-Hub]]"
used_by:
  - "[[{p_name}-APIs]]"
---

# ⚙️ Business Services & Core Logic: {p_name}

## 📌 แก่นการทำงานทางธุรกิจ (Business Rules & Domain Services)
รวบรวม Application Services, Logic, Rules Engine, และ Data Repositories ของโปรเจกต์ `{p_name}`

---

## 📂 รายการบริการจำแนกตามโฟลเดอร์ (Services by Folder)
{svc_sections_str}

---

## 🔗 ความสัมพันธ์เชิงความหมาย (Semantic Knowledge Links)
- depends_on:: [[{p_name}-Database]]
- part_of:: [[{p_name}-Hub]]
- used_by:: [[{p_name}-APIs]]
"""
    with open(svc_file, "w", encoding="utf-8") as f:
        f.write(svc_content.strip() + "\n")

    # 6. Infra -> wiki/cheatsheets/[name]-Infra.md
    infra_file = os.path.join("wiki/cheatsheets", f"{p_name}-Infra.md")
    infra_list_str = format_collapsible_file_list(infra_files, sample_count=8, item_prefix="- ", label="ไฟล์ Config/Infra") if infra_files else "*(ไม่พบไฟล์ Infrastructure เพิ่มเติม)*"

    infra_content = f"""---
type: cheatsheet
title: "Infra & Config: {p_name}"
created: {today}
updated: {today}
tags:
  - devops
  - infra
  - config
  - {p_tag}
project: "{p_name}"
part_of:
  - "[[{p_name}-Hub]]"
---

# 🐳 Infrastructure & Configuration: {p_name}

## 📌 การตั้งค่าระบบและสภาพแวดล้อมจริง
รวบรวมไฟล์ Configuration, Container, PaaS Deployment, และ Web Server ของโปรเจกต์ `{p_name}`

---

## 📄 รายการไฟล์ Configuration ที่ตรวจพบ
{infra_list_str}

---

## 🔗 ความสัมพันธ์เชิงความหมาย (Semantic Knowledge Links)
- part_of:: [[{p_name}-Hub]]
"""
    with open(infra_file, "w", encoding="utf-8") as f:
        f.write(infra_content.strip() + "\n")

    # 7. สร้าง Obsidian JSON Canvas Mindmap
    generate_project_canvas(p_name, clean_tech_ids, analysis)

    update_index_file(p_name)
    append_log_entry(p_name, [
        f"สแกนไฟล์โค้ดเบสทั้งหมด: {analysis['total_files']} ไฟล์",
        f"Tech Stacks: {', '.join(analysis['tech_stacks'])}",
        f"กระจายความรู้: [[{p_name}-Architecture]], [[{p_name}-Database]], [[{p_name}-APIs]], [[{p_name}-Services]], [[{p_name}-Infra]]"
    ])
    print(f"✨ ซิงค์และกระจายความรู้โปรเจกต์ [{p_name}] สำเร็จเรียบร้อยตามหมวดหมู่จริง")

def append_log_entry(project_name: str, details: list[str], log_path: str = "log.md"):
    """บันทึกประวัติการซิงค์ลงใน log.md ในรูปแบบ append-only ตามมาตรฐาน GEMINI.md"""
    if not os.path.exists(log_path):
        return
    today = str(date.today())
    entry = f"\n## [{today}] sync | ซิงค์โปรเจกต์ [[{project_name}-Hub]] สำเร็จ\n"
    for d in details:
        entry += f"- {d}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)

def update_index_file(project_name: str, index_path: str = "index.md"):
    """อัปเดตสารบัญ index.md ให้เชื่อมโยงไปยังไฟล์ที่กระจายอยู่แต่ละหมวด"""
    if not os.path.exists(index_path):
        return
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    hub_link = f"[[{project_name}-Hub]]"
    if hub_link not in content:
        sub_modules = (
            f"- {hub_link} — ภาพรวมโปรเจกต์ `{project_name}`\n"
            f"  - [[{project_name}-Architecture]] *(สถาปัตยกรรม ใน `wiki/architecture/`)*\n"
            f"  - [[{project_name}-Database]] *(ฐานข้อมูลและโมเดล ใน `wiki/tech-stacks/`)*\n"
            f"  - [[{project_name}-APIs]] *(เส้นทางและหน้าจอ ใน `wiki/patterns/`)*\n"
            f"  - [[{project_name}-Services]] *(บริการและ Business Logic ใน `wiki/patterns/`)*\n"
            f"  - [[{project_name}-Infra]] *(DevOps และ Infrastructure ใน `wiki/cheatsheets/`)*\n"
        )
        placeholder = "*(จะถูกสร้างอัตโนมัติเมื่อซิงค์โค้ดเบสจาก repositories.md)*\n"
        if placeholder in content:
            content = content.replace(placeholder, sub_modules)
        elif "### 🚀 ศูนย์กลางโปรเจกต์ (Project Hubs)\n" in content:
            content = content.replace(
                "### 🚀 ศูนย์กลางโปรเจกต์ (Project Hubs)\n",
                f"### 🚀 ศูนย์กลางโปรเจกต์ (Project Hubs)\n{sub_modules}"
            )
        else:
            content += f"\n### 🚀 ศูนย์กลางโปรเจกต์ (Project Hubs)\n{sub_modules}"
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)

def load_sync_state() -> dict:
    """โหลดประวัติ Commit hash ของแต่ละโปรเจกต์จากแคช"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_sync_state(state: dict):
    """บันทึกประวัติ Commit hash ลงในแคช"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def get_git_commit_hash(repo_dir: str) -> str:
    """ดึง Commit hash ล่าสุดของ repository"""
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""

def sync_single_repo(target: str, force: bool = False, sync_state: dict = None, custom_name: str = "") -> bool:
    """Persistent Cache & High-Speed Differential Sync Engine (รองรับทั้ง Git URLs, Local Folders และ Custom Name)"""
    if sync_state is None:
        sync_state = load_sync_state()

    p_name = custom_name.strip() if custom_name else extract_project_name(target)
    print(f"\n=======================================================")
    print(f"🔄 กำลังตรวจสอบโปรเจกต์: {p_name} ({target})")
    print(f"=======================================================")

    # 1. กรณีเป็น Local Folder ภายในเครื่อง (ไม่มี Git Remote)
    if os.path.isdir(target):
        print(f"📁 สแกนตรงจาก Local Folder ในเครื่อง: {target}")
        print(f"🔍 วิเคราะห์โครงสร้างโค้ดแบบคู่ขนาน (Parallel Engine)...")
        analysis = scan_codebase_structure(target, repo_url="", custom_name=p_name)
        generate_project_wiki(analysis)
        return True

    # 2. กรณีเป็น Git URL จากอินเทอร์เน็ต
    os.makedirs(CACHE_DIR, exist_ok=True)
    repo_dir = os.path.join(CACHE_DIR, p_name)
    hub_file = os.path.join("wiki/projects", f"{p_name}-Hub.md")

    # 2.1 จัดการ Git Cache (Clone หรือ Fetch ส่วนต่าง)
    if os.path.exists(os.path.join(repo_dir, ".git")):
        print(f"⚡ พบ Local Cache ({repo_dir}) — ดึงการเปลี่ยนแปลงล่าสุด...")
        fetch_res = subprocess.run(["git", "fetch", "--depth", "1", "origin"], cwd=repo_dir, capture_output=True, text=True)
        if fetch_res.returncode == 0:
            subprocess.run(["git", "reset", "--hard", "origin/HEAD"], cwd=repo_dir, capture_output=True, text=True)
        else:
            # Fallback หาก remote default branch ไม่ใช่ HEAD
            subprocess.run(["git", "pull", "--depth", "1"], cwd=repo_dir, capture_output=True, text=True)
    else:
        print(f"📥 กำลัง Shallow Clone เข้าสู่แคช ({target}) ...")
        cmd = ["git", "clone", "--depth", "1", target, repo_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if result.returncode != 0:
            print(f"❌ ไม่สามารถ Clone {target}: {result.stderr.strip()}")
            return False

    # 2.2 ตรวจสอบ Commit Hash เพื่อข้ามการประมวลผลซ้ำ (Instant 0.1s Bypass)
    current_hash = get_git_commit_hash(repo_dir)
    last_hash = sync_state.get(p_name, "")

    if not force and current_hash and current_hash == last_hash and os.path.exists(hub_file):
        print(f"✨ โค้ดเบส [{p_name}] เป็นเวอร์ชันล่าสุดแล้ว (Commit: {current_hash[:8]}) — ข้ามการสแกนซ้ำใน 0.1s ⚡")
        return True

    # 2.3 วิเคราะห์โครงสร้างโค้ดแบบ Multi-Threaded Parallel Scanner
    print(f"🔍 สแกนและวิเคราะห์โครงสร้างโค้ดแบบคู่ขนาน (Parallel Engine)...")
    analysis = scan_codebase_structure(repo_dir, repo_url=target, custom_name=p_name)
    generate_project_wiki(analysis)

    # 2.4 อัปเดต Cache State
    if current_hash:
        sync_state[p_name] = current_hash
        save_sync_state(sync_state)

    return True

def ensure_in_repositories_md(entry: str, alias: str = ""):
    """เพิ่ม Git URL หรือ Local Path ลงใน repositories.md อัตโนมัติ หากยังไม่มีอยู่ในรายการ"""
    repo_file = "repositories.md"
    if not os.path.exists(repo_file):
        return
    try:
        with open(repo_file, "r", encoding="utf-8-sig") as f:
            content = f.read()
        existing_items = extract_urls_from_markdown(content)
        existing_targets = [it["target"].strip() for it in existing_items]
        clean_entry = entry.strip()
        is_already_present = False
        for ex in existing_targets:
            if clean_entry.lower() == ex.lower():
                is_already_present = True
                break
            if os.path.exists(clean_entry) and os.path.exists(ex) and os.path.abspath(clean_entry) == os.path.abspath(ex):
                is_already_present = True
                break

        if not is_already_present:
            line_to_write = f"- [{alias.strip()}]({clean_entry})\n" if alias and alias.strip() else f"- {clean_entry}\n"
            with open(repo_file, "a", encoding="utf-8") as f:
                if not content.endswith("\n"):
                    f.write("\n")
                f.write(line_to_write)
            print(f"📝 บันทึก [{alias.strip() or clean_entry}] ลงใน repositories.md เรียบร้อยแล้ว")
    except Exception as e:
        pass

def main():
    parser = argparse.ArgumentParser(description="Git Repositories Tracker & High-Performance Auto-Sync Engine for Dev Brain")
    parser.add_argument("repo_url", nargs="?", help="Git URL หรือเว้นว่างเพื่ออ่านจาก repositories.md ทั้งหมด")
    parser.add_argument("--name", "-n", help="กำหนดชื่อโปรเจกต์ (Custom Project Alias Name) สำหรับสร้างใน Dev Brain")
    parser.add_argument("--force", action="store_true", help="บังคับสแกนใหม่ทั้งหมดแม้โค้ดไม่มีการเปลี่ยนแปลง")
    args = parser.parse_args()

    repos_to_sync = []
    if args.repo_url:
        target = args.repo_url.strip()
        custom_name = args.name.strip() if args.name else ""
        repos_to_sync.append({"target": target, "name": custom_name})
        # ตรวจสอบว่าถ้าเป็น local folder ที่มี git remote ให้ใช้ git remote URL บันทึกแทน
        saved_entry = target
        if os.path.isdir(target) and os.path.exists(os.path.join(target, ".git")):
            try:
                res = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=target, capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    saved_entry = res.stdout.strip()
            except Exception:
                pass
        elif os.path.isdir(target):
            saved_entry = os.path.abspath(target)
        ensure_in_repositories_md(saved_entry, alias=custom_name)
    else:
        repo_file = "repositories.md"
        if not os.path.exists(repo_file):
            print(f"❌ ไม่พบไฟล์ {repo_file} — กรุณาสร้างและใส่ลิงก์ Git")
            sys.exit(1)
        with open(repo_file, "r", encoding="utf-8-sig") as f:
            content = f.read()
            repos_to_sync = extract_urls_from_markdown(content)

    if not repos_to_sync:
        print("ℹ️ ไม่พบ Git URL ใน repositories.md")
        return

    sync_state = load_sync_state()
    success_count = 0
    for item in repos_to_sync:
        target_url = item["target"]
        item_name = item.get("name", "")
        if sync_single_repo(target_url, force=args.force, sync_state=sync_state, custom_name=item_name):
            success_count += 1

    print(f"\n=======================================================")
    print(f"🕸️ อัปเดต Graph & ตรวจสุขภาพระบบหลังซิงค์...")
    python_exe = sys.executable
    subprocess.run([python_exe, "scripts/run_graphify.py"])
    subprocess.run([python_exe, "scripts/lint_wiki.py"])
    print(f"🎉 ซิงค์สำเร็จทั้งหมด {success_count}/{len(repos_to_sync)} โปรเจกต์!")


if __name__ == "__main__":
    main()
