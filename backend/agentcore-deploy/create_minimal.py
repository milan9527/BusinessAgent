import boto3, io, zipfile

REGION = "us-east-1"
S3_BUCKET = "agentcore-code-632930644527-us-east-1"
ROLE_ARN = "arn:aws:iam::632930644527:role/AgentCoreRuntimeRole"

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write("backend/agentcore-deploy/agent_minimal.py", "agent_minimal.py")
    zf.writestr("requirements.txt", "bedrock-agentcore\n")
buf.seek(0)

s3 = boto3.client("s3", region_name=REGION)
s3.put_object(Bucket=S3_BUCKET, Key="agentcore-deploy/minimal-test/code.zip", Body=buf.read())
print("Uploaded to S3")

client = boto3.client("bedrock-agentcore-control", region_name=REGION)
try:
    resp = client.create_agent_runtime(
        agentRuntimeName="superAgent_minimal_test",
        description="Minimal test agent",
        agentRuntimeArtifact={
            "codeConfiguration": {
                "code": {"s3": {"bucket": S3_BUCKET, "prefix": "agentcore-deploy/minimal-test/code.zip"}},
                "runtime": "PYTHON_3_12",
                "entryPoint": ["agent_minimal.py"],
            }
        },
        networkConfiguration={"networkMode": "PUBLIC"},
        roleArn=ROLE_ARN,
    )
    print(f"Created: {resp['agentRuntimeArn']} ({resp['status']})")
except Exception as e:
    print(f"Error: {e}")
