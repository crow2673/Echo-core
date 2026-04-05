# Echo Income Knowledge Base

_Last updated: 2026-04-05 02:38_

This document is generated weekly by `income_researcher.py`.
Echo reads this file and reasons about which income paths to pursue.

---

## Known Income Mechanisms

These are verified or researched paths Echo can pursue:

### ✅ Golem Network — Compute Provider
**What it is:** Sell GPU/CPU compute to the Golem marketplace. Passive once running.
**Realistic ceiling:** ~$20-80/month for a single RTX 3060 at current rates
**What it needs:** yagna running, competitive pricing, patience (new node penalty ~7-14 days)
**Echo's current status:** ACTIVE — node running, 0 tasks completed (new node penalty phase) | _checked 2026-04-05 02:38_
**Effort level:** low (passive)

### ✅ Dev.to Content — AI Writing
**What it is:** Publish technical articles. Build audience. Monetize via dev.to badges, sponsorships.
**Realistic ceiling:** $5-50/article in badges initially; sponsorship possible at 1k+ followers
**What it needs:** Consistent publishing, quality, niche authority
**Echo's current status:** ACTIVE — 4 articles published, 1 scheduled Tuesday 2026-03-17 | _checked 2026-04-05 02:38_
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

### Dev.to — AI tag
_4 relevant of 12 fetched_

- **[I built a 126K-line Android app with AI — here is the workflow that actually works](https://dev.to/stoyan_minchev/i-built-a-126k-line-android-app-with-ai-here-is-the-workflow-that-actually-works-2llj)**
  Most developers trying AI coding tools hit the same wall. They open a chat, type "build me a todo app," get something that looks right, and then spend 3 hours fixing the mess. They try again with a bi
- **[Attie.ai Revolution](https://dev.to/joaopakina/attieai-revolution-4d3m)**
  Introduction to Attie.ai   Attie.ai is a cutting-edge AI company that has been making waves in the tech industry with its groundbreaking approach to machine learning and data analysis. Founded by a te
- **[How to Add Persistent Memory to Any AI Agent (Step-by-Step)](https://dev.to/adam_cipher/how-to-add-persistent-memory-to-any-ai-agent-step-by-step-1lam)**
  Your agent works perfectly on day one. By day three, it's asking the same questions it already answered. By week two, it contradicts decisions it made last Tuesday.  The problem isn't your prompts. It
- **[Anthropic's $60B IPO Bet: What October Means for AI](https://dev.to/ji_ai/anthropics-60b-ipo-bet-what-october-means-for-ai-2o3d)**
  $1 billion to $19 billion in annualized revenue. Fourteen months. That is the growth curve Anthropic is now trying to price on the public market.  Bloomberg reported on March 27 that Anthropic — the c

### Dev.to — Productivity tag
_3 relevant of 12 fetched_

- **[7 Mac Apps That Make Remote Pair Programming Better in 2026](https://dev.to/godnick/7-mac-apps-that-make-remote-pair-programming-better-in-2026-2hpn)**
  Pair programming is one of those practices that sounds great in theory but falls apart fast if your tools aren't up to the task. Laggy screen shares, audio that cuts out mid-thought, no way to both ty
- **[Notion Has a Free API — Here's How to Build a CMS, Database, or Automation on Top of It](https://dev.to/0012303/notion-has-a-free-api-heres-how-to-build-a-cms-database-or-automation-on-top-of-it-1a9n)**
  A content team I know was using a custom WordPress setup for their editorial calendar. 3 plugins, $50/month hosting, constant maintenance. They moved everything to a Notion database with the API power
- **[Linear Has a Free API — Here's How to Build Custom Project Management Workflows](https://dev.to/0012303/linear-has-a-free-api-heres-how-to-build-custom-project-management-workflows-5g6m)**
  An engineering lead told me his team spent 2 hours every Monday manually creating sprint issues from a spreadsheet. He wrote a 50-line script with Linear's API — now it takes 0 seconds and happens aut

### Reddit — r/selfhosted
_6 relevant of 25 fetched_

- **[[Request] Any self hosted service to handle comics (with automation)?](https://www.reddit.com/r/selfhosted/comments/1s6eiub/request_any_self_hosted_service_to_handle_comics/)**
- **[macOS desktop app to manage GitHub Actions self-hosted runners — open source](https://www.reddit.com/r/selfhosted/comments/1s6ose7/macos_desktop_app_to_manage_github_actions/)**
- **[Instructions and script for migrating from Umami cloud to self-hosted](https://www.reddit.com/r/selfhosted/comments/1s6i5oz/instructions_and_script_for_migrating_from_umami/)**
- **[SparkyFitness - A Self-Hosted MyFitnessPal alternative now supports Starva & updated Mobile app](https://www.reddit.com/r/selfhosted/comments/1s5mfux/sparkyfitness_a_selfhosted_myfitnesspal/)**
- **[What’s your plan for your self-hosted data if you die? I guess I didn't have one](https://www.reddit.com/r/selfhosted/comments/1s5ko9d/whats_your_plan_for_your_selfhosted_data_if_you/)**
- **[Free 750-page guide to self-hosting production apps - NO AI SLOP](https://www.reddit.com/r/selfhosted/comments/1s51bg1/free_750page_guide_to_selfhosting_production_apps/)**

### Reddit — r/LocalLLaMA
_2 relevant of 25 fetched_

- **[Friendly reminder inference is WAY faster on Linux vs windows](https://www.reddit.com/r/LocalLLaMA/comments/1s6hb1h/friendly_reminder_inference_is_way_faster_on/)**
- **[2x RTX Pro 6000 vs 2x A100 80GB dense model inference](https://www.reddit.com/r/LocalLLaMA/comments/1s6jyij/2x_rtx_pro_6000_vs_2x_a100_80gb_dense_model/)**

### Reddit — r/SideProject
_5 relevant of 25 fetched_

- **[I built a photo editor with local AI (no cloud) — segmentation + infill](https://www.reddit.com/r/SideProject/comments/1s64a01/i_built_a_photo_editor_with_local_ai_no_cloud/)**
- **[I quit my 9 to 5 to freelance and the first three months were the most humbling experience of my entire professional life](https://www.reddit.com/r/SideProject/comments/1s64vyi/i_quit_my_9_to_5_to_freelance_and_the_first_three/)**
- **[I built an open-source tool that lets you work with AI agents like co-workers](https://www.reddit.com/r/SideProject/comments/1s6nquf/i_built_an_opensource_tool_that_lets_you_work/)**
- **[My idea got killed 9 times by my own AI tool. Each time it came back stronger.](https://www.reddit.com/r/SideProject/comments/1s6oay9/my_idea_got_killed_9_times_by_my_own_ai_tool_each/)**
- **[I finally got tired of Instagram's BS and built my own unfollow tracker (free + open source)](https://www.reddit.com/r/SideProject/comments/1s6nmrj/i_finally_got_tired_of_instagrams_bs_and_built_my/)**

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

_Generated by Echo income_researcher.py | 2026-03-29 04:00_
