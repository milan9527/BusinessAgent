/**
 * Strands Agent Service
 *
 * Manages AI agent conversations by invoking Strands agents deployed on
 * Amazon Bedrock AgentCore Runtime. Provides an async generator interface
 * that yields ConversationEvents for SSE streaming, maintaining the same
 * contract as the previous Claude Agent SDK integration.
 *
 * Each agent is deployed as a container on AgentCore. This service looks up
 * the agent's runtime ARN from a static mapping and invokes it via the
 * AWS SDK InvokeAgentRuntime API.
 */

import { config } from '../config/index.js';
import { spawn, type ChildProcess } from 'child_process';
import { join, resolve } from 'path';
import { readFile as fsReadFile, writeFile, mkdir } from 'fs/promises';
import { existsSync } from 'fs';
import { WorkspaceManager, type SkillForWorkspace } from './workspace-manager.js';
import { prisma } from '../config/database.js';
import crypto from 'crypto';
import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from '@aws-sdk/client-bedrock-agentcore';
import { chatMessageRepository } from '../repositories/chat.repository.js';

// ---------------------------------------------------------------------------
// Types — compatible with the existing ConversationEvent contract
// ---------------------------------------------------------------------------

export interface AgentConfig {
  id: string;
  name: string;
  displayName: string;
  systemPrompt: string | null;
  organizationId: string;
  skillIds: string[];
  mcpServerIds: string[];
}

export type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool_use_id: string; content: string | null; is_error: boolean };

export interface ConversationEvent {
  type: 'session_start' | 'assistant' | 'result' | 'heartbeat' | 'error' | 'preview_ready';
  sessionId?: string;
  content?: ContentBlock[];
  model?: string;
  durationMs?: number;
  numTurns?: number;
  code?: string;
  message?: string;
  suggestedAction?: string;
  appId?: string;
  url?: string;
  appName?: string;
  speakerAgentName?: string;
  speakerAgentAvatar?: string | null;
}

/** MCP server configuration */
export interface MCPServerSDKConfig {
  type: 'stdio' | 'sse' | 'http';
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
}

export interface MCPServerInProcessConfig {
  type: 'sdk';
  name: string;
  instance: unknown;
}

export type AnyMCPServerConfig = MCPServerSDKConfig | MCPServerInProcessConfig;

export interface MCPServerRecord {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  host_address: string;
  status: string;
  headers: unknown;
  config: Record<string, unknown> | null;
}

export interface StrandsAgentServiceOptions {
  agentId: string;
  sessionId?: string;
  claudeSessionId?: string;
  message: string;
  organizationId: string;
  userId: string;
  workspacePath?: string;
}

// Alias for backward compatibility
export type ClaudeAgentServiceOptions = StrandsAgentServiceOptions;

// ---------------------------------------------------------------------------
// Strands Agent Runner (Python subprocess protocol)
// ---------------------------------------------------------------------------

const STRANDS_RUNNER_SCRIPT = `
import sys, json, os, time, uuid, traceback, io

def main():
    """Strands Agent runner — reads config from stdin, streams JSON-line events to stdout."""
    # Keep a reference to the real stdout for our JSON protocol
    real_stdout = sys.stdout

    try:
        config_raw = sys.stdin.read()
        cfg = json.loads(config_raw)

        from strands import Agent
        from strands.models import BedrockModel

        model_id = cfg.get("model_id", "us.anthropic.claude-sonnet-4-20250514-v1:0")
        region = cfg.get("region", "us-east-1")
        system_prompt = cfg.get("system_prompt", "You are a helpful AI assistant.")
        message = cfg.get("message", "")
        session_id = cfg.get("session_id", str(uuid.uuid4()))

        model = BedrockModel(
            model_id=model_id,
            region_name=region,
            max_tokens=4096,
        )

        tools = []
        # Load community tools if available
        try:
            from strands_tools import http_request, python_repl
            tools.extend([http_request, python_repl])
        except ImportError:
            pass

        agent = Agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
        )

        # Emit session_start via real stdout
        event = {"type": "session_start", "session_id": session_id}
        real_stdout.write(json.dumps(event) + "\\n")
        real_stdout.flush()

        start_time = time.time()

        # Redirect stdout to stderr while agent runs (Strands prints to stdout)
        sys.stdout = sys.stderr
        response = agent(message)
        sys.stdout = real_stdout

        duration_ms = int((time.time() - start_time) * 1000)

        # Emit assistant response
        text = str(response)
        event = {
            "type": "assistant",
            "session_id": session_id,
            "content": [{"type": "text", "text": text}],
            "model": model_id,
        }
        real_stdout.write(json.dumps(event) + "\\n")
        real_stdout.flush()

        # Emit result
        event = {
            "type": "result",
            "session_id": session_id,
            "duration_ms": duration_ms,
            "num_turns": 1,
        }
        real_stdout.write(json.dumps(event) + "\\n")
        real_stdout.flush()

    except Exception as e:
        sys.stdout = real_stdout
        error_event = {
            "type": "error",
            "code": "AGENT_EXECUTION_ERROR",
            "message": f"{type(e).__name__}: {str(e)}",
            "suggested_action": "Check agent configuration and try again",
        }
        real_stdout.write(json.dumps(error_event) + "\\n")
        real_stdout.flush()
        traceback.print_exc(file=sys.stderr)

if __name__ == "__main__":
    main()
`;

// ---------------------------------------------------------------------------
// StrandsAgentService
// ---------------------------------------------------------------------------

export class StrandsAgentService {
  private abortControllers: Map<string, AbortController> = new Map();
  private lastActivity: Map<string, number> = new Map();
  private cleanupInterval: NodeJS.Timeout | null = null;
  private workspaceManager: WorkspaceManager;
  private runnerScriptPath: string | null = null;

  // AgentCore Runtime
  private agentCoreClient: BedrockAgentCoreClient;
  private runtimeArns: Record<string, string> | null = null;

  // Concurrency control
  private activeSessions = 0;
  private waitQueue: Array<{ resolve: () => void; reject: (err: Error) => void }> = [];

  constructor(workspaceManager?: WorkspaceManager) {
    this.workspaceManager = workspaceManager ?? new WorkspaceManager();
    this.agentCoreClient = new BedrockAgentCoreClient({
      region: config.aws.region || 'us-east-1',
      ...(config.aws.accessKeyId && config.aws.secretAccessKey
        ? { credentials: { accessKeyId: config.aws.accessKeyId, secretAccessKey: config.aws.secretAccessKey } }
        : {}),
    });
  }

  /**
   * Load the agent-name → runtime-ARN mapping from runtime_arns.json.
   * Handles both flat format {"name": "arn:..."} and nested format
   * {"name": {"agent_id": "...", "agent_arn": "arn:..."}}.
   * Also normalizes agent names (hyphens → underscores) so DB names
   * like "global-marketer" match runtime keys like "global_marketer".
   */
  private async loadRuntimeArns(): Promise<Record<string, string>> {
    if (this.runtimeArns) return this.runtimeArns;
    const arnsPath = join(resolve(), 'agentcore-deploy', 'runtime_arns.json');
    try {
      const raw = await fsReadFile(arnsPath, 'utf-8');
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      const flat: Record<string, string> = {};
      for (const [key, value] of Object.entries(parsed)) {
        if (typeof value === 'string') {
          flat[key] = value;
        } else if (value && typeof value === 'object' && 'agent_arn' in value) {
          flat[key] = (value as { agent_arn: string }).agent_arn;
        }
      }
      this.runtimeArns = flat;
      console.log(`[AgentCore] Loaded ${Object.keys(flat).length} runtime ARNs from ${arnsPath}: ${Object.keys(flat).join(', ')}`);
    } catch {
      console.warn(`[AgentCore] runtime_arns.json not found at ${arnsPath}, falling back to local Python runner`);
      this.runtimeArns = {};
    }
    return this.runtimeArns;
  }

  /**
   * Ensure the Python runner script is written to disk (fallback mode).
   */
  private async ensureRunnerScript(): Promise<string> {
    if (this.runnerScriptPath && existsSync(this.runnerScriptPath)) {
      return this.runnerScriptPath;
    }
    const dir = join(config.claude.workspaceBaseDir, '_strands');
    await mkdir(dir, { recursive: true });
    const scriptPath = join(dir, 'runner.py');
    await writeFile(scriptPath, STRANDS_RUNNER_SCRIPT, 'utf-8');
    this.runnerScriptPath = scriptPath;
    return scriptPath;
  }

  async loadSDK(): Promise<void> {
    // No-op for Strands — the Python subprocess handles SDK loading
  }

  startCleanupTimer(): void {
    if (this.cleanupInterval) return;
    this.cleanupInterval = setInterval(() => { this.cleanupTimedOutSessions(); }, 60_000);
    if (this.cleanupInterval.unref) this.cleanupInterval.unref();
  }

  stopCleanupTimer(): void {
    if (this.cleanupInterval) { clearInterval(this.cleanupInterval); this.cleanupInterval = null; }
  }

  private async acquireSlot(signal?: AbortSignal): Promise<void> {
    const max = config.claude.maxConcurrentSessions;
    if (this.activeSessions < max) {
      this.activeSessions++;
      return;
    }
    return new Promise<void>((resolve, reject) => {
      const entry = { resolve, reject };
      this.waitQueue.push(entry);
      const onAbort = () => {
        const idx = this.waitQueue.indexOf(entry);
        if (idx !== -1) this.waitQueue.splice(idx, 1);
        reject(new Error('Session queued but aborted while waiting for a concurrency slot'));
      };
      signal?.addEventListener('abort', onAbort, { once: true });
    });
  }

  private releaseSlot(): void {
    this.activeSessions--;
    const next = this.waitQueue.shift();
    if (next) {
      this.activeSessions++;
      next.resolve();
    }
  }

  private async cleanupTimedOutSessions(): Promise<void> {
    const now = Date.now();
    const timeoutMs = config.claude.sessionTimeoutMs;
    const timedOut: string[] = [];
    for (const [sid, ts] of this.lastActivity.entries()) {
      if (now - ts > timeoutMs) timedOut.push(sid);
    }
    for (const sid of timedOut) {
      console.log(`Session ${sid} timed out after ${timeoutMs}ms — disconnecting`);
      await this.disconnectSession(sid);
      this.lastActivity.delete(sid);
    }
  }

  /**
   * Run a conversation with the Strands agent via AgentCore Runtime.
   * Falls back to local Python subprocess if no runtime ARN is found.
   * Yields ConversationEvent objects compatible with the existing SSE streaming.
   */
  async *runConversation(
    options: StrandsAgentServiceOptions,
    agentConfig: AgentConfig,
    skills: SkillForWorkspace[],
    pluginPaths?: string[],
    mcpServers?: Record<string, AnyMCPServerConfig>,
  ): AsyncGenerator<ConversationEvent> {
    const abortController = new AbortController();
    await this.acquireSlot(abortController.signal);

    const sessionId = options.sessionId ?? crypto.randomUUID();

    try {
      // Check if this agent has a deployed AgentCore runtime
      const arns = await this.loadRuntimeArns();
      const agentName = agentConfig.name;
      // Normalize: DB uses hyphens (global-marketer), runtime_arns uses underscores (global_marketer)
      const normalizedName = agentName.replace(/-/g, '_');
      const runtimeArn = arns[normalizedName] || arns[agentName];

      if (runtimeArn) {
        // ── AgentCore Runtime invocation ──
        console.log(`[AgentCore] Matched agent "${agentName}" → "${normalizedName}" → ${runtimeArn}`);
        // Load chat history for context continuity
        const history = await this.loadChatHistory(options.organizationId, sessionId);
        yield* this.invokeAgentCore(runtimeArn, agentName, options.message, sessionId, history);
      } else {
        // ── Fallback: local Python subprocess ──
        console.log(`[AgentCore] No runtime ARN for "${agentName}" (available: ${Object.keys(arns).join(', ')}), falling back to local Python runner`);
        yield* this.runLocalPythonAgent(options, agentConfig, sessionId);
      }

    } catch (error) {
      console.error('[runConversation] Error:', error instanceof Error ? error.stack : error);
      yield {
        type: 'error',
        sessionId,
        code: 'AGENT_EXECUTION_ERROR',
        message: error instanceof Error ? error.message : 'Unknown error',
        suggestedAction: 'Please try again',
      };
    } finally {
      this.releaseSlot();
      this.abortControllers.delete(sessionId);
    }
  }

  /**
   * Load recent chat history for a session to provide conversation context.
   */
  private async loadChatHistory(
    organizationId: string,
    sessionId: string,
  ): Promise<Array<{ role: 'user' | 'assistant'; content: string }>> {
    try {
      const messages = await chatMessageRepository.findBySession(organizationId, sessionId, { limit: 20 });
      // findBySession returns desc order, reverse to chronological
      return messages.reverse().map(m => ({
        role: m.type === 'user' ? 'user' as const : 'assistant' as const,
        content: m.type === 'ai' ? this.extractTextFromContent(m.content) : m.content,
      }));
    } catch (err) {
      console.warn('[AgentCore] Failed to load chat history:', err);
      return [];
    }
  }

  /**
   * Extract plain text from stored AI message content (may be JSON ContentBlock[]).
   */
  private extractTextFromContent(content: string): string {
    try {
      const parsed = JSON.parse(content);
      if (Array.isArray(parsed)) {
        return parsed
          .filter((b: Record<string, unknown>) => b.type === 'text')
          .map((b: Record<string, unknown>) => b.text)
          .join('\n');
      }
    } catch { /* not JSON, use as-is */ }
    return content;
  }

  /**
   * Invoke an agent deployed on AgentCore Runtime.
   */
  private async *invokeAgentCore(
    runtimeArn: string,
    agentName: string,
    message: string,
    sessionId: string,
    history?: Array<{ role: 'user' | 'assistant'; content: string }>,
  ): AsyncGenerator<ConversationEvent> {
    console.log(`[AgentCore] Invoking runtime: ${agentName} → ${runtimeArn}`);

    this.abortControllers.set(sessionId, new AbortController());
    this.lastActivity.set(sessionId, Date.now());

    // Emit session_start
    yield { type: 'session_start', sessionId };

    // The frontend already shows a typing indicator (bouncing dots) while
    // the AI message content is empty, so no extra "thinking" event needed.

    const startTime = Date.now();

    const command = new InvokeAgentRuntimeCommand({
      agentRuntimeArn: runtimeArn,
      payload: new TextEncoder().encode(JSON.stringify({
        prompt: message,
        history: history && history.length > 0 ? history : undefined,
      })),
    });

    console.log(`[AgentCore] Sending InvokeAgentRuntimeCommand for ${agentName}...`);
    const response = await this.agentCoreClient.send(command);
    console.log(`[AgentCore] Received response from ${agentName} after ${Date.now() - startTime}ms`);

    // Read the response — it's a StreamingBlobPayloadOutputTypes
    let responseBody = '';
    const respData = response.response;
    if (respData) {
      if (respData instanceof Uint8Array || Buffer.isBuffer(respData)) {
        responseBody = new TextDecoder().decode(respData);
      } else if (typeof respData === 'string') {
        responseBody = respData;
      } else if (typeof (respData as any)[Symbol.asyncIterator] === 'function') {
        // Streaming response — collect chunks
        const chunks: Buffer[] = [];
        for await (const chunk of respData as AsyncIterable<Uint8Array>) {
          chunks.push(Buffer.from(chunk));
        }
        responseBody = Buffer.concat(chunks).toString('utf-8');
      } else if (typeof (respData as any).transformToString === 'function') {
        responseBody = await (respData as any).transformToString();
      } else if (typeof (respData as any).read === 'function') {
        const chunks: Buffer[] = [];
        for await (const chunk of respData as AsyncIterable<Uint8Array>) {
          chunks.push(Buffer.from(chunk));
        }
        responseBody = Buffer.concat(chunks).toString('utf-8');
      }
    }

    const durationMs = Date.now() - startTime;

    // Parse the response — AgentCore returns {"result": "..."}
    let resultText = responseBody;
    try {
      const parsed = JSON.parse(responseBody);
      resultText = parsed.result ?? parsed.message ?? responseBody;
    } catch {
      // Not JSON — use raw text
    }

    console.log(`[AgentCore] ${agentName} responded in ${durationMs}ms (${resultText.length} chars)`);

    // Emit assistant event
    yield {
      type: 'assistant',
      sessionId,
      content: [{ type: 'text', text: resultText }],
      model: 'bedrock-agentcore',
    };

    // Emit result event
    yield {
      type: 'result',
      sessionId,
      durationMs,
      numTurns: 1,
    };
  }

  /**
   * Fallback: run agent via local Python subprocess (original behavior).
   */
  private async *runLocalPythonAgent(
    options: StrandsAgentServiceOptions,
    agentConfig: AgentConfig,
    sessionId: string,
  ): AsyncGenerator<ConversationEvent> {
    const scriptPath = await this.ensureRunnerScript();

    const modelId = config.claude.model || 'anthropic.claude-sonnet-4-20250514-v1:0';
    const runnerConfig = {
      model_id: modelId,
      region: config.aws.region,
      system_prompt: this.buildSystemPrompt(agentConfig),
      message: options.message,
      session_id: sessionId,
    };

    const pythonCmd = process.env.STRANDS_PYTHON_CMD || 'python3';
    const child: ChildProcess = spawn(pythonCmd, [scriptPath], {
      env: {
        ...process.env,
        AWS_REGION: config.aws.region,
        AWS_DEFAULT_REGION: config.aws.region,
        ...(config.aws.accessKeyId ? { AWS_ACCESS_KEY_ID: config.aws.accessKeyId } : {}),
        ...(config.aws.secretAccessKey ? { AWS_SECRET_ACCESS_KEY: config.aws.secretAccessKey } : {}),
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    child.stdin!.write(JSON.stringify(runnerConfig));
    child.stdin!.end();

    const abortController = new AbortController();
    this.abortControllers.set(sessionId, abortController);
    this.lastActivity.set(sessionId, Date.now());
    abortController.signal.addEventListener('abort', () => {
      try { child.kill('SIGTERM'); } catch { /* ignore */ }
    });

    child.stderr?.on('data', (chunk: Buffer) => {
      console.error('[strands-agent-stderr]', chunk.toString().trim());
    });

    let buffer = '';
    const eventQueue: ConversationEvent[] = [];
    let resolveNext: (() => void) | null = null;
    let childDone = false;

    const processLine = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      try {
        const parsed = JSON.parse(trimmed);
        const event = this.parseRunnerEvent(parsed, sessionId);
        if (event) {
          eventQueue.push(event);
          if (resolveNext) { resolveNext(); resolveNext = null; }
        }
      } catch { /* Non-JSON line */ }
    };

    child.stdout?.on('data', (chunk: Buffer) => {
      buffer += chunk.toString();
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) processLine(line);
    });

    const exitPromise = new Promise<void>((resolve) => {
      child.on('close', () => {
        if (buffer.trim()) processLine(buffer);
        childDone = true;
        resolve();
        if (resolveNext) { resolveNext(); resolveNext = null; }
      });
    });

    while (true) {
      if (eventQueue.length > 0) {
        const event = eventQueue.shift()!;
        this.lastActivity.set(sessionId, Date.now());
        yield event;
      } else if (childDone) {
        break;
      } else {
        await new Promise<void>((r) => { resolveNext = r; });
      }
    }

    await exitPromise;
  }

  private buildSystemPrompt(agentConfig: AgentConfig): string {
    const base = agentConfig.systemPrompt ?? '';
    const suffix = [
      '',
      'You are a professional AI assistant. Be concise, accurate, and helpful.',
      'When you don\'t know something, say so honestly.',
      'Respond in the same language as the user\'s message.',
    ].join('\n');
    return base ? `${base}\n${suffix}` : suffix.trim();
  }

  private parseRunnerEvent(
    parsed: Record<string, unknown>,
    sessionId: string,
  ): ConversationEvent | null {
    const type = parsed.type as string;
    switch (type) {
      case 'session_start':
        return { type: 'session_start', sessionId: (parsed.session_id as string) ?? sessionId };
      case 'assistant':
        return {
          type: 'assistant',
          sessionId,
          content: (parsed.content as ContentBlock[]) ?? [{ type: 'text', text: '' }],
          model: parsed.model as string | undefined,
        };
      case 'result':
        return {
          type: 'result',
          sessionId,
          durationMs: parsed.duration_ms as number | undefined,
          numTurns: parsed.num_turns as number | undefined,
        };
      case 'error':
        return {
          type: 'error',
          sessionId,
          code: (parsed.code as string) ?? 'AGENT_ERROR',
          message: (parsed.message as string) ?? 'Unknown error',
          suggestedAction: parsed.suggested_action as string | undefined,
        };
      default:
        return null;
    }
  }

  async disconnectSession(sessionId: string): Promise<void> {
    const controller = this.abortControllers.get(sessionId);
    if (!controller) return;
    try { controller.abort(); } catch (error) {
      console.error(`Error disconnecting session ${sessionId}:`, error instanceof Error ? error.message : error);
    } finally {
      this.abortControllers.delete(sessionId);
      this.lastActivity.delete(sessionId);
    }
  }

  async disconnectAll(): Promise<number> {
    for (const entry of this.waitQueue) {
      entry.reject(new Error('Service shutting down'));
    }
    this.waitQueue.length = 0;
    const sessionIds = Array.from(this.abortControllers.keys());
    const count = sessionIds.length;
    await Promise.allSettled(sessionIds.map((id) =>
      Promise.race([this.disconnectSession(id), new Promise<void>((r) => setTimeout(r, 5000))])
    ));
    this.abortControllers.clear();
    this.lastActivity.clear();
    this.activeSessions = 0;
    this.stopCleanupTimer();
    console.log(`Cleaned up ${count} active Strands sessions`);
    return count;
  }

  async loadMCPServers(organizationId: string): Promise<Record<string, MCPServerSDKConfig>> {
    try {
      if (organizationId === 'system') return {};
      const servers = await prisma.mcp_servers.findMany({ where: { organization_id: organizationId } });
      return transformMCPServers(servers as unknown as MCPServerRecord[]);
    } catch (error) {
      console.error('Failed to load MCP servers:', error instanceof Error ? error.message : error);
      return {};
    }
  }

  get activeClientCount(): number { return this.abortControllers.size; }
  hasSession(sessionId: string): boolean { return this.abortControllers.has(sessionId); }
  getLastActivity(sessionId: string): number | undefined { return this.lastActivity.get(sessionId); }
  get trackedSessionCount(): number { return this.lastActivity.size; }
  get isCleanupTimerRunning(): boolean { return this.cleanupInterval !== null; }
  async triggerCleanup(): Promise<void> { await this.cleanupTimedOutSessions(); }
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

export function transformMCPServers(servers: MCPServerRecord[]): Record<string, MCPServerSDKConfig> {
  const result: Record<string, MCPServerSDKConfig> = Object.create(null);
  for (const server of servers) {
    if (server.status !== 'active') continue;
    const sdkConfig = parseMCPServerConfig(server);
    if (sdkConfig) result[server.name] = sdkConfig;
  }
  return result;
}

export function parseMCPServerConfig(server: MCPServerRecord): MCPServerSDKConfig | null {
  if (server.config && typeof server.config === 'object') {
    const c = server.config as Record<string, unknown>;
    const type = (c.type as string) || 'stdio';
    if (type === 'sse' || type === 'http') {
      const url = c.url as string | undefined;
      if (!url) return null;
      return { type, url };
    }
    const command = c.command as string | undefined;
    if (!command) return null;
    return {
      type: 'stdio',
      command,
      args: Array.isArray(c.args) ? (c.args as string[]) : undefined,
      env: c.env && typeof c.env === 'object' ? (c.env as Record<string, string>) : undefined,
    };
  }
  const address = server.host_address?.trim();
  if (!address) return null;
  if (address.startsWith('http://') || address.startsWith('https://')) return { type: 'sse', url: address };
  const parts = address.split(/\s+/);
  return { type: 'stdio', command: parts[0], args: parts.length > 1 ? parts.slice(1) : undefined };
}

// Export singleton — drop-in replacement for claudeAgentService
export const strandsAgentService = new StrandsAgentService();

// Backward-compatible alias
export const claudeAgentService = strandsAgentService;
