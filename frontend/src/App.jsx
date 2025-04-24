import React from 'react'
import { Box, ChakraProvider, extendTheme } from '@chakra-ui/react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import HomePage from './pages/HomePage'
import AboutPage from './pages/AboutPage'
import ChatPage from './pages/ChatPage'
import FileUploadPage from './pages/knowledge/FileUploadPage'
import ChatHistoryPage from './pages/ChatHistoryPage'
import ConnectorsPage from './pages/ConnectorsPage'
import LLMProviderConnectorPage from './pages/connectors/LLMProviderConnectorPage'
import ChatInterface from './components/ChatInterface'
import GitHubConnectors from './pages/GitHubConnectors'
import RepositoryPage from './pages/RepositoryPage'
import TestPage from './pages/TestPage'
import ErrorBoundary from './components/ErrorBoundary'

// Create theme
const theme = extendTheme({
  styles: {
    global: {
      body: {
        bg: 'white',
      }
    }
  }
})

function App() {
  console.log('App is rendering');
  
  return (
    <ErrorBoundary>
      <ChakraProvider theme={theme}>
        <Router>
          <Box minH="100vh">
            <Routes>
              <Route path="/test" element={<TestPage />} />
              <Route path="/" element={<HomePage />} />
              <Route path="/chat" element={
                <MainLayout>
                  <ChatPage />
                </MainLayout>
              } />
              <Route path="/chat/:conversationId" element={
                <MainLayout>
                  <ChatPage />
                </MainLayout>
              } />
             {/* <Route path="/upload" element={
                <MainLayout>
                  <FileUploadPage />
                </MainLayout>
              } /> */}
              <Route path="/history" element={
                <MainLayout>
                  <ChatHistoryPage />
                </MainLayout>
              } />
              <Route path="/history/:conversationId" element={
                <MainLayout>
                  <ChatHistoryPage />
                </MainLayout>
              } />
              <Route path="/connectors" element={
                <MainLayout>
                  <ConnectorsPage />
                </MainLayout>
              } />
              <Route path="/connectors/llm" element={
                <MainLayout>
                  <LLMProviderConnectorPage />
                </MainLayout>
              } />
              <Route path="/connectors/github" element={
                <MainLayout>
                  <GitHubConnectors />
                </MainLayout>
              } />
              <Route path="/repository" element={
                <MainLayout>
                  <RepositoryPage />
                </MainLayout>
              } />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </Box>
        </Router>
      </ChakraProvider>
    </ErrorBoundary>
  )
}

export default App