import './styles/aurora.css'
import './styles/glass.css'

function App() {
  return (
    <div className="min-h-screen text-white">
      <div className="aurora-background">
        <div className="aurora-orb" />
        <div className="aurora-orb" />
        <div className="aurora-orb" />
        <div className="aurora-orb" />
        <div className="aurora-orb" />
        <div className="aurora-orb" />
      </div>
      <div className="relative z-10 flex items-center justify-center min-h-screen">
        <div className="glass p-8 text-center">
          <h1 className="text-3xl font-bold mb-2">MetaScreener</h1>
          <p className="text-white/70">AI-Assisted Systematic Review</p>
        </div>
      </div>
    </div>
  )
}

export default App
