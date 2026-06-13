from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto('https://www.youtube.com/watch?v=LhB602i8p8c')
        page.wait_for_timeout(5000)
        page.screenshot(path='C:\\Users\\hp\\.gemini\\antigravity\\brain\\436a4e75-006f-471e-a321-334a18b84337\\playwright_screenshot.png')
        browser.close()

if __name__ == '__main__':
    main()
