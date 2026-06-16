"""Scenario: Main.WebHome server-side rendering throughput (no browser).

1000 GETs to bin/get/Main/WebHome — no skin, JS or CSS.
Baseline for XWiki's home-page template cost from a warm cache.
No user_sleep(): throughput benchmark, not a user journey.
"""
from helpers import http
from helpers.helper_functions import log_note

REPS = 1000

if __name__ == "__main__":
    log_note(f"Start: render Main.WebHome without UI x{REPS}")
    for _ in range(REPS):
        http.get("/bin/get/Main/WebHome")
    log_note(f"Done: render Main.WebHome without UI x{REPS}")
