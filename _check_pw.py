import re
content = open('document/update/v1.0.2/preview/index_pure_wendland.html', 'r', encoding='utf-8').read()
js_match = re.search(r'<script type="module">(.*?)</script>', content, re.DOTALL)
js = js_match.group(1) if js_match else ''
braces = js.count('{') - js.count('}')
parens = js.count('(') - js.count(')')
brackets = js.count('[') - js.count(']')
print(f'Braces: {braces}, Parens: {parens}, Brackets: {brackets}')
print('BALANCED' if braces==0 and parens==0 and brackets==0 else 'UNBALANCED')
