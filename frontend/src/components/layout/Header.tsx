interface HeaderProps {
  title: string
  description?: string
}

export function Header({ title, description }: HeaderProps) {
  return (
    <header className="mb-6">
      <h2 className="text-2xl font-bold text-white">{title}</h2>
      {description && (
        <p className="text-white/60 mt-1">{description}</p>
      )}
    </header>
  )
}
