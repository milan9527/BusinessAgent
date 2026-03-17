#!/usr/bin/env python3
"""Update all agent runtimes with lazy-init code to fix cold start timeout."""
import boto3
import io
import os
import zipfile

REGION = "us-east-1"
S3_BUCKET = "agentcore-code-632930644527-us-east-1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

ROLE_ARN = "arn:aws:iam::632930644527:role/AgentCoreRuntimeRole"

RUNTIMES = {
    "player-analyst": "superAgent_player_analyst-EUT7w667Tw",
    "event-planner": "superAgent_event_planner-HX4lB2BBg2",
    "content-localizer": "superAgent_content_localizer-03ybDKDN6F",
    "ad-optimizer": "superAgent_ad_optimizer-01Xl0dDM7I",
    "site-generator": "superAgent_site_generator-BhHO4MHyND",
    "seo-optimizer": "superAgent_seo_optimizer-yLUocs3zri",
    "hr-assistant": "superAgent_hr_assistant-YwrCLo8CPI",
    "it-support": "superAgent_it_support-xJvASCG0Cj",
}

# Build zip
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    for fname in ["agent_template.py", "requirements.txt"]:
        zf.write(os.path.join(SCRIPT_DIR, fname), fname)
buf.seek(0)
zip_bytes = buf.read()
print(f"Built zip: {len(zip_bytes)} bytes")

s3 = boto3.client("s3", region_name=REGION)
client = boto3.client("bedrock-agentcore-control", region_name=REGION)

for name, rid in RUNTIMES.items():
    s3_key = f"agentcore-deploy/{name}/code.zip"
    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=zip_bytes)

    try:
        resp = client.update_agent_runtime(
            agentRuntimeId=rid,
            agentRuntimeArtifact={
                "codeConfiguration": {
                    "code": {"s3": {"bucket": S3_BUCKET, "prefix": s3_key}},
                    "runtime": "PYTHON_3_12",
                    "entryPoint": ["agent_template.py"],
                }
            },
            roleArn=ROLE_ARN,
            networkConfiguration={"networkMode": "PUBLIC"},
        )
        print(f"  Updated {name}: {resp.get('status')}")
    except Exception as e:
        print(f"  Failed {name}: {e}")

print("\nDone. Runtimes will rebuild with lazy initialization.")
