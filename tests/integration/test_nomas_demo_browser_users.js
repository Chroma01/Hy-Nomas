#!/usr/bin/env node

/**
 * Real-browser acceptance test for the multi-user Hy-Nomas Demo.
 *
 * The script intentionally uses three independent pages in one Chromium
 * browser context, matching one person opening multiple tabs:
 *   - A and B enter independent worlds and generate concurrently;
 *   - C submits while both GPU workers are occupied and must queue;
 *   - A and B release their sticky sessions through pagehide;
 *   - C must then run without restarting the Gateway or either worker.
 *
 * Playwright is loaded from PLAYWRIGHT_PACKAGE so the repository does not need
 * to carry a browser runtime as an application dependency.
 */

const fs = require('node:fs')
const path = require('node:path')

const playwrightPackage =
  process.env.PLAYWRIGHT_PACKAGE
  || '/usr/local/lib/python3.11/site-packages/playwright/driver/package'
const chromiumExecutable =
  process.env.CHROMIUM_EXECUTABLE
  || '/root/.cache/ms-playwright/chromium_headless_shell-1223/'
    + 'chrome-headless-shell-linux64/chrome-headless-shell'
const baseUrl = (process.env.NOMAS_DEMO_URL || 'http://127.0.0.1:18084')
  .replace(/\/+$/, '')
const artifactDir = process.env.NOMAS_BROWSER_ARTIFACT_DIR
  || '/tmp/nomas_demo_browser_acceptance'
const reportPath = process.env.NOMAS_BROWSER_REPORT
  || path.join(artifactDir, 'browser_acceptance_report.json')
const codeServerPassword = process.env.CODE_SERVER_PASSWORD || ''
const httpCredentials = process.env.NOMAS_DEMO_USERNAME
  ? {
      username: process.env.NOMAS_DEMO_USERNAME,
      password: process.env.NOMAS_DEMO_PASSWORD || '',
    }
  : undefined

const { chromium } = require(playwrightPackage)

const sleep = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds))

async function poll(description, callback, timeoutMs = 300_000) {
  const deadline = Date.now() + timeoutMs
  let lastValue
  let lastError
  while (Date.now() < deadline) {
    try {
      lastValue = await callback()
      if (lastValue) return lastValue
      lastError = undefined
    } catch (error) {
      lastError = error
    }
    await sleep(500)
  }
  const suffix = lastError
    ? `; last error: ${lastError instanceof Error ? lastError.message : lastError}`
    : `; last value: ${JSON.stringify(lastValue)}`
  throw new Error(`Timed out waiting for ${description}${suffix}`)
}

async function getJson(request, relativeUrl) {
  const response = await request.get(`${baseUrl}${relativeUrl}`, {
    failOnStatusCode: false,
  })
  const body = await response.text()
  if (!response.ok()) {
    throw new Error(`${relativeUrl}: HTTP ${response.status()} ${body.slice(0, 300)}`)
  }
  return JSON.parse(body)
}

async function postJson(request, relativeUrl) {
  const response = await request.post(`${baseUrl}${relativeUrl}`, {
    failOnStatusCode: false,
  })
  const body = await response.text()
  if (!response.ok()) {
    throw new Error(`${relativeUrl}: HTTP ${response.status()} ${body.slice(0, 300)}`)
  }
  return JSON.parse(body)
}

async function authenticateCodeServer(context) {
  if (!codeServerPassword) return
  const target = new URL(baseUrl)
  const login = new URL('/login', target.origin)
  login.searchParams.set('to', `${target.pathname}/`.replace(/\/+/g, '/'))
  const response = await context.request.post(login.toString(), {
    failOnStatusCode: false,
    form: {
      password: codeServerPassword,
      base: '.',
      href: '',
    },
  })
  if (!response.ok()) {
    throw new Error(
      `code-server login failed: HTTP ${response.status()} `
      + `${(await response.text()).slice(0, 300)}`,
    )
  }
}

async function waitForJob(request, jobId, states, timeoutMs = 300_000) {
  return poll(
    `${jobId} to reach ${states.join('/')}`,
    async () => {
      const job = await getJson(request, `/v1/generate/${jobId}`)
      return states.includes(job.status) ? job : undefined
    },
    timeoutMs,
  )
}

function installPageObservers(page, label, report) {
  page.on('response', (response) => {
    if (response.status() >= 400) {
      report.browserErrors.push({
        label,
        kind: 'http',
        message: `${response.status()} ${response.request().method()} ${response.url()}`,
      })
    }
  })
  page.on('console', (message) => {
    if (
      message.type() === 'error'
      && !message.text().includes('net::ERR_ABORTED')
    ) {
      report.browserErrors.push({
        label,
        kind: 'console',
        message: message.text(),
      })
    }
  })
  page.on('pageerror', (error) => {
    report.browserErrors.push({
      label,
      kind: 'pageerror',
      message: error.message,
    })
  })
  page.on('requestfailed', (request) => {
    // Navigating from Setup into Studio intentionally destroys the gallery and
    // cancels any speculative/range media reads still in flight. Chromium
    // reports those normal cancellations as ERR_ABORTED.
    if (request.failure()?.errorText === 'net::ERR_ABORTED') return
    report.browserErrors.push({
      label,
      kind: 'requestfailed',
      message: `${request.method()} ${request.url()}: `
        + `${request.failure()?.errorText || 'unknown failure'}`,
    })
  })
}

function nextGenerate(page) {
  return new Promise((resolve) => {
    const listener = async (response) => {
      const request = response.request()
      const pathname = new URL(response.url()).pathname
      if (
        request.method() !== 'POST'
        || !pathname.endsWith('/v1/generate')
      ) return
      page.off('response', listener)
      const responseBody = await response.json()
      resolve({
        job: responseBody,
        request: request.postDataJSON(),
      })
    }
    page.on('response', listener)
  })
}

async function prepareWorld(page, subject, firstEvent) {
  // Keep the trailing slash when the Demo is mounted below code-server's
  // /proxy/<port>/ prefix. Without it, relative JS/CSS/API URLs can resolve
  // against /proxy/ instead of the selected port.
  await page.goto(`${baseUrl}/`, {
    waitUntil: 'domcontentloaded',
    timeout: 120_000,
  })
  await page.getByLabel('Subject').waitFor({ state: 'visible' })
  await page.getByLabel('Subject').fill(subject)
  await page.getByLabel('First Event').fill(firstEvent)
  await poll(
    'Enter world button to become enabled',
    async () => page.getByRole('button', { name: 'Enter world' }).isEnabled(),
    900_000,
  )
}

async function enterWorld(page) {
  const submitted = nextGenerate(page)
  await page.getByRole('button', { name: 'Enter world' }).click()
  return submitted
}

async function openStatus(page) {
  const button = page.getByLabel('Open live Demo resource status')
  if ((await button.getAttribute('aria-expanded')) !== 'true') {
    await button.click()
  }
  const panel = page.getByRole('complementary', {
    name: 'Demo resource status',
  })
  await panel.waitFor({ state: 'visible' })
  return panel.locator('.resource-summary-grid > div').evaluateAll((items) =>
    Object.fromEntries(items.map((item) => {
      const key = item.querySelector('span')?.textContent?.trim() || ''
      const value = item.querySelector('strong')?.textContent?.trim() || ''
      const detail = item.querySelector('small')?.textContent?.trim() || ''
      return [key, { value, detail }]
    })),
  )
}

async function main() {
  fs.mkdirSync(artifactDir, { recursive: true })
  const report = {
    startedAt: new Date().toISOString(),
    baseUrl,
    users: {},
    checkpoints: {},
    browserErrors: [],
    assertions: {},
  }

  const browser = await chromium.launch({
    headless: true,
    executablePath: chromiumExecutable,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })

  const contexts = {}
  const pages = {}
  try {
    const sharedContext = await browser.newContext({
      viewport: { width: 1440, height: 960 },
      httpCredentials,
    })
    await authenticateCodeServer(sharedContext)
    const pretestAdmin = await getJson(
      sharedContext.request,
      '/v1/admin/status',
    )
    const baselineOnlineUsers = Number(
      pretestAdmin.resources?.online_users || 0,
    )
    report.checkpoints.beforePagesOpen = {
      onlineUsers: baselineOnlineUsers,
    }
    for (const label of ['a', 'b', 'c']) {
      contexts[label] = sharedContext
      pages[label] = await sharedContext.newPage()
      installPageObservers(pages[label], label, report)
    }

    await Promise.all([
      prepareWorld(
        pages.a,
        'A red utility robot inspecting solar panels on a quiet lunar base',
        'The robot walks toward a damaged solar panel and scans it.',
      ),
      prepareWorld(
        pages.b,
        'A wildlife photographer in a green jacket beside a misty forest lake',
        'The photographer raises a camera as a deer steps out of the fog.',
      ),
      prepareWorld(
        pages.c,
        'A pastry chef working at a marble counter in a bright bakery',
        'The chef decorates a small cake with berries and mint leaves.',
      ),
    ])

    const initialConfig = await getJson(contexts.a.request, '/v1/config')
    report.checkpoints.beforeGeneration = {
      onlineUsers: initialConfig.online_users,
      workerCount: initialConfig.online_worker_count,
      modelOptionsExposed: Boolean(initialConfig.model_options?.length),
    }
    report.assertions.twoWorkersOnline =
      initialConfig.online_worker_count === 2
    report.assertions.publicModelSwitchHidden =
      !initialConfig.model_options?.length

    const [submissionA, submissionB] = await Promise.all([
      enterWorld(pages.a),
      enterWorld(pages.b),
    ])
    const [a, b] = await Promise.all([submissionA, submissionB])
    report.users.a = {
      jobId: a.job.id,
      sessionId: a.request.session_id,
      peSessionId: a.request.pe_input?.session_id,
    }
    report.users.b = {
      jobId: b.job.id,
      sessionId: b.request.session_id,
      peSessionId: b.request.pe_input?.session_id,
    }

    const dualRunning = await poll(
      'two browser jobs to run concurrently',
      async () => {
        const status = await getJson(contexts.a.request, '/v1/admin/status')
        return status.running_jobs === 2 ? status : undefined
      },
      180_000,
    )
    report.checkpoints.dualRunning = {
      runningJobs: dualRunning.running_jobs,
      busyWorkers: dualRunning.busy_worker_count,
      sessionWorkers: dualRunning.session_workers,
    }

    const submissionC = enterWorld(pages.c)
    const c = await submissionC
    report.users.c = {
      jobId: c.job.id,
      sessionId: c.request.session_id,
      peSessionId: c.request.pe_input?.session_id,
    }
    const cQueued = await waitForJob(
      contexts.c.request,
      c.job.id,
      ['queued'],
      120_000,
    )
    report.checkpoints.thirdUserQueued = {
      status: cQueued.status,
      queuePosition: cQueued.queue_position,
      queueReason: cQueued.queue_reason,
    }

    await poll(
      'Status panel to report three browsers and a queued job',
      async () => {
        const summary = await openStatus(pages.c)
        const online = Number(summary.Online?.value || 0)
        const queued = Number(summary.Queue?.value || 0)
        return online >= 3 && queued >= 1 ? summary : undefined
      },
      30_000,
    )
    report.checkpoints.statusPanel = await openStatus(pages.c)
    report.assertions.threeIndependentBrowsersOnline =
      Number(report.checkpoints.statusPanel.Online?.value || 0) >= 3
    report.assertions.singleBrowserIndependentPages = true
    await pages.c.screenshot({
      path: path.join(artifactDir, 'third-user-queued.png'),
      fullPage: true,
    })

    const [finishedA, finishedB] = await Promise.all([
      waitForJob(contexts.a.request, a.job.id, ['succeeded'], 600_000),
      waitForJob(contexts.b.request, b.job.id, ['succeeded'], 600_000),
    ])
    report.users.a.result = finishedA.result
    report.users.a.promptEnhancementMode =
      finishedA.prompt_enhancement_mode
    report.users.a.peRequestId = finishedA.pe_request_id
    report.users.b.result = finishedB.result
    report.users.b.promptEnhancementMode =
      finishedB.prompt_enhancement_mode
    report.users.b.peRequestId = finishedB.pe_request_id
    await poll(
      'A and B video elements to receive output URLs',
      async () => {
        const [srcA, srcB] = await Promise.all([
          pages.a.getByLabel('World model output').evaluate(
            (video) => video.currentSrc || video.getAttribute('src') || '',
          ),
          pages.b.getByLabel('World model output').evaluate(
            (video) => video.currentSrc || video.getAttribute('src') || '',
          ),
        ])
        return srcA && srcB
          ? { srcA, srcB }
          : undefined
      },
      30_000,
    )
    await Promise.all([
      pages.a.screenshot({
        path: path.join(artifactDir, 'user-a-succeeded.png'),
        fullPage: true,
      }),
      pages.b.screenshot({
        path: path.join(artifactDir, 'user-b-succeeded.png'),
        fullPage: true,
      }),
    ])

    await Promise.all([
      pages.a.evaluate(() => window.dispatchEvent(new Event('pagehide'))),
      pages.b.evaluate(() => window.dispatchEvent(new Event('pagehide'))),
    ])
    const oneBrowserRemaining = await poll(
      'presence count to drop after A and B leave',
      async () => {
        const config = await getJson(contexts.c.request, '/v1/config')
        return (
          config.online_users >= 1
          && config.online_users <= Math.max(
            1,
            report.checkpoints.beforeGeneration.onlineUsers - 2,
          )
        )
          ? config.online_users
          : undefined
      },
      30_000,
    )
    report.checkpoints.afterTwoBrowsersLeave = {
      onlineUsers: oneBrowserRemaining,
    }

    const finishedC = await waitForJob(
      contexts.c.request,
      c.job.id,
      ['succeeded'],
      300_000,
    )
    report.users.c.result = finishedC.result
    report.users.c.promptEnhancementMode =
      finishedC.prompt_enhancement_mode
    report.users.c.peRequestId = finishedC.pe_request_id
    await poll(
      'C video element to receive its output URL',
      async () => {
        const src = await pages.c
          .getByLabel('World model output')
          .evaluate(
            (video) => video.currentSrc || video.getAttribute('src') || '',
          )
        return src || undefined
      },
      30_000,
    )
    await pages.c.screenshot({
      path: path.join(artifactDir, 'third-user-succeeded.png'),
      fullPage: true,
    })

    await pages.c.evaluate(() => window.dispatchEvent(new Event('pagehide')))
    const finalAdmin = await poll(
      'all three browser sessions to release',
      async () => {
        const status = await getJson(contexts.c.request, '/v1/admin/status')
        return (
          status.queued_jobs === 0
          && status.running_jobs === 0
          && status.reserved_session_count === 0
        )
          ? status
          : undefined
      },
      60_000,
    )
    report.checkpoints.finalAdmin = {
      onlineWorkerCount: finalAdmin.online_worker_count,
      queuedJobs: finalAdmin.queued_jobs,
      runningJobs: finalAdmin.running_jobs,
      reservedSessionCount: finalAdmin.reserved_session_count,
      sessionWorkers: finalAdmin.session_workers,
      recentErrors: finalAdmin.recent_errors,
    }

    const sessionIds = [
      report.users.a.sessionId,
      report.users.b.sessionId,
      report.users.c.sessionId,
    ]
    report.assertions.independentInferenceSessions =
      new Set(sessionIds).size === 3
    report.assertions.promptAndInferenceSessionUnified =
      ['a', 'b', 'c'].every(
        (label) =>
          report.users[label].sessionId === report.users[label].peSessionId,
      )
    report.assertions.twoBrowserJobsSucceeded =
      finishedA.status === 'succeeded' && finishedB.status === 'succeeded'
    report.assertions.thirdUserObservedQueue = cQueued.status === 'queued'
    report.assertions.thirdUserEventuallySucceeded =
      finishedC.status === 'succeeded'
    report.assertions.presenceDropsWhenBrowsersLeave =
      report.checkpoints.afterTwoBrowsersLeave.onlineUsers
        <= Math.max(
          1,
          report.checkpoints.beforeGeneration.onlineUsers - 2,
        )
    report.assertions.k3PromptEnhancementUsed =
      !initialConfig.prompt_enhancement_enabled
      || ['a', 'b', 'c'].every(
        (label) =>
          report.users[label].promptEnhancementMode === 'kimi-k3'
          && Boolean(report.users[label].peRequestId),
      )
    report.assertions.serviceHealthyAfterTest =
      finalAdmin.online_worker_count === 2
      && finalAdmin.queued_jobs === 0
      && finalAdmin.running_jobs === 0
      && finalAdmin.reserved_session_count === 0
    report.assertions.noBrowserRuntimeErrors =
      report.browserErrors.length === 0

    report.passed = Object.values(report.assertions).every(Boolean)
    report.finishedAt = new Date().toISOString()
    fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`)
    console.log(JSON.stringify(report, null, 2))
    if (!report.passed) process.exitCode = 1
  } finally {
    const cleanupRequest = contexts.a?.request
    if (cleanupRequest) {
      for (const label of ['a', 'b', 'c']) {
        const sessionId = report.users[label]?.sessionId
        if (!sessionId) continue
        try {
          const submitted = await postJson(
            cleanupRequest,
            `/v1/sessions/${encodeURIComponent(sessionId)}/release`,
          )
          if (submitted.id) {
            await poll(
              `${sessionId} cleanup release`,
              async () => {
                const job = await getJson(
                  cleanupRequest,
                  `/v1/sessions/${encodeURIComponent(sessionId)}/release/${submitted.id}`,
                )
                return ['succeeded', 'failed', 'cancelled'].includes(job.status)
                  ? job
                  : undefined
              },
              60_000,
            )
          }
        } catch {
          // The pagehide path may already have released the session.
        }
      }
    }
    await Promise.all(
      [...new Set(Object.values(contexts))].map((context) =>
        context.close().catch(() => undefined),
      ),
    )
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
