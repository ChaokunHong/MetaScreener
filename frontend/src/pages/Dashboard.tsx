import { Link } from 'react-router-dom'
import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'
import { GlassButton } from '../components/glass/GlassButton'
import {
  Search,
  BarChart3,
  FileText,
  Shield,
  ArrowRight,
  Upload,
} from 'lucide-react'

const workflowSteps = [
  {
    icon: Upload,
    title: 'Upload Records',
    description: 'Import your search results from RIS, BibTeX, CSV, or Excel files',
    link: '/screening',
    color: 'text-blue-400',
  },
  {
    icon: Search,
    title: 'Screen Studies',
    description: 'AI-powered title/abstract screening with the Hierarchical Consensus Network',
    link: '/screening',
    color: 'text-purple-400',
  },
  {
    icon: BarChart3,
    title: 'Evaluate Performance',
    description: 'Compute sensitivity, specificity, and calibration metrics against gold standards',
    link: '/evaluation',
    color: 'text-green-400',
  },
  {
    icon: FileText,
    title: 'Extract Data',
    description: 'Multi-LLM parallel extraction with consensus validation',
    link: '/extraction',
    color: 'text-cyan-400',
  },
  {
    icon: Shield,
    title: 'Assess Quality',
    description: 'Risk of bias assessment using RoB 2, ROBINS-I, or QUADAS-2',
    link: '/quality',
    color: 'text-amber-400',
  },
]

export function Dashboard() {
  return (
    <>
      <Header
        title="Dashboard"
        description="AI-Assisted Systematic Review Tool"
      />

      <div className="space-y-6">
        {/* Quick Start */}
        <GlassCard variant="strong">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-white">Quick Start</h3>
              <p className="text-white/60 text-sm mt-1">
                Begin a new systematic review by uploading your search results
              </p>
            </div>
            <Link to="/screening">
              <GlassButton>
                <span className="flex items-center gap-2">
                  Start Screening <ArrowRight size={16} />
                </span>
              </GlassButton>
            </Link>
          </div>
        </GlassCard>

        {/* Workflow Steps */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workflowSteps.map((step) => {
            const Icon = step.icon
            return (
              <Link key={step.title} to={step.link}>
                <GlassCard className="h-full hover:bg-white/15 transition-colors cursor-pointer">
                  <Icon size={24} className={step.color} />
                  <h4 className="text-white font-medium mt-3">{step.title}</h4>
                  <p className="text-white/50 text-sm mt-1">{step.description}</p>
                </GlassCard>
              </Link>
            )
          })}
        </div>

        {/* System Info */}
        <GlassCard variant="subtle">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/50 text-sm">MetaScreener v2.0</p>
              <p className="text-white/30 text-xs mt-0.5">
                4 open-source LLMs · Hierarchical Consensus Network · TRIPOD-LLM compliant
              </p>
            </div>
            <Link to="/settings">
              <GlassButton variant="ghost" size="sm">
                Configure API Keys
              </GlassButton>
            </Link>
          </div>
        </GlassCard>
      </div>
    </>
  )
}
