"""只点击一次评测，仅接受本次点击后更新的结果区域。"""
import re
import uuid

SUMMARY = 'div[class^="test-set-container___"] p.test-result'
BUTTON = 'button[title="运行评测"]'


def classify_result(text, classes):
    counts = re.findall(r'(\d+)\s*/\s*(\d+)', text)
    if len(counts) != 1:
        return 'unknown'
    passed, total = map(int, counts[0])
    if total <= 0 or passed > total:
        return 'unknown'
    if 'success' in classes.split() and '全部通过' in text and passed == total:
        return 'passed'
    if passed < total:
        return 'failed'
    return 'unknown'


def evaluate_once(page, timeout_ms=120000):
    button = page.locator(BUTTON)
    if button.count() != 1:
        raise ValueError('未找到唯一已验证的评测按钮。')
    key = '__educoder_eval_' + uuid.uuid4().hex
    page.evaluate('''({key, selector, button}) => {
      const initial = document.querySelector(selector);
      const before = initial?.textContent || '';
      const state = {armed:false, fresh:false};
      const trigger = document.querySelector(button);
      const arm = () => {state.armed=true;};
      trigger.addEventListener('click', arm, {once:true, capture:true});
      const observer = new MutationObserver(() => {
        if (!state.armed) return;
        const node = document.querySelector(selector);
        if (node && (node !== initial || node.textContent !== before)) state.fresh=true;
      });
      observer.observe(document.body, {childList:true, subtree:true, characterData:true});
      state.dispose=()=>{observer.disconnect(); trigger.removeEventListener('click',arm,true);};
      window[key]=state;
    }''', {'key': key, 'selector': SUMMARY, 'button': BUTTON})
    try:
        button.click()  # 唯一点击；超时/失败不重试。
        page.wait_for_function('''({key, selector}) => {
          const node=document.querySelector(selector);
          return window[key]?.fresh && node && node.getClientRects().length && /\\d+\\s*\\/\\s*\\d+/.test(node.innerText);
        }''', arg={'key': key, 'selector': SUMMARY}, timeout=timeout_ms)
        summary = page.locator(SUMMARY)
        if summary.count() != 1:
            raise ValueError('评测结果区域不唯一，不能确认通过。')
        text = summary.inner_text()
        return {'status': classify_result(text, summary.get_attribute('class') or ''), 'text': text}
    finally:
        if not page.is_closed():
            page.evaluate('key => { window[key]?.dispose(); delete window[key]; }', key)
