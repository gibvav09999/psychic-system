# Stability wrapper

This package keeps the original application source unchanged, including the solver modules.

The only addition is `run-stable.sh`, which:
- starts Xvfb if needed;
- starts the original `npm start` command;
- restarts the Node process if it exits unexpectedly.

It does not alter solver timing, browser connection logic, CAPTCHA handling, or task behavior.

For Docker, the existing command can be replaced with:

    CMD ["./run-stable.sh"]
