#!/usr/bin/env python3
"""
Upload all SKILL.md files to S3 so AgentCore agents can fetch them at runtime.

S3 layout:
  s3://super-agent-files/skills/{skill-name}/SKILL.md

Also uploads a skills-index.json manifest listing all skills with metadata.
"""
import json
import os
import re

import boto3

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
BUCKET = "super-agent-files"
S3_PREFIX = "skills"
REGION = "us-east-1"


def parse_skill_frontmatter(content):
    """Extract name and description from YAML frontmatter."""
    meta = {"name": "", "description": ""}
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm = content[3:end]
            for line in fm.strip().split("\n"):
                if line.startswith("name:"):
                    meta["name"] = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    meta["description"] = line.split(":", 1)[1].strip()
    return meta


def get_skill_body(content):
    """Strip YAML frontmatter, return body only."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].strip()
    return content


def main():
    s3 = boto3.client("s3", region_name=REGION)

    if not os.path.isdir(SKILLS_DIR):
        print(f"❌ Skills directory not found: {SKILLS_DIR}")
        return

    skills_index = []
    uploaded = 0

    for skill_name in sorted(os.listdir(SKILLS_DIR)):
        skill_md = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue

        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read()

        meta = parse_skill_frontmatter(content)
        s3_key = f"{S3_PREFIX}/{skill_name}/SKILL.md"

        print(f"  📤 Uploading {skill_name} → s3://{BUCKET}/{s3_key}")
        s3.put_object(
            Bucket=BUCKET,
            Key=s3_key,
            Body=content.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
        )
        uploaded += 1

        skills_index.append({
            "name": meta["name"] or skill_name,
            "skill_folder": skill_name,
            "s3_key": s3_key,
            "description": meta["description"],
        })

        # Upload any sub-files (scripts/, references/, assets/)
        skill_dir = os.path.join(SKILLS_DIR, skill_name)
        for root, dirs, files in os.walk(skill_dir):
            for fname in files:
                if fname == "SKILL.md":
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, skill_dir)
                sub_key = f"{S3_PREFIX}/{skill_name}/{rel}"
                print(f"       📎 {rel} → s3://{BUCKET}/{sub_key}")
                with open(fpath, "rb") as ff:
                    s3.put_object(Bucket=BUCKET, Key=sub_key, Body=ff.read())

    # Upload index
    index_key = f"{S3_PREFIX}/skills-index.json"
    print(f"\n  📤 Uploading index → s3://{BUCKET}/{index_key}")
    s3.put_object(
        Bucket=BUCKET,
        Key=index_key,
        Body=json.dumps(skills_index, indent=2, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    print(f"\n✅ Uploaded {uploaded} skills to s3://{BUCKET}/{S3_PREFIX}/")
    print(f"   Index: s3://{BUCKET}/{index_key}")
    for s in skills_index:
        print(f"   • {s['name']} ({s['skill_folder']})")


if __name__ == "__main__":
    main()
