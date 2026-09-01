/**
 * API_RECAPTCHA2 - Production Solver
 */
async function recaptchaV2({ domain, siteKey, action = "submit", isInvisible = false, proxy }, page) {
    if (!domain) throw new Error("Missing domain parameter");
    if (!siteKey) throw new Error("Missing siteKey parameter");

    const timeout = 65000;

    return new Promise(async (resolve, reject) => {
        let isResolved = false;

        const cl = setTimeout(() => {
            if (!isResolved) {
                isResolved = true;
                reject(new Error("Timeout Error (reCAPTCHA v2 took > 65s)"));
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
                    <title>reCAPTCHA v2</title>
                    <script src="https://www.google.com/recaptcha/api.js?onload=onRecaptchaLoad&render=explicit" async defer></script>
                </head>
                <body style="background: #f5f5f5; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
                    <div id="recaptcha-widget"></div>
                    <script>
                        window.recaptchaToken = null;
                        function onRecaptchaLoad() {
                            grecaptcha.render('recaptcha-widget', {
                                'sitekey': '${siteKey}',
                                'callback': function(token) {
                                    window.recaptchaToken = token;
                                }
                            });
                        }
                    </script>
                </body>
                </html>
            `;

            try {
                await page.setRequestInterception(true);
                page.removeAllListeners("request");
                page.on("request", async (req) => {
                    const url = req.url();
                    if (req.isNavigationRequest() && req.resourceType() === "document") {
                        await req.respond({ status: 200, contentType: "text/html", body: htmlContent });
                    } else if (["media"].includes(req.resourceType())) {
                        await req.abort();
                    } else {
                        await req.continue();
                    }
                });
            } catch (_) {}

            await page.goto(domain, { waitUntil: "domcontentloaded", timeout: 30000 });

            // Tự động tìm frame và click checkbox
            const clickCheckbox = async () => {
                for (let i = 0; i < 20; i++) {
                    if (isResolved) break;
                    try {
                        for (const frame of page.frames()) {
                            if (frame.url().includes("google.com/recaptcha") && frame.url().includes("anchor")) {
                                const box = await frame.$("#recaptcha-anchor");
                                if (box) {
                                    await box.click();
                                    return true;
                                }
                            }
                        }
                    } catch (_) {}
                    await new Promise(r => setTimeout(r, 1000));
                }
                return false;
            };

            clickCheckbox();

            // Chờ token hoàn tất
            const tokenHandle = await page.waitForFunction(() => {
                if (window.recaptchaToken && window.recaptchaToken.length > 20) return window.recaptchaToken;
                const textarea = document.querySelector('textarea[name="g-recaptcha-response"]');
                if (textarea && textarea.value && textarea.value.length > 20) return textarea.value;
                return null;
            }, { timeout: 60000, polling: 300 });

            const tokenValue = await tokenHandle.jsonValue();

            isResolved = true;
            clearTimeout(cl);

            if (!tokenValue || tokenValue.length < 20) {
                reject(new Error("Failed to get valid token"));
            } else {
                resolve({ token: tokenValue, type: 'recaptcha_v2' });
            }
        } catch (error) {
            if (!isResolved) {
                isResolved = true;
                clearTimeout(cl);
                reject(error);
            }
        }
    });
}

module.exports = recaptchaV2;