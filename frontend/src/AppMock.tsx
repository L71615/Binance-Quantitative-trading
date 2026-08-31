import { useState } from 'react'
import { Layout, type PageId } from './mock/layout'
import { Dashboard } from './mock/pages/Dashboard'
import { Charts } from './mock/pages/Charts'
import { Grids } from './mock/pages/Grids'
import { Orders } from './mock/pages/Orders'
import { Logs } from './mock/pages/Logs'
import { Settings } from './mock/pages/Settings'

function AppMock() {
  const [page, setPage] = useState<PageId>('dashboard')

  return (
    <Layout
      page={page}
      onNav={setPage}
      status={{ label: 'mock · 2 running', tone: 'ok' }}
    >
      {page === 'dashboard' && <Dashboard />}
      {page === 'charts' && <Charts />}
      {page === 'grids' && <Grids />}
      {page === 'orders' && <Orders />}
      {page === 'logs' && <Logs />}
      {page === 'settings' && <Settings />}
    </Layout>
  )
}

export default AppMock