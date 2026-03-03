import asyncio
from playwright.async_api import async_playwright

async def get_login_request():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        async def handle_request(request):
            if 'admin' not in request.url and request.method == 'POST':
                print('\nPOST Request to:', request.url)
                print('Headers:', request.headers)
                print('Data:', request.post_data)

        page.on('request', handle_request)
        await page.goto('https://students.its.aperptech.com/')
        print('Page loaded. Simulating login attempt...')
        await page.fill('input[placeholder="Email"]', 'test@test.com')
        await page.fill('input[placeholder="Password"]', 'password123')
        await page.click('button:has-text("Log in")')
        await asyncio.sleep(4)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(get_login_request())
