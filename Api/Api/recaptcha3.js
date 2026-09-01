/**
 * recaptcha3.js - Fast Token Generator
 */
async function recaptchaV3({ domain, siteKey, action = "submit", proxy }, page) {
    if (!domain) throw new Error("Missing domain parameter");
    if (!siteKey) throw new Error("Missing siteKey parameter");

    const timeout = 30000;

    return new Promise(async (resolve, reject) => {
        let isResolved = false;

        const cl = setTimeout(() => {
            if (!isResolved) {
                isResolved = true;
                reject(new Error("Timeout Error (reCAPTCHA v3)"));
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
                    <title>reCAPTCHA v3</title>
                    <script src="https://www.google.com/recaptcha/api.js?render=${siteKey}"></script>
                </head>
                <body style="background:#f0f0f0; margin:0; padding:20px;">
                    <h3>reCAPTCHA v3</h3>
                    <script>
                        window.recaptchaToken = null;
                        function runRecaptcha() {
                            if (typeof grecaptcha !== 'undefined') {
                                grecaptcha.ready(function() {
                                    grecaptcha.execute('${siteKey}', { action: '${action || "submit"}' }).then(function(token) {
                                        window.recaptchaToken = token;
                                    }).catch(function(err) {
                                        window.recaptchaError = err ? (err.message || String(err)) : "Execute error";
                                    });
                                });
                            } else {
                                setTimeout(runRecaptcha, 150);
                            }
                        }
                        runRecaptcha();
                    </script>
                </body>
                </html>
            `;

            try {
                await page.setRequestInterception(true);
                page.removeAllListeners("request");
                page.on("request", async (req) => {
                    const url = req.url();
                    // Chỉ intercept trang chủ chính của domain, TUYỆT ĐỐI không intercept iframe của Google reCAPTCHA
                    const isMainDoc = (url === domain || url === domain + "/" || url.startsWith(domain)) && 
                                      !url.includes("google.com") && 
                                      !url.includes("gstatic.com") && 
                                      !url.includes("recaptcha") && 
                                      req.resourceType() === "document";

                    if (isMainDoc) {
                        await req.respond({ status: 200, contentType: "text/html", body: htmlContent });
                    } else {
                        await req.continue();
                    }
                });
            } catch (_) {}

            await page.goto(domain, { waitUntil: "domcontentloaded", timeout: 20000 });

            // Chờ token hoàn thành
            const tokenHandle = await page.waitForFunction(() => {
                if (window.recaptchaToken && window.recaptchaToken.length > 20) {
                    return window.recaptchaToken;
                }
                if (window.recaptchaError) {
                    throw new Error("reCAPTCHA execution error: " + window.recaptchaError);
                }
                return null;
            }, { timeout: 25000, polling: 150 });

            const token = await tokenHandle.jsonValue();

            isResolved = true;
            clearTimeout(cl);

            if (!token || token.length < 20) {
                reject(new Error("Failed to get valid reCAPTCHA v3 token"));
            } else {
                resolve({ token: token, type: "recaptcha3" });
            }
        } catch (e) {
            if (!isResolved) {
                isResolved = true;
                clearTimeout(cl);
                reject(e);
            }
        }
    });
}

module.exports = recaptchaV3;