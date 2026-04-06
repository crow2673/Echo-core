# Echo Income Knowledge Base

_Last updated: 2026-04-06 02:42_

This document is generated weekly by `income_researcher.py`.
Echo reads this file and reasons about which income paths to pursue.

---

## Known Income Mechanisms

These are verified or researched paths Echo can pursue:

### ✅ Golem Network — Compute Provider
**What it is:** Sell GPU/CPU compute to the Golem marketplace. Passive once running.
**Realistic ceiling:** ~$20-80/month for a single RTX 3060 at current rates
**What it needs:** yagna running, competitive pricing, patience (new node penalty ~7-14 days)
**Echo's current status:** ACTIVE — node running, 0 tasks completed (new node penalty phase) | _checked 2026-04-06 02:42_
**Effort level:** low (passive)

### ✅ Dev.to Content — AI Writing
**What it is:** Publish technical articles. Build audience. Monetize via dev.to badges, sponsorships.
**Realistic ceiling:** $5-50/article in badges initially; sponsorship possible at 1k+ followers
**What it needs:** Consistent publishing, quality, niche authority
**Echo's current status:** ACTIVE — 4 articles published, 1 scheduled Tuesday 2026-03-17 | _checked 2026-04-06 02:42_
**Effort level:** medium (weekly writing)

### 🔲 Local LLM API Reselling
**What it is:** Expose Echo's Ollama instance as a pay-per-use API endpoint. Charge for inference.
**Realistic ceiling:** $50-300/month depending on model quality and pricing
**What it needs:** Public endpoint (reverse proxy), auth layer, billing (Stripe), terms of service
**Echo's current status:** NOT STARTED — infrastructure exists, needs auth + billing layer
**Effort level:** high (build once, then passive)

### 🔲 Freelance Task Execution
**What it is:** Accept paid tasks (research, writing, summarization, data processing) via a storefront.
**Realistic ceiling:** $10-50/task; scalable if automated
**What it needs:** Storefront (Gumroad, own site), trust signals, intake → auto_act pipeline
**Echo's current status:** NOT STARTED — auto_act pipeline exists but no intake storefront
**Effort level:** medium (storefront setup + task routing)

### 🔲 Echo Shell / Setup Wizard Product
**What it is:** Package Echo as a deployable product. Charge builders to spin up their own Echo.
**Realistic ceiling:** $50-500/license; recurring if SaaS model
**What it needs:** Stable core, installer, documentation, pricing page
**Echo's current status:** LONG TERM — core must be proven first
**Effort level:** very high (product build)

### 🔲 GPU Rental — Vast.ai / RunPod
**What it is:** Rent RTX 3060 to researchers and developers on GPU rental marketplaces.
**Realistic ceiling:** $1.50-3.00/hr * utilization; $30-90/month realistic
**What it needs:** Account on Vast.ai or RunPod, machine registered, uptime
**Echo's current status:** NOT STARTED — hardware available, account not created
**Effort level:** low (passive once registered)

---

## Discovered This Week

Items scraped from the web that may signal new income opportunities:

### Hacker News — Ask HN / Show HN
_2 relevant of 30 fetched_

- **[Introduction to Computer Music (2009) [pdf]](https://composerprogrammer.com/introductiontocomputermusic.pdf)**
  Comments
- **[Show HN: I made open source, zero power PCB hackathon badges](https://github.com/KaiPereira/Overglade-Badges)**
  Comments

### Dev.to — AI tag
_6 relevant of 12 fetched_

- **[Anthropic's 3-Agent Harness Is Just a Sprint - And That's the Point](https://dev.to/itskondrat/anthropics-3-agent-harness-is-just-a-sprint-and-thats-the-point-3k8o)**
  I've been mapping PM workflows to agent architectures for months. Then Anthropic went and published the diagram.  Their multi-agent harness for autonomous software engineering has three roles:    Plan
- **[I Built a Voice AI with Sub-500ms Latency. Here's the Echo Cancellation Problem Nobody Talks About](https://dev.to/remi_etien/i-built-a-voice-ai-with-sub-500ms-latency-heres-the-echo-cancellation-problem-nobody-talks-about-14la)**
  When I started building GoNoGo.team — a platform where AI agents interview founders by voice to validate startup ideas — I thought the hard part would be the AI reasoning. The multi-agent orchestratio
- **[How I Found $1,240/Month in Wasted LLM API Costs (And Built a Tool to Find Yours)](https://dev.to/buildwithabid/how-i-found-1240month-in-wasted-llm-api-costs-and-built-a-tool-to-find-yours-3041)**
  I was spending about $2,000/month on OpenAI and Anthropic APIs across a few projects.  I knew some of it was wasteful. I just couldn't prove it. The provider dashboards show you one number — your tota
- **[3 Articles to 30: The Final Push](https://dev.to/huineng6/3-articles-to-30-the-final-push-368c)**
  27 articles down. 3 to go. Here's the final push to 30.           The Numbers So Far      Metric Value     Time invested ~12 hours   Articles published 27   Revenue $0              The
- **[I let Claude Code run marketing workflows for brands](https://dev.to/tgdn/i-let-claude-code-run-marketing-workflows-for-brands-3n0e)**
  I got tired of context-switching between Figma, Buffer, Instagram, analytics, random downloads folders, and whatever tab I had open for reference images.  The problem was not "marketing is hard" in so
- **[Introduction to Bioinformatics: A Beginner Guide](https://dev.to/laura_ashaley_be356544300/introduction-to-bioinformatics-a-beginner-guide-11og)**
  Bioinformatics is a field that combines biology and computer science to analyze biological data such as DNA, RNA, and proteins.  In simple terms, it is the use of computational tools to understand bio

### Dev.to — Productivity tag
_3 relevant of 12 fetched_

- **[Anthropic's 3-Agent Harness Is Just a Sprint - And That's the Point](https://dev.to/itskondrat/anthropics-3-agent-harness-is-just-a-sprint-and-thats-the-point-3k8o)**
  I've been mapping PM workflows to agent architectures for months. Then Anthropic went and published the diagram.  Their multi-agent harness for autonomous software engineering has three roles:    Plan
- **[How I Built a Patch Automation Platform with Python and BigFix](https://dev.to/subhrajitpyne108/how-i-built-a-patch-automation-platform-with-python-and-bigfix-4h6)**
  The problem nobody talks about If you work in enterprise IT, you already know this pain. Every month, patch Tuesday arrives. Hundreds — sometimes thousands — of servers need patches deployed, verified
- **[I Let AI Coding Agents Build My Side Projects for a Month — Here's My Honest Take](https://dev.to/samhartley_dev/i-let-ai-coding-agents-build-my-side-projects-for-a-month-heres-my-honest-take-52l3)**
  Last month I ran an experiment: instead of writing code myself, I delegated as much as possible to AI coding agents. Not just autocomplete — full autonomous agents that read files, run commands, and s

### Reddit — r/selfhosted
_5 relevant of 25 fetched_

- **[I dockerized my entire self-hosted stack and packaged each piece as standalone compose files - here's what I learned](https://www.reddit.com/r/selfhosted/comments/1scb596/i_dockerized_my_entire_selfhosted_stack_and/)**
- **[Looking for feedback: self-hosted alternative to internal tools (tasks, workflow, reports)](https://www.reddit.com/r/selfhosted/comments/1scyslp/looking_for_feedback_selfhosted_alternative_to/)**
- **[anomalisa - self-hosted anomaly detection that emails you when your events look weird (zero config, Deno KV only)](https://www.reddit.com/r/selfhosted/comments/1scqc3m/anomalisa_selfhosted_anomaly_detection_that/)**
- **[Not a lot of selfhosted clouds that work with network shares](https://www.reddit.com/r/selfhosted/comments/1scyjec/not_a_lot_of_selfhosted_clouds_that_work_with/)**
- **[Running Android OS as selfhosted VM (especially Proxmox) is possible?](https://www.reddit.com/r/selfhosted/comments/1sckhuv/running_android_os_as_selfhosted_vm_especially/)**

### Reddit — r/LocalLLaMA
_2 relevant of 25 fetched_

- **[Gemma 4 26b is the perfect all around local model and I'm surprised how well it does.](https://www.reddit.com/r/LocalLLaMA/comments/1scucfg/gemma_4_26b_is_the_perfect_all_around_local_model/)**
- **[We absolutely need Qwen3.6-397B-A17B to be open source](https://www.reddit.com/r/LocalLLaMA/comments/1sccpbj/we_absolutely_need_qwen36397ba17b_to_be_open/)**

### Reddit — r/SideProject
_1 relevant of 25 fetched_

- **[📱 Built a kids' treasure hunt app, got 240 downloads and €0 revenue. Is this a real product?](https://www.reddit.com/r/SideProject/comments/1scn1ac/built_a_kids_treasure_hunt_app_got_240_downloads/)**

### Golem Network Blog
_12 relevant of 15 fetched_

- **[Golem Ecosystem Fund: One Year In - Highlights, Allocations, and What’s Next](https://blog.golem.network/golem-ecosystem-fund-one-year-in-highlights-allocations-and-whats-next/)**
  GEF has supported Golem, Ethereum, and Web3 for over a year! We've learned and are evolving the Fund. New goals, tracks, and focus areas are coming soon. Get ready!
- **[Introducing golem-js 3.5 release](https://blog.golem.network/introducing-golem-js-3-5-release/)**
  Dive into the recent features and updates from the flag SDK component designed for JavaScript and TypeScript developers!
- **[Golem Network ETH Solo Staking Tests: Summary](https://blog.golem.network/eth-staking-tests-summary/)**
  As stated in our June blog post, Golem Network has decided to stake its ETH to support the future growth and development of the project. With the initial milestones successfully achieved, we want to s
- **[Golem-Workers MVP Is Live: Call for Beta Testers](https://blog.golem.network/golem-workers-mvp-is-live/)**
  We are happy to announce that the MVP of Golem-Workers is now ready! You can access the repository here:&#x1F4C1;<a href="https://github.com/golemfactory/golem-workers?ref=blog.golem.network" rel="nor
- **[Yagna v.0.16.0: Introducing Deposits](https://blog.golem.network/yagna-v-0-16-0/)**
  We have just released Yagna v0.16.0! Here is a quick summary of the changes from v0.15:A New Payment Method: DepositsNew roles in the Ecosystem: Deposits differentiate between End-users who use and pa
- **[Golem Network AI/GPU Roadmap Update](https://blog.golem.network/ai-gpu-roadmap-update/)**
  We are excited to announce an updated version that reflects a tactical shift designed to foster Golem Network development and maximize benefits for the AI market.
- **[AI/GPU Roadmap Spotlight: Golem-Workers](https://blog.golem.network/golem-workers/)**
  Golem Workers is an API providing direct and high-level access to GPU and CPU resources on the Golem Network. Unlike services focused solely on specific tasks such as AI model deployment and inference
- **[AI/GPU Roadmap Spotlight: Modelserve](https://blog.golem.network/modelserve/)**
  Modelserve is a service designed to run AI model inferences at scale, affordably.
- **[Introducing golem-js 3.0](https://blog.golem.network/golem-js-3-0/)**
  We’re excited to announce the official release of golem-js 3.0! The final stable version is now available with major updates, new features, and crucial improvements.
- **[Golem ETH Staking Tests](https://blog.golem.network/golem-eth-staking-tests/)**
  Golem Network has moved a non-trivial but small portion of its reserves to initiate ETH staking tests to support our project's future growth and development.

---

## Echo's Standing Questions

When Echo reads this file, she should consider:

1. Which income mechanism is closest to being ready to activate?
2. What single action this week would move the highest-potential path forward?
3. Are any discovered items above describing something new I should add to the known mechanisms list?
4. What is my honest estimate of income earned so far vs. effort invested?
5. Which path has the best effort-to-income ratio given my current capabilities?

---

_Generated by Echo income_researcher.py | 2026-04-05 04:00_
