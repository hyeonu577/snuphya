# snuphya

Automated announcement checker for the SNU Physics & Astronomy intranet.

Periodically scrapes announcements, summarizes them via OpenAI, and sends notifications through email, LINE, and Todoist.

## Structure

```
main.py        Main loop and orchestration
config.py      Paths, constants, OpenAI client
db.py          SQLite (checked items, click counts, batch list)
scraper.py     Selenium scraping, file/image download, JSON I/O
batch.py       OpenAI Batch API lifecycle
notifier.py    Email, LINE, Todoist, urgency analysis
models.py      Pydantic model (AnnouncementCheck)
```

## Workflow

1. **Scrape** - Fetches graduate/undergraduate announcements from the intranet
2. **Urgency check** - Uses GPT to detect compensation or participant limits; sends immediate alerts
3. **Batch summarize** - Submits announcements to OpenAI Batch API for summarization
4. **Process results** - Sends summary emails and creates Todoist tasks

## External Dependencies

- `snulogin.py` - SNU intranet login with 2FA
- `true_email/` - Email sending (git submodule)
- `true_line/` - LINE messaging (git submodule)

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY_SNUPHYA` | OpenAI API key |
| `CHROMIUM_PATH` | Path to Chromium binary |
| `CHROME_DRIVER_PATH` | Path to ChromeDriver |
| `TODOIST_API_TOKEN` | Todoist API token |
| `HEALTHCHECK_SNUPHYA` | Healthcheck webhook URL |
