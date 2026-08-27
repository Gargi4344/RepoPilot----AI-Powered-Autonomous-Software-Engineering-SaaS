import { AgentNetwork } from '../components/sections/AgentNetwork'
import { FinalCTA, Footer } from '../components/sections/FinalCTA'
import { LiveCommit } from '../components/sections/LiveCommit'
import { LiveTerminal } from '../components/sections/LiveTerminal'
import { PullRequestPreview } from '../components/sections/PullRequestPreview'
import { RepositoryRadar } from '../components/sections/RepositoryRadar'
import { Safety } from '../components/sections/Safety'
import { Workflow } from '../components/sections/Workflow'
import { Hero } from '../components/hero/Hero'
import { Navbar } from '../components/navigation/Navbar'

export function LandingPage() {
  return (
    <div className="landing-theme min-h-screen bg-background font-sans text-foreground">
      <Navbar />
      <main>
        <Hero />
        <LiveCommit />
        <AgentNetwork />
        <RepositoryRadar />
        <Workflow />
        <LiveTerminal />
        <PullRequestPreview />
        <Safety />
        <FinalCTA />
      </main>
      <Footer />
    </div>
  )
}
