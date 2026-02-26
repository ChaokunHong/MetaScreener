import { Check } from 'lucide-react'

interface StepperProps {
  steps: string[]
  currentStep: number
}

export function Stepper({ steps, currentStep }: StepperProps) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {steps.map((label, i) => {
        const isCompleted = i < currentStep
        const isCurrent = i === currentStep
        return (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-all ${
                isCompleted
                  ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                  : isCurrent
                    ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                    : 'bg-white/5 text-white/30 border border-white/10'
              }`}
            >
              {isCompleted ? <Check size={14} /> : i + 1}
            </div>
            <span
              className={`text-sm ${
                isCurrent ? 'text-white' : isCompleted ? 'text-white/70' : 'text-white/30'
              }`}
            >
              {label}
            </span>
            {i < steps.length - 1 && (
              <div className={`w-8 h-px ${isCompleted ? 'bg-green-500/30' : 'bg-white/10'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}
