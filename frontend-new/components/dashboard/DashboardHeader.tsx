export const DashboardHeader = () => {
  return (
    <header className="bg-background-card px-4 py-5 shadow-sm sm:px-6 lg:px-8 lg:py-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary sm:text-2xl">
            Аналитика канала
          </h1>
          <p className="text-text-secondary mt-1">
            Метрики и факты из подключённого источника данных.
          </p>
        </div>
      </div>
    </header>
  )
}
