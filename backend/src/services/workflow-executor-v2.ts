/**
 * Workflow Executor V2 — Unified Agent Execution with Hook-Based Progress
 *
 * Executes an entire workflow as a single Claude Code session.
 * The workflow plan is serialized into a mission brief (CLAUDE.md),
 * and Claude executes all steps within one conversation.
 *
 * Progress is reported via an in-process MCP server that provides
 * workflow_step_start / workflow_step_complete / workflow_step_failed tools.
 * Claude calls these tools as it works through each step, giving the
 * frontend deterministic, real-time progress updates.
 */

import { writeFile } from 'fs/promises';
import { join } from 'path';
import { claudeAgentService, type AgentConfig, type ConversationEvent, type AnyMCPServerConfig } from './claude-agent.service.js';
import { workspaceManager, type ScopeForWorkspace, type SkillForWorkspace } from './workspace-manager.js';
import { businessScopeService } from './businessScope.service.js';
import { skillService } from './skill.service.js';
import { agentRepository } from '../repositories/agent.repository.js';
import { skillRepository } from '../repositories/skill.repository.js';
import { createWorkflowProgressServer } from './workflow-progress-mcp.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WorkflowV2Node {
  id: string;
  title: string;
  type: 'agent' | 'action' | 'condition' | 'document' | 'codeArtifact';
  prompt: string;
  dependentTasks?: string[];
  agentId?: string;
}

export interface WorkflowV2Variable {
  variableId: string;
  name: string;
  value: string;
  description?: string;
}

export interface WorkflowV2Plan {
  title: string;
  description?: string;
  nodes: WorkflowV2Node[];
  edges: Array<{ source: string; target: string }>;
  variables?: WorkflowV2Variable[];
}

export interface WorkflowProgressEvent {
  type: 'step_start' | 'step_complete' | 'step_failed' | 'log' | 'error' | 'done';
  taskId?: string;
  taskTitle?: string;
  message?: string;
  content?: unknown;
}

// ---------------------------------------------------------------------------
// Plan Serializer
// ---------------------------------------------------------------------------

function serializePlanToMissionBrief(
  plan: WorkflowV2Plan,
  agents: Array<{ id: string; name: string; displayName: string; role: string | null }>,
  scopeSkillNames: string[],
): string {
  const lines: string[] = [
    `# Workflow: ${plan.title}`,
    '',
  ];

  if (plan.description) {
    lines.push(plan.description, '');
  }

  // Variables
  if (plan.variables && plan.variables.length > 0) {
    lines.push('## Input Variables', '');
    for (const v of plan.variables) {
      lines.push(`- **${v.name}**: ${v.value || '(not provided)'}${v.description ? ` — ${v.description}` : ''}`);
    }
    lines.push('');
  }

  // Available integrations
  if (scopeSkillNames.length > 0) {
    lines.push('## Available API Skills', '');
    lines.push('You have access to these API integration skills. Use them when a step requires external API calls:');
    for (const name of scopeSkillNames) {
      lines.push(`- ${name}`);
    }
    lines.push('');
  }

  // Build dependency map for ordering
  const depMap = new Map<string, string[]>();
  for (const node of plan.nodes) {
    depMap.set(node.id, node.dependentTasks || []);
  }

  // Execution plan
  lines.push('## Execution Plan', '');

  for (let i = 0; i < plan.nodes.length; i++) {
    const node = plan.nodes[i]!;
    const stepNum = i + 1;
    const typeLabel = `[${node.type}]`;

    // Agent reference
    let agentLabel = '';
    if (node.agentId) {
      const agent = agents.find(a => a.id === node.agentId);
      if (agent) {
        agentLabel = ` (delegate to agent: ${agent.name})`;
      }
    }

    lines.push(`### Step ${stepNum}: ${node.id} — ${node.title} ${typeLabel}${agentLabel}`);

    // Dependencies
    const deps = depMap.get(node.id) || [];
    if (deps.length > 0) {
      lines.push(`Depends on: ${deps.join(', ')}`);
    }

    lines.push('');
    lines.push(node.prompt);
    lines.push('');
  }

  // Progress reporting instructions — use MCP tools instead of text markers
  lines.push('## Progress Reporting (CRITICAL)', '');
  lines.push('You have access to three workflow progress tools. You MUST call them as you work:');
  lines.push('');
  lines.push('1. **Before starting each step**: call `workflow_step_start` with the task ID');
  lines.push('2. **After completing each step**: call `workflow_step_complete` with the task ID');
  lines.push('3. **If a step fails**: call `workflow_step_failed` with the task ID and reason');
  lines.push('');
  lines.push('The task IDs for each step are listed above (e.g. the ID after "Step N:"). Use the EXACT task ID.');
  lines.push('');
  lines.push('Execute the steps in dependency order. Steps with no dependencies can be done first.');
  lines.push('Steps that share the same dependencies can be done in any order.');

  return lines.join('\n');
}

// ---------------------------------------------------------------------------
// Executor
// ---------------------------------------------------------------------------

export class WorkflowExecutorV2 {
  /**
   * Execute a workflow plan as a single Claude session.
   * Yields progress events that can be forwarded as SSE to the frontend.
   *
   * Progress tracking uses an in-process MCP server that gives Claude
   * explicit tools to report step start/complete/failed. This is far more
   * reliable than parsing text markers from Claude's output.
   */
  async *execute(
    plan: WorkflowV2Plan,
    organizationId: string,
    scopeId: string,
    userId: string,
  ): AsyncGenerator<WorkflowProgressEvent> {
    // 1. Load scope data
    const scope = await businessScopeService.getBusinessScopeById(scopeId, organizationId);
    if (!scope) {
      yield { type: 'error', message: 'Business scope not found' };
      return;
    }

    // 2. Load agents with skills
    const agents = await agentRepository.findByBusinessScope(organizationId, scopeId);
    const agentSkillsMap = new Map<string, string[]>();
    for (const agent of agents) {
      const agentSkills = await skillRepository.findByAgentId(organizationId, agent.id);
      agentSkillsMap.set(agent.id, agentSkills.map(s => s.name));
    }

    // 3. Load scope-level skills
    const scopeLevelSkills = await skillService.getScopeLevelSkills(organizationId, scopeId);

    // 4. Build combined skills list for workspace
    const skillMap = new Map<string, SkillForWorkspace>();
    for (const agent of agents) {
      const agentSkills = await skillRepository.findByAgentId(organizationId, agent.id);
      for (const s of agentSkills) {
        if (!skillMap.has(s.id)) {
          const meta = s.metadata as Record<string, unknown> | null;
          skillMap.set(s.id, {
            id: s.id, name: s.name, hashId: s.hash_id,
            s3Bucket: s.s3_bucket, s3Prefix: s.s3_prefix,
            localPath: meta?.localPath as string | undefined,
          });
        }
      }
    }
    for (const s of scopeLevelSkills) {
      if (!skillMap.has(s.id)) {
        const meta = s.metadata as Record<string, unknown> | null;
        skillMap.set(s.id, {
          id: s.id, name: s.name, hashId: s.hash_id,
          s3Bucket: s.s3_bucket, s3Prefix: s.s3_prefix,
          localPath: meta?.localPath as string | undefined,
        });
      }
    }

    // 5. Provision workspace
    const sessionId = crypto.randomUUID();
    const scopeForWorkspace: ScopeForWorkspace = {
      id: scope.id,
      name: scope.name,
      description: scope.description,
      configVersion: scope.config_version ?? 1,
      agents: agents.map(a => ({
        id: a.id,
        name: a.name,
        displayName: a.display_name,
        role: a.role,
        systemPrompt: a.system_prompt,
        skillNames: agentSkillsMap.get(a.id) || [],
      })),
      skills: Array.from(skillMap.values()),
      mcpServers: [],
      plugins: [],
    };

    const { workspacePath } = await workspaceManager.ensureSessionWorkspace(
      organizationId, sessionId, scopeForWorkspace, null,
    );

    // 6. Build node title map
    const nodeTitleMap = new Map<string, string>();
    for (const node of plan.nodes) {
      nodeTitleMap.set(node.id, node.title);
    }

    // 7. Create in-process MCP server for progress reporting
    //    Events from tool calls are pushed into a queue that the generator drains.
    const eventQueue: WorkflowProgressEvent[] = [];
    const progressServer = await createWorkflowProgressServer(
      nodeTitleMap,
      (event) => { eventQueue.push(event); },
    );

    // 8. Write mission brief as CLAUDE.md
    const missionBrief = serializePlanToMissionBrief(
      plan,
      agents.map(a => ({ id: a.id, name: a.name, displayName: a.display_name, role: a.role })),
      scopeLevelSkills.map(s => s.name),
    );
    await writeFile(join(workspacePath, 'CLAUDE.md'), missionBrief, 'utf-8');

    // 9. Run single Claude session with the progress MCP server attached
    const agentConfig: AgentConfig = {
      id: `workflow-v2-${sessionId}`,
      name: 'workflow-executor',
      displayName: `Workflow: ${plan.title}`,
      organizationId,
      systemPrompt: '',
      skillIds: [],
      mcpServerIds: [],
    };

    // Build MCP servers map: include the in-process progress server
    const mcpServers: Record<string, AnyMCPServerConfig> = {
      'workflow-progress': progressServer as unknown as AnyMCPServerConfig,
    };

    try {
      const generator = claudeAgentService.runConversation(
        {
          agentId: agentConfig.id,
          message: 'Execute the workflow defined in CLAUDE.md. Follow the execution plan step by step. Use the workflow_step_start, workflow_step_complete, and workflow_step_failed tools to report your progress on each step.',
          organizationId,
          userId,
          workspacePath,
        },
        agentConfig,
        Array.from(skillMap.values()),
        undefined, // pluginPaths
        mcpServers,
      );

      for await (const event of generator) {
        // Drain any progress events that accumulated from MCP tool calls
        while (eventQueue.length > 0) {
          yield eventQueue.shift()!;
        }

        // Extract text content for log events
        const textContent = this.extractText(event);
        if (textContent) {
          yield { type: 'log', content: textContent };
        }

        // Handle errors
        if (event.type === 'error') {
          yield {
            type: 'error',
            message: (event as ConversationEvent & { message?: string }).message || 'Execution error',
          };
        }
      }

      // Drain any remaining progress events
      while (eventQueue.length > 0) {
        yield eventQueue.shift()!;
      }

      yield { type: 'done' };
    } catch (error) {
      yield {
        type: 'error',
        message: error instanceof Error ? error.message : 'Workflow execution failed',
      };
    }
  }

  private extractText(event: ConversationEvent): string | null {
    if (event.type === 'assistant' || event.type === 'result') {
      const content = (event as ConversationEvent & { content?: unknown }).content;
      if (Array.isArray(content)) {
        return content
          .filter((b: { type: string; text?: string }) => b.type === 'text' && b.text)
          .map((b: { type: string; text?: string }) => b.text ?? '')
          .join('');
      }
      if (typeof content === 'string') return content;
    }
    return null;
  }
}

export const workflowExecutorV2 = new WorkflowExecutorV2();
