import { useState } from 'react'
import { Header } from '../components/layout/Header'
import { Stepper } from '../components/screening/Stepper'
import { FileUpload } from '../components/screening/FileUpload'
import { CriteriaSetup } from '../components/screening/CriteriaSetup'
import { ScreeningRunner } from '../components/screening/ScreeningRunner'
import { ScreeningResults } from '../components/screening/ScreeningResults'

const STEPS = ['Upload', 'Criteria', 'Screen', 'Results']

export function Screening() {
  const [step, setStep] = useState(0)

  return (
    <>
      <Header
        title="Screening"
        description="Title/abstract and full-text screening"
      />

      <Stepper steps={STEPS} currentStep={step} />

      {step === 0 && <FileUpload onComplete={() => setStep(1)} />}
      {step === 1 && <CriteriaSetup onComplete={() => setStep(2)} />}
      {step === 2 && <ScreeningRunner onComplete={() => setStep(3)} />}
      {step === 3 && <ScreeningResults />}
    </>
  )
}
