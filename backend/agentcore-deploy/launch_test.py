#!/usr/bin/env python3
"""Test agentcore launch with proper YAML config."""
import subprocess
import os
import shutil
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="agentcore-test-")

for f in ["agent_template.py", "requirements.txt"]:
    shutil.copy(os.path.join(SCRIPT_DIR, f), tmp)
open(os.path.join(tmp, "__init__.py"), "w").close()

# Create .bedrock_agentcore.yaml
yaml_content = """agents:
  superAgent_test:
    entry_point: agent_template.py
    deployment_type: direct_code_deploy
    role_arn: arn:aws:iam::632930644527:role/AgentCoreRuntimeRole
    region: us-east-1
    environment_variables:
      AGENT_SYSTEM_PROMPT: "You are a test agent."
      MODEL_ID: "us.anthropic.claude-sonnet-4-20250514-v1:0"
      AWS_REGION: "us-east-1"
"""
with open(os.path.join(tmp, ".bedrock_agentcore.yaml"), "w") as f:
    f.write(yaml_content)

print(f"Temp dir: {tmp}")
print(f"Config:\n{yaml_content}")

result = subprocess.run(
    ["agentcore", "launch", "--agent", "superAgent_test"],
    cwd=tmp,
    capture_output=True,
    text=True,
    timeout=600,
    input="\n\n\n\n",
)
print(f"RC: {result.returncode}")
print(f"STDOUT:\n{result.stdout}")
if result.stderr:
    print(f"STDERR:\n{result.stderr[:1000]}")

shutil.rmtree(tmp, ignore_errors=True)
