from playwright.sync_api import sync_playwright

URL = "https://www.trimx.in/menu"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, wait_until='networkidle')
    page.wait_for_timeout(1000)

    imgs = page.query_selector_all('img')
    print('IMG_COUNT:', len(imgs))
    for i, img in enumerate(imgs[:80]):
        src = img.get_attribute('src') or img.get_attribute('data-src') or img.get_attribute('data-lazy') or img.get_attribute('srcset')
        print(f'IMG {i:02d}:', src)

    explore = page.locator('text=EXPLORE SERVICES')
    try:
        print('EXPLORE_SERVICES_COUNT:', explore.count())
    except Exception:
        print('EXPLORE_SERVICES_COUNT: 0')

    # Print details for each 'EXPLORE SERVICES' element
    try:
        cnt = explore.count()
        print('\nEXPLORE_DETAILS:')
        for i in range(min(12, cnt)):
            info = explore.nth(i).evaluate("e => { const a = e.closest('a'); return {outer: e.outerHTML.slice(0,300), href: a ? a.href : null, attrs: Array.from(e.attributes||[]).map(x=>[x.name,x.value])} }")
            print(f'-{i}: href={info.get("href")}, attrs={len(info.get("attrs"))}, outer_len={len(info.get("outer"))}')
            print('  outer:', info.get('outer'))
    except Exception as ex:
        print('EXPLORE_DETAILS_ERROR', ex)

    # Set up a collector for image network responses
    image_responses = set()
    def on_response(r):
        try:
            ct = r.headers.get('content-type', '')
            if 'image' in ct or r.request.resource_type == 'image':
                image_responses.add(r.url)
        except Exception:
            pass

    page.on('response', on_response)

    # Click each EXPLORE SERVICES button and look for new images / responses
    try:
        print('\nCLICK_AND_CAPTURE:')
        initial_imgs = set([img.get_attribute('src') or '' for img in page.query_selector_all('img')])
        seen_responses = set()
        for i in range(min(8, explore.count())):
            print(f'Clicking explore #{i}')
            explore.nth(i).scroll_into_view_if_needed()
            try:
                explore.nth(i).click(timeout=5000)
            except Exception as e:
                print('  click error:', e)
            page.wait_for_timeout(1200)
            after_imgs = set([img.get_attribute('src') or '' for img in page.query_selector_all('img')])
            new_imgs = [u for u in after_imgs - initial_imgs if u]
            new_responses = list(image_responses - seen_responses)
            print(f'  New DOM images: {len(new_imgs)}')
            for u in new_imgs[:10]:
                print('   DOM:', u)
            print(f'  New image network responses seen: {len(new_responses)}')
            for u in new_responses[:20]:
                print('   NET:', u)
            seen_responses.update(new_responses)

            # Try closing modal by clicking the overlay, then fallback to Escape
            try:
                overlay = page.query_selector('div.fixed.inset-0')
                if overlay:
                    overlay.click()
                    page.wait_for_timeout(400)
                else:
                    page.keyboard.press('Escape')
                    page.wait_for_timeout(400)
            except Exception:
                try:
                    page.keyboard.press('Escape')
                    page.wait_for_timeout(400)
                except Exception:
                    pass
    except Exception as ex:
        print('CLICK_CAPTURE_ERROR', ex)

    top_classes = page.evaluate('''() => {
        const nodes = Array.from(document.querySelectorAll('[class]'));
        const sels = nodes.map(e => typeof e.className === 'string' ? e.className : '').filter(Boolean);
        const uniq = {};
        sels.forEach(s => { s.split(/\s+/).forEach(c => { uniq[c] = (uniq[c] || 0) + 1; }); });
        return Object.entries(uniq).sort((a,b) => b[1] - a[1]).slice(0,80);
    }''')
    print('\nTOP_CLASSES:')
    for cls,count in top_classes[:40]:
        print(f'{count:4d} {cls}')

    modals = page.evaluate('''() => {
        const nodes = Array.from(document.querySelectorAll('[role="dialog"],[data-modal],[class*="modal"],[class*="popup"],[data-gallery]'));
        return nodes.map(n => ({ class: typeof n.className === 'string' ? n.className : '', id: n.id || '', sample: (n.innerHTML || '').slice(0,200) })).slice(0,20);
    }''')
    print('\nMODAL_LIKE_COUNT:', len(modals))
    for i,m in enumerate(modals[:10]):
        print("MODAL {}: class=\"{}\" id=\"{}\" sample_len={}".format(i, m.get('class'), m.get('id'), len(m.get('sample') or '')))

    # search inline scripts for gallery/data
    content = page.content()
    hits = []
    for token in ['gallery','images','photos','lightbox','modal','service','fetch','api','assets','cdn','galleria']:
        if token.lower() in content.lower():
            hits.append(token)
    print('\nINLINE_TOKEN_HITS:', hits)

    browser.close()
