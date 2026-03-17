/**
 * Database Seed Script
 * 
 * Populates the database with test data for development.
 * Run with: npx tsx prisma/seed.ts
 */

import { PrismaClient } from '@prisma/client';
import { PrismaPg } from '@prisma/adapter-pg';
import pg from 'pg';
import * as dotenv from 'dotenv';

// Load environment variables
dotenv.config();

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
  throw new Error('DATABASE_URL environment variable is required');
}

// Create pg Pool
const pool = new pg.Pool({ connectionString });

// Create Prisma adapter and client
const adapter = new PrismaPg(pool);
const prisma = new PrismaClient({ adapter });

async function main() {
  console.log('🌱 Starting database seed...');

  // Get existing organization or create one
  let org = await prisma.organizations.findFirst();
  
  if (!org) {
    console.log('Creating organization...');
    org = await prisma.organizations.create({
      data: {
        name: 'Demo Company',
        slug: 'demo-company',
        plan_type: 'enterprise',
      },
    });
  }
  
  const orgId = org.id;
  console.log(`Using organization: ${org.name} (${orgId})`);

  // Get or create a test user
  let profile = await prisma.profiles.findFirst();
  
  if (!profile) {
    console.log('Creating test user...');
    profile = await prisma.profiles.create({
      data: {
        id: crypto.randomUUID(),
        username: 'admin@example.com',
        full_name: 'Admin User',
        active_organization_id: orgId,
      },
    });

    await prisma.memberships.create({
      data: {
        user_id: profile.id,
        organization_id: orgId,
        role: 'owner',
      },
    });
  }
  
  const userId = profile.id;
  console.log(`Using user: ${profile.full_name} (${userId})`);

  // Create Business Scopes
  console.log('Creating business scopes...');
  const scopes = await Promise.all([
    prisma.business_scopes.upsert({
      where: { unique_scope_name_per_org: { organization_id: orgId, name: 'Game Operations' } },
      update: {},
      create: {
        organization_id: orgId,
        name: 'Game Operations',
        description: '游戏运营管理：玩家数据分析、活动策划、版本更新管理、用户留存优化、付费转化分析',
        icon: '🎮',
        color: '#FF5722',
        is_default: true,
      },
    }),
    prisma.business_scopes.upsert({
      where: { unique_scope_name_per_org: { organization_id: orgId, name: 'Global Marketing' } },
      update: {},
      create: {
        organization_id: orgId,
        name: 'Global Marketing',
        description: '出海营销：多语言内容生成、社交媒体运营、KOL合作管理、广告投放优化、市场本地化',
        icon: '🌍',
        color: '#2196F3',
        is_default: true,
      },
    }),
    prisma.business_scopes.upsert({
      where: { unique_scope_name_per_org: { organization_id: orgId, name: 'AI Website Builder' } },
      update: {},
      create: {
        organization_id: orgId,
        name: 'AI Website Builder',
        description: 'AI生成网站：自然语言建站、模板生成、SEO优化、响应式设计、一键部署发布',
        icon: '🌐',
        color: '#9C27B0',
        is_default: true,
      },
    }),
    prisma.business_scopes.upsert({
      where: { unique_scope_name_per_org: { organization_id: orgId, name: 'Human Resources' } },
      update: {},
      create: {
        organization_id: orgId,
        name: 'Human Resources',
        description: 'HR department operations and employee management',
        icon: '👥',
        color: '#4CAF50',
        is_default: true,
      },
    }),
    prisma.business_scopes.upsert({
      where: { unique_scope_name_per_org: { organization_id: orgId, name: 'Information Technology' } },
      update: {},
      create: {
        organization_id: orgId,
        name: 'Information Technology',
        description: 'IT support and infrastructure management',
        icon: '💻',
        color: '#607D8B',
        is_default: true,
      },
    }),
  ]);

  const [gameOpsScope, globalMktScope, aiWebScope, hrScope, itScope] = scopes;
  console.log(`Created ${scopes.length} business scopes`);

  // Create Agents
  console.log('Creating agents...');
  const agents = await Promise.all([
    // Game Operations Agents
    prisma.agents.create({
      data: {
        organization_id: orgId,
        business_scope_id: gameOpsScope.id,
        name: 'player-analyst',
        display_name: '玩家数据分析师',
        role: 'Player Data Analyst',
        avatar: '📊',
        status: 'active',
        metrics: { taskCount: 234, responseRate: 98, avgResponseTime: '1.5s' },
        tools: [
          { id: 'tool-1', name: 'Player Analytics', description: 'Analyzes player behavior and retention data' },
          { id: 'tool-2', name: 'Revenue Dashboard', description: 'Tracks in-app purchase and ad revenue' },
        ],
        scope: ['Player Retention', 'Revenue Analysis', 'Churn Prediction'],
        system_prompt: '你是一位专业的游戏数据分析师。你擅长分析玩家行为数据、留存率、付费转化率和LTV。请用数据驱动的方式提供运营建议。回答时请使用中文。',
        model_config: { provider: 'Bedrock', modelId: 'anthropic.claude-sonnet-4-20250514-v1:0', agentType: 'Worker', framework: 'strands' },
      },
    }),
    prisma.agents.create({
      data: {
        organization_id: orgId,
        business_scope_id: gameOpsScope.id,
        name: 'event-planner',
        display_name: '活动策划助手',
        role: 'Game Event Planner',
        avatar: '🎯',
        status: 'active',
        metrics: { taskCount: 156, responseRate: 96, avgResponseTime: '2.0s' },
        tools: [
          { id: 'tool-3', name: 'Event Template Generator', description: 'Generates game event templates' },
          { id: 'tool-4', name: 'A/B Test Manager', description: 'Manages event A/B testing' },
        ],
        scope: ['Event Planning', 'A/B Testing', 'Reward Design'],
        system_prompt: '你是一位游戏活动策划专家。你擅长设计游戏内活动、奖励机制和限时活动。请根据玩家画像和游戏类型提供创意方案。回答时请使用中文。',
        model_config: { provider: 'Bedrock', modelId: 'anthropic.claude-sonnet-4-20250514-v1:0', agentType: 'Worker', framework: 'strands' },
      },
    }),
    // Global Marketing Agents
    prisma.agents.create({
      data: {
        organization_id: orgId,
        business_scope_id: globalMktScope.id,
        name: 'content-localizer',
        display_name: '多语言内容生成器',
        role: 'Content Localization Specialist',
        avatar: '🌏',
        status: 'active',
        metrics: { taskCount: 312, responseRate: 99, avgResponseTime: '1.8s' },
        tools: [
          { id: 'tool-5', name: 'Translation Engine', description: 'Multi-language content translation and localization' },
          { id: 'tool-6', name: 'Cultural Adapter', description: 'Adapts content for local cultural context' },
        ],
        scope: ['Translation', 'Localization', 'Cultural Adaptation'],
        system_prompt: '你是一位出海营销内容专家。你精通多语言内容创作和本地化，了解不同市场的文化差异和用户偏好。支持英语、日语、韩语、东南亚语言等。回答时请使用中文，但生成的营销内容请使用目标语言。',
        model_config: { provider: 'Bedrock', modelId: 'anthropic.claude-sonnet-4-20250514-v1:0', agentType: 'Worker', framework: 'strands' },
      },
    }),
    prisma.agents.create({
      data: {
        organization_id: orgId,
        business_scope_id: globalMktScope.id,
        name: 'ad-optimizer',
        display_name: '广告投放优化师',
        role: 'Ad Campaign Optimizer',
        avatar: '📈',
        status: 'active',
        metrics: { taskCount: 189, responseRate: 97, avgResponseTime: '1.2s' },
        tools: [
          { id: 'tool-7', name: 'Ad Performance Analyzer', description: 'Analyzes ad campaign performance across platforms' },
          { id: 'tool-8', name: 'Budget Allocator', description: 'Optimizes ad budget allocation' },
        ],
        scope: ['Ad Optimization', 'Budget Management', 'ROI Analysis'],
        system_prompt: '你是一位数字广告投放优化专家。你擅长Facebook、Google、TikTok等平台的广告投放策略，能够分析广告数据并提供优化建议。回答时请使用中文。',
        model_config: { provider: 'Bedrock', modelId: 'anthropic.claude-sonnet-4-20250514-v1:0', agentType: 'Worker', framework: 'strands' },
      },
    }),
    // AI Website Builder Agents
    prisma.agents.create({
      data: {
        organization_id: orgId,
        business_scope_id: aiWebScope.id,
        name: 'site-generator',
        display_name: 'AI建站助手',
        role: 'Website Generator',
        avatar: '🏗️',
        status: 'active',
        metrics: { taskCount: 567, responseRate: 99, avgResponseTime: '3.0s' },
        tools: [
          { id: 'tool-9', name: 'HTML/CSS Generator', description: 'Generates responsive HTML/CSS from descriptions' },
          { id: 'tool-10', name: 'Template Engine', description: 'Applies and customizes website templates' },
        ],
        scope: ['Website Generation', 'Template Design', 'Responsive Layout'],
        system_prompt: '你是一位AI网站生成专家。你能根据用户的自然语言描述生成完整的网站代码，包括HTML、CSS和JavaScript。生成的网站应该是响应式的、美观的、符合现代设计标准的。回答时请使用中文。',
        model_config: { provider: 'Bedrock', modelId: 'anthropic.claude-sonnet-4-20250514-v1:0', agentType: 'Worker', framework: 'strands' },
      },
    }),
    prisma.agents.create({
      data: {
        organization_id: orgId,
        business_scope_id: aiWebScope.id,
        name: 'seo-optimizer',
        display_name: 'SEO优化助手',
        role: 'SEO Specialist',
        avatar: '🔍',
        status: 'active',
        metrics: { taskCount: 145, responseRate: 95, avgResponseTime: '1.5s' },
        tools: [
          { id: 'tool-11', name: 'SEO Analyzer', description: 'Analyzes and optimizes website SEO' },
          { id: 'tool-12', name: 'Meta Tag Generator', description: 'Generates optimized meta tags' },
        ],
        scope: ['SEO Optimization', 'Meta Tags', 'Content Strategy'],
        system_prompt: '你是一位SEO优化专家。你擅长网站SEO分析、关键词优化、meta标签生成和内容策略制定。回答时请使用中文。',
        model_config: { provider: 'Bedrock', modelId: 'anthropic.claude-sonnet-4-20250514-v1:0', agentType: 'Worker', framework: 'strands' },
      },
    }),
    // HR Agent
    prisma.agents.create({
      data: {
        organization_id: orgId,
        business_scope_id: hrScope.id,
        name: 'hr-assistant',
        display_name: 'HR Assistant',
        role: 'Recruitment Specialist',
        avatar: 'H',
        status: 'active',
        metrics: { taskCount: 156, responseRate: 98, avgResponseTime: '1.2s' },
        tools: [
          { id: 'tool-13', name: 'Resume Parser', description: 'Extracts information from resumes' },
          { id: 'tool-14', name: 'Calendar Integration', description: 'Schedules interviews' },
        ],
        scope: ['Recruitment', 'Onboarding', 'Employee Records'],
        system_prompt: 'You are an HR assistant specialized in recruitment and onboarding processes.',
        model_config: { provider: 'Bedrock', modelId: 'anthropic.claude-sonnet-4-20250514-v1:0', agentType: 'Worker', framework: 'strands' },
      },
    }),
    // IT Agent
    prisma.agents.create({
      data: {
        organization_id: orgId,
        business_scope_id: itScope.id,
        name: 'it-support',
        display_name: 'IT Support Agent',
        role: 'Technical Support',
        avatar: 'I',
        status: 'active',
        metrics: { taskCount: 234, responseRate: 99, avgResponseTime: '0.8s' },
        tools: [
          { id: 'tool-15', name: 'Ticket System', description: 'Manages support tickets' },
          { id: 'tool-16', name: 'Remote Access', description: 'Provides remote assistance' },
        ],
        scope: ['Troubleshooting', 'System Access', 'Password Reset'],
        system_prompt: 'You are an IT support agent helping users with technical issues.',
        model_config: { provider: 'Bedrock', modelId: 'anthropic.claude-sonnet-4-20250514-v1:0', agentType: 'Worker', framework: 'strands' },
      },
    }),
    // Global Marketing Agent
    prisma.agents.create({
      data: {
        organization_id: orgId,
        business_scope_id: globalMktScope.id,
        name: 'global-marketer',
        display_name: '出海营销专家',
        role: 'Global Marketing Specialist',
        avatar: '🚀',
        status: 'active',
        metrics: { taskCount: 0, responseRate: 0, avgResponseTime: '2.5s' },
        tools: [
          { id: 'tool-17', name: 'Web Browser', description: 'AgentCore Browser for web data collection, competitor analysis, and market research' },
          { id: 'tool-18', name: 'Web Search', description: 'Search the web for real-time marketing data and industry trends' },
          { id: 'tool-19', name: 'Skill Loader', description: 'Load marketing skills and knowledge frameworks on demand' },
        ],
        scope: ['Social Media Marketing', 'Competitor Analysis', 'Ad Optimization', 'Content Localization', 'KOL Management', 'Market Research', 'Web Data Collection'],
        system_prompt: '你是一位资深的出海营销专家(Global Marketing Specialist)。你精通全球市场营销策略制定、多语言内容创作、社交媒体矩阵运营(TikTok/Facebook/Instagram/LinkedIn/YouTube/小红书)、KOL网红合作管理、广告投放优化(Facebook Ads/Google Ads/TikTok Ads)、市场本地化和竞品分析。你具备浏览器数据采集能力，可以访问网页获取实时市场数据、竞品信息和行业趋势。回答时请使用中文，但生成的营销内容请使用目标市场语言。',
        model_config: { provider: 'Bedrock', modelId: 'anthropic.claude-sonnet-4-20250514-v1:0', agentType: 'Worker', framework: 'strands' },
      },
    }),
  ]);
  console.log(`Created ${agents.length} agents`);

  // Create Workflows
  console.log('Creating workflows...');
  const workflows = await Promise.all([
    prisma.workflows.create({
      data: {
        organization_id: orgId,
        business_scope_id: gameOpsScope.id,
        name: 'Player Churn Prevention',
        version: '1.0.0',
        is_official: true,
        nodes: [
          { id: 'node-1', type: 'trigger', label: 'Daily Player Data', position: { x: 100, y: 100 } },
          { id: 'node-2', type: 'agent', label: '玩家数据分析师', position: { x: 300, y: 100 }, agentId: agents[0].id },
          { id: 'node-3', type: 'agent', label: '活动策划助手', position: { x: 500, y: 100 }, agentId: agents[1].id },
          { id: 'node-4', type: 'human', label: 'Manager Review', position: { x: 700, y: 100 } },
          { id: 'node-5', type: 'end', label: 'Execute Campaign', position: { x: 900, y: 100 } },
        ],
        connections: [
          { id: 'conn-1', from: 'node-1', to: 'node-2' },
          { id: 'conn-2', from: 'node-2', to: 'node-3' },
          { id: 'conn-3', from: 'node-3', to: 'node-4' },
          { id: 'conn-4', from: 'node-4', to: 'node-5' },
        ],
        created_by: userId,
      },
    }),
    prisma.workflows.create({
      data: {
        organization_id: orgId,
        business_scope_id: globalMktScope.id,
        name: 'Global Content Pipeline',
        version: '1.0.0',
        is_official: true,
        nodes: [
          { id: 'node-1', type: 'trigger', label: 'New Campaign Brief', position: { x: 100, y: 100 } },
          { id: 'node-2', type: 'agent', label: '多语言内容生成器', position: { x: 300, y: 100 }, agentId: agents[2].id },
          { id: 'node-3', type: 'agent', label: '广告投放优化师', position: { x: 500, y: 100 }, agentId: agents[3].id },
          { id: 'node-4', type: 'human', label: 'Content Review', position: { x: 700, y: 100 } },
          { id: 'node-5', type: 'end', label: 'Publish', position: { x: 900, y: 100 } },
        ],
        connections: [
          { id: 'conn-1', from: 'node-1', to: 'node-2' },
          { id: 'conn-2', from: 'node-2', to: 'node-3' },
          { id: 'conn-3', from: 'node-3', to: 'node-4' },
          { id: 'conn-4', from: 'node-4', to: 'node-5' },
        ],
        created_by: userId,
      },
    }),
    prisma.workflows.create({
      data: {
        organization_id: orgId,
        business_scope_id: aiWebScope.id,
        name: 'AI Website Generation',
        version: '1.0.0',
        is_official: true,
        nodes: [
          { id: 'node-1', type: 'trigger', label: 'User Request', position: { x: 100, y: 100 } },
          { id: 'node-2', type: 'agent', label: 'AI建站助手', position: { x: 300, y: 100 }, agentId: agents[4].id },
          { id: 'node-3', type: 'agent', label: 'SEO优化助手', position: { x: 500, y: 100 }, agentId: agents[5].id },
          { id: 'node-4', type: 'end', label: 'Deploy', position: { x: 700, y: 100 } },
        ],
        connections: [
          { id: 'conn-1', from: 'node-1', to: 'node-2' },
          { id: 'conn-2', from: 'node-2', to: 'node-3' },
          { id: 'conn-3', from: 'node-3', to: 'node-4' },
        ],
        created_by: userId,
      },
    }),
  ]);
  console.log(`Created ${workflows.length} workflows`);

  // Create Tasks
  console.log('Creating tasks...');
  const tasks = await Promise.all([
    prisma.tasks.create({
      data: {
        organization_id: orgId,
        agent_id: agents[0].id,
        workflow_id: workflows[0].id,
        description: 'Analyze player retention data for the past 30 days',
        status: 'complete',
        details: { playerCount: 50000, churnRate: '12%', retentionD7: '45%' },
        created_by: userId,
      },
    }),
    prisma.tasks.create({
      data: {
        organization_id: orgId,
        agent_id: agents[2].id,
        workflow_id: workflows[1].id,
        description: 'Localize marketing content for Japanese market',
        status: 'complete',
        details: { targetLanguage: 'ja', contentPieces: 15 },
        created_by: userId,
      },
    }),
    prisma.tasks.create({
      data: {
        organization_id: orgId,
        agent_id: agents[4].id,
        workflow_id: workflows[2].id,
        description: 'Generate landing page for new product launch',
        status: 'running',
        details: { template: 'modern-saas', pages: 3 },
        created_by: userId,
      },
    }),
    prisma.tasks.create({
      data: {
        organization_id: orgId,
        agent_id: agents[1].id,
        description: 'Design Spring Festival in-game event',
        status: 'running',
        details: { eventType: 'seasonal', duration: '14 days' },
        created_by: userId,
      },
    }),
    prisma.tasks.create({
      data: {
        organization_id: orgId,
        agent_id: agents[3].id,
        description: 'Optimize Facebook ad campaign for Southeast Asia',
        status: 'complete',
        details: { platform: 'Facebook', region: 'SEA', budget: '$5000' },
        created_by: userId,
      },
    }),
  ]);
  console.log(`Created ${tasks.length} tasks`);

  // Create MCP Servers
  console.log('Creating MCP servers...');
  const mcpServers = await Promise.all([
    prisma.mcp_servers.create({
      data: {
        organization_id: orgId,
        name: 'GitHub Integration',
        description: 'Connect to GitHub repositories and manage code',
        host_address: 'https://api.github.com',
        headers: { 'X-Custom-Header': 'github-integration' },
        status: 'active',
      },
    }),
    prisma.mcp_servers.create({
      data: {
        organization_id: orgId,
        name: 'Slack Integration',
        description: 'Send messages and manage Slack channels',
        host_address: 'https://slack.com/api',
        headers: {},
        status: 'active',
      },
    }),
  ]);
  console.log(`Created ${mcpServers.length} MCP servers`);

  // Create Documents
  console.log('Creating documents...');
  const documents = await Promise.all([
    prisma.documents.create({
      data: {
        organization_id: orgId,
        title: 'Company Policies',
        category: 'HR',
        file_name: 'company-policies.pdf',
        file_type: 'PDF',
        file_path: '/documents/company-policies.pdf',
        status: 'indexed',
      },
    }),
    prisma.documents.create({
      data: {
        organization_id: orgId,
        title: 'API Documentation',
        category: 'Technical',
        file_name: 'api-docs.md',
        file_type: 'MD',
        file_path: '/documents/api-docs.md',
        status: 'indexed',
      },
    }),
    prisma.documents.create({
      data: {
        organization_id: orgId,
        title: 'Product Roadmap',
        category: 'Product',
        file_name: 'roadmap.docx',
        file_type: 'DOCX',
        file_path: '/documents/roadmap.docx',
        status: 'processing',
      },
    }),
  ]);
  console.log(`Created ${documents.length} documents`);

  console.log('\n✅ Database seeded successfully!');
  console.log('\n📋 Summary:');
  console.log(`   Organization: ${org.name}`);
  console.log(`   User: ${profile.username} (login with this email)`);
  console.log(`   Business Scopes: ${scopes.length}`);
  console.log(`   Agents: ${agents.length}`);
  console.log(`   Workflows: ${workflows.length}`);
  console.log(`   Tasks: ${tasks.length}`);
  console.log(`   MCP Servers: ${mcpServers.length}`);
  console.log(`   Documents: ${documents.length}`);
}

main()
  .catch((e) => {
    console.error('❌ Seed failed:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
