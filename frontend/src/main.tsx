import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { LandingHero } from './components/landing/LandingHero.tsx'

// Lightweight path check instead of pulling in a router dependency for one
// extra page: /landing (or /) shows the Pathfinder hero, anything else
// shows the existing pipeline dashboard app unchanged.
const isLandingPath = window.location.pathname === '/landing'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isLandingPath ? <LandingHero /> : <App />}
  </StrictMode>,
)
