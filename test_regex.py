import re

xml_content = open('./repos/super-mario/web/config/user/beans/sqlmap/CustomerMapper.xml', 'r').read()

# Test the SQL extraction regex
pattern = r'<(?P<type>select|insert|update|delete)\s+id\s*=\s*["\']([\w]+)["\'][^>]*>(?P<sql>.*?)</(?P=type)>'

count = 0
for match in re.finditer(pattern, xml_content, re.DOTALL | re.IGNORECASE):
    sql_id = match.group(2)
    sql_type = match.group('type')
    sql_text = match.group('sql').strip()
    print(f'{sql_type}: {sql_id}')
    count += 1
    if count > 20:
        break

