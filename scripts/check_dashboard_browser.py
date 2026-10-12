"""Optional browser smoke test. Requires playwright and installed Chrome.

Run against a disposable local server: python -m scripts.check_dashboard_browser
Creates one explicitly simulated event through the dashboard.
"""
from playwright.sync_api import sync_playwright, expect


def main(base_url='http://localhost:8000'):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base_url + '/')
        expect(page.locator('#connection')).to_contain_text('API connected')
        page.get_by_role('button', name='SIMULATE DEMO FALL').click()
        card = page.locator('article.event').first
        expect(card).to_contain_text('DEMO / SIMULATED FALL')
        card.get_by_role('button', name='ACKNOWLEDGE FALL').click()
        expect(card).to_contain_text('Fall acknowledged')
        expect(card.locator('.hospital')).to_have_count(3)
        card.locator('.hospital').nth(1).get_by_role('button', name='SELECT', exact=True).click()
        expect(card).to_contain_text('Hospital selected: Mock City Hospital')
        card.get_by_role('button', name='RECORD EMERGENCY RESPONSE').click()
        expect(card).to_contain_text('Mock emergency response recorded successfully.')
        page.reload()
        expect(page.locator('article.event').first).to_contain_text('Mock emergency response recorded successfully.')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
        page.set_viewport_size({'width': 1280, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Desktop horizontal overflow'
        assert not errors, errors
        assert page.request.get(base_url + '/docs').status == 200
        browser.close()
        print('PASS: mobile demo, acknowledgement, selection, recording, refresh, desktop layout, and /docs; no JS errors.')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:8000')
    main(parser.parse_args().url.rstrip('/'))
