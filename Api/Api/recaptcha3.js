/**
 * recaptcha3.js - Fast Token Generator without Image Challenges
 */
async function recaptchaV3({ domain, siteKey, action = "submit", proxy }, page) {
    if (!domain) throw new Error("Missing domain parameter");
    if (!siteKey) throw new Error("Missing siteKey parameter");

    const timeout = 35000;

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

            await page.goto(domain, { waitUntil: "domcontentloaded", timeout: 25000 });

            // Nạp thư viện Google reCAPTCHA
            await page.addScriptTag({ url: "https://www.google.com/recaptcha/api.js?render=" + siteKey });

            // Chờ grecaptcha khởi tạo
            await page.waitForFunction(() => typeof window.grecaptcha !== "undefined" && typeof window.grecaptcha.execute === "function", { timeout: 15000 });

            const token = await page.evaluate(async (sKey, act) => {
                return new Promise((res, rej) => {
                    grecaptcha.ready(async () => {
                        try {
                            const t = await grecaptcha.execute(sKey, { action: act || "submit" });
                            res(t);
                        } catch (err) {
                            rej(err);
                        }
                    });
                });
            }, siteKey, action);

            isResolved = true;
            clearTimeout(cl);

            if (!token || token.length < 10) {
                reject(new Error("Failed to get valid token"));
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