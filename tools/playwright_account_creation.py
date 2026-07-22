from playwright.sync_api import sync_playwright


def create_devto_account():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto('https://dev.to')
        page.click('#navbar-sign-up-link')
        page.fill('input[name=email]', 'testemail@example.com')
        page.fill('input[name=password]', 'testpassword123')
        page.fill('input[name=repeat_password]', 'testpassword123')
        page.fill('input[name=username]', 'testuser123')
        page.click('button[type=submit]')
        browser.close()

create_devto_account()