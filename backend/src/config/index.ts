import { config as dotenvConfig } from 'dotenv';
import { z } from 'zod';

// Load .env file
dotenvConfig();

const envSchema = z.object({
  // Server
  PORT: z.string().default('3000').transform(Number),
  HOST: z.string().default('0.0.0.0'),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),

  // Database
  DATABASE_URL: z.string().min(1, 'DATABASE_URL is required'),

  // Redis Configuration
  REDIS_HOST: z.string().default('localhost'),
  REDIS_PORT: z.string().default('6379').transform(Number),
  REDIS_PASSWORD: z.string().optional(),
  REDIS_DB: z.string().default('0').transform(Number),

  // Authentication (Cognito)
  COGNITO_USER_POOL_ID: z.string().min(1, 'COGNITO_USER_POOL_ID is required'),
  COGNITO_CLIENT_ID: z.string().min(1, 'COGNITO_CLIENT_ID is required'),
  COGNITO_REGION: z.string().default('us-east-1'),
  COGNITO_DOMAIN: z.string().optional(),

  // Existing user binding — the Cognito sub that maps to the admin profile
  COGNITO_ADMIN_SUB: z.string().optional(),

  // AWS
  AWS_REGION: z.string().default('us-east-1'),
  AWS_ACCESS_KEY_ID: z.string().optional(),
  AWS_SECRET_ACCESS_KEY: z.string().optional(),

  // Cognito-specific credentials (if the user pool is in a different AWS account)
  COGNITO_AWS_ACCESS_KEY_ID: z.string().optional(),
  COGNITO_AWS_SECRET_ACCESS_KEY: z.string().optional(),

  // S3
  S3_BUCKET_NAME: z.string().default('super-agent-files'),
  S3_PRESIGNED_URL_EXPIRES: z.string().default('3600').transform(Number),

  // Logging
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),

  // CORS
  // Supports '*' for all origins (development) or comma-separated list of allowed origins (production)
  // Example: 'https://app.example.com,https://admin.example.com'
  CORS_ORIGIN: z.string().default('*'),

  // Claude Agent SDK
  ANTHROPIC_API_KEY: z.string().optional(),
  CLAUDE_CODE_USE_BEDROCK: z.string().optional().default('false'),
  CLAUDE_MODEL: z.string().optional().default('claude-sonnet-4-5-20250929'),
  AGENT_WORKSPACE_BASE_DIR: z.string().optional().default('/tmp/super-agent-workspaces'),
  CLAUDE_CODE_EXECUTABLE: z.string().optional(),
  CLAUDE_SESSION_TIMEOUT_MS: z.string().optional().default('1800000').transform(Number), // 30 min
  CLAUDE_RESPONSE_TIMEOUT_MS: z.string().optional().default('1200000').transform(Number), // 20 min
  CLAUDE_MAX_CONCURRENT_SESSIONS: z.string().optional().default('10').transform(Number),

  // Langfuse Observability
  LANGFUSE_SECRET_KEY: z.string().optional(),
  LANGFUSE_PUBLIC_KEY: z.string().optional(),
  LANGFUSE_BASE_URL: z.string().optional(),
});

function loadConfig(): z.infer<typeof envSchema> {
  const result = envSchema.safeParse(process.env);

  if (!result.success) {
    console.error('❌ Invalid environment variables:');
    console.error(result.error.format());
    throw new Error('Invalid environment configuration');
  }

  return result.data;
}

const env = loadConfig();

export const config = {
  port: env.PORT,
  host: env.HOST,
  nodeEnv: env.NODE_ENV,
  isDevelopment: env.NODE_ENV === 'development',
  isProduction: env.NODE_ENV === 'production',
  isTest: env.NODE_ENV === 'test',

  database: {
    url: env.DATABASE_URL,
  },

  redis: {
    host: env.REDIS_HOST,
    port: env.REDIS_PORT,
    password: env.REDIS_PASSWORD,
    db: env.REDIS_DB,
  },

  cognito: {
    userPoolId: env.COGNITO_USER_POOL_ID,
    clientId: env.COGNITO_CLIENT_ID,
    region: env.COGNITO_REGION,
    domain: env.COGNITO_DOMAIN,
    adminSub: env.COGNITO_ADMIN_SUB,
  },

  aws: {
    region: env.AWS_REGION,
    accessKeyId: env.AWS_ACCESS_KEY_ID,
    secretAccessKey: env.AWS_SECRET_ACCESS_KEY,
  },

  cognitoCredentials: {
    // Falls back to general AWS credentials if not separately configured
    accessKeyId: env.COGNITO_AWS_ACCESS_KEY_ID ?? env.AWS_ACCESS_KEY_ID,
    secretAccessKey: env.COGNITO_AWS_SECRET_ACCESS_KEY ?? env.AWS_SECRET_ACCESS_KEY,
  },

  s3: {
    bucketName: env.S3_BUCKET_NAME,
    presignedUrlExpires: env.S3_PRESIGNED_URL_EXPIRES,
  },

  claude: {
    anthropicApiKey: env.ANTHROPIC_API_KEY,
    useBedrock: env.CLAUDE_CODE_USE_BEDROCK === 'true' || env.CLAUDE_CODE_USE_BEDROCK === '1',
    model: env.CLAUDE_MODEL,
    workspaceBaseDir: env.AGENT_WORKSPACE_BASE_DIR,
    executablePath: env.CLAUDE_CODE_EXECUTABLE,
    sessionTimeoutMs: env.CLAUDE_SESSION_TIMEOUT_MS,
    responseTimeoutMs: env.CLAUDE_RESPONSE_TIMEOUT_MS,
    maxConcurrentSessions: env.CLAUDE_MAX_CONCURRENT_SESSIONS,
  },

  langfuse: {
    secretKey: env.LANGFUSE_SECRET_KEY,
    publicKey: env.LANGFUSE_PUBLIC_KEY,
    baseUrl: env.LANGFUSE_BASE_URL,
    enabled: !!(env.LANGFUSE_SECRET_KEY && env.LANGFUSE_PUBLIC_KEY),
  },

  logLevel: env.LOG_LEVEL,
  corsOrigin: env.CORS_ORIGIN,
} as const;

export type Config = typeof config;
