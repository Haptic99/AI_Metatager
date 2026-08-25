path = r"F:\Jellyfin_AI_Cockpit\src\ai_metatagger\ui\screens\validator.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_parse = """                                if '-->' in line:
                                    start_str = line.split('-->')[0].strip()
                                    h, m, s_ms = start_str.split(':')
                                    s, ms = s_ms.split(',')
                                    seek_time_ms = int(
                                        h)*3600000 + int(m)*60000 + int(s)*1000 + int(ms)
                                    seek_time_ms = max(0, seek_time_ms - 2000)
                                    break"""

new_parse = """                                if '-->' in line:
                                    start_str = line.split('-->')[0].strip()
                                    h, m, s_ms = start_str.split(':')
                                    s, ms = s_ms.split(',')
                                    seek_time_ms = int(h)*3600000 + int(m)*60000 + int(s)*1000 + int(ms)
                                    seek_time_ms = max(0, seek_time_ms - 2000)
                                    break
                                elif line.startswith('[') and ']' in line:
                                    import re
                                    m_match = re.match(r'^\[(\d+):(\d+):(\d+)\]', line.strip())
                                    if m_match:
                                        h, m, s = m_match.groups()
                                        seek_time_ms = int(h)*3600000 + int(m)*60000 + int(s)*1000
                                        seek_time_ms = max(0, seek_time_ms - 2000)
                                        break"""

content = content.replace(old_parse, new_parse)
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
