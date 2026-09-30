# AI Calling Agent — functional starter

SIM → GSM/4G SIP gateway → Asterisk → Python AI voice agent → customer.
This is a turn-by-turn voice agent: it plays a reply, then records a question. It does not support interruption/barge-in. AI speech and questions are processed by OpenAI. SIM call charges and AI usage are extra. Actual gateway calls have NOT been tested in the build environment.

## Ubuntu/Debian setup (dedicated Asterisk machine)
1. Install Asterisk, Python 3, venv and ffmpeg using your package manager.
2. Place this project at `/opt/ai-calling-agent`. Create `.venv` using `python3 -m venv .venv`, then `.venv/bin/pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`. Set API key, a long random admin token, caller ID and SIP endpoint. Do not put credentials in public_html. Restrict `.env` permissions to the Asterisk service user.
4. Include `extensions.conf` in Asterisk's existing dialplan. Add `[reject-inbound]` with `exten => _X!,1,Hangup()` if using the example gateway context.
5. Merge `pjsip.conf.example` into existing configuration; replace gateway IP. Configure gateway to accept Asterisk SIP requests and route them to the SIM. Gateway authentication, number prefix, SIM port selection and codec requirements vary by model. Do not overwrite an existing production configuration.
6. Create `/var/spool/asterisk/ai-staging` and `/var/spool/asterisk/outgoing_done`. Staging and outgoing MUST be on the same filesystem for atomic rename. Give the `asterisk` user ownership of project/data and staging directories. Run both API and AGI as `asterisk`; `chmod +x /opt/ai-calling-agent/agent.py`. AGI shebang points to the project venv.
7. Reload Asterisk dialplan and PJSIP. Verify gateway routing with a manual test call before campaign use.
8. Start API as `asterisk`: `/opt/ai-calling-agent/.venv/bin/gunicorn --workers 1 --threads 4 --timeout 0 --bind 127.0.0.1:8080 app:app` from project directory. Disable automatic reload during campaigns. Run persistently under systemd for use beyond testing.
9. Open `http://127.0.0.1:8080/dashboard` on the server, or use an SSH tunnel to access it from your computer. Set API URL to match the browser origin and enter the admin token. Keep API bound to localhost; do not expose this starter directly to the internet.

## Behavior
- Enter numbers one per line and fill the business message with greeting, services, price, timings and FAQs.
- Only one campaign can run; duplicates removed. No automatic retries.
- If customer disconnects, Asterisk archives the call file and the queue advances.
- Busy/no answer: archive marks failed and queue advances. Some gateway/SIM networks answer early; test carrier behavior.
- Hard 600-second limit starts when answered dialplan begins. Ring timeout is 45 seconds.
- Stop lets the current call finish, then prevents the next call.
- Queue halts if completion cannot be confirmed. This prevents overlap.
- On API restart a campaign is not automatically resumed. Check Asterisk active channels before manually starting another campaign. Persistent crash recovery and an active-channel reconciliation guard are required for unattended production use.
- AI is prompted to answer only from the message. This is a model instruction, not a guarantee; review live test answers before production.
- No permanent audio/transcript storage. Campaign files contain numbers and message; restrict access and remove when no longer needed.

## Acceptance test before real use
Use two consenting test numbers. Confirm greeting, Hindi questions, unknown-answer fallback, busy/no answer, caller hangup, 10-minute timeout, Stop, and API process restart. Verify no two calls overlap. If no audio, check gateway codec and RTP firewall settings. Use `asterisk -rvvv` to diagnose AGI/dialplan issues; never log API keys.

## Information references
https://docs.asterisk.org/Asterisk_20_Documentation/API_Documentation/AGI_Commands/record_file/
https://docs.asterisk.org/Asterisk_22_Documentation/API_Documentation/AGI_Commands/stream_file/
https://github.com/openai/openai-python

Use with customers who agreed to receive calls and a SIM/carrier plan that permits your calling use.
