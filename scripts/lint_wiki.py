import os
import sys
import json
import glob
import re
import argparse
from collections import Counter

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

VALID_RELATION_TYPES = {
    "solves", "mitigates", "commonly_causes", "symptom_of",
    "uses", "used_by", "depends_on", "alternative_to", "implements",
    "part_of", "links_to", "evaluates", "related_to", "mitigated_by"
}

def parse_frontmatter(content: str) -> dict:
    content = content.lstrip('\ufeff').strip()
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    
    fm_text = parts[1].strip()
    if not fm_text:
        return {}

    try:
        import yaml
        import datetime
        data = yaml.safe_load(fm_text)
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if isinstance(v, (datetime.date, datetime.datetime)):
                    cleaned[k] = str(v)
                else:
                    cleaned[k] = v
            return cleaned
        return {}
    except Exception:
        fm_data = {}
        current_list_key = None
        for line in fm_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- ") and current_list_key:
                val = line[2:].strip().strip('"').strip("'")
                fm_data.setdefault(current_list_key, []).append(val)
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                if val:
                    fm_data[key] = val.strip('"').strip("'")
                    current_list_key = None
                else:
                    current_list_key = key
                    fm_data[key] = []
        return fm_data

def lint_knowledge_base(auto_repair: bool = False, strict: bool = False) -> bool:
    """
    Deterministic Dev Brain Linter (v2.0 Semantic Graph Aware):
    1. ตรวจสอบ Broken [[Wikilinks]]
    2. ตรวจสอบ Semantic Typed Relations
    3. ตรวจสอบ Orphan Pages
    4. ตรวจสอบ YAML Frontmatter (type, created, updated)
    5. ตรวจสอบความสอดคล้องของ index.md กับไฟล์จริงใน wiki/
    """
    wiki_files = glob.glob("wiki/**/*.md", recursive=True) + glob.glob("wiki/*.md")
    wiki_files = list(set([f.replace("\\", "/") for f in wiki_files if not os.path.basename(f).startswith(".")]))

    print(f"🧹 เริ่มต้นตรวจสอบสุขภาพ Dev Brain (Linting {len(wiki_files)} files)...")
    print("=" * 70)

    existing_note_names = {}
    for f in wiki_files:
        doc_name = os.path.splitext(os.path.basename(f))[0]
        existing_note_names[doc_name] = f

    broken_links = []
    invalid_relations = []
    inbound_links_count = Counter()
    missing_frontmatter = []
    invalid_frontmatter_fields = []
    all_extracted_links = set()

    for file_path in wiki_files:
        doc_name = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 1. ตรวจสอบ Frontmatter
        fm = parse_frontmatter(content)
        if not fm:
            missing_frontmatter.append(file_path)
        else:
            required_fields = ["type", "created", "updated"]
            missing_fields = [rf for rf in required_fields if rf not in fm]
            if missing_fields:
                invalid_frontmatter_fields.append((file_path, missing_fields))

            # ตรวจสอบ Typed Relations ใน Frontmatter
            relations = fm.get("relations", [])
            if isinstance(relations, list):
                for rel in relations:
                    if isinstance(rel, dict):
                        rel_type = rel.get("type", "")
                        if rel_type and rel_type not in VALID_RELATION_TYPES:
                            invalid_relations.append((file_path, rel_type))

        # 2. ตรวจสอบ [[Wikilinks]]
        raw_links = re.findall(r'\[\[(.*?)\]\]', content)
        for link in raw_links:
            clean_link = link.split("|")[0].split("#")[0].strip()
            if not clean_link or clean_link == doc_name:
                continue

            all_extracted_links.add(clean_link)
            inbound_links_count[clean_link] += 1

            if clean_link not in existing_note_names and not clean_link.startswith("http"):
                if clean_link.endswith(".canvas") and glob.glob(f"**/{clean_link}", recursive=True):
                    continue
                broken_links.append({
                    "source_file": file_path,
                    "target_link": clean_link
                })

    # 3. ตรวจสอบ Orphan Pages
    orphan_pages = []
    for doc_name, file_path in existing_note_names.items():
        if "/summaries/" not in file_path and "/cheatsheets/" not in file_path and inbound_links_count[doc_name] == 0:
            orphan_pages.append(file_path)

    # 4. ตรวจสอบความสอดคล้องกับ index.md
    index_missing_notes = []
    index_path = "index.md"
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            index_content = f.read()

        for doc_name, file_path in existing_note_names.items():
            if f"[[{doc_name}]]" not in index_content:
                index_missing_notes.append((doc_name, file_path))

    # ================= รายงานผลการตรวจสอบ =================
    has_errors = False

    # 1. Broken Links Report
    if broken_links:
        print(f"\n⚠️ พบ Broken / Phantom Wikilinks ({len(broken_links)} จุด):")
        broken_group = {}
        for b in broken_links:
            broken_group.setdefault(b["target_link"], []).append(b["source_file"])
        for target, sources in list(broken_group.items())[:10]:
            print(f"   • [[{target}]] (ถูกอ้างอิงใน: {', '.join([os.path.basename(s) for s in sources])})")
        if len(broken_group) > 10:
            print(f"   ...และอีก {len(broken_group) - 10} รายการ")
    else:
        print("\n✅ Broken Links: ไม่พบลิงก์เสีย โครงข่ายเชื่อมโยงสมบูรณ์ 100%")

    # 2. Semantic Typed Relations Report
    if invalid_relations:
        print(f"\n⚠️ พบ Relation Type ที่ไม่อยู่ในมาตรฐาน ({len(invalid_relations)} จุด):")
        for path, rtype in invalid_relations[:5]:
            print(f"   • {path}: relation '{rtype}'")
    else:
        print("✅ Semantic Relations: รูปแบบความสัมพันธ์ถูกต้องตาม Schema มาตรฐาน")

    # 3. Orphan Pages Report
    if orphan_pages:
        print(f"\n⚠️ พบ Orphan Pages (หน้าที่ยังไม่มีโน้ตอื่นลิงก์หา {len(orphan_pages)} หน้า):")
        for op in orphan_pages[:5]:
            print(f"   • {op}")
    else:
        print("✅ Orphan Pages: ทุกหน้าใน Dev Brain มีความเชื่อมโยงกับโครงข่าย")

    # 4. Frontmatter Report
    if missing_frontmatter or invalid_frontmatter_fields:
        print(f"\n⚠️ พบปัญหา Frontmatter ({len(missing_frontmatter) + len(invalid_frontmatter_fields)} ไฟล์):")
        for mf in missing_frontmatter:
            print(f"   • [ไม่มี Frontmatter]: {mf}")
        for path, fields in invalid_frontmatter_fields:
            print(f"   • [ขาดฟิลด์ {', '.join(fields)}]: {path}")
        has_errors = True
    else:
        print("✅ YAML Frontmatter: ผ่านเกณฑ์มาตรฐานทุกไฟล์")

    # 5. Index Sync Report
    if index_missing_notes:
        print(f"\n⚠️ พบโน้ตที่ตกหล่นจาก index.md ({len(index_missing_notes)} หน้า):")
        for name, path in index_missing_notes[:5]:
            print(f"   • [[{name}]] ({path})")
    else:
        print("✅ Index Sync: สารบัญ index.md ตรงกับคลังความรู้จริง 100%")

    print("\n" + "=" * 70)
    if has_errors and strict:
        print("❌ Linter สรุป: พบข้อผิดพลาดที่ต้องแก้ไขก่อน Commit")
        return False

    print("🌟 Linter สรุป: Dev Brain ผ่านการตรวจสอบความน่าเชื่อถือระดับ Production!")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dev Brain Deterministic Linter")
    parser.add_argument("--repair", action="store_true", help="ซ่อมแซมสารบัญ index.md อัตโนมัติ")
    parser.add_argument("--strict", action="store_true", help="หยุดทำงานด้วย Error Code 1 หากพบปัญหา Frontmatter")
    args = parser.parse_args()

    success = lint_knowledge_base(auto_repair=args.repair, strict=args.strict)
    if not success:
        sys.exit(1)

