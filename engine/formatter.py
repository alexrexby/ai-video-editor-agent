import html
import re

def markdown_to_telegram_html(text: str) -> str:
    """
    Converts LLM markdown into valid, safe Telegram HTML.
    Preserves existing Telegram HTML tags (<b>, <i>, <code>, <pre>, <a>)
    and converts Markdown (**bold**, *italic*, headers, lists, code) into valid HTML.
    """
    if not text:
        return ""

    # 1. Temporarily protect existing valid Telegram HTML tags
    valid_tags = []
    def save_valid_tag(match):
        valid_tags.append(match.group(0))
        return f"__VALID_HTML_TAG_{len(valid_tags)-1}__"

    # Match Telegram-supported tags
    tag_pattern = r'</?(?:b|i|u|s|code|pre|a(?:\s+href="[^"]*")?|blockquote)>'
    text = re.sub(tag_pattern, save_valid_tag, text, flags=re.IGNORECASE)

    # 2. Extract and store preformatted code blocks (```code```)
    code_blocks = []
    def save_code_block(match):
        code_blocks.append(match.group(1))
        return f"__PRE_CODE_BLOCK_{len(code_blocks)-1}__"
    
    text = re.sub(r'```(?:[a-zA-Z0-9_-]+)?\n?(.*?)```', save_code_block, text, flags=re.DOTALL)
    
    # 3. Extract and store inline code (`code`)
    inline_codes = []
    def save_inline_code(match):
        inline_codes.append(match.group(1))
        return f"__INLINE_CODE_{len(inline_codes)-1}__"
    text = re.sub(r'`([^`\n]+)`', save_inline_code, text)
    
    # 4. Escape remaining HTML entities (like <, >, & that are not protected)
    text = html.escape(text)
    
    # 5. Markdown Headers: # Header -> <b>Header</b>
    text = re.sub(r'^#{1,6}\s*(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    
    # 6. Markdown Bold: **text** -> <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    
    # 7. Markdown Italic: *text* -> <i>text</i> (when not inside words)
    text = re.sub(r'(?<!\w)\*([^*\n]+?)\*(?!\w)', r'<i>\1</i>', text)
    
    # 8. Lists: format bullet points cleanly
    text = re.sub(r'^\s*[\*\-]\s+', '• ', text, flags=re.MULTILINE)
    
    # 9. Restore inline code
    for i, code in enumerate(inline_codes):
        text = text.replace(f"__INLINE_CODE_{i}__", f"<code>{html.escape(code)}</code>")
        
    # 10. Restore code blocks
    for i, code in enumerate(code_blocks):
        text = text.replace(f"__PRE_CODE_BLOCK_{i}__", f"<pre><code>{html.escape(code)}</code></pre>")

    # 11. Restore valid HTML tags
    for i, tag in enumerate(valid_tags):
        text = text.replace(f"__VALID_HTML_TAG_{i}__", tag)
        
    return text
