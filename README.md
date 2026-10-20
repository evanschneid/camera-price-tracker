# 📷 Camera Price Tracker

Checks camera prices at new and used retailers twice a day and emails me when
something drops. Runs free on GitHub Actions — no server, no paid APIs.

- **New:** B&H, Adorama, and any shop with standard product markup
- **Used:** MPB, KEH, and eBay Buy It Now (lowest price + shipping)
- **Alerts:** email on a drop of 3%+ or when a camera first hits my target price
- **History:** every price is saved to [`data/prices.csv`](data/prices.csv);
  the latest snapshot is in [`data/latest.md`](data/latest.md)

## How it works

```
GitHub Actions (~9am + 9pm US Eastern; 8am/8pm in winter)
   └─ python -m tracker run
        ├─ reads cameras.yaml
        ├─ fetches each product page / eBay search
        ├─ extracts the price (schema.org data → meta tags → markup)
        ├─ compares with data/prices.csv → emails on drops
        └─ commits the new prices back to the repo
```

| File | What it does |
|---|---|
| `cameras.yaml` | **The only file you normally edit.** Cameras, target prices, sources |
| `tracker/sources/product_page.py` | Reads the price from any product page |
| `tracker/sources/ebay.py` | Lowest matching eBay listing, filtered by title |
| `tracker/alerts.py` | Decides what's worth an email |
| `tracker/run.py` | One full check of everything |
| `.github/workflows/check-prices.yml` | The twice-daily schedule |

## Setup (about 10 minutes)

### 1. Email alerts (Gmail)

1. Turn on 2-Step Verification on your Google account if it isn't already.
2. Go to <https://myaccount.google.com/apppasswords>, create an app password
   named "camera tracker", and copy the 16-character password.
3. In this repo on GitHub: **Settings → Secrets and variables → Actions →
   New repository secret**, and add:

   | Name | Value |
   |---|---|
   | `EMAIL_ADDRESS` | your Gmail address |
   | `EMAIL_APP_PASSWORD` | the app password from step 2 |
   | `EMAIL_TO` | *(optional)* a different address to receive alerts |

Secrets stay private even though the repo is public.

### 2. Add your cameras

Edit `cameras.yaml`. For each camera, find its page on each shop and paste the
URL. For eBay, write a search plus title filters so accessories and other
models don't count.

### 3. Run it once by hand

**Actions tab → Check camera prices → Run workflow.** After a minute, check
the run log: each source shows ✓ with a price or ✗ with a reason. The first
run only records prices; alerts start from the second run.

That's it — it now runs on its own twice a day.

## Running locally

```bash
pip install -r requirements.txt
python -m tracker check https://www.mpb.com/en-us/product/fujifilm-x-t5   # test one URL
python -m tracker check "ebay:fujifilm x-t5 body"                          # test an eBay search
python -m tracker run --dry-run                                            # check all, change nothing
python -m unittest discover tests                                          # run the tests
```

For email locally, set `EMAIL_ADDRESS` and `EMAIL_APP_PASSWORD` in your shell,
then `python -m tracker test-email`.

## Good to know

- **Cost:** $0. Public repos get unlimited free Actions minutes; each run
  takes about a minute.
- **Some shops block bots.** Amazon and Best Buy usually do. If a source shows
  ✗ HTTP 403 for a few runs, swap it for another shop. You get one email if a
  source fails for 3 days straight. For Amazon, a free tool like
  CamelCamelCamel or Keepa does this job better.
- **eBay prices are noisy** because listings come and go. The 3% threshold and
  title filters keep false alarms down; tune `min_price` and `exclude` if needed.
- **Out of stock** pages are skipped, not counted as broken.
- **Public repo = public price history.** Your camera list and prices are
  visible; your email settings are not.
- GitHub pauses scheduled workflows after 60 days without commits. The tracker
  commits its price history every run, so this shouldn't happen.

## Ideas for later

- A price history chart page on GitHub Pages
- Phone push notifications via [ntfy.sh](https://ntfy.sh)
- More shops with their own parsers (Best Buy, Amazon via Keepa API)
- A weekly digest email even when nothing dropped
