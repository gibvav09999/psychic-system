/**
 * API.js - Production-ready
 * - Max 4 concurrent browsers
 * - Queue max 20 waiting
 * - Hard timeout per task (5 menit)
 * - Browser selalu ditutup di finally
 * - Task otomatis dihapus setelah diambil atau TTL (5 menit)
 * - Cache dimatikan secara default
 * - Health endpoint dengan memory metrics
 * - Logging minimal
 */

const express = require('express');
const { connect } = require("puppeteer-real-browser");
const fs = require('fs');
const path = require('path');

// ============================
// CONFIGURATION
// ============================
const PORT = process.env.PORT || 8080;
const AUTH_TOKEN = process.env.authToken || null;

// Resource limits
const MAX_BROWSERS = 4;
const MAX_QUEUE = 20;
const TASK_TTL = 5 * 60 * 1000;        // 5 minutes – for cleanup of abandoned tasks
const SOLVE_TIMEOUT = global.timeOut || 300000; // 5 minutes – hard timeout per task
const CACHE_AUTOSAVE = process.env.CACHE_AUTOSAVE === "true" || false; // default false

// Cache (disk) – optional, disabled by default
const CACHE_DIR = path.join(__dirname, "cache");
const CACHE_TYPES = ["turnstile", "recaptcha3", "recaptcha2", "interstitial", "error"];

function readCache(type, taskId) {
    if (!CACHE_AUTOSAVE) return null;
    const file = path.join(CACHE_DIR, type, `${taskId}.json`);
    if (!fs.existsSync(file)) return null;
    try {
        const data = JSON.parse(fs.readFileSync(file, 'utf-8'));
        if (Date.now() - data.timestamp < TASK_TTL) {
            return data;
        }
        return null;
    } catch {
        return null;
    }
}

function writeCache(type, taskId, value) {
    if (!CACHE_AUTOSAVE) return;
    const dir = path.join(CACHE_DIR, type);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, `${taskId}.json`);
    const data = { timestamp: Date.now(), ...value };
    fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf-8');
}

function cleanCache() {
    const now = Date.now();
    const TTL = 60 * 60 * 1000; // 1 hour
    CACHE_TYPES.forEach(type => {
        const dir = path.join(CACHE_DIR, type);
        if (!fs.existsSync(dir)) return;
        fs.readdirSync(dir).forEach(file => {
            const filePath = path.join(dir, file);
            try {
                const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
                if (now - data.timestamp > TTL) {
                    fs.unlinkSync(filePath);
                    console.log(`Cache expired: ${filePath}`);
                }
            } catch {
                fs.unlinkSync(filePath);
            }
        });
    });
}
setInterval(cleanCache, 600 * 1000); // every 10 minutes

// ============================
// EXPRESS SETUP
// ============================
const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ============================
// IN-MEMORY STATE
// ============================
const tasks = new Map();            // taskId -> { status, result?, createdAt, completedAt? }
const queue = [];                  // array of task objects { taskId, type, domain, siteKey, ... }
let activeBrowsers = 0;

// ============================
// HELPER: clean up old tasks (only for abandoned ones)
// ============================
function cleanupTasks() {
    const now = Date.now();
    for (const [taskId, task] of tasks) {
        // Only remove tasks that are done or error (completed)
        if (task.status === 'done' || task.status === 'error') {
            if (task.completedAt && (now - task.completedAt > TASK_TTL)) {
                tasks.delete(taskId);
                console.log(`Task ${taskId} removed (TTL expired)`);
            }
        }
        // Also remove pending/processing if they are older than TASK_TTL (stuck)
        // but we also rely on hard timeout to abort them, so this is a safety net
        if ((task.status === 'pending' || task.status === 'processing') && (now - task.createdAt > TASK_TTL)) {
            tasks.delete(taskId);
            console.log(`Task ${taskId} removed (stale)`);
        }
    }
}
setInterval(cleanupTasks, 60 * 1000); // every minute

// ============================
// QUEUE PROCESSOR (scheduler)
// ============================
function processQueue() {
    // While there are tasks in queue and we have free browser slots
    while (queue.length > 0 && activeBrowsers < MAX_BROWSERS) {
        const item = queue.shift();
        activeBrowsers++;
        // Execute task asynchronously (non-blocking)
        executeTask(item).finally(() => {
            activeBrowsers--;
            // After finishing, try to process more tasks
            processQueue();
        });
    }
}

// ============================
// TASK EXECUTION (with browser & hard timeout)
// ============================
async function executeTask({ taskId, type, domain, siteKey, action, proxy, isInvisible }) {
    const task = tasks.get(taskId);
    if (!task) {
        // Task might have been removed by cleanup, just release browser slot
        return;
    }

    task.status = 'processing';
    console.log(`[${taskId}] Processing ${type} on ${domain}`);

    let browser = null;
    let page = null;
    let timeoutId = null;

    // Create a promise that rejects after SOLVE_TIMEOUT
    const timeoutPromise = new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
            reject(new Error(`Task timeout after ${SOLVE_TIMEOUT}ms`));
        }, SOLVE_TIMEOUT);
    });

    try {
        // 1. Launch browser (with auto-detected Chrome path & optional proxy)
        const possiblePaths = [
            process.env.CHROME_PATH,
            process.env.CHROME_BIN,
            process.env.PUPPETEER_EXECUTABLE_PATH,
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            '/snap/bin/chromium'
        ].filter(Boolean);

        let detectedChrome = possiblePaths.find(p => fs.existsSync(p));
        if (detectedChrome) {
            process.env.CHROME_PATH = detectedChrome;
            process.env.CHROME_BIN = detectedChrome;
            process.env.PUPPETEER_EXECUTABLE_PATH = detectedChrome;
        }

        const connectOptions = {
            headless: false,
            turnstile: true,
            connectOption: { 
                defaultViewport: null,
                args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            },
            disableXvfb: false,
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        };
        if (detectedChrome) {
            connectOptions.customConfig = { chromePath: detectedChrome };
            connectOptions.executablePath = detectedChrome;
        }
        if (proxy?.server) {
            connectOptions.args.push(`--proxy-server=${proxy.server}`);
        }

        // Race between browser launch and timeout
        const { browser: b, page: p } = await Promise.race([
            connect(connectOptions),
            timeoutPromise
        ]);
        browser = b;
        page = p;
        clearTimeout(timeoutId);

        // Set request interception to block images, etc.
        await page.setRequestInterception(true);
        page.on('request', (req) => {
            const type = req.resourceType();
            if (["image", "stylesheet", "font", "media"].includes(type)) {
                req.abort();
            } else {
                req.continue();
            }
        });

        await page.goto('about:blank');

        // 2. Choose solver based on type – each solver returns a promise
        let solverPromise;
        switch (type) {
            case 'turnstile':
                solverPromise = require('./Api/turnstile')({ domain, siteKey, action, proxy }, page);
                break;
            case 'interstitial':
                solverPromise = require('./Api/interstitial')({ domain, proxy }, page);
                break;
            case 'recaptcha2':
                solverPromise = require('./Api/recaptcha2')({ domain, siteKey, action, isInvisible, proxy }, page);
                break;
            case 'recaptcha3':
                solverPromise = require('./Api/recaptcha3')({ domain, siteKey, action, proxy }, page);
                break;
            default:
                throw new Error('Invalid solver type');
        }

        // Race solver vs timeout (reuse timeoutId)
        timeoutId = setTimeout(() => {
            // We can't easily cancel the solver promise, but we'll reject via Promise.race
            // However, we need to propagate the error. We'll use a separate reject.
        }, SOLVE_TIMEOUT);

        const result = await Promise.race([
            solverPromise,
            new Promise((_, reject) => {
                // This reject will be triggered by the timeout
                const handler = () => reject(new Error(`Task timeout after ${SOLVE_TIMEOUT}ms`));
                timeoutId = setTimeout(handler, SOLVE_TIMEOUT);
                // Store the handler so we can clear it later
                task._timeoutHandler = handler;
                task._timeoutId = timeoutId;
            })
        ]);

        clearTimeout(timeoutId);
        delete task._timeoutId;
        delete task._timeoutHandler;

        // 3. Store result
        task.status = 'done';
        task.result = result;
        task.completedAt = Date.now();
        console.log(`[${taskId}] Solved successfully`);

        // Optionally write to cache
        if (CACHE_AUTOSAVE) {
            writeCache(type, taskId, { status: 'done', ...result });
        }

    } catch (err) {
        // 4. Error handling (including timeout)
        clearTimeout(timeoutId);
        delete task._timeoutId;
        delete task._timeoutHandler;

        task.status = 'error';
        task.result = { message: err.message || 'Solver failed' };
        task.completedAt = Date.now();
        console.error(`[${taskId}] Failed: ${err.message}`);
    } finally {
        // 5. Always close browser and release resources
        try {
            if (page && !page.isClosed()) {
                await page.close();
            }
        } catch (e) { /* ignore */ }
        try {
            if (browser) {
                await browser.close();
            }
        } catch (e) { /* ignore */ }
        console.log(`[${taskId}] Browser closed`);
        // Note: activeBrowsers is decremented in the caller (processQueue)
    }
}

// ============================
// EXPRESS ROUTES
// ============================

// Health & info
app.get("/", (req, res) => {
    const baseUrl = `${req.protocol}://${req.get('host')}`;
    const uptime = process.uptime();
    const memory = process.memoryUsage();

    res.json({
        message: "Welcome",
        server: {
            domain: baseUrl,
            version: "7.3.0",
            uptime: `${Math.floor(uptime)} seconds`,
            maxBrowsers: MAX_BROWSERS,
            maxQueue: MAX_QUEUE,
            activeBrowsers,
            queueLength: queue.length,
            taskCount: tasks.size,
            status: "running"
        },
        memory: {
            rss: `${Math.round(memory.rss / 1024 / 1024)} MB`,
            heapTotal: `${Math.round(memory.heapTotal / 1024 / 1024)} MB`,
            heapUsed: `${Math.round(memory.heapUsed / 1024 / 1024)} MB`,
            external: `${Math.round(memory.external / 1024 / 1024)} MB`
        },
        solvers: ["turnstile", "recaptcha2", "recaptcha3", "interstitial"]
    });
});

// Solve endpoint
app.post('/solve', async (req, res) => {
    const { type, domain, siteKey, taskId, action, proxy, isInvisible } = req.body;

    // 1. If taskId is provided, return existing result (or processing status)
    if (taskId) {
        const task = tasks.get(taskId);
        if (!task) {
            return res.status(404).json({ status: "error", message: "Task not found or expired" });
        }
        if (task.status === 'pending' || task.status === 'processing') {
            return res.json({ status: "processing" });
        }
        // done or error – return result and delete task to free memory
        const response = { status: task.status, ...task.result };
        tasks.delete(taskId);
        return res.json(response);
    }

    // 2. Validate required fields
    if (!type || !domain) {
        return res.status(400).json({ status: "error", message: "Missing type or domain" });
    }
    if (!['turnstile', 'recaptcha2', 'recaptcha3', 'interstitial'].includes(type)) {
        return res.status(400).json({ status: "error", message: "Invalid solver type" });
    }
    if ((type === 'turnstile' || type === 'recaptcha2' || type === 'recaptcha3') && !siteKey) {
        return res.status(400).json({ status: "error", message: "Missing siteKey" });
    }

    // 3. Check queue limit
    if (queue.length >= MAX_QUEUE) {
        return res.status(503).json({ status: "error", message: "Server busy, queue full" });
    }

    // 4. Create new task
    const newTaskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 4);
    const task = {
        status: 'pending',
        createdAt: Date.now(),
    };
    tasks.set(newTaskId, task);

    // 5. Enqueue task
    queue.push({
        taskId: newTaskId,
        type,
        domain,
        siteKey,
        action,
        proxy,
        isInvisible
    });

    console.log(`[${newTaskId}] Queued (${type} on ${domain})`);

    // 6. Trigger queue processing (non-blocking)
    processQueue();

    // 7. Return taskId immediately
    res.json({ taskId: newTaskId, status: "pending" });
});

// 404 handler
app.use((req, res) => {
    res.status(404).json({ message: 'Not Found' });
});

// ============================
// START SERVER
// ============================
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
    console.log(`Max browsers: ${MAX_BROWSERS}, Max queue: ${MAX_QUEUE}`);
    console.log(`Cache autosave: ${CACHE_AUTOSAVE}`);
    console.log(`Task timeout: ${SOLVE_TIMEOUT}ms`);
});