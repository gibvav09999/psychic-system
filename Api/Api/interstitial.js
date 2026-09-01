/**
 * Cloudflare Interstitial / 5s Challenge Solver
 */
async function interstitial({ domain, proxy }, page) {
    return new Promise(async (resolve, reject) => {
        if (!domain) return reject(new Error("Missing domain parameter"));

        let isResolved = false;
        const timeout = 35000;

        const cl = setTimeout(async () => {
            if (!isResolved) {
                isResolved = true;
                try {
                    const cookies = await page.cookies();
                    const cf = cookies.find(c => c.name === "cf_clearance");
                    const userAgent = await page.evaluate(() => navigator.userAgent);
                    const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join("; ");
                    resolve({
                        cf_clearance: cf ? cf.value : null,
                        cookies: cookieStr,
                        user_agent: userAgent,
                        type: 'interstitial'
                    });
                } catch {
                    resolve({ cf_clearance: null, cookies: null, user_agent: null, type: 'interstitial' });
                }
            }
        }, timeout);

        try {
            if (proxy?.username && proxy?.password) {
                await page.authenticate({
                    username: proxy.username,
                    password: proxy.password,
                });
            }

            // Theo dõi set-cookie header
            page.on("response", async (res) => {
                try {
                    const headers = res.headers();
                    if (headers["set-cookie"]) {
                        const cookies = headers["set-cookie"];
                        const match = cookies.match(/cf_clearance=([^;]+)/);
                        if (match && !isResolved) {
                            const cf_clearance = match[1];
                            const userAgent = await page.evaluate(() => navigator.userAgent);
                            const allCookies = await page.cookies();
                            const cookieStr = allCookies.map(c => `${c.name}=${c.value}`).join("; ");
                            isResolved = true;
                            clearTimeout(cl);
                            return resolve({
                                cf_clearance,
                                cookies: cookieStr,
                                user_agent: userAgent,
                                type: 'interstitial'
                            });
                        }
                    }
                } catch (_) {}
            });

            await page.goto(domain, { waitUntil: "domcontentloaded", timeout: 30000 });
            const userAgent = await page.evaluate(() => navigator.userAgent);

            // Kiểm tra định kỳ cookies
            for (let i = 0; i < 20; i++) {
                if (isResolved) break;
                await new Promise(r => setTimeout(r, 1000));
                const cookies = await page.cookies();
                const cf = cookies.find(c => c.name === "cf_clearance");
                if (cf && !isResolved) {
                    const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join("; ");
                    isResolved = true;
                    clearTimeout(cl);
                    return resolve({
                        cf_clearance: cf.value,
                        cookies: cookieStr,
                        user_agent: userAgent,
                        type: 'interstitial'
                    });
                }
            }

            if (!isResolved) {
                const cookies = await page.cookies();
                const cf = cookies.find(c => c.name === "cf_clearance");
                const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join("; ");
                isResolved = true;
                clearTimeout(cl);
                resolve({
                    cf_clearance: cf ? cf.value : null,
                    cookies: cookieStr,
                    user_agent: userAgent,
                    type: 'interstitial'
                });
            }
        } catch (err) {
            if (!isResolved) {
                isResolved = true;
                clearTimeout(cl);
                reject(err);
            }
        }
    });
}

module.exports = interstitial;