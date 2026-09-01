/**
 * API_RECAPTCHA2 - Production Solver
 */
async function recaptchaV2({ domain, siteKey, action = "submit", isInvisible = false, proxy }, page) {
    if (!domain) throw new Error("Missing domain parameter");
    if (!siteKey) throw new Error("Missing siteKey parameter");

    const timeout = global.timeOut || 90000; // 90 giây mặc định

    return new Promise(async (resolve, reject) => {
        let isResolved = false;

        const cl = setTimeout(() => {
            if (!isResolved) {
                isResolved = true;
                reject(new Error("Timeout Error (reCAPTCHA v2 took longer than 90s)"));
            }
        }, timeout);

        try {
            if (proxy?.username && proxy?.password) {
                await page.authenticate({
                    username: proxy.username,
                    password: proxy.password,
                });
            }

            const htmlContent = `
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>reCAPTCHA v2 Solver</title>
                    <style>
                        body {
                            font-family: Arial, sans-serif;
                            margin: 0;
                            padding: 20px;
                            background: #f5f5f5;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            min-height: 100vh;
                        }
                        .container {
                            background: white;
                            padding: 30px;
                            border-radius: 10px;
                            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                            text-align: center;
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h2>reCAPTCHA v2 Solver</h2>
                        <div id="recaptcha-container">
                            <div class="g-recaptcha"
                                 data-sitekey="${siteKey}"
                                 data-callback="recaptchaCallback"
                                 data-size="${isInvisible ? 'invisible' : 'normal'}"
                                 data-theme="light"></div>
                        </div>
                        <input type="hidden" id="recaptcha-token-input" name="g-recaptcha-response" />
                    </div>

                    <script>
                        window.recaptchaToken = null;
                        window.recaptchaCallback = function(token) {
                            window.recaptchaToken = token;
                            var input = document.getElementById('recaptcha-token-input');
                            if (input) input.value = token;
                        };
                    </script>
                    <script src="https://www.google.com/recaptcha/api.js" async defer></script>
                </body>
                </html>
            `;

            await page.setRequestInterception(true);
            page.removeAllListeners("request");
            page.on("request", async (req) => {
                const url = req.url();
                if ([domain, domain + "/", domain + "/faucet/PEPE"].some(u => url.startsWith(u)) && req.resourceType() === "document") {
                    await req.respond({ status: 200, contentType: "text/html", body: htmlContent });
                } else if (url.includes("google.com") || url.includes("gstatic.com") || url.includes("recaptcha")) {
                    await req.continue();
                } else if (["media"].includes(req.resourceType())) {
                    await req.abort();
                } else {
                    await req.continue();
                }
            });

            await page.goto(domain, { waitUntil: "domcontentloaded", timeout: 30000 });

            // Tự động tương tác với checkbox reCAPTCHA v2
            setTimeout(async () => {
                try {
                    if (isInvisible) {
                        await page.evaluate(() => { if (window.grecaptcha) grecaptcha.execute(); });
                    } else {
                        const frameHandle = await page.waitForSelector('iframe[src*="google.com/recaptcha/api2/anchor"]', { timeout: 10000 }).catch(() => null);
                        if (frameHandle) {
                            const frame = await frameHandle.contentFrame();
                            if (frame) {
                                const checkbox = await frame.waitForSelector('#recaptcha-anchor', { timeout: 10000 }).catch(() => null);
                                if (checkbox) {
                                    await checkbox.click({ delay: 100 });
                                }
                            }
                        }
                    }
                } catch (_) {}
            }, 1500);

            // Chờ token hoàn thành
            const tokenHandle = await page.waitForFunction(() => {
                const input = document.querySelector('#recaptcha-token-input');
                if (input && input.value && input.value.length > 20) return input.value;
                if (window.recaptchaToken && window.recaptchaToken.length > 20) return window.recaptchaToken;
                const textarea = document.querySelector('textarea[name="g-recaptcha-response"]');
                if (textarea && textarea.value && textarea.value.length > 20) return textarea.value;
                return null;
            }, { timeout, polling: 300 });

            const tokenValue = await tokenHandle.jsonValue();

            isResolved = true;
            clearTimeout(cl);

            if (!tokenValue || tokenValue.length < 20) {
                reject(new Error("Failed to get valid reCAPTCHA token"));
            } else {
                resolve({ token: tokenValue, type: 'recaptcha_v2' });
            }
        } catch (error) {
            if (!isResolved) {
                isResolved = true;
                clearTimeout(cl);
                reject(new Error(`reCAPTCHA solving failed: ${error.message}`));
            }
        }
    });
}

module.exports = recaptchaV2;