/**
 * Claude Agent Service — Compatibility Shim
 *
 * Re-exports everything from strands-agent.service.ts for backward compatibility.
 * The actual agent implementation now uses Strands Agents SDK on Amazon Bedrock.
 */

export {
  type AgentConfig,
  type ContentBlock,
  type ConversationEvent,
  type MCPServerSDKConfig,
  type MCPServerInProcessConfig,
  type AnyMCPServerConfig,
  type MCPServerRecord,
  type StrandsAgentService as ClaudeAgentService,
  type ClaudeAgentServiceOptions,
  StrandsAgentService,
  strandsAgentService as claudeAgentService,
  transformMCPServers,
  parseMCPServerConfig,
} from './strands-agent.service.js';

// Re-export legacy SDK types as stubs for files that reference them
export interface SDKHookInput {
  session_id: string;
  transcript_path: string;
  cwd: string;
  permission_mode?: string;
  hook_event_name: string;
  tool_name?: string;
  tool_input?: unknown;
  [key: string]: unknown;
}

export interface SDKHookOutput {
  continue?: boolean;
  suppressOutput?: boolean;
  stopReason?: string;
  decision?: 'approve' | 'block';
  reason?: string;
  hookSpecificOutput?: Record<string, unknown>;
}

export type SDKHookCallback = (
  input: SDKHookInput,
  toolUseID: string | undefined,
  options: { signal: AbortSignal },
) => Promise<SDKHookOutput>;

export interface SDKHookCallbackMatcher {
  matcher?: string;
  hooks: SDKHookCallback[];
}

export interface ClaudeCodeOptions {
  systemPrompt?: string | { type: 'preset'; preset: 'claude_code'; append?: string };
  allowedTools?: string[];
  cwd?: string;
  resume?: string;
  model?: string;
  permissionMode?: 'default' | 'acceptEdits' | 'bypassPermissions' | 'plan';
  allowDangerouslySkipPermissions?: boolean;
  hooks?: Partial<Record<string, SDKHookCallbackMatcher[]>>;
  mcpServers?: Record<string, AnyMCPServerConfig>;
  abortController?: AbortController;
  maxTurns?: number;
  pathToClaudeCodeExecutable?: string;
  env?: Record<string, string | undefined>;
  stderr?: (data: string) => void;
  settingSources?: Array<'user' | 'project' | 'local'>;
  plugins?: Array<{ type: 'local'; path: string }>;
}

export interface SDKSystemMessage {
  type: 'system';
  subtype: string;
  session_id: string;
  uuid: string;
  model?: string;
  tools?: string[];
  cwd?: string;
  [key: string]: unknown;
}

export interface TextBlock { type: 'text'; text: string; }
export interface ToolUseBlock { type: 'tool_use'; id: string; name: string; input: Record<string, unknown>; }
export interface ToolResultBlock { type: 'tool_result'; tool_use_id: string; content: string | null; is_error: boolean; }
export type SDKContentBlock = TextBlock | ToolUseBlock | ToolResultBlock;

export interface SDKAssistantMessage {
  type: 'assistant';
  uuid: string;
  session_id: string;
  message: {
    content: Array<{ type: string; text?: string; id?: string; name?: string; input?: Record<string, unknown> }>;
    model?: string;
    [key: string]: unknown;
  };
  parent_tool_use_id: string | null;
}

export interface SDKResultMessage {
  type: 'result';
  subtype: string;
  uuid: string;
  session_id: string;
  duration_ms: number;
  num_turns: number;
  is_error: boolean;
  result?: string;
  [key: string]: unknown;
}

export type SDKMessage = SDKSystemMessage | SDKAssistantMessage | SDKResultMessage | { type: string; [key: string]: unknown };
export interface SDKQuery extends AsyncGenerator<SDKMessage, void> { interrupt(): Promise<void>; }
export type QueryFactory = (args: { prompt: string; options?: ClaudeCodeOptions }) => SDKQuery;
