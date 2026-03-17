"""Minimal test agent - no strands, just echo."""
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload):
    return {"result": f"Echo: {payload.get('prompt', 'no prompt')}"}

if __name__ == "__main__":
    app.run()
