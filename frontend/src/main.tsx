import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { createQueryClient } from './api/query-client'
import App from './App'
import './index.css'
import './app.css'
import { installSpotlight } from './spotlight'
import { applyTheme, getTheme } from './theme'

const queryClient = createQueryClient()

installSpotlight()
applyTheme(getTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
