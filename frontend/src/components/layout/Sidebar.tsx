import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Search,
  BarChart3,
  FileText,
  Shield,
  Settings,
} from 'lucide-react'

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/screening', label: 'Screening', icon: Search },
  { path: '/evaluation', label: 'Evaluation', icon: BarChart3 },
  { path: '/extraction', label: 'Extraction', icon: FileText },
  { path: '/quality', label: 'Quality', icon: Shield },
  { path: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  const location = useLocation()

  return (
    <aside className="glass-strong w-64 min-h-screen p-4 flex flex-col border-r border-white/10">
      <div className="mb-8 px-3">
        <h1 className="text-xl font-bold text-white">MetaScreener</h1>
        <p className="text-xs text-white/50 mt-1">AI-Assisted Systematic Review</p>
      </div>
      <nav className="flex-1 space-y-1">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          const Icon = item.icon
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? 'bg-purple-500/20 text-white border border-purple-500/30'
                  : 'text-white/70 hover:text-white hover:bg-white/5'
              }`}
            >
              <Icon size={18} />
              {item.label}
            </Link>
          )
        })}
      </nav>
      <div className="mt-auto pt-4 border-t border-white/10 px-3">
        <p className="text-xs text-white/30">v2.0.0</p>
      </div>
    </aside>
  )
}
