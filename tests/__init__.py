"""
Test suite for SmartVoyage.

Run everything:           python -m unittest discover -s tests -v
Run model tests only:     python -m unittest tests.test_models -v
Run route tests only:     python -m unittest tests.test_routes -v
Run Selenium tests only:  python -m unittest tests.test_selenium -v

The Selenium tests require Chrome (or Chromium) on PATH. Selenium 4.6+
auto-downloads the matching chromedriver, so no extra driver setup is
needed.
"""
