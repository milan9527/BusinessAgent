import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { TranslationProvider } from '@/i18n'
import { AppShell, ErrorBoundary, ToastProvider, ProtectedRoute, SkillMarketplaceBrowser, AIScopeGenerator, SkillWorkshop } from '@/components'
import { Dashboard, Chat, WorkflowEditor, Agents, Tools, AgentConfigurator, TaskAuditLog, TaskExecutionCenter, MCPConfigurator, KnowledgeManager, InfrastructureConfigurator, Login, CreateBusinessScope, Marketplace, AppRunner } from '@/pages'
import { Settings } from '@/pages/Settings'
import { AuthCallback } from '@/pages/AuthCallback'
import { AuthProvider } from '@/services/AuthContext'

function AppContent() {
  return (
    <Routes>
      {/* Full-page routes without AppShell */}
      <Route path="/create-business-scope" element={<CreateBusinessScope />} />
      <Route path="/create-business-scope/ai" element={<AIScopeGenerator />} />
      <Route path="/agents/config/:agentId/workshop" element={<SkillWorkshop />} />
      
      {/* Routes with AppShell */}
      <Route path="/*" element={
        <AppShell>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/workflow" element={<WorkflowEditor />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/agents/config/:agentId" element={<AgentConfigurator />} />
            <Route path="/tools" element={<Tools />} />
            <Route path="/tasks" element={<TaskAuditLog />} />
            <Route path="/task-monitoring" element={<TaskExecutionCenter />} />
            {/* Config routes - placeholder for admin menu navigation */}
            <Route path="/config/mcp" element={<MCPConfigurator />} />
            <Route path="/config/skills" element={<SkillMarketplaceBrowser />} />
            <Route path="/config/rest-api" element={<div className="p-6 text-white">REST API Configuration</div>} />
            <Route path="/config/knowledge" element={<KnowledgeManager />} />
            <Route path="/config/framework" element={<InfrastructureConfigurator />} />
            <Route path="/apps" element={<Marketplace />} />
            <Route path="/apps/:id" element={<AppRunner />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </AppShell>
      } />
    </Routes>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <TranslationProvider>
          <ToastProvider>
            <AuthProvider>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/auth/callback" element={<AuthCallback />} />
                <Route path="/*" element={
                  <ProtectedRoute>
                    <AppContent />
                  </ProtectedRoute>
                } />
              </Routes>
            </AuthProvider>
          </ToastProvider>
        </TranslationProvider>
      </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
